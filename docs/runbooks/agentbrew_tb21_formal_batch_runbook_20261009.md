# AgentBrew TB2.1 Batch 正式运行

用户于2026-10-09授权启动正式评测，并在正式运行中定位问题，特别检查并发。完整教学分支在固定smoke中未触发的限制已披露；本次正式运行保留该风险，不扩大预算或筛选失败。

## 运行身份

- 服务器：`xinhaidong@10.31.112.40`，SSH使用`-S none -o BatchMode=yes -i /Users/yimingniu/.ssh/id_ed25519`。
- 冻结代码release：`/home/xinhaidong/agentbrew-tb21-batch-smoke-20261009-r2`，沿用已通过真实smoke的源码；不是复制到新的release。不得修改其源码。
- 新campaign：`/home/xinhaidong/agentbrew-tb21-formal-batch-20261009/outputs/agentbrew_tb21_formal_batch_20261009`。
- supervisor PID701166，start_time_ticks1815630115，boot_id `cd6930ab-43e0-4637-b5f6-f873208e8fe1`；wrapper PID701169；evaluation PID704830。判断存活必须读取当前receipt并核验完整身份。
- launch_id：`4d28eaf77eaa4184bdf7968345481e06`。教师relay端口18133，由远程wrapper拥有，没有本地隧道依赖。
- 旧顺序正式campaign `agentbrew_tb21_formal_20261008`已停止，锁可获取；旧产物、费用及教师失败原样保留，不导入新合同。

学生`qwen3.6-plus-distill`；教师`deepseek-v4-flash-0731-tencent`。配置`configs/agentbrew_tb21_batch.yaml`，完整evolve41、test28单次serve及匹配vanilla28；validation20不进入主指标。主指标单次成功率及逐task配对差。
student/teacher/curator四个逻辑槽位；initial空池批处理屏障，Ralph逐轮屏障、task-local候选，最多3轮；scope间并行curator、scope内固定顺序、协调器单writer提交。教师provider最多4并发、全局每60秒放行一次。单task adapter内部n_concurrent=1，不能设4导致四次同题采样。
模型、reasoning与token预算与已验证smoke一致：学生65536输出/131072上下文，教师8192输出。

## 启动检查与观察

本地相关165项测试通过、Ruff通过；完整batch资产dry-run通过，检查89题snapshot/harness及41/28覆盖。本地dry-run合同`ce16889da06714f8b5f13451b027dab3e8eff398169bb62b3026aabe29f6fda4`仅是本地配置，不覆盖远程合同。
真实两initial及serve/vanilla smoke四rollout审计通过，失败预检及成本保留。正式wrapper另执行真实学生、教师、embedding、原生setup预检，healthy=true；正式教学分支尚待执行。
初始四child PID705024/705025/705026/705028，在约0.29秒内启动，每个独立session/PGID。完成后补槽，多个新shell快照核对活跃数始终4；已观察有效reward0不触发提前教学，等待完整initial屏障。
远程实际formal合同hash：`89d6f529ab62afe8298d19b4026aa321ad6885861b28daa56445dd084ce1a838`。运行中再次核对149文件部署manifest无变化，当前20个完成initial全部通过独立raw verifier/checksum/request/空池证据检查；4个reward0保留，teacher调用0，不将partial audit称为正式完整性通过。
远程campaign全部依赖为远程路径，凭据仅从远程忽略的`.env`读取。supervisor与各driver独立session，SSH断开不影响运行。**不部署服务器侧看门狗或自动重启。**

## 检查及恢复

本地状态快照：运行`benchmark/terminalbench-eval/tmp/agentbrew_tb21_formal_batch_20261009/fetch_status.py`；只打印状态与用量，不打印密钥、轨迹内容或隐藏答案。
核对`launch.json`、`supervisor.log.pid/.identity.json/.done`、`remote_execution.json`、`remote_preflight_child.json`、`remote_child.json`、`remote_done.json`、`run/run.lock`、`remote_driver/run.lock`以及当前launch的preflight/evaluation日志。
逐单元检查state/rollout/request/physical child、`run/phases`、教师`http_*.json`及relay SSE证据、`run/token_totals.json`，必要时重新从raw账本核对成本。未完成时pending/unknown不等于错误；不能只凭计数或PID数字认定进程死亡，禁止`pgrep -f`。

