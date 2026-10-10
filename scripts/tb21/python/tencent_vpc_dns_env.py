"""Tencent E2B task environment that fixes sandbox networking right after start.

Three independent, opt-in switches (environment variables of the host process;
all unset = behaviour identical to TencentSnapshotE2BEnvironment):

  TBENCH_VPC_DNS=<ip>
      Prepend this nameserver to $R/etc/resolv.conf.  The task-sandbox template
      only ships public resolvers (1.1.1.1, 8.8.8.8), which cannot resolve
      Tencent intranet names such as mirrors.tencentyun.com; the VPC DNS
      server 183.60.83.19 resolves them to 169.254.0.3.  Public resolvers stay
      as fallback.

  TBENCH_APT_INTRANET_MIRROR=1
      Point Debian/Ubuntu apt at mirrors.tencentyun.com (needs the VPC DNS).
      Skipped on bullseye when TBENCH_APT_SNAPSHOT_BULLSEYE=1 handles it.

  TBENCH_APT_SNAPSHOT_BULLSEYE=1
      Debian 11 (bullseye) is out of security support: the security index
      still lists curl 7.74.0-1.3+deb11u16 but the pool no longer serves it
      (HTTP 404 on deb.debian.org, security.debian.org and the Tencent
      mirror alike), so the verifier cannot install curl and never runs
      (qemu-startup, qemu-alpine-ssh).  The task images already carry the
      author's commented-out snapshot.debian.org lines; this switch enables
      exactly those lines and nothing else.  Only acts when the image is
      bullseye AND those lines exist.

Everything else is inherited unchanged from the read-only
/data2/liyishan/tb21-tencent-skill/python/tencent_tb2_snapshot.py.
"""
from __future__ import annotations

import os

from tencent_tb2_snapshot import TencentSnapshotE2BEnvironment

_SETUP = r'''
set -e
R=${ROOT_PREFIX:-}
if [ -n "$VPC_DNS" ] && ! grep -q "^nameserver $VPC_DNS" $R/etc/resolv.conf; then
  { echo "nameserver $VPC_DNS"; grep -v '^#' $R/etc/resolv.conf; } > $R/tmp/.resolv.new
  cat $R/tmp/.resolv.new > $R/etc/resolv.conf && rm -f $R/tmp/.resolv.new
fi
ID=; VERSION_CODENAME=
[ -r $R/etc/os-release ] && . $R/etc/os-release
APT_DONE=no
if [ "$APT_SNAPSHOT" = 1 ] && [ "$ID" = debian ] && [ "$VERSION_CODENAME" = bullseye ] \
   && grep -q '^# *deb http://snapshot.debian.org/' $R/etc/apt/sources.list 2>/dev/null; then
  cp $R/etc/apt/sources.list $R/etc/apt/sources.list.orig
  grep '^# *deb http://snapshot.debian.org/' $R/etc/apt/sources.list.orig \
    | sed -E 's/^# *deb /deb [check-valid-until=no] /' > $R/etc/apt/sources.list
  APT_DONE=snapshot
fi
if [ "$APT_MIRROR" = 1 ] && [ "$APT_DONE" = no ]; then
  M=http://mirrors.tencentyun.com
  case "$ID" in
    debian|ubuntu)
      mkdir -p $R/etc/apt/sources.list.d
      for f in $R/etc/apt/sources.list.d/*.list $R/etc/apt/sources.list.d/*.sources $R/etc/apt/sources.list; do
        [ -e "$f" ] && mv "$f" "$f.orig"
      done
      ;;
  esac
  case "$ID" in
    debian)
      printf 'deb %s/debian/ %s main contrib non-free\ndeb %s/debian/ %s-updates main contrib non-free\ndeb %s/debian-security/ %s-security main contrib non-free\n' \
        "$M" "$VERSION_CODENAME" "$M" "$VERSION_CODENAME" "$M" "$VERSION_CODENAME" > $R/etc/apt/sources.list
      APT_DONE=intranet ;;
    ubuntu)
      printf 'Types: deb\nURIs: %s/ubuntu/\nSuites: %s %s-updates %s-security\nComponents: main restricted universe multiverse\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' \
        "$M" "$VERSION_CODENAME" "$VERSION_CODENAME" "$VERSION_CODENAME" > $R/etc/apt/sources.list.d/ubuntu.sources
      APT_DONE=intranet ;;
  esac
fi
echo "os=$ID/$VERSION_CODENAME apt=$APT_DONE first_ns=$(grep -m1 '^nameserver' $R/etc/resolv.conf | cut -d' ' -f2)"
'''


class TencentVpcDnsE2BEnvironment(TencentSnapshotE2BEnvironment):
    async def start(self, force_build: bool) -> None:
        await super().start(force_build)
        vpc_dns = os.environ.get("TBENCH_VPC_DNS", "").strip()
        apt_mirror = os.environ.get("TBENCH_APT_INTRANET_MIRROR", "0").strip()
        apt_snapshot = os.environ.get("TBENCH_APT_SNAPSHOT_BULLSEYE", "0").strip()
        if not vpc_dns and apt_mirror != "1" and apt_snapshot != "1":
            return
        result = await self.exec(
            _SETUP, user="root",
            env={"VPC_DNS": vpc_dns, "APT_MIRROR": apt_mirror, "APT_SNAPSHOT": apt_snapshot},
        )
        if result.return_code != 0:
            raise RuntimeError(
                f"Failed to configure sandbox networking: {result.stderr or result.stdout}")
        self.logger.info("sandbox network setup: %s", (result.stdout or "").strip())
