# AgentBrew / UpSkill 在 terminalbench-eval 的移植方案与复核

> **Deprecated protocol (2026-10-26):** 本文档记录旧的 41/20/28 切分。当前 AgentBrew TB2.1 使用 25/64，见 `benchmark/terminalbench-eval/docs/AGENTBREW.md`。

日期:2026-10-08。依据:论文 v1、已拉取 UpSkill、本地已安装 Harbor、任务缓存/切分、terminalbench-eval 注入与结果接口。本轮只修订方案,未实现移植器、调用模型或启动容器实验。

**目标更新:** 用户已确认在现有TB2.0/Terminus上保留论文提出的方法。执行设计以[论文方法复现契约](../reports/agentbrew_tb20_paper_faithful_adaptation_20261008.md)为准。本文保留为TB2.0源码审计与旧适配方案记录;其中批量构建、整类prefix不再作为忠实论文方法的主实现。现有41/20/28可继续用于本地统一比较,但须声明与作者25/64的区别。已发现的源码缺陷仍然有效。

## 1. 结论与复现目标

**可行,但原方案不能直接用于完整实验。** 核心链路可通过现有评测接口实现:冻结学生尝试开发任务,教师根据学生轨迹写经验,学生在真实环境验证,合并类别记忆,测试时只读。主要工作是方法编排和证据管理,不需要训练模型。

撤回原稿的三项判断:“论文设置全部落实”“教师直接 API 化无保真损失”“Paper-level 已有条件成立,剩余仅外部依赖”。源码与论文一般方法存在差异,还有已确认的代码缺陷、资产和注入问题。资产完整度较高不等于复现已经成立。

必须分别命名以下结果,避免混报:

| 结果 | 设置与目的 | 可以声称什么 |
|---|---|---|
| `AgentBrew-TB-adapted` (建议主实验) | 我们的学生、Terminus-2、41/20/28;失败触发、验证后准入 | 论文核心机制的TB适配,不能称原论文数值复现 |
| `UpSkill-TB-adapted` (可选伴随实验) | 同一接口,保留仓库对成功/失败任务都brew的行为 | 仓库TB策略的适配,须声明准入和编排修复 |
| `UpSkill-native-reference` (可选独立轨道) | Claude Code、原教师/学生、25/64 | 完成运行与审计后报告数值接近程度,修补项单列 |

论文一般方法明确失败触发、certified notes才由curator合并;但§3.8 TB案例列出的顺序是brew → category curation → Ralph → serve,与仓库顺序相近。不能把一般方法、TB案例和本地修正版当成同一个已经确认的实现。

本适配沿用TB脚本的批量构建:初始evolve尝试不读取此前累积记忆,最后统一类别合并。它不复现论文一般框架的逐任务记忆增长和动态检索;若研究该行为,应另设streaming变体及任务顺序,不能把批量适配称为完整一般算法复现。

