# TB2.1 batch notes：新版本操作约束

> **Deprecated protocol (2026-10-26):** 本文档记录旧的 41/20/28 切分。当前 AgentBrew TB2.1 使用 25/64，见 `benchmark/terminalbench-eval/docs/AGENTBREW.md`。

日期：2026-10-09。当前状态：本地修复与离线验证；未部署远程，正式评测及两小时自动检查保持暂停。

## 配置与方法身份

入口：`benchmark/terminalbench-eval/configs/agentbrew_tb21_batch.yaml`。
学生 qwen3.6-plus-distill，教师 deepseek-v4-flash-0731-tencent；evolve41、validation20、test28。
默认各阶段四个独立任务槽位，每题每轮一个学生 trial；不是每题四次尝试。
教师另有 provider admission，当前配置最多四个在途请求、请求启动间隔60秒；额度尚未真实验证。
Ralph 最多三轮、教师输出8192，模型推理设置保持原配置。

采用公开 TB 的阶段并行、Ralph 屏障、固定末尾 message 视图。保留失败触发教师、schema Note/BGE、Ralph 后 curation。
这是适配版；不宣称类别ACP、教师工具执行器、curator先于Ralph等上游细节也原样复现。
不将顺序模式中前题经验影响后题initial的语义带入批调度。

## 启动前门槛

1. 代码检查、离线失败矩阵、恢复不变量、配对控制预算、89题快照与harness哈希均须通过。
2. 使用新的远程运行目录，按远程路径审计检查全部依赖、凭据变量及输出权限。
3. 完成固定开发小样本真实链路：至少一个真实initial失败走过教师→Ralph→curator，另有同条件bare/control单元；两个单元并行验证资源限制。健康请求或合成schema不能替代此项。
4. 若既定预算下发生完整length/无效内容，登记blocked；不能为“修网络”关闭reasoning、加输出token、多采样、跳题或改方法。
5. 通过后才能启动全量。当前没有执行第2–5项，不得称“远程全链路已验证”。

使用 remote wrapper 时需在远程启动已脱离SSH会话的supervisor：launcher用Python `Popen(..., start_new_session=True, stdin=DEVNULL)`，日志落在远程磁盘。
supervisor只管理一次命令，不自动重启；不部署远程看门狗。使用目标venv的原入口路径，不将其resolve到基础Python。

## 新日志与判活

`scripts/run_agentbrew_remote.py` 为每次启动分配不可变 `launch_id`：

- `<campaign>/launches/<id>/preflight.log`、`evaluation.log`、相应 `*_child.json`、`done.json`。
- `<campaign>/remote_execution.json`、`remote_preflight_child.json`、`remote_child.json`、`remote_done.json` 指向最新一次启动。
- `<campaign>/teacher_relay_evidence/` 保存关联attempt UUID的SSE和envelope。
- `<campaign>/run/contract.json` 绑定调度模式、源码、模型预算、任务、Python环境及外部relay源hash。
- `<campaign>/run/phases/`、逐单元state/request/rollout/HTTP证据供进度审计。
- `<campaign>/run/token_totals.json` 是benchmark账本；`<campaign>/token_totals.json` 是包含健康/诊断的campaign账本，不将两者相加。
- `<supervisor-log>.identity.json` 与 `.launches/<id>/` 保存精确进程身份和历史完成receipt；数字 `.pid` / `.done` 保留兼容。

判活必须验证PID与start time（Linux同时boot ID）等身份，不能只看PID存在，也不能用 `pgrep -f`。
run锁和remote_driver锁均排他。PID-only旧记录保守阻止重复启动，但不能授权自动kill。
新日志不再依赖campaign根目录下旧 `preflight.log`/`evaluation.log`；任何后续监控须先更新到上述路径。

## 停止与恢复

driver收到停止信号先阻止新学生派发，终止已注册且身份匹配的rollout进程组，保存在途证据和成本。
wrapper逐项尝试清理driver、rollout、relay与成本；某项失败仍记录其他项和failed receipt，不能返回成功。
每个独立unit排他写入；共享池仅协调器按任务固定顺序提交，不越过blocked前置决策。

续跑前可用 `run_agentbrew.py --phase readiness --work-dir <campaign>/run` 做只读检查；它不授予任何新额度。
只有契约完全一致且没有活跃子进程时，才能 `--resume`。完整reward0/1、完整教师无效输出不可重采样。
unknown/pending尝试继续计入未知用量，固定次数耗尽则blocked；本版本不提供自动增加额度或批量移走失败记录的捷径。
若需基础设施恢复或修实现bug，应另存证据及恢复依据，不修改旧contract；源码变更需要新的运行契约和明确的数据处理方案。

serve只读冻结池，正式完成还须精确覆盖serve28/vanilla28、零教师调用/池写入、单次成功率与逐任务配对差重算、累计成本核对。
brew审计通过明确 `formal_complete=false`，不能当正式评测完结。

## 仍未解决的实测边界

真实provider并发额度、长reasoning请求及失败教师链路仍待固定小样本验证。
Harbor原生内部模型重试保持现状；外层分类修复没有消除这些调用，必须保留其raw账本与成本。
curator merge是否保留原规则属于教师语义约束，schema只能验证结构，不能证明语义等价。
旧run的未知历史HTTP成本不会通过新版本被凭空恢复，旧产物也没有覆盖或迁移。
若provider已执行但relay在创建pending证据前崩溃，无法证明物理请求恰好执行一次；保留未知用量与固定传输重试边界，不宣称exactly-once。
