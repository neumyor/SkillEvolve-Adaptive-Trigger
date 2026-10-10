# TB2.1 完整评测：自包含评测包手册

用 Tencent E2B 沙箱跑 TerminalBench 2.1 的裸 rollout（无 Skill）并统计 avg@N / pass@N。
本包自 2026-10-10 起三层代码自包含（见第 1 节），可在任意腾讯 VPC 内网机器上部署运行。
注意：远程 node29 的 `/data2/niuyiming/scripts/` 目前还是旧版（服务进行中的补跑），补跑结束后用本包替换。

## 1. 组件总览

本目录是一个**自包含的评测包**（2026-10-10 起三层全部打进来）：

| 层 | 包内位置 | 内容 | 来源 |
|---|---|---|---|
| 1. 我们的启动与审计 | 根目录 + `python/` | runner、网络修复环境类、滚动启动器、审计 | 我们 |
| 2. 腾讯适配层 | `vendor/tb21-tencent-skill/python/`、`vendor/framework-python/` | `run_tencent_job.py`、`tencent_tb2_snapshot.py`（E2B 环境类）、`tencent_sandbox_terminus.py`（agent）等 | liyishan（快照，快照时间 2026-10-10） |
| 3. Harbor 与题库 | `vendor/claw-harbor/`（main @ `37a234f8de64`）、`vendor/tasks/`（89 题）、`vendor/requirements.txt` | trial 调度、verifier、重试 | 上游 |

密钥：`secrets.env`（含 `E2B_API_KEY` / `E2B_DOMAIN` / `TBENCH_LLM_KEY`，权限 600）。
**它在 `.gitignore` 里**：目录拷贝会带上它，但 git 推送永远不会泄露它。

### 新机器部署（三步）

```bash
# 1. 拷贝整个 scripts/tb21 目录（含 vendor/ 和 secrets.env）
# 2. 复原 venv（需要 python3.12；harbor 从 vendor/claw-harbor 源码安装）
./bootstrap.sh
# 3. 网络前提：机器必须在腾讯 VPC 内（TBENCH_VPC_DNS、内网 PyPI 镜像、
#    ap-beijing.tencentags.com 只在腾讯内网可达，见第 4 节）
. ./campaign.env && python3 recover_rolling.py <queue.tsv> <jobs_dir>
```

### 本目录文件

| 文件 | 作用 |
|---|---|
| `run_tencent_tb21_smoke_niuyiming.sh` | **runner**：liyishan 原脚本的副本，生成 Harbor job YAML 并启动。我们加的全部改动都由环境变量控制（见第 3 节）；**所有路径默认相对本目录**（vendor/、.venv/、secrets.env、python/），可用环境变量指到外部树 |
| `bootstrap.sh` | 新机器上复原 Harbor venv（python3.12 + vendor/requirements.txt + vendor/claw-harbor） |
| `python/tencent_vpc_dns_env.py` | **网络修复环境类**：继承原 E2B 环境类，只重写 `start()`，在沙箱启动后修 DNS / apt 源（见第 4 节） |
| `python/test_tencent_vpc_dns_env.py` | 上面那个类的离线测试（6 个用例，在伪造的根文件系统上跑 shell 逻辑，不需要沙箱） |
| `campaign.env` | **一次评测的全部参数**（网络开关、重试、verifier 时限）。启动前 `source`，启动器会把这些值逐条记进 manifest |
| `recover_rolling.py` | **滚动启动器**：队列里每一行是一次独立的 runner 调用（1 个 trial），每分钟启动 2 个、不设并发上限 |
| `audit_trials.py` | **审计 + 指标**：逐条判定每个 trial 是否有效，算出每题缺几条，输出 avg@N / pass@N。结果根目录用 `TBENCH_RESULTS_ROOT` 改（默认 node29 的 `/data2/niuyiming`），明细写到 `$TBENCH_RESULTS_ROOT/audit_<日期>.json` |
| `build_rerun_queue.py` | 从审计结果生成补跑队列 |
| `rerun_queue_20261010.tsv` | 当前的补跑队列（39 条：qwen 10、dpsk 29） |
| `secrets.env` | 密钥（E2B / LLM API key）。**gitignore，勿提交、勿推送** |
| `env.sh.example` | 按主机覆盖默认路径时的参考（新机器通常不需要） |
| `vendor/` | 第二、三层的完整快照（见上表） |
| `archive/` | 已被取代的旧工具与旧队列，仅留档 |

### vendor 里两处不会触发的写死路径

第二层代码快照里有两个 `/data2/liyishan/.../cache` 写死路径，在裸 rollout 下**不会执行**：
`TB21_PIPELINE_CACHE`（默认 0）控制 pipeline 缓存；uv 0.9.5 归档缓存只在 skills 评测模式（`tencent_tb2_skill_env`）里用到。开着这些开关才需要 node29 上的缓存树。