只恢复infra/transport故障；有效reward0/1、完整无效教师输出不可重采样，不跳困难题或被阻塞的evolve单元来freeze。不增Ralph/模型预算，不查隐藏答案，不改方法或合同hash。
同合同续跑前先确认所有记录的driver/rollout及其进程组退出、三个锁可获取，验证已有raw结果；优先采用已经完成且证据有效的trial，不重复执行。失败重试额度耗尽时，按旧runbook的failed-only归档规则保存费用和原始证据，再记录修复receipt并使用`--resume`；完整无效模型输出不归入传输重试。
需要实现bug修复时先保存故障证据并做独立小检查，记录影响；当前代码合同绑定源码及执行身份，不能静默修改后在原目录resume。若必须新合同，明确归档旧campaign并建立新run，保留全部成本；不能把旧trial改hash假装满足新合同。
同合同恢复用`launch.json`中的wrapper_command（或supervisor command中`--`后的部分），加`--resume`，保持原port18133、release和任务，不加新schema probe。启动以`Popen(start_new_session=True)`脱离SSH，并保存每launch精确身份。新启动存在旧remote_done时，必须按launch_id区分历史完成记录。

两个小时自动检查从本机Codex运行；正常推进或无变化保持安静，只在故障、修复、重要进展、完成或需要处理时通知。本机关闭不停止远程评测，但本机自动检查不可用。
旧`agentbrew-tb2-1`在app中已不存在，建立的新heartbeat为`agentbrew-tb2-1-batch`，ACTIVE，每两小时一次，指向本次batch新campaign。
完成后必须独立审计41 completed brew、28 serve、28 vanilla、distinct raw trial、冻结池一致、serve零教师、累计成本及逐task配对指标；保存报告、同步无密钥产物并暂停检查。

## 2026-10-09 20:37 检查发现的中断

当前launch于20:16:40退出1，initial barrier blocked。有效initial39/41（26 reward1、13 reward0）；038-torch-tensor-parallelism、040-write-compressor各两个physical均无verifier分数，state为infra_retryable blocked。教师请求0、Ralph0，未freeze、未serve/vanilla。
独立核查39个有效rollout的raw verifier/checksum/request全部通过；源码149文件无变更；run账本与raw重算相同。所有记录的评测supervisor、wrapper、driver、rollout及其进程组均退出，三个排他锁可取得；没有并发超限或重复writer证据。现场检查receipt为`stopped_inspection_20261009T1237Z.json`。

write-compressor：两个attempt均首个模型HTTP200后，下一轮native调用在E2B `handle.wait()`超时；同一轮由原生Terminus重复3次，未保存对应完整response。SDK命令超时620秒、urllib读取超时600秒，二者与65536输出预算并不能保证完整stream在窗口内完成。没有证据证明服务故障已经修好；未知用量保留。禁止擅自关闭reasoning、扩大时间/token预算或从原始缺失response中编造答案。
torch-tensor-parallelism：两次均完成学生调用后，在900秒verifier deadline超时，无reward，verifier stdout文件0字节。**虽然当前scorer标为infra_retryable，这个标签本身不证明是基础设施故障；可能涉及候选实现的执行时间，尚未确定。**不能凭标签反复重跑整段学生、扩大verifier时限或填reward0/1。此前自动第二次尝试的证据和成本完整保留。

随后在独立`environment_diagnostic_20261009T1240Z`目录并行启动两道任务的全新原生环境、setup及64-token健康请求，不运行benchmark指令、隐藏tests或教学。两道健康检查均healthy=true，sandbox清理完成。这个检查仅证明小请求和环境setup可用，不能证明失败轮/长响应或verifier可用，不能作为已修复声明。
目前没有执行failed-only归档或新增正式采样；正式campaign保持停止。自动检查仍可只读检查，但**上述两个重复超时必须先获得可验证的原因/修复证据，再决定infra恢复；不得每两小时盲目归档重跑。** 39有效结果不可重采样，不跳过两道题进入教学/冻结。
截至停止时run已知输入33425847、输出1669476；unknown学生用量16、教师0。独立健康检查另有成本，campaign扫描包含它，不能与run账本相加。诊断原始response、snapshot和token_totals独立保留。

