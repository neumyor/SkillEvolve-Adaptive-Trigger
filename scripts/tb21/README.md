# TB2.1 裸 rollout 实验脚本（node29 / Tencent E2B）

2026-10-09/10 在远程 node29 上跑通的 qwen / dpsk 全量 TerminalBench 2.1 裸 rollout
实验所用的最终版脚本，原样入库（字节与实际运行的一致，路径为该次 campaign 的绝对路径，
复用时需按自己的环境调整）。完整操作手册见内层仓库
`repos/experiments/ExpeToSkill-merged/docs/TERMINALBENCH_TESTING.md`（TB-eval 分支）。

## 脚本清单

| 文件 | 用途 |
|---|---|
| `run_tencent_tb21_smoke_niuyiming.sh` | Harbor/Tencent runner 的自用副本。相对 liyishan 原件（`/data2/liyishan/tb21-tencent-skill/scripts/run_tencent_tb21_smoke.sh`，只读）的改动：① `SKILL_ROOT` 写死为 liyishan 的根（使副本可从任意位置运行）；② `verifier_timeout_multiplier`（默认 2）、`agent_setup_timeout_multiplier`（默认 3）、`verifier.override_timeout_sec` 均由环境变量驱动；③ 重试默认 1 次且 `include_exceptions` 只含基础设施异常（AgentSetupTimeoutError / SandboxException / AddTestsDirError），模型行为失败不重试。VerifierTimeoutError 已于 2026-10-10 从名单中移除——评测超时改为只靠 Harbor trial 内部的同沙箱 verifier 重跑，不再整条轨迹重跑；④ `reasoning_effort` 由 `TBENCH_REASONING_EFFORT` 控制（空=不发该参数）；⑤ `TBENCH_PYPI_MIRROR`（2026-10-10 新增，空=不注入）非空时往生成的 YAML `environment.env` 注入 `PIP_INDEX_URL` / `UV_INDEX_URL`，经 Harbor 的 `persistent_env` 对沙箱内每一次 exec 生效（verifier 脚本、agent 的 tmux 会话、环境准备命令），只影响 pip/uv 下载源、不影响 apt。当时实测腾讯内网域名 `mirrors.tencentyun.com` 在沙箱内无法解析，可用的是 `https://mirrors.cloud.tencent.com/pypi/simple/`。注意：使用镜像的补跑轨迹与原始轨迹的装包条件不同，统计时须单独标注 |
| `recover_rolling.py` + `recover_queue.tsv` | 滚动补跑：50 个缺口 trial 组成一条队列（重任务在前），每分钟启动 2 个、不设并发上限，每个 trial 是一次独立 runner 调用（独立 RUN_ID `e1rec_<q|d>_<task>_<n>`）。这是第二版设计：最初的分组串行链（按缺口分 6 个 run、每 run 整组冷启动）会在每次 run 边界制造并发冷启动突发——正是被补跑的失败根因——已被废弃。启动时逐条写 `manifest.tsv` |
| `tb_stats.py` | 从 trial 目录的 `result.json` 计算 avg@N（每任务先对有效 trial 取平均，再对任务平均）与 pass@N（至少一次成功），并列出异常任务与异常类型分布 |
| `tb_exceptions.py` | 把两个 run 的全部异常 trial 按真实原因分组（verifier 超时 / 沙箱启动超时 / tmux 类失败 / 其他） |
| `tb_recover_plan.py` | 按目标臂数计算每个任务的补跑缺口，输出分组补跑清单 |
| `tb_full_status.py` | 合并主 run + 补跑（`e1_recover/jobs/e1rec_*`）的任务级汇总：每题有效臂数、成功数、verifier 超时数、其他异常数、在跑数。任务名从 `RUN_ID` 目录名反解（形如 `e1rec_<q\|d>_<task>_<n>`），只匹配 `*__*/result.json`，避免把 job 级 `result.json` 误当任务 |
| `env.sh.example` | 远程 `~/niuyiming/SkillExpand-tbeval/env.sh` 的副本（本身不含密钥，只引用 `~/agentbrew-tb21/.env`） |

一次性诊断脚本（effort_test*.py、health*.py）没有入库，留在远程
`~/niuyiming/SkillExpand-tbeval/work/` 下。已废弃的第一版补跑链 `recover_chain.sh`
留在远程 `/data2/niuyiming/scripts/`（附 `.bak_20261010_premirror` 为 runner
加镜像补丁前的原版），均未入库。

## 远程工作区布局（node29，用户 xinhaidong）

```
~/niuyiming/SkillExpand-tbeval/   # SkillExpand 工作区（repo/ venv/ env.sh logs/）
/data2/niuyiming/                 # 大盘：全部产物
  e1_full_q36flash_2att/          # qwen3.6-flash-distill, 89任务 x 2采样, 默认effort
  e1_full_dsv4max_5att/           # DEEPSEEK_up5zdj(deepseek-v4-flash), 89任务 x 5采样, reasoning_effort=max
  e1_recover/                     # 滚动补跑产物（e1rec_*）与 manifest.tsv
  retry_archives/                 # 重试归档
  e1_full_q36flash_2att_partial_killed{,2}/  # 中断的历史 run 归档
```

启动方式与进度检查命令见内层仓库的 TERMINALBENCH_TESTING.md 第 3 节；判据是
pidfile 进程退出 + `find <jobs> -name result.json | wc -l` 达到 178 / 445。

## 两个 run 的口径（比较时必须注意）

| | qwen | dpsk |
|---|---|---|
| 模型 | qwen3.6-flash-distill | DEEPSEEK_up5zdj（deepseek v4 flash 0731） |
| 采样数 | 2 | 5 |
| reasoning effort | 默认（high） | max |
| verifier 超时 | task.toml 原值（多为 900s） | 原值 × 2 |
| pass@N 的可比性 | — | pass@5 > pass@2 有采样数的机械成分，不能直接归因模型；avg@N 是可比性较好的指标 |

基础设施异常共 50 个 trial（qwen 23 / dpsk 27），按类分布与补跑决策记录在
2026-10-10 的会话中；约半数是 7 个任务的 verifier 固有超长（装 torch /
nvidia 依赖时从 pypi.org 原生下载太慢），补跑统一用 `TBENCH_VERIFIER_OVERRIDE=7200`。
其中卡在评测上的 9 条已停掉，待镜像 smoke 验证通过后用
`TBENCH_PYPI_MIRROR=https://mirrors.cloud.tencent.com/pypi/simple/` 重新排队。