来源:[AgentBrew v1](https://arxiv.org/abs/2607.16851v1)、[UpSkill](https://github.com/HKUDS/UpSkill)。本地全文:`tmp/terminal_skill_literature/2607.16851v1.txt`。

## 2. 已确认问题与修复要求

### P0:最终记忆没有真正受Ralph准入约束

`tb_harbor_2.0/REPRODUCE.md` 先执行curator,再执行Ralph。Ralph修改的是`brew_acp`中的per-task文件,最后写`ralph_status.json`;curator不读该状态;serve读之前的`curated_acp`。失败笔记可能进入最终池,修订成功的版本也可能没有进入最终池。

证据:`scripts/run_ralph.py:180`部署per-task CLAUDE.md,`:290`提取修订,`:341`保存状态;`scripts/run_curator.py:83`遍历全部输入;`scripts/run_serve.sh:84`读取类别成品。

**修复:** provisional → Ralph → accepted exact version → curator → frozen pool。每个accepted条目绑定文件hash、验证trial及reward;curator只读accepted清单,不能扫描整个brew目录。这个顺序是明确的方法修复,不是仓库原样运行。合并产物仍不能称为“已逐条环境验证”;它是从通过验证的候选合并而来。

### P0:上游成品池会污染我们自己的留出集

已按任务ID计算上游train25与我们切分的交集:

| 本地split | 任务数 | 与上游train25交叉 |
|---|---:|---:|
| evolve | 41 | 13 |
| validation | 20 | 4 |
| test | 28 | 8 |

validation交叉:`git-multibranch`, `pytorch-model-recovery`, `qemu-startup`, `schemelike-metacircular-eval`。

test交叉:`caffe-cifar-10`, `crack-7z-hash`, `feal-differential-cryptanalysis`, `large-scale-text-editing`, `modernize-scientific-stack`, `prove-plus-comm`, `regex-chess`, `sqlite-with-gcov`。

**修复:** 正式41/20/28实验从空池开始,只使用evolve的指令、学生轨迹和二值反馈。禁止上游`curated_acp`初始化、教师阅读其成品或混入上游train25轨迹。成品可用于独立25/64 reference,不能进入我们的正式对照。

### P0:prefix接口没有类别路由,验证和部署方式也不一致

`src/tbench_eval/skills.py:278` 的`instruction-prefix`只接收一个Markdown文档,给本次所有任务加相同内容,不接收“类别→文件”映射。`task-scoped`要求`<root>/<task>/SKILL.md`及有效YAML `name/description`,不能直接把一堆CLAUDE.md当输入。

**修复:** 方法层按固定manifest类别分组,每组调用`run_eval.py --tasks ... --skill-mode instruction-prefix --skill-path <类别文件>`;无经验任务单独以`none`运行。Ralph也用prefix,每次评估对应task/candidate。最后统一汇总原始trial行,不能平均类别pass rate或只保留有经验的题。

prefix位于task instruction,不是system prompt,也不能视为CC自动加载的等价证明。文件读取模式作为独立消融,必须在Ralph和serve两阶段同时采用。删除“先在10题上挑效果最好的方式再定义主口径”;主方式预先固定为prefix,调优仅在开发数据开展。

### P0:原样运行有明确工程阻塞

1. `scripts/patch_harbor.sh:38`启动heredoc,`:71`写成`PYEOF "$CLAUDE_CODE_PY"`,结束符不是独立行。静态编译Python body得到SyntaxError。原生轨道需改为`python3 "$CLAUDE_CODE_PY" << 'PYEOF'`,以独立`PYEOF`结束;还需对固定Harbor版本核对实际安装模板,不能只相信补丁输出“成功”。
2. `run_brew.py:92`忽略完整Write之后的Edit;curator提取器可能把Edit的`new_string`当整份文件。Write→Edit最小夹具已确认brew返回旧版内容。正式实现应取实际最终文件,或用受限写文件工具维护完整状态,不能把该正则提取器作为可信产物来源。
3. vendor任务有**27个未展开的Git LFS指针**。须展开并校验二进制资源,或使用已展开的本地registry cache。缺图片、视频、模型等资源的结果不能当作模型失败。
4. 原生合成任务的顶层`max_agent_timeout_sec/max_test_timeout_sec`在本地已安装Harbor中未设置有效预算。实际解析为agent timeout=None、verifier timeout=600,不是1800/1200。原生轨道须按选定版本使用有效`[agent]/[verifier]`字段。

补丁由我们的方法目录维护,记录上游commit、补丁和锁定依赖,避免就地修改拉取仓库后失去对照依据。

### P1:机制和保真度被过度简化

- **仓库不是失败才brew。** `run_brew.py:141`遍历train全部任务,`:163`决定PASS/FAIL,prompt含成功经验分支。建议主实验失败触发;all-outcome另作明确命名的仓库适配或消融。
- **三件套有下游作用。** Ralph/serve直接只部署CLAUDE.md,但`run_curator.py:87`收集CLAUDE、skill、feedback三类输入用于合并。原稿“不参与任何下游环节”错误;保留三类authoring artifact与curator输入。
- **教师不是单次API调用。** brew/refine使用裸Ubuntu合成任务,没有原任务环境;教师由CC编排,可以多轮调用工具。API authoring改变系统指令、工具、停止条件和预算,应标作适配,不能说无保真损失。
- **教师看到截断message,不是完整轨迹。** brew最后15步×250字符,Ralph最后10步×200字符;独立tool_calls/observation没有完整序列化。默认保留此视图并保存原轨迹;更完整行动/观察视图另列增强变体。
- **恢复不等于因果有效或跨task泛化。** Ralph只能证明该候选在源任务某次运行成功,随机重试也可能自己救回。需要无经验重试对照和test留出结果支持主张。

### P1:恢复、统计与归因方案不成立

原脚本多处删除job目录;本地`run_eval.py`也没有`--resume`。supervisor只能帮助进程脱离会话,不提供逐单元恢复、锁或成本累加。删除“外包supervisor即满足恢复”的表述。

原脚本未提供可配对生成seed。重复3次是independent attempts,不是“同种子配对”;bootstrap seed仅控制统计重采样。删除±3pp复现成功阈值与无测量依据的“数百美元/1–2周”估计。

文本重叠可检查题面相似性,不能直接分解“程序知识/近重复”的因果贡献,也不自动构成泄露。合法使用evolve解法与使用test信息须区分。去题面化、检索改造、schema设计者切换都另列研究变体,不能默认加入baseline。

## 3. 本地资产与接口核实

上游commit:`ed42b147411bde72620a9a61bc956693413b0607`;origin:`ssh://git@ssh.github.com:443/HKUDS/UpSkill.git`。train/test/split与9类别成品ACP均为仓库跟踪文件。

| 项目 | 本轮证据 | 移植决定 |
|---|---|---|
| Harbor | `pyproject.toml`固定claw-harbor `37a234f8de64243e675254d14264c39363692483` | 用现有Python3.12 venv,原生轨道另锁依赖 |
| Claude Code | 安装目录有`agents/installed/claude_code.py`,factory已导入;`AgentConfig.name`支持built-in | 撤回“fork没有CC”;可研究复用,端点/安装/注入仍需干跑 |
| 主学生 | SkillTerminus2,配置默认max_turns=50,实际可覆盖 | 对照同模型/harness/预算/环境 |
| 切分 | evolve41/validation20/test28,seed42 | 锁split hash,与method run保存 |
| manifest | task89,source revision `2fd12b88aafdd04a52c298e3940bcb189f9766d6`,registry commit `69671fbaac6d67a7ef0dfec016cc38a64ef7a77c` | 保存实际任务文件hash,不只记manifest |
| `sources/terminal-bench-2` | 本地仅task.toml的metadata checkout | 不能当可执行任务根;现有接口回退registry |
| `sources/harbor-cache` | 89任务有完整body;instruction/task.toml/Dockerfile/test.sh四项与vendor全部一致 | 优先复用已展开cache,显式绑定路径/版本 |
| 全文件比较 | vendor文件821个与cache一致、28个不同、无缺失;vendor有27个LFS指针,cache无指针 | 四项一致不是全资产逐字一致;正式生成完整清单 |
| 结果 | results.py读逐trial verifier reward,validate_attempts核对覆盖 | 不依赖“最新目录”猜测 |
| helper | rollout_api.py的task.pass是any-of-N | Ralph显式1attempt,正式3attempt不能据此当多数通过 |

**原生CLAUDE.md部署仍需验证:** serve只复制到宿主task根。当前Docker构建context是`environment/`,已检查的安装/执行代码没有自动上传该根目录CLAUDE.md的路径。不能确认CC在容器里看到了经验。干跑须在模型启动前核对容器工作目录、文件bytes/hash与实际加载证据;若增加上传,作为显式部署补丁记录。宿主文件存在不是注入成功证据。

我们的evolve没有system-administration类别,但test有5道该类题:`compile-compcert`, `configure-git-webserver`, `mailman`, `qemu-alpine-ssh`, `sqlite-with-gcov`。默认回退none,保留总分母;不要借用上游成品。Ralph后其他类别也可能无accepted条目,同样回退并报告覆盖率。

## 4. 主轨道:AgentBrew-TB-adapted

### 4.1 数据、预算与对照

- evolve41:初始每题1attempt;失败才教师authoring;Ralph最多3轮,每轮1attempt,首次失败才修订,第3轮失败丢弃。
- validation20:冻结候选池后的开发侧检查;默认1次全体评估、每题3attempt,仅检查覆盖、基础设施错误率和上下文预算,不按成功率挑池。若要效果验收,预先增加同配置无经验对照与明确门槛;不得用validation轨迹写经验。多轮调优另设有限选择预算并记录全部候选/结果。
- test28:学生无经验vs学生+池,同配置各3attempt。各attempt环境重置,不共享结果、反思或记忆;教师无调用权,池只读。教师直接做test可作独立能力参考,其输出隔离于池构建与学生。
- Ralph随机重试诊断:失败源任务做预先固定次数的无经验重试,与有经验验证匹配学生预算。不能挑多次重试里最有利的一次证明笔记有效。

固定初始轨迹选择规则。已有3attempt基线时只用预先指定attempt,或另立“3次失败才触发”变体,不得事后挑轨迹。缺reward、下载/安装/网络等基础设施异常不触发经验总结。预算耗尽按现有scorer规则属于模型失败,保留异常标签。

教师输入只允许开发任务指令、学生轨迹和二值反馈,不允许参考solution、隐藏tests或verifier细节。检查学生agent阶段隐藏tests/solution是否可见,避免把特权信息带入经验。任务资产的本轮静态比较不代表已经验证运行时隔离。

### 4.2 控制流与版本绑定

```
evolve student attempt (none, 1/task)
  ├─ reward=1:不调用teacher (all-outcome变体除外)
  ├─ infrastructure error:审计/按固定重试政策恢复
  └─ reward=0:teacher drafts provisional triple
       → student prefix validation on same task (1attempt/round,最多3rounds)
           ├─ pass:exact candidate triple + hash + trial → accepted
           └─ fail:teacher revise;耗尽则rejected
accepted only → category curator → immutable pool
  → validation assessment → freeze selected hash
  → test student only, category route / none fallback
```

修订保存三件套完整快照。上游Ralph仅提取修订CLAUDE,不能假定sibling skill/feedback已更新或验证。本适配明确三类文件版本关系;学生只验证CLAUDE,skill/feedback是同轮合并辅助输入,不能声称它们单独通过环境验证。

合并为类别文档后不保证效果保持。可额外在evolve重跑合并文档检查漂移,但属于额外预算/增强开关,不得静默添加。validation检查也不允许把失败当新的brew来源。

### 4.3 教师authoring与schema

保留上游brew/refine/curator文本语义,模型名参数化,保留截断视图。API authoring使用结构化输出或受限`write_file`工具,只允许三种相对路径,确定性保存完整最终bytes;拒绝缺字段、空文件、路径越界和不完整输出。不要用“分隔符+正则”作为唯一解析保证。

教师工具预算、输出上限、temperature、重试和停止条件在pilot前固定;保存请求/回复、实际文件版本和usage。端点不支持结构化输出时用受限工具与严格解析,失败须记录,API重试成本计入构建成本。

最小管理schema: `entry_id`, `source_task`, `category`, `student_model`, `teacher_model`, `prompt_version`, `source_trial_id`, `candidate_version`, `artifact_hashes`, `validation_trial_id`, `reward`, `status`, `usage`, `created_at`。这是研究者固定的管理schema;正文沿用上游三件套,不要把“big/small设计schema”研究变量混进baseline。

### 4.4 类别路由与封装

用manifest的固定`task→category`,声明是外部类别元数据,不声称实现论文一般top-k检索/重排序。自由检索或学生自选经验另作变体。

类别分组调用单文档prefix即可,无需为主轨道重写评测器。每个组/Ralph单元指定独立`--out`/`--jobs-dir`,防止同规模任务组run ID相同造成覆盖。`--tasks`会使现有接口split provenance为None;wrapper须核对集合是相应split子集并保存父split hash。

聚合后再核对:任务集合准确、每题3attempt、trial唯一、无跨组重复/遗漏、reward合法、注入hash与冻结池一致。不要用目录排序暗示共享随机种子。

### 4.5 恢复、锁与成本

方法runner提供`--resume`;每完成source rollout、teacher authoring、Ralph round或curator category即原子落盘。单元签名包含任务资产、模型、prompt、预算、注入内容和split hash。只有签名一致且证据完整的completed单元可复用;中断单元单列,不覆盖旧trial。

run目录取排他锁,保存状态表和child PID,禁止删除已有输出来“重跑”。usage按请求ID落盘累加,resume后不清零;不确定的中断请求另报。supervisor使用`start_new_session=True`或`os.setsid()`,追踪自己的child,从新shell确认,不用`pgrep -f`。遵守本仓库AGENTS.md全部长任务检查和完结审计要求。

成本区分初始学生尝试、教师draft/refine/curate、Ralph、无经验重试诊断、validation和test。缺usage记unknown而非0。本地vLLM报告token/时长/资源口径,不套用原API单价。

### 4.6 预先固定指标与泛化分析

正式主指标`avg@3`=28题共84attempt中的reward1比例;缺reward按现有conservative口径计失败,infra率与条件evaluated accuracy另报。`pass@3`和`pass_2of3`为次指标,不得看结果后切换。若改1attempt协议,须运行前另注册,不能混报avg@3。

task为配对单位,计算每题平均reward差、task bootstrap置信区间和救回/回归;attempt index仅为记录对应,不保证共同随机性。更正:本地paired_comparison的GAIN/LOSS按any-of-N成功定义,不是此前所写的多数通过;该统计与每题平均reward差分别标明。test28较小,1task占3.57pp的task通过率,单次小增益不能支撑“稳定超过教师”。

空池→evolve构建→冻结→未见test评估是跨task泛化的基本证据。文本近重复只是诊断,不作因果分解。更强证据可另设任务族留出、参数化经验消融、同类别/格式/长度匹配无关经验;规则预先固定,不能按test结果改池。审计test题面不得把内容回流给教师或开发prompt。

## 5. 实施位置

建议新增,当前尚未创建:

```
benchmark/terminalbench-eval/src/tbench_eval/agentbrew/
  prompts.py      # 参数化上游文本/视图版本
  trajectory.py   # 规范轨迹/截断视图/逐trial反馈
  authoring.py    # teacher接口/三件套完整输出
  pipeline.py     # failure trigger/Ralph/accepted/curator/freeze
  state.py        # 单元签名/checkpoint/锁/usage
  serving.py      # 类别分组/none回退/统一汇总
benchmark/terminalbench-eval/scripts/run_agentbrew.py
benchmark/terminalbench-eval/configs/agentbrew_tb2.yaml
```

可借用已有teacher client、usage和状态工具,但先核对真实行为,不要假定wrapper天然支持恢复。评测仍用run_eval.py/results.py/scorer.py。原生轨道可复用fork中的CC,但prefix kwargs未必被CC消费,须明确上传/加载适配,不能只换agent.name。

## 6. 执行顺序与启动门槛

**先完成主适配的低成本检查,原生完整实验不是前置条件。**

1. 静态契约:锁任务/split/依赖,校验assets/LFS,检查schema解析、accepted过滤、失败触发、类别回退、版本hash和覆盖。人工PASS/FAIL/infra夹具验证状态机,Write→Edit验证最终文件,中断/恢复夹具验证无重复、锁和usage累加。
2. 1–2个evolve任务真实全链路:student→teacher→Ralph→curator→prefix serve,包含修订失败路径。保存实际前缀请求/reward/完整证据;自然pilot未出现的状态另用mock覆盖。smoke serve也用evolve,不提前打开正式test反馈。
3. 独立复核:同一原始trial只换分析/展示prompt时reward/action证据hash保持不变;验证candidate与accepted hash相同;未通过版本不进入curator。核对no-skill确实无经验,prefix未截断,对照预算一致。
4. 冻结配置、主指标、对照、infra重试和validation选择规则;先evolve构建并审计,再冻结池和validation,通过预注册门槛后test。每阶段查完备性,异常run不进入结论。

启动前发真实模型请求确认内容返回,检查sandbox执行、网络和资源。Linux/GPU服务器不自动具备Docker/KVM权限,E2B与Docker也非等价配置。QEMU按实际任务需求核对,不能笼统声称“macOS必失败/Linux必成功”。

预算先由pilot测量。失败源任务数F≤41,Ralph轮数R≤3,有效类别数C:主轨道学生构建rollout上界41+RF,教师authoring单元上界RF+C(工具多轮时请求数更多)。默认validation为60rollouts,若加效果验收对照再加60;test两学生臂168rollouts。无经验重试、infra重试和教师reference另加。墙钟按实测任务时长/并发/吞吐估计,不由论文单题serve价推出brew总价。

## 7. 可选原生reference轨道

独立依赖锁和补丁副本,原25/64与原教师/学生,从1–2题检查开始。先修安装补丁、LFS、task schema预算、文件提取和容器CLAUDE加载;区分执行修复与方法改变。原成品池可做serve接口检查,不能据此证明brew/Ralph已复现。

保留curator→Ralph旧顺序则标repo-faithful reference,明确验证没有控制最终池;改accepted准入顺序则标repaired variant。二者不能都称“不改方法原样复现”。

论文reference:学生29/64、教师32/64、学生+经验33/64(45.3/50.0/51.6%),一次brew约$116。记录实际模型/CC/Harbor版本和逐题reward,重复评测时所有比较臂采用相同attempt数。数值偏差与不确定性据实报告,不以±3pp认证复现。

## 8. 本轮已完成与未验证

已完成:逐阶段源码复核、本地agent/接口复核、split交叉计算、89任务关键文件和全部vendor文件对比、LFS检查、补丁Python语法检查、Write→Edit最小检查、合成task配置实际解析。

未完成:端点真实生成、Docker/E2B执行、容器CC自动加载、实际模型轨迹全链路、Ralph恢复/冻结部署、论文数值复现。这些由后续实现与pilot验证,不把静态审核写成运行成功。

本方案不修改其他历史审计/结果报告。AgentBrew仍适合作为baseline候选;其主要价值是学生感知的教师经验与Ralph恢复过滤,不能据未运行的方案声称跨任务增益已经存在。