## 用户授权两道超时最终失败后续跑

用户随后明确指示“这两个记录为失败即可，继续后续任务”，覆盖上一节禁止推进的处理决定，仅适用于本次两道initial超时。
`torch-tensor-parallelism`、`write-compressor`计为最终brew失败，reported_reward=0、verifier_reward=null、teaching_eligible=false，不重试initial、不伪造verifier分数、不用其不完整轨迹生成经验。其余39个有效initial（26成功、13失败）原样保留，教学仍只消费13个有效reward0。

原冻结源码、`run/contract.json`、request/physical/raw记录及成本全部不改；新增`operator_amendment_20261009/operator_amendment.json`，包含用户原话、两个original blocked state、原始证据SHA256清单和独立续跑入口hash。`run/continuation_contract.json`显式绑定parent合同、amendment和扩展代码；后续实验应称“原batch合同加用户超时失败修订”，不能声称无变更的原始协议。
amendment hash `a6069bec370a8d8259f838c577133297c81c90d011a1c26961afd5e613e4e85e`；扩展代码hash `9035a32c329658c56d50c8df4f2a671a1b354997af64a3aa58b7e8282a0bf1a3`。
续跑脚本`operator_amendment_20261009/continue_with_timeout_failures.py`包装原远程wrapper和driver；仅替换这两题的initial调度及增加独立amended审计，relay/teacher/Ralph/curator/serve、四槽位并发、60秒admission与所有预算仍使用冻结实现。
原`run/audit.json`保留原审计结果，会指出这两道题缺有效initial；`run/amended_audit.json`仅允许恰好这两个明确例外，验证其所有原始超时证据、reported失败及零教学，其余审计问题必须继续阻塞。最终report也注明protocol/amendment和两个operator失败，不将原审计失败隐藏为无例外通过。

本地新增3项协议例外/防重采样/审计回归加原测试共168项通过；Ruff通过；远程新增及调度/远程集成29项通过；真实资产dry-run与原合同hash完全相同。再次确认39有效trial通过、所有owned进程及组退出、三个锁释放、18133端口空闲后启动。
新supervisor PID2720914，start_time_ticks1818062465，同boot_id；精确身份见最新`launch.json`。历史启动/退出记录保存在amendment目录的`prior_launch.json`、`prior_done.json`，新receipt仍每launch落盘。
后续恢复必须使用最新`launch.json.wrapper_command`中的扩展入口，**不可恢复原wrapper而丢失此次用户修订**。新`remote_done.json`写入前可能仍显示旧launch_id退出1，需要按当前remote_execution.launch_id判读。
自动检查必须承认这两个特例，不再次把它们当blocked来重跑；不把该特例扩大到其他任务、Ralph或test超时。正常其他任务出现异常仍按原恢复边界处理。完成报告同时保留原审计与amended审计，注明两道evolve最终失败及其未知成本。

## 用户授权放行已知relay差异，续跑V2

