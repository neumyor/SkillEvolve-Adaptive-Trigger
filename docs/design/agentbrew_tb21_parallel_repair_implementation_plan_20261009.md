# AgentBrew TB2.1 并行修复实施计划

> **Deprecated protocol (2026-10-26):** 本文档记录旧的 41/20/28 切分。当前 AgentBrew TB2.1 使用 25/64，见 `benchmark/terminalbench-eval/docs/AGENTBREW.md`。

日期：2026-10-09。依据：UpSkill `ed42b147411bde72620a9a61bc956693413b0607` 的TB脚本，以及 `agentbrew_tb21_upstream_parallel_audit_20261009.md` 的运行证据。用户授权多个子代理并行修改；正式评测和自动检查仍暂停。

## 1. 复核后的实施边界

设计目标仍是强教师向持久、带schema的经验池写入，冻结学生读取，经验在不同任务上复用，不训练权重。保留已明确的科学约束：只对有效学生失败调用教师；候选通过同源任务Ralph才能准入；test单rollout，零教师调用与零写池；固定41/20/28、学生/教师、最大3轮及现有模型token预算。

本次对齐的是**上游TB的阶段内独立任务并行和Ralph轮次屏障**，不是默默采用脚本中成功也brew、curator先于验证、类别CLAUDE.md替代schema等不同语义。新模式命名 `tb_batch_notes`：公开TB批处理调度 + 已披露的论文失败触发/验证准入/schema检索适配。它不是上游TB脚本逐行复现，也不是论文Algorithm 1的顺序增量记忆实现。原 `paper_streaming` 模式保留；新模式必须新run契约，禁止修改旧正式run源码hash或覆盖旧产物。

对上一版方案的收紧：

- 不直接把当前Runtime包进线程池，也不在worker中写共享Memory。
- 初始baseline全部读取同一空池；Ralph读取固定空基底 + 该task候选，不因完成次序读取别题经验。
- Ralph全部完成后，curator按scope分组并行、同scope按固定task顺序去重/合并；协调器按固定顺序提交验证过的决策。不同scope的worker不共享可变Memory。
- 结构化笔记和现有scope/BGE检索保留并披露，避免为“并行”擅自更换表示与检索方法。
- 上游固定轨迹裁剪提供单独配置策略：初次15步×250字符，修订10步×200字符，保留完整ATIF及映射/省略证据；仅新profile使用，旧profile保持旧策略。
- 无效教师完整输出必须持久化为不可重采样的模型失败，不能换HTTP额度。本轮先登记为blocked而非跳过后发布完整实验；其他独立任务可完成，冻结必须等待全部所需单元无阻塞。
- 8192输出token和模型reasoning不自动扩大/关闭。传输等待、队列和deadline分开配置，不能以增加模型预算修网络。
- 此次验证使用无付费fixture与本地资产检查；真实1–2单元完整smoke仍是正式重启前硬门槛，不把fixture通过冒充真实链路通过。

## 2. 固定执行图和产物接口

1. evolve initial baseline：默认学生4个任务槽位，每task单adapter trial；即时保存state。
2. 对有效reward0任务并行draft r1：教师默认4个逻辑槽位，provider独立admission限制。
3. 每轮r：批量Ralph单trial → 屏障 → 尚未恢复者draft r+1 → 屏障；通过者不进入下一轮。
4. 验证后scope curator：scope间并行、scope内确定顺序；共享池单writer提交，保留候选/决策hash及准入证据。
5. 全evolve无未解决阻塞才freeze；test serve/vanilla使用同一个学生并发上限和预算，每(task,replicate,arm)单独落盘；全部结束后独立配对审计。

每个逻辑单元保持现有 `brew/NNN-task/initial`、`draft/rNN`、`ralph/rNN`、`curator` 和serve/vanilla目录约定，增加phase ledger及不可变输入hash。不重新编号旧HTTP尝试；失联pending成本保持unknown；同unit排他锁避免重复writer。

