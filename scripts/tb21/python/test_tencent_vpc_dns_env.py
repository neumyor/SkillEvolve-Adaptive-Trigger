"""Offline tests of the sandbox network setup script (no sandbox, no network).

Runs _SETUP from tencent_vpc_dns_env against fake root filesystems that mimic
the real task images (bullseye qemu image with the author's commented-out
snapshot lines, a noble ubuntu image, a debian image without snapshot lines).
"""
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

# Import the module without Harbor: stub its base class.
stub = types.ModuleType("tencent_tb2_snapshot")
stub.TencentSnapshotE2BEnvironment = type("Base", (), {})
sys.modules["tencent_tb2_snapshot"] = stub
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tencent_vpc_dns_env as M  # noqa: E402

BULLSEYE_SOURCES = """\
# deb http://snapshot.debian.org/archive/debian/20251020T000000Z bullseye main
deb http://deb.debian.org/debian bullseye main
# deb http://snapshot.debian.org/archive/debian-security/20251020T000000Z bullseye-security main
deb http://deb.debian.org/debian-security bullseye-security main
# deb http://snapshot.debian.org/archive/debian/20251020T000000Z bullseye-updates main
deb http://deb.debian.org/debian bullseye-updates main
"""
RESOLV = "nameserver 1.1.1.1\nnameserver 8.8.8.8\n"


def fake_root(os_id, codename, sources=None, ubuntu_sources=None):
    root = Path(tempfile.mkdtemp())
    (root / "etc/apt/sources.list.d").mkdir(parents=True)
    (root / "tmp").mkdir()
    (root / "etc/resolv.conf").write_text(RESOLV)
    (root / "etc/os-release").write_text(f'ID={os_id}\nVERSION_CODENAME={codename}\n')
    if sources is not None:
        (root / "etc/apt/sources.list").write_text(sources)
    if ubuntu_sources is not None:
        (root / "etc/apt/sources.list.d/ubuntu.sources").write_text(ubuntu_sources)
    return root


def run(root, dns="", mirror="0", snapshot="0"):
    env = dict(os.environ, ROOT_PREFIX=str(root), VPC_DNS=dns,
               APT_MIRROR=mirror, APT_SNAPSHOT=snapshot)
    out = subprocess.run(["bash", "-c", M._SETUP], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def read(root, rel):
    return (root / rel).read_text()


def test_dns_prepended_and_idempotent():
    r = fake_root("debian", "bullseye", BULLSEYE_SOURCES)
    run(r, dns="183.60.83.19")
    run(r, dns="183.60.83.19")
    assert read(r, "etc/resolv.conf") == "nameserver 183.60.83.19\n" + RESOLV
    assert read(r, "etc/apt/sources.list") == BULLSEYE_SOURCES  # apt untouched


def test_snapshot_enables_only_the_authors_lines_on_bullseye():
    r = fake_root("debian", "bullseye", BULLSEYE_SOURCES)
    out = run(r, snapshot="1")
    assert "apt=snapshot" in out
    lines = read(r, "etc/apt/sources.list").splitlines()
    assert lines == [
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20251020T000000Z bullseye main",
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20251020T000000Z bullseye-security main",
        "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20251020T000000Z bullseye-updates main",
    ]
    assert read(r, "etc/apt/sources.list.orig") == BULLSEYE_SOURCES
    assert read(r, "etc/resolv.conf") == RESOLV  # dns untouched


def test_snapshot_wins_over_intranet_mirror_on_bullseye():
    r = fake_root("debian", "bullseye", BULLSEYE_SOURCES)
    out = run(r, dns="183.60.83.19", mirror="1", snapshot="1")
    assert "apt=snapshot" in out
    assert "mirrors.tencentyun.com" not in read(r, "etc/apt/sources.list")


def test_snapshot_ignored_on_other_releases_and_without_author_lines():
    r = fake_root("debian", "bookworm", "deb http://deb.debian.org/debian bookworm main\n")
    assert "apt=no" in run(r, snapshot="1")
    r = fake_root("debian", "bullseye", "deb http://deb.debian.org/debian bullseye main\n")
    assert "apt=no" in run(r, snapshot="1")
    assert read(r, "etc/apt/sources.list") == "deb http://deb.debian.org/debian bullseye main\n"


def test_intranet_mirror_debian_and_ubuntu():
    r = fake_root("debian", "bookworm", "deb http://deb.debian.org/debian bookworm main\n")
    assert "apt=intranet" in run(r, mirror="1")
    assert "mirrors.tencentyun.com/debian/ bookworm main" in read(r, "etc/apt/sources.list")
    assert (r / "etc/apt/sources.list.orig").exists()
    r = fake_root("ubuntu", "noble", ubuntu_sources="Types: deb\nURIs: http://archive.ubuntu.com/ubuntu/\n")
    assert "apt=intranet" in run(r, mirror="1")
    new = read(r, "etc/apt/sources.list.d/ubuntu.sources")
    assert "URIs: http://mirrors.tencentyun.com/ubuntu/" in new and "Suites: noble noble-updates noble-security" in new
    assert (r / "etc/apt/sources.list.d/ubuntu.sources.orig").exists()


def test_all_off_is_a_no_op():
    r = fake_root("debian", "bullseye", BULLSEYE_SOURCES)
    assert "apt=no" in run(r)
    assert read(r, "etc/resolv.conf") == RESOLV
    assert read(r, "etc/apt/sources.list") == BULLSEYE_SOURCES


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