## 2. 怎么用

### 2.0 前置条件与标准工作流

前置条件（缺一不可）：

1. 机器在**腾讯 VPC 内网**里（`183.60.83.19` DNS、`mirrors.tencentyun.com` 内网镜像、`ap-beijing.tencentags.com` 沙箱服务只在腾讯内网可达）；
2. `secrets.env` 在包根目录（`E2B_API_KEY` / `E2B_DOMAIN` / `TBENCH_LLM_KEY`）；
3. `./bootstrap.sh` 跑过一次（生成 `.venv/`，需要 python3.12）。

一轮完整评测的循环：

```
生成队列 ──► source campaign.env ──► 滚动投喂 ──► 盯进度
                                                │
        ┌───────────────────────────────────────┘
        ▼
   audit_trials.py 审计 ──有缺口──► build_rerun_queue.py 生成补跑队列 ──┐
        │                                                            │
      无缺口◄────────────────────────────────────────────────────────┘
        ▼
   记录 avg@N / pass@N（只认审计后的数字）
```

队列是 TSV，每行一次独立的 trial：`run_id  model  effort  task`。
effort 为空表示不发 `reasoning_effort`（qwen3.6-flash-distill 用默认），`max` 表示发（DEEPSEEK_up5zdj）。
**全量跑 89 题 × N 条 = 89N 行**，每行 run_id 互不相同（如 `run_<q|d>_<task>_<n>`）；补跑队列则只含审计判定的缺口。

### 2.1 跑一批 trial（补跑或全量都用这个）

```bash
# 在 bundle 目录（node29 上 = /data2/niuyiming/scripts）
cd <bundle> && . ./campaign.env
python3 - <<'EOF'      # 用 start_new_session 脱离当前 shell，射后不管（AGENTS.md）
import os, subprocess
h = os.environ.get("TBENCH_LOGS_DIR", os.path.join(os.getcwd(), "logs"))
p = subprocess.Popen(["python3", "recover_rolling.py",
                      "rerun_queue_20261010.tsv", "/data2/niuyiming/e1_fix/jobs"],
                     env=os.environ.copy(), stdout=open(h + "/e1_fix.log", "ab"),
                     stderr=subprocess.STDOUT, start_new_session=True)
open(h + "/e1_fix.pid", "w").write(f"{p.pid}\n")
EOF
```

队列格式：TSV，每行 `run_id  model  effort  task`。effort 为空表示不发 `reasoning_effort`（qwen），`max` 表示发（dpsk）。
全量跑 89 题时，用同样的格式生成 89×N 行即可：每题 N 行，run_id 互不相同。

### 2.2 看进度

```bash
kill -0 $(cat logs/e1_fix.pid) && echo 运行中        # 投喂器判活（pidfile 在日志目录）
find <jobs_dir> -mindepth 2 -maxdepth 2 -name result.json | wc -l   # 已完成条数
```

启动器的日志最后会打印 `ALL DONE`。**判活只认 pidfile + `kill -0`，禁止 `pgrep -f`**（它会把启动它的 shell 也匹配进来，见 AGENTS.md 的事故记录）。

### 2.3 审计与出指标（每批跑完都要先审计再用数字，AGENTS.md）

```bash
python3 audit_trials.py        # 结果根目录用 TBENCH_RESULTS_ROOT 覆盖（默认 node29 的 /data2/niuyiming）
```

输出每题还缺几条、各类无效原因的计数，以及 avg@N / pass@N。逐条明细写在 `$TBENCH_RESULTS_ROOT/audit_<日期>.json`。
判定规则就是第 5 节的异常处理契约。脚本顶部的 `REC_GLOBS` 已包含 `e1_recover` 和 `e1_fix` 两代补跑；以后再加新一代时，在那里追加一行。

## 3. runner 的开关（全部由环境变量控制）