首次扩展续跑在preflight前合同检查失败，launch `67685facc255489787a6b0f896dce0da`，无新正式模型采样；原共享relay文件已由外部修改，原hash `2e3c06d2921479db855a0dab2cdce35ed800bfed2d6d0b9fffd16b7faa7fdf73`，新hash `ec00814298af8ddf1db36bb14c0c462851986c63494e86cb3f778f827a7a7d5a`。不覆盖他人文件，未恢复原版本。
用户明确指示“忽略严格校验，直接继续”，授权放行该relay差异。新版修订目录为`operator_amendment_20261009_v2`；旧修订、失败预检、历史receipt不覆盖。V2 receipt承接V1 amendment hash，并保存用户第二条授权及当前relay快照。
当前relay源码已复制到V2目录的`llm_relay_snapshot.py`，续跑只读此私有快照，不再依赖共享源变化。已观察差异包括deepseek未指定max_tokens时的默认输出上限和stream空内容错误处理；本方法显式传8192且自有SSE证据adapter仍使用，实际源码改变必须披露，不宣称完全相同的transport。
V2续跑入口仅对parent与实际合同中的`execution_identity.owned_relay.relay_source_sha256`这一字段应用授权兼容映射，**原始contract.json完全不修改**。实际执行合同另存V2的`observed_execution_contract.json`及wrapper的`remote_execution.json`；continuation_contract绑定新代码/修订，其他配置差异仍不能被掩盖。
V2 amendment hash `d35fd92d54b7fc4242b66d232535d7b6372036537b7422c490df09db6448d5c1`。两题最终失败口径与零教学不变，其余39个原始initial不重跑；并发4、teacher8192、student65536及Ralph3轮不变。
本地30项扩展/调度/远程回归、远程独立30项均通过；Ruff通过；远程真实资产dry-run验证只有已授权relay字段不同，兼容parent hash一致。预启动再次核对进程组/锁及18133空闲。
V2 supervisor PID2748363，start_time_ticks1818105496，同boot_id，完整身份与恢复命令见最新launch.json。后续恢复必须使用V2 wrapper_command；不使用V1入口或原wrapper。标准原审计与amended审计保持分别落盘，最终报告明确两道超时最终失败及relay变更两项修订。
V2真实预检已通过并进入正式evaluation，launch_id `755f025ccb7a4d87afef9baebdf762f3`。initial阶段completed：39个原trial读取复用、没有新initial child；两道operator_timeout_failure均completed、reported_reward0/verifier_rewardnull、teaching_eligible=false。已进入draft-r01，13个有效失败的教师请求开始落盘；阶段内仍四个逻辑槽位和60秒provider admission。后续状态以当前launch和逐单元证据为准。

## 2026-10-10 连接恢复后的实况

用户确认网络应恢复后，09:55（Asia/Shanghai）成功连接并读取实时记录。此前SSH超时不影响远程独立执行，但当时无法确认状态；旧快照不能作为运行正常证据。
V2于10月10日02:21:47退出1，current done.launch_id与remote_execution相同，cleanup_failures为空。独立核查所有owned supervisor/wrapper/driver及physical child/进程组已退出，三个锁释放，源码、V2 extension、私有relay快照hash未变。

initial39有效结果原样保留，另两道operator失败终态保留。已完成9个Ralph r1及4个Ralph r2，共13个有效Ralph rollout。count-dataset-tokens、sparql-university两道在r1得到reward1，status=validated，但尚未curator准入。其他11个有效Ralph结果均reward0。共52个有效rollout独立checksum/request/原始verifier复核通过。
教师20次正式HTTP请求均完成，14次valid、6次output_budget_exhausted：dna-insert/r1、extract-elf/r1、gpt2-codegolf/r1、mteb-retrieve/r1、raman-fitting/r2、train-fasttext/r2。六次均HTTP200、finish_reason=length、completion_tokens=8192；前五次visible content长度0，第六次有1204字符但回答不完整。原始SSE、raw及用量保留，这些是完成的模型预算失败，不能归为transport重新请求，也不能自动增输出或关闭reasoning。

本次实际fatal错误为sanitize-git-repo/ralph/r02/physical_01的`InvalidArgumentException: cwd '/app/dclm' does not exist`，发生在tmux send_keys经E2B执行命令时；不是已确认的可恢复网络故障。该trial没有verifier分数、16次模型HTTP均200；原始physical标为unknown_exception/infra=false。保留原始证据，禁止把它重分类为infra后自动重采样。模型动作与harness cwd之间的关系仍需分析，未宣称根因已修复。
fatal停止r2派发并drain在途任务；r2 ledger仍running是未完成阶段，不能把它误认为活跃进程。validated候选还未curate，全cohort有预算阻塞，因此冻结池尚不存在、serve0、vanilla0，不能报正式结果或迁移收益。

run已知输入88306460、输出3112152；教师输入61580、输出100425，未知学生用量23，美元成本未知。campaign（含健康检查）学生输入88306516/输出3112747，教师输入61754/输出100457；两账本均与raw重算一致，不能相加。未知请求继续保留，不填0。
复核报告`reconnected_inspection_20261010.json`已远程保存并同步本地tmp目录。**当前campaign停止；没有新增模型请求或续跑。** 自动检查不应盲目重启本次确定的模型输出预算失败或cwd证据错误，也不能将两道initial operator例外扩大到这些任务。需用户另行指定对这些新增模型失败的处理或可验证修复，才能推进冻结/测试。