错误分类至少为infra_retryable、output_budget_exhausted、invalid_content、configuration_invalid、evidence_invalid。契约/证据异常停止派发并保全在途结果；教师模型失败阻塞该单元，真实infra保留固定尝试政策及可审核恢复。request/response身份分离；finish与usage在schema解析之前落盘。

## 3. 子代理分工和文件所有权

| 工作包 | 范围 | 所有文件 |
|---|---|---|
| A：调度与候选隔离 | tb_batch_notes执行图、round barrier、scope内顺序curator、单writercommit、冻结serve并行、失败隔离与resume | 新 `batch_runtime.py`、`tests/test_agentbrew_batch.py`；不得编辑config/runner/现有runtime |
| B：教师与传输 | 类型化错误、完整/截断响应、HTTP正文/headers、请求锁、attempt与usage持久化、固定重试/RPM admission、SSE证据 | `teacher.py`、新 `errors.py`/`transport.py`/`relay.py`、`tests/test_agentbrew_transport.py`；不编辑remote wrapper/config |
| C：审计、成本、预检 | phase与formal完成门槛、准确覆盖/配对重算、raw账本累计、未知用量、学生模型错误分类、实际配置预检 | `audit.py`、新 `costs.py`、`preflight.py`、共享 `scorer.py`必要最小改动、新audit/cost tests |
| 主代理：集成与独立复核 | config/profile、runner选择、轨迹策略、并发安全原子写、PID身份/清理和wrapper执行契约、跨包集成 | `config.py`、`storage.py`、`trajectory.py`、`adapter.py`、`runtime.py`最小接线、两个runner、supervisor、配置与集成tests/docs |

子代理不得调用真实模型、启动评测、修改远程正式目录或恢复heartbeat。需要跨文件接口变更先向主代理报告，避免同时编辑。所有代理都须说明已验证内容和未覆盖的边界。

## 4. 集成验收清单

- 两个阻塞fixture证明真并行且不超过worker上限；完成顺序变化不改变输入。
- candidate隔离与轮次屏障；成功轮后无多余teacher/Ralph调用；curation仅处理真实恢复候选。
- length/空content/无效JSON保留raw和usage，resume不再调用provider；429/503固定重试并保留成本。
- 崩溃/恢复单元、共享保存、进程PID复用、精确子进程管理和run锁。
- 不删reward0，不跳过blocked单元freeze，正式test零教师与冻结池不变。
- 完整serve/vanilla身份集合与配对指标从raw重算，partial审计不能标formal complete。
- 成本包含失败、history和在途unknown，不双算同物理请求；新进程汇总不清零。
- 新profile干跑、全89task/harness hash、bare/control预算不变量及执行契约。
- 相关原测试与新增回归通过后，再独立检查真实smoke gate；不得直接启动全量。

## 5. 完成记录

已完成本地实现与集成；三个子代理分别修改调度、教师传输、审计成本，另有最后独立复核。正式评测、自动检查仍暂停，未部署远程、未调用真实模型。

### 已落实的修改

- `batch_runtime.py` 与新profile：默认四任务并行、initial与Ralph屏障、task-local候选、scope内固定curation顺序、协调器固定顺序提交；blocked前置决策不允许晚序跨scope抢先写池。全Ralph cohort未解决时不curate、不freeze。
- `teacher.py`、`errors.py`、`transport.py`、`relay.py`：先保存raw/usage再验证；完整length/空内容/schema错误不可重采样；429/503与配置拒绝分开；全局admission、请求UUID、unit锁、Retry-After；SSE原始证据与最终usage保留。
- `adapter.py`与共享scorer必要改动：未知/模型/配置错误不再统称infra；保留raw verifier reward；有二值verifier却带infra标志时明确证据阻塞，不能重跑。缺最终trial但已留完整模型回答也不授予新采样；duplicate trial和变化的pending intent拒绝。
- `costs.py`：从物理请求账本重建跨进程累计，历史、诊断、pending及失败都保留；唯一身份去重；未知usage/dollar不猜0。wrapper另写campaign范围账本，不能与run范围账本相加。
- `audit.py`：brew和formal区分；精确serve/vanilla身份覆盖、配对重算、冻结池和教师账本内容hash核验；partial不标formal complete。
- `storage.py`：唯一临时文件、原子替换与fsync；`memory.py`空池也持久化current，并核对磁盘一致性。
- config/runner/trajectory：旧 `paper_streaming` 保留、新 `tb_batch_notes`选择；上游15×250/10×200裁剪及完整源证据；新契约绑定wrapper、supervisor、relay源码、Python入口与环境；89题快照/harness校验。
- `processes.py`、adapter、wrapper、supervisor：精确PID/start time身份、进程组清理、停止派发、排他锁、每launch独立receipt；清理失败不报成功，不遗漏其他清理/成本/receipt。弱PID或死leader遗留未知组成员只能阻止resume，不能自动kill未知身份。supervisor单次运行，无看门狗/自动重启。

