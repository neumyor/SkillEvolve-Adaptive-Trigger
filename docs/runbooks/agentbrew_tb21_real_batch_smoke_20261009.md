# AgentBrew TB2.1 真实批调度 smoke

> **Deprecated protocol (2026-10-26):** 本文档记录旧的 41/20/28 切分。当前 AgentBrew TB2.1 使用 25/64，见 `benchmark/terminalbench-eval/docs/AGENTBREW.md`。

日期：2026-10-09。用户授权尝试真实1–2单元完整smoke；正式评测和heartbeat继续暂停。

## 启动前固定协议

配置：`benchmark/terminalbench-eval/configs/agentbrew_tb21_batch_smoke.yaml`，继承新batch profile。
evolve固定 `dna-insert`、`fix-git`；validation固定 `nginx-request-logging`，单次serve及匹配vanilla。
选择依据为之前旧run中dna-insert已存在有效initial失败、fix-git已存在initial成功：本次重新独立执行固定小样本，不复用/覆盖旧run，也不观察新结果后更换题目以制造链路成功。
validation不用作研究主指标；不使用test28开发或调参。

学生 qwen3.6-plus-distill、教师 deepseek-v4-flash-0731-tencent；输出/上下文/推理/时间预算、最多3轮Ralph与4槽位调度均保持batch配置。
这里只改变任务子集和serve_split=validation。全量正式评测不在本次授权执行范围。

验收需要实际initial失败→有效teacher Draft→Ralph二值verifier→curator准入/拒绝→冻结池→实际serve/vanilla请求证据，逐单元独立审计。
若initial全成功，或length/schema/基础设施阻塞、三轮仍失败，没有经历该完整路径则如实记“全链路门槛未通过”。
不能扩大模型预算、关闭reasoning、重采样有效失败/完整无效输出或换简单题凑成功。

远程代码采用新隔离release目录，依赖仅指向远程已有venv、任务与embedding资产。旧正式产物和代码不覆盖。
先本地独立回归/配置干跑，再远程哈希、全部路径、旧run进程与锁检查，之后脱离SSH启动单次supervisor。
无远程看门狗、无自动重启；凭据仍只在远程忽略的.env读取。

## 实际执行记录

首次隔离release：`/home/xinhaidong/agentbrew-tb21-batch-smoke-20261009`。
首次产物：上述目录的 `outputs/agentbrew_tb21_batch_real_smoke_20261009`；supervisor PID4045902。
代码本地165项相关测试、远程原164项与变更后43项通过，149文件SHA一致，全部远程依赖、端口18134、旧run精确进程/锁通过。

首次预检退出1，没有任何benchmark rollout。教师健康请求完成（prompt87/output16，reasoning13）；native学生健康请求在原始dna-insert镜像中因 `python3: command not found` 失败6次。
失败HTTP证据保留unknown usage6，不凭空填0；SSE、preflight日志、全部receipt和成本保留。wrapper清理无异常，supervisor/preflight进程已退出。
诊断确认preflight在environment.start后直接用E2BSandboxLLM，跳过了真实Terminus的setup（tmux/asciinema依赖安装）。旧正式该任务曾成功执行模型，不据预检误认为模型服务不可用。

修复仅使preflight先以正式构造参数执行原生TencentSandboxTerminus2.setup，再调用原health请求；setup deadline沿用1800秒。
新增sequence不变量检查：fake native setup完成后才允许health call，model_info/llm_call_kwargs与正式配置一致。完整相关165项和Ruff再次通过。
正式方法/模型输出预算/推理/任务不变。由于源码合同变化，将以新隔离release与新run重新预检，旧合同及失败证据不覆盖、不迁移。
任何新实现bug先保存证据，代码改变不静默改旧契约续跑。

修复后release：`/home/xinhaidong/agentbrew-tb21-batch-smoke-20261009-r2`。
产物：`outputs/agentbrew_tb21_batch_real_smoke_20261009_r2`；supervisor PID4087367，以Linux start_time_ticks1814763479和boot ID核对，不能只按数字判活。
149文件manifest SHA256 `8f796174382bd319475ea2ebb52374271ea39015327f30dc167eeed5dfe0781f`。
修改后本地165项、远程43项及89题资产干跑再次通过；27项路径检查通过；端口18134可用；首次smoke全部进程已退出且run/remote_driver锁可获取后才启动r2。
远程launcher、supervisor和wrapper均脱离SSH会话，未部署看门狗或恢复heartbeat；首次失败证据已同步本地 `benchmark/terminalbench-eval/tmp/agentbrew_tb21_real_smoke_20261009/preflight_failure_r1`。

## 固定样本结果及覆盖限制

第二次预检healthy=true：原生setup完成后学生HTTP200/stop（prompt14/output150，健康请求cap64；供应商回报含reasoning的usage150，不据此推断完整预算行为）。教师健康请求HTTP完成（prompt87/output8，reasoning5）。
initial两道任务的独立子进程start_time_ticks均为1814788032，处于不同session，真实并行启动；两个实际请求均选择0条note、rendered_system为空。