| 变量 | 默认 | 作用 |
|---|---|---|
| `MODEL_NAME` | — | provider 的模型 ID |
| `TBENCH_REASONING_EFFORT` | 空 | 非空时，请求的 `extra_body` 里带 `reasoning_effort` |
| `TBENCH_N_ATTEMPTS` / `TBENCH_N_CONCURRENT` | 1 / 1 | 每题采样数 / 并发数。滚动启动器固定为 1 / 1 |
| `TBENCH_MAX_TRIAL_RETRIES` | 1 | 整条 trial 重跑的次数，**只针对** `AgentSetupTimeoutError`、`SandboxException`、`AddTestsDirError`。评测超时**不会**触发整条重跑 |
| `TBENCH_VERIFIER_OVERRIDE` | null | 统一覆盖每题 task.toml 里的 verifier 时限（秒） |
| `TBENCH_VERIFIER_MULTIPLIER` | 2 | 覆盖值为 null 时，对 task.toml 的 verifier 时限乘以这个倍数 |
| `TBENCH_SETUP_MULTIPLIER` | 3 | 沙箱启动时限的倍数（360 秒 × 3） |
| `TBENCH_PYPI_MIRROR` | 空 | 非空时，往沙箱注入 `PIP_INDEX_URL` / `UV_INDEX_URL`，对沙箱内**所有**命令生效（verifier、agent 的终端、准备命令） |
| `TBENCH_VPC_DNS` / `TBENCH_APT_SNAPSHOT_BULLSEYE` / `TBENCH_APT_INTRANET_MIRROR` | 空 / 0 / 0 | 传给网络修复环境类，见第 4 节 |

## 4. 沙箱网络问题与修复（2026-10-10）

| 问题 | 证据 | 修复（开关） |
|---|---|---|
| 沙箱只配了公网 DNS（1.1.1.1 / 8.8.8.8），解析不了腾讯内网域名 | `mirrors.tencentyun.com` 解析失败 | `TBENCH_VPC_DNS=183.60.83.19`：把 VPC 的 DNS 插到最前面，内网镜像解析到 169.254.0.3 |
| verifier 用 uvx 从官方 PyPI 装 torch 系依赖（约 3 GB），速度只有 0.19 MB/s，下载会反复中断；uv 0.9.5（test.sh 里写死的版本）不支持断点续传 | 评测超时，或下载失败但被记成 0 分 | `TBENCH_PYPI_MIRROR=https://mirrors.tencentyun.com/pypi/simple/`：torch 865 MB 用 5 秒下完，sha256 与官方一致，uvx 一次装好 |
| Debian 11（bullseye）已停止安全支持，security 索引里列出的 curl 在软件池中已删除，官方源和腾讯镜像都返回 404 → 装不上 curl → 装不上 uv → 评测从未运行（qemu-startup、qemu-alpine-ssh） | 两个模型在这两题上的 14 条轨迹全部如此 | `TBENCH_APT_SNAPSHOT_BULLSEYE=1`：只启用题目镜像里作者自己注释掉的 `snapshot.debian.org` 源，只对 bullseye 镜像生效。实测 apt update 需要约 230 秒 |
| 公网镜像 `mirrors.cloud.tencent.com` 走公网时，大文件会被截断 | smoke 中 torch 重下 6 次后 zip 损坏 | 不要用。配了 VPC DNS 后，这个域名也会解析到内网 |

**这些开关会改变 agent 的环境**：agent 自己用 pip/uv 装包会变快，在 qemu 题里用 apt 会走 snapshot 源。所以用这套设置跑出的轨迹，和第一批全量 run 的条件不同，统计时要单独标注。

**还没解决的**：从 GitHub 下载的部分（装 uv、uv 下载 Python 解释器、个别题的 `git clone`），这些不走 PyPI；有 5 次和下载无关的评测超时（configure-git-webserver 等），原因未知。

## 5. 异常处理契约（看数据之前就定好的）

**一句话原则：模型自己造成的失败，保留计 0 分；我们这边的环境和基础设施造成的失败，补跑。**

### 5.1 两级重跑，别混淆

| 层级 | 触发 | 范围 | 在哪配置 |
|---|---|---|---|
| ① trial 内自动重跑 | 异常属于 `AgentSetupTimeoutError` / `SandboxException` / `AddTestsDirError` | Harbor 把整条 trial 原样重来一次 | runner 生成 job YAML（`TBENCH_MAX_TRIAL_RETRIES`，默认 1） |
| ② 事后审计补跑 | 审计判定为伪 0 分或基础设施失败 | 只补该题缺的那几条 | `audit_trials.py` → `build_rerun_queue.py` → 重新投喂 |

**评测超时（VerifierTimeoutError）不走第①级**——评测没跑完就原样重来没有意义（模型轨迹相同、评测结果必然相同），只在审计标记后按需补跑。verifier 时限已统一放宽到 7200 秒，正常情况下不应再出现。

### 5.2 异常分类契约表（实测中见过的全部情况）