### 独立复核发现并修正的边界

1. 跨scope curator阻塞时晚序任务提前占据同note_key，恢复顺序变化：改为仅提交可用固定顺序前缀。
2. 客户端断线但relay已DONE：同次HTTP错误后及退避后按attempt UUID恢复精确回答，不派新采样；relay仍pending则阻塞，不能制造重复请求。
3. 既有二值verifier与infra标志矛盾：阻塞证据，不改变共享scorer既有异常口径，也不重采样。
4. 教师UUID不变但raw/usage/finish被改：formal审计强制核对batch before/after内容hash。
5. 全initial pass或无候选准入的空池：freeze同步保存current，完整batch审计可通过。
6. wrapper finally修改code但此前return已决定0：返回移到finally之后；清理错误逐项保留，最终receipt与退出码一致。
7. missing/duplicate raw trial、pending signature、PID复用、死leader孤儿组：收紧证据和恢复门槛。

### 实际验证

最终相关集成：**164项通过**，14条Harbor已存在的task配置弃用警告。命令范围：

```bash
.venv/bin/python -m pytest -q tests/test_agentbrew*.py tests/test_scorer.py tests/test_results.py tests/test_jobconfig.py tests/test_e2b_env.py
```

相关AgentBrew源码、三个入口、共享scorer、新旧AgentBrew测试的Ruff通过；compileall通过。
另独立运行了真实本地进程组终止（包含忽略TERM的孙进程）、supervisor脱离会话及历史receipt、64个并发原子writer；不涉及真实模型或远程服务器。
batch完整brew→serve→resume夹具证明输入、memory/stat、cost、report及模型调用数不变；正式审计fixture包含空池和教师内容变更。

最终新profile资产干跑通过：evolve41/test28共69个执行资产，验证整个89题snapshot及固定harness；validation20保持留出。
产物：`benchmark/terminalbench-eval/tmp/agentbrew_tb21_parallel_repair_20261009/final_batch_dry_run/contract.json`。
本地干跑contract hash：`e80d75f35b187327e90bae1255d7f51deabfb4ab6a16a0f4fc74aefbc2b329ab`。
这是本地Python/路径的契约，不是远程部署契约，不应复制该hash覆盖远程run。

### 剩余门槛与限制

固定开发小样本真实失败→教师→Ralph→curator、匹配bare/control及两个并行真实单元尚未执行；真实provider额度与8192 reasoning输出可行性尚未验证。没有声称远程全链路通过。
Harbor原生内部模型重试保留，外层修复不消除其预算/成本；merge的语义等价仍依赖教师合同，schema不能证明。
最终独立复核未发现新的明确阻塞问题；provider已执行而relay在pending证据创建前崩溃的窗口无法证明physical exactly-once，仍按未知用量及固定传输重试边界披露。
完整无效输出按既定协议blocked，不通过增加预算/重采样/跳题“完成”实验。旧run产物、hash与未知历史成本保留；新版本不能直接在旧run目录resume。
新操作路径及恢复约束见 `docs/agentbrew_tb21_batch_operations_20261009.md`。后续启动前须按AGENTS.md通过真实smoke与独立复核，不自动解除用户暂停要求。