| 单元 | reward | 原生模型响应数 | 输入token | 输出token |
| --- | --- | --- | --- | --- |
| evolve dna-insert initial | 1 | 23 | 374293 | 26514 |
| evolve fix-git initial | 1 | 6 | 13187 | 2171 |
| validation nginx-request-logging serve | 1 | 8 | 26645 | 4034 |
| validation nginx-request-logging vanilla | 1 | 8 | 25918 | 4104 |

两道initial均成功，按照failure-only教师触发规则，不调用Draft/Ralph/curator；状态为initial_pass、rounds为空。冻结池note_count=0，digest `b5be67c4cb9b75d6fe4d5e834af985a346c868d98de86f9c22cc0ee7f5de257c`。
本次已验证真实学生执行、并行initial及空池冻结/serve路径；**教师健康检查不等于教学链路验证**。没有覆盖教师Draft、真实Ralph、curator、非空池检索注入，所以尚未满足完整教学链路验收。
不会更换任务、重复有效initial或将旧失败轨迹改写成新合同下的initial。旧dna-insert失败轨迹仅已做只读可用性核查，未发起回放或付费模型调用。

## 最终独立审计

r2于2026-10-09 12:18:46（Asia/Shanghai）完成，约42分钟，包括预检、环境准备、两道并行initial、serve和vanilla；wrapper和supervisor均exit=0，cleanup_failures为空。
标准产物审计通过，独立审计再次通过：149个源码文件哈希保持不变；四个rollout各有独立原生raw_result/trajectory，request hash、task checksum、verifier二值结果、模型真实payload与记忆注入证据匹配，无重复请求。
每次真实benchmark请求均为qwen3.6-plus-distill、max_tokens65536、top_p0.95、top_k20、enable_thinking=true、preserve_thinking=true；记录的上下文上限131072、输出上限65536。
serve/vanilla的任务checksum、instruction hash、contract hash一致，均为空经验，预算/模型/原生harness相同。它们轨迹token不同属于独立模型执行，不要求逐位相同。
冻结经验池前后digest不变；benchmark教师调用0，serve阶段教师调用0。教师健康检查只计入campaign成本。
精确进程身份及其进程组核查无活跃遗留子进程；run、remote_driver、supervisor三个排他锁均可取得。没有远程看门狗，没有续跑/重复有效单元。

审计中的`scope=formal`与`formal_complete=true`只指**当前小样本合同的全部单元完成**，不表示evolve41/test28正式评测完成，更不表示教学分支验证。独立审计明确记录`teaching_branch_exercised=false`、`full_teaching_chain_passed=false`。
validation这一个任务的serve=1、vanilla=1、逐任务配对差=0，仅用于工程smoke；不进入研究结果表、不说明AgentBrew有效或无效。

## 用量及证据位置

| 口径 | 学生输入 | 学生输出 | 教师输入 | 教师输出 | 未知学生用量次数 |
| --- | --- | --- | --- | --- | --- |
| r2 benchmark run，45次学生HTTP | 440043 | 36823 | 0 | 0 | 0 |
| r2 campaign，含学生/教师健康检查 | 440057 | 36973 | 87 | 8 | 0 |
| r1失败预检，保留原始失败成本 | 已知下界0 | 已知下界0 | 87 | 16 | 6 |
| r1+r2 campaign累计已知下界 | 440057 | 36973 | 174 | 24 | 6 |

不能将run与campaign两行相加，它们包含关系；只有不重叠的r1/r2 campaign可以相加。所有美元成本未知，不能推算为0。未知6次保持未知，不因第二次成功而消失。

远程完整原始产物：`/home/xinhaidong/agentbrew-tb21-batch-smoke-20261009-r2/outputs/agentbrew_tb21_batch_real_smoke_20261009_r2`。
本地完整镜像：`benchmark/terminalbench-eval/tmp/agentbrew_tb21_real_smoke_20261009/completed_r2`，307个文件逐个SHA256与远程一致；同步前扫描确认没有本次服务凭据。
本地独立审计：上述目录的`independent_smoke_audit.json`；标准审计`run/audit.json`；逐任务报告`run/report.json`；原始请求/响应及trajectory位于对应`physical_01/jobs`目录。
首次失败预检：`benchmark/terminalbench-eval/tmp/agentbrew_tb21_real_smoke_20261009/preflight_failure_r1`。
累计成本口径：`benchmark/terminalbench-eval/tmp/agentbrew_tb21_real_smoke_20261009/smoke_campaign_accounting.json`。

**结论：真实两单元并行initial→空池冻结→serve/vanilla→正常退出/证据审计已跑通；完整教师教学链路门槛未通过，原因是固定initial均成功、分支未触发，并非已观察到教学分支出错。** 正式评测与heartbeat继续暂停。