| 异常（实测案例） | 判定 | 处理 | 为什么 |
|---|---|---|---|
| **tmux 按键失败**（`RuntimeError: send keys` / `tmux: command not found`） | 模型自身失败 | **保留，计 0 分，不补跑** | agent 搞坏了自己会话里的 tmux（比如把它卸载了），是模型输出直接造成的 |
| **AgentTimeoutError**（模型用完全部时限没做完） | 模型自身失败 | 保留，计 0 分 | 模型的速度/策略问题 |
| **ContextLengthExceeded / OutputLengthExceeded** | 模型自身失败 | 保留，计 0 分 | 同上 |
| **GitHub 下载失败**（verifier 装 uv、uv 拉 Python 解释器时 `HTTP/2 stream not closed` / `failed to download https://github.com/...`） | 伪 0 分 | **补跑** | GitHub 不走任何内网镜像，间歇性掐断，与模型无关、与我们配置无关。同题重试往往就成功 |
| **PyPI 包下载失败 / zip 损坏**（`Could not find EOCD` / `Invalid zip`） | 伪 0 分 | 补跑 | 下载中途断开。配内网 PyPI 镜像后基本消失 |
| **apt 包 404**（bullseye 的 curl 已从池中下架，索引还在） | 伪 0 分 | 补跑 | 过期发行版的通病。根治靠 snapshot 源开关（第 4 节），e1_fix 里 qemu 两题已验证修复 |
| **apt 锁冲突**（`Could not get lock`，agent 占着 apt 时 verifier 也要装包） | 伪 0 分 | 补跑 | 时序冲突，与模型无关 |
| **uvx: command not found**（装 uv 那步失败的连锁反应） | 伪 0 分 | 补跑 | 上游失败的下游表现 |
| **AgentSetupTimeoutError / EnvironmentStartTimeoutError**（沙箱没起来） | 基础设施失败 | 先走第①级自动重跑；仍失败则审计后补跑 | 冷启动突发/慢，滚动投喂已大幅减少 |
| **SandboxException / AddTestsDirError / DownloadVerifierDirError / RewardFileNotFoundError** | 基础设施失败 | 同上 | 沙箱侧问题 |
| **VerifierTimeoutError**（评测没在时限内跑完） | 基础设施失败 | 不走第①级，审计后按需补跑 | 见 5.1 |
| **LLM 请求失败**（`model request failed` / `context deadline`） | 基础设施失败 | 补跑 | 模型服务侧的网络/限流，不算模型能力 |
| **沙箱 RPC 失败**（`InvalidArgumentException` / `TimeoutException`） | 基础设施失败 | 补跑 | E2B 服务侧问题 |
| **CancelledError** | 基础设施失败 | 补跑 | 我们自己手动停止补跑器时留下的 |
| **未识别的异常** | 默认基础设施失败 | 补跑 | 宁可多补，不把环境故障算到模型头上 |
| RUNNING（已投喂但没有 result.json） | 进行中 | 等待，不计缺口 | 审计时单独计数 |

### 5.3 伪 0 分的总判据

有 reward（通常是 0），**但 verifier 日志（`verifier/test-stdout.txt`）里没有 pytest 的 `collected N items`** → 评测从未真正运行，判伪 0 分，必须补跑。
判据依据：89 题的 verifier 全部用 pytest；dpsk 全部 240 条得 1 分的评测日志都含 `collected`——它是"评测确实跑过"的可靠标志。

### 5.4 指标算法（审计脚本自动执行）

每题取前 N 条**有效**轨迹（原始 run 优先，然后按补跑先后），avg@N = 每题成功率再对题取平均；pass@N = 至少成功一次的题占比。
**分母固定为 89 题**；轨迹不足 N 条的题单独列出（样本不足，不补齐也不剔除）；补跑多出的轨迹会被截断，不能抬高 pass@N。

## 6. 远程目录布局（node29，用户 xinhaidong）

```
~/niuyiming/SkillExpand-tbeval/   # env.sh、venv、logs/（e1_fix 这代的运行日志在 logs/）
/data2/niuyiming/
  scripts/                        # = 本目录（另有 .bak_* 是每次改 runner 前的备份）
  e1_full_q36flash_2att/          # 第一批全量：qwen3.6-flash-distill，89 题 × 2，默认 effort，旧网络
  e1_full_dsv4max_5att/           # 第一批全量：DEEPSEEK_up5zdj，89 题 × 5，reasoning_effort=max，旧网络
  e1_recover/                     # 第一轮补跑（e1rec_*），旧网络，部分伪 0 分
  e1_fix/                         # 修好网络后的补跑（e1fix_*），2026-10-10 17:27 启动
  audit_*.json                    # 最新审计明细
```

## 7. 当前状态（2026-10-10 晚）

- e1_fix 补跑 39 条（+1 条中途补的 pytorch-model-recovery_6）已全部投喂，qemu 两题 10 条全 1.0（上一批全是伪 0 分）；
- 等全部出结果后跑 `audit_trials.py` 出最终 avg@N / pass@N；
- 补跑之前的指标：qwen avg@2 = 0.4326、pass@2 = 45/89；dpsk avg@5 = 0.6152、pass@5 = 74/89。
