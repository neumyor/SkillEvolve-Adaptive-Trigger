# 第 4.2 节批次 2 核验：SkillAdaptor、SkillCAT、Trace2Skill、SkillPyramid、SkillX

范围：仅对照 `papers/` 下五篇原始 PDF，核对主综述 `skill_evolve_survey.md` 第 4.2 节表格的 evolve setting、source 经验范围、target 测试范围、G0–G8 标注和可支持结论。逐列指出“正确 / 错误 / 过强 / 缺证据”，并给出建议替换文本。未修改主综述。

## SkillAdaptor

PDF：`papers/skilladaptor_self_adapting_skills_for_llm_agents_from_trajectories.pdf`（15 页）

PDF 证据要点：
- p.1–2：框架为已有 skill collection 上的 failure attribution + targeted update，backbone 冻结；初始化时先从成功轨迹蒸馏出初始 collection K0，之后用失败轨迹触发 Attribution/Modification/Qualification。
- p.3：Linker 在 REVISE 与 GENERATE 之间路由；Modifier 更新最相关 skill 或新增 skill。
- p.3–4：评测为 WebShop、PinchBench、Claw-Eval 三个 benchmark 的任务分数；最多 10 轮 adaptation，collection 不变 3 轮早停（p.9）。
- p.9：WebShop 使用官方 Gym 环境和 1,624 训练 / 200 测试 split；PinchBench 与 Claw-Eval 使用基准自带的 OpenClaw runtime 与任务配置。
- p.5–6：结论限定在“step-level attribution 支持训练自由的 skill maintenance”；Limitations 明确指出缺乏更长部署期与更广分布偏移评测。

### 主综述逐列核对

| 列 | 当前表述 | 核验结论 | 证据 | 建议 |
|---|---|---|---|---|
| evolve setting | “已有 SC 内的局部 fault attribution 和 repair” | **基本正确但需补全**。还应包含新增 skill 生成（GENERATE 路径）和 qualification gate；它不只是 repair。 | p.2–3 | 建议改为：“已有 SC 内的 step-level fault attribution、局部 revise/generate 与 qualification gate” |
| source 经验范围 | “failed trajectory、故障步骤、候选 skill responsibility” | **部分正确但缺初始化与成功轨迹**。初始 collection 由成功轨迹蒸馏得到；后续更新才主要由失败轨迹驱动。 | p.2 | 建议改为：“成功轨迹蒸馏的初始 skill collection；后续失败轨迹、first actionable fault step、候选 skill responsibility” |
| target 测试范围 | “WebShop、PinchBench、Claw-Eval 中的后续任务” | **“后续任务”易误导**。论文报告的是三个 benchmark 上的测试任务分数与多轮 adaptation 曲线，没有定义严格的 chronological future-task test split。 | p.3–4, 9 | 建议改为：“同三个 benchmark 的测试任务：WebShop 200 题 test，PinchBench/Claw-Eval 官方任务；另有多轮 adaptation 后的 headline 分数” |
| 明确泛化 setting | “G0/G8；不是从零 acquisition” | **G0 合理；G8 过强**。多轮更新不等于 G8 要求的 chronological stream、retention、遗忘或非平稳分布协议；“不是从零 acquisition”与初始化逻辑不完全一致（初始库确实从成功轨迹从零蒸馏，之后才是维护）。 | p.2–4, 9 | 建议改为：“G0（同 benchmark 失败轨迹→局部修复）；迭代 maintenance 候选，但缺少严格 G8 协议；初始库构建仍是 acquisition” |
| 可支持结论 | “能否维护现有 skill；不能与从空 skill 开始的方法直接等价” | **方向正确但需收窄并修正一处**。可支持的是固定 benchmark/工具条件下的局部归因修复与合格性过滤；不能证明跨环境或跨 harness 维护。“不能与从空 skill 开始的方法直接等价”应改为更精确的“演化阶段与协议不同，不应直接同表排名”。 | p.2–6, 9 | 建议改为：“固定 benchmark 与工具条件下，step-level attribution 能改善失败修复并控制回归；结果不证明跨环境 portability，也不应与从空 collection 开始的 acquisition 方法直接排名” |

## SkillCAT

PDF：`papers/skillcat_contrastive_assessment_and_topology_aware_skill_self_evolution_for_llm_agents.pdf`（9 页）

PDF 证据要点：
- p.1–2：三阶段 CCE（多 seed 对比提取）、AAE（source-task replay 过滤后分层合并）、TTE（topology routing）。
- p.4：主 benchmark 为 SpreadsheetBench-Verified，沿 Trace2Skill 将 400 例切成 200 evolution + 200 held-out；AAE 在 source-task clones 上 replay。
- p.5：200 held-out SpreadsheetBench-Verified、full SpreadsheetBench Soft/Hard、WikiTableQuestions OOD；另用 DocVQA validation 前 2,700 题做 evolution，剩余 2,649 题评测。
- p.5–6：cross-model 复用 Deepening skills，gemma-4-31B-it 与 gpt-5.4-mini 作为 user。

### 主综述逐列核对

| 列 | 当前表述 | 核验结论 | 证据 | 建议 |
|---|---|---|---|---|
| evolve setting | “多 trajectory patch extraction + assessment + topology routing” | **正确**。可再补充三阶段名 CCE/AAE/TTE 与 source-task replay 语义。 | p.1–4 | 建议改为：“CCE 多 seed 对比提取 + AAE source-task replay 过滤/分层合并 + TTE topology routing” |
| source 经验范围 | “SpreadsheetBench-Verified evolution split；成功/失败多 seed” | **正确但缺数量与跨 benchmark 细节**。SpreadsheetBench-Verified 为 200 evolution；DocVQA 前 2,700 题也用于 evolution。 | p.4–5 | 建议改为：“SpreadsheetBench-Verified 200 evolution；每任务 5 seed 成功/失败对比；DocVQA 另用前 2,700 题做独立 evolution” |
| target 测试范围 | “200 held-out；WikiTableQuestions OOD；DocVQA/cross-model” | **基本正确但混叠多个 cell**。应区分 SpreadsheetBench held-out、full SpreadsheetBench Soft/Hard、WikiTQ OOD、DocVQA 独立 split、cross-model reuse。 | p.5–6 | 建议改为：“SpreadsheetBench-Verified 200 held-out 与 full SpreadsheetBench；WikiTableQuestions OOD；DocVQA 2,649 held-out；另用同一 evolved skill 在 gemma-4/gpt-5.4-mini 上测试” |
| 明确泛化 setting | “G1/G2；G3；G4” | **G1/G2、G3 合理；G4 需限定**。SpreadsheetBench→WikiTQ 可按综述 4.3 规范化为表格功能相邻的 G4，但 DocVQA 与 SpreadsheetBench 更像独立多模态 cell，直接写 G4 过强。 | p.4–6 | 建议改为：“G1/G2；SpreadsheetBench→WikiTQ 按相邻表格功能可标 G4（survey-level 规范化）；DocVQA 为独立多模态 cell，不宜直接并入 G4” |
| 可支持结论 | “同 spreadsheet workflow、表格问答相邻迁移；需拆 extraction/assessment/routing” | **前半过强，后半正确**。WikiTQ 是 converted-into-spreadsheet-format 的相邻迁移；DocVQA 增益是另一评测域的结果，不宜与 WikiTQ 合并成单一迁移结论。 | p.4–6 | 建议改为：“支持同 workflow held-out 增益与转换格式后的表格问答相邻迁移；DocVQA 与 cross-model 为独立复用/评测 cell，需分别解释” |

## Trace2Skill

PDF：`papers/trace2skill_distill_trajectory_local_lessons_into_transferable_agent_skills.pdf`（25 页）

PDF 证据要点：
- p.3：S0 + D_evolve → S*，fixed LLM，不更新模型；两模式 Skill Deepening（human-written seed）与 Skill Creation（parametric seed）。
- p.4：SpreadsheetBench-Verified 400 例切成 200 evolution + 200 held-out；另报 full SpreadsheetBench Soft/Hard（排除 evolving set）；WikiTableQuestions 与 HiTab 转成 spreadsheet 格式作 OOD。
- p.5：Gemma-4-31B-it / GPT-5.5-high 作为 user 或 author 的 cross-family 实验。
- p.5–6：Math 为独立域：400 DAPO evolution、100 held-out DAPO、AIME 2026 30 题 avg@8。DocVQA：50 例 evolution、5,299 held-out。
- p.9 与 p.18–19：三个独立 document cell：VRDU→VAREX、TSBench deck-disjoint OOD、generated DOCX→OfficeBench DOCX holdout；p.18 明确“source traces only for evolution, held-out targets only for evaluation”。

### 主综述逐列核对

| 列 | 当前表述 | 核验结论 | 证据 | 建议 |
|---|---|---|---|---|
| evolve setting | “pooled trajectories→many-to-one consolidated directory” | **正确**。可补“fixed agent、static directory、无 retrieval”的要点。 | p.3, 9 | 建议改为：“fixed agent 上，pooled trajectories → parallel patch proposal → many-to-one consolidated static directory” |
| source 经验范围 | “200 Spreadsheet evolution samples；另有 DAPO、VRDU、TSBench、generated DOCX source traces” | **正确但遗漏 DocVQA 50 例与 seed/eval 细节**；各 source pool 是独立 cell，不是同一个 pooled distribution。 | p.4–6, 18 | 建议改为：“SpreadsheetBench 200 evolution；Math 400 DAPO；DocVQA 50；PDF/PPTX/DOCX 分别用 VRDU、TSBench、generated DOCX；各为独立 evolution cell” |
| target 测试范围 | “Spreadsheet held-out、WikiTableQuestions/HiTab、AIME、DocVQA、VAREX、deck-disjoint TSBench、OfficeBench” | **基本正确但需强调“逐个独立 cell”**，且应加入 held-out DAPO、AIME 30 题、OfficeBench 64 个 DOCX 子任务等具体范围。 | p.4–6, 18–19 | 建议改为：“各 cell 分别测试：Spreadsheet 200 held-out + full Soft/Hard；WikiTQ/HiTab 转换格式；100 held-out DAPO 与 AIME 2026；DocVQA 5,299 held-out；VAREX Flat；deck-disjoint TSBench；OfficeBench 64 DOCX 子任务” |
| 明确泛化 setting | “G1/G2；G3；G4” | **遗漏 G7**。论文有明确 cross-family trace induction 与 cross-model user 实验；这是 model portability 维度，不应只写任务泛化层级。 | p.5–6, 15 | 建议改为：“G1/G2；G3（DAPO→AIME、VRDU→VAREX、TSBench deck-disjoint）；G4（Spreadsheet→WikiTQ/HiTab、generated DOCX→OfficeBench 等，按相邻功能规范化）；另有 G7 cross-family author/user 证据” |
| 可支持结论 | “当前较完整的同功能跨数据集和相邻文档/表格迁移证据；仍非 unrestricted G5” | **正确但建议补一条边界**：appendix 记录了 patch interaction 与 off-source regression 风险，结论不宜写成无条件稳健迁移。 | p.9, 16 | 建议改为：“多个独立 source→target cell 提供当前最完整的同功能/相邻任务迁移证据；需逐 cell 报告，注意 patch interaction 与 off-source regression；不构成 unrestricted G5” |

## SkillPyramid

PDF：`papers/skillpyramid_a_hierarchical_skill_consolidation_framework_for_self_evolving_agents.pdf`（16 页）

PDF 证据要点：
- p.1：层级 consolidation + self-evolution，任务中组合、验证并纳入新 skill。
- p.5–6：ALFWorld、WebShop、ScienceWorld 三个 benchmark；ALFWorld/ScienceWorld 报 seen/unseen，WebShop 为 seen 单 split。
- p.6：ALFWorld eval_in_distribution=140 seen、eval_out_of_distribution=134 unseen；ScienceWorld dev=194 seen、test=211 unseen（p.10）。
- p.8：GAIA-Lite 75 题为另一个 web-mined skill 评测 cell（从 150K 候选保留 2,271 个 web skills）。
- p.7：self-evolution 消融比较 static、append-only、from-scratch，说明 incremental incorporation 有助于后期稳定。

### 主综述逐列核对

| 列 | 当前表述 | 核验结论 | 证据 | 建议 |
|---|---|---|---|---|
| evolve setting | “SC consolidation、atomic extraction、hierarchy/topology” | **正确但缺 self-evolution 一半**。论文还有任务中 incremental incorporation / new-skill composition。 | p.1, 5, 7 | 建议改为：“SC consolidation、atomic/abstract induction、hierarchy topology + incremental self-evolution” |
| source 经验范围 | “训练 split trajectories” | **过泛**。benchmark 内是各自独立协议；GAIA-Lite 另来自 web-mined skills，与 benchmark 训练轨迹不是同一 source pool。 | p.5, 8, 10–11 | 建议改为：“ALFWorld/ScienceWorld/WebShop 各自训练或初始化 split；GAIA-Lite 为 2,271 个 web-mined skills 的独立来源” |
| target 测试范围 | “ALFWorld/ScienceWorld seen→unseen；WebShop；GAIA-Lite” | **基本正确但应写清数字与独立性**。seen/unseen 是环境内 split，不是跨数据集 transfer；GAIA-Lite 是独立评测。 | p.6, 8, 10 | 建议改为：“ALFWorld 140 seen/134 unseen；ScienceWorld 194 seen/211 unseen；WebShop 200 固定任务；GAIA-Lite 75 独立评测” |
| 明确泛化 setting | “G1/G2；同环境内 G3 的弱形式” | **G3 弱形式不成立**。seen→unseen 属于同环境 G1/G2；多 benchmark 并列与 GAIA-Lite 不能自动升级为 G3。 | p.5–8 | 建议改为：“ALFWorld/ScienceWorld 内 G1/G2；GAIA-Lite 为独立 web-mined 评测 cell，不作为 G3 证据” |
| 可支持结论 | “collection organization 与 environment-internal transfer；多 benchmark 并列不等于跨环境” | **方向正确，建议更精确**。支持的是层级组织带来的环境内 held-out 复用与效率提升，以及 web-mined skills 的组织收益；不证明同一 collection 的跨环境/跨 harness 迁移。 | p.5–8 | 建议改为：“支持环境内 seen→unseen 复用与步骤效率提升，以及 web-mined skills 的层级组织收益；不证明跨环境或跨 harness 的 collection 迁移” |

## SkillX

PDF：`papers/skillx_automatically_constructing_skill_knowledge_bases_for_agents.pdf`（24 页）

PDF 证据要点：
- p.3–4：三层结构 planning/functional/atomic skills；从 seed training rollout 提炼、refinement，最多 3 轮。
- p.5：BFCL-v3 base multi-turn 50 train/150 test；AppWorld 90 train、TestNormal test；τ²-Bench 各子域自带 train/test split。
- p.6：主表三 benchmark 分列：BFCL-v3 Avg@4/Pass@4、AppWorld Avg@4/Pass@4、τ²-Bench Retail/Airline/Telecom Pass@1。
- p.6–7：GLM-4.6 抽取经验可迁移到较弱模型（distillation），强模型自身增益有限；skillexpansion 提升较弱的 Qwen3-32B/K2。
- p.15：AppWorld 有 train/test distribution gap，说明其测试分布不同于训练。

### 主综述逐列核对

| 列 | 当前表述 | 核验结论 | 证据 | 建议 |
|---|---|---|---|---|
| evolve setting | “三层 SC/KB construction、retrieval、composition” | **正确但缺 refinement/expansion**。论文还有最多 3 轮 refinement 和 experience-guided exploration 的 skill expansion。 | p.3–5 | 建议改为：“三层 planning/functional/atomic SC/KB construction + refinement + experience-guided expansion，运行时 retrieval/composition” |
| source 经验范围 | “generated experience 和 benchmark training data” | **正确但可更具体**。每个 benchmark 有各自 seed training set；BFCL 50、AppWorld 90、τ²-Bench 按子域 train split；GLM-4.6 每训练任务 rollout 4 次。 | p.5, 16 | 建议改为：“各 benchmark 独立 seed training set（BFCL 50、AppWorld 90、τ²-Bench 子域 train split）上的 rollout/generated experience；GLM-4.6 也可作为 extractor” |
| target 测试范围 | “AppWorld、BFCL-v3、τ²-Bench test” | **正确但应区分指标与子域**。BFCL 150 test、AppWorld TestNormal、τ²-Bench Retail/Airline/Telecom；指标分别是 Avg@4/Pass@4 与 Pass@1。 | p.5–6, 15 | 建议改为：“BFCL-v3 150 test、AppWorld TestNormal、τ²-Bench Retail/Airline/Telecom test，分别报 Avg@4/Pass@4 或 Pass@1” |
| 明确泛化 setting | “G1/G2；G6（tool schema/environment）” | **G6 需降级为“弱 G6”**。论文是三个工具型 benchmark 各自 train→test，未证明同一固定 KB 在仅改变 tool schema/environment 的严格协议下跨 benchmark 迁移；另有经验 extractor 与 user 模型不同的 distillation 结果，可视作部分 G7 迹象，但主协议不是固定 artifact 的 model portability 测试。 | p.5–7, 15–16 | 建议改为：“G1/G2；跨 schema 可视为弱 G6/多环境覆盖证据，而非严格固定 collection 的 schema-shift portability；GLM-4.6→弱模型结果可另标为经验 distillation，不宜写成完整 G7” |
| 可支持结论 | “collection 在多工具环境中的覆盖和复用；不同 benchmark 不能 pooled 成单一 G5” | **正确，建议补两层边界**：(1) 收益来自 procedural knowledge 与 tool/environment-specific skills 的混合；(2) 三 benchmark 的指标与交互形式不同，不能汇总成单一泛化分数。 | p.3–7, 15 | 建议改为：“支持三层 KB 在多个工具型环境中的检索/组合收益，尤其对较弱模型；需按 benchmark 分开解释，且不把 tool-specific knowledge 与通用 workflow 复用合并成 G5” |

## 需要修正的主综述表格文本（建议替换）

| 论文 | 建议替换的“明确的泛化 setting” | 建议替换的“可支持的结论” |
|---|---|---|
| SkillAdaptor | G0；固定 benchmark 迭代 maintenance，缺严格 G8 协议 | 在固定 benchmark 与工具条件下，step-level attribution 改善失败修复并控制回归；不证明跨环境维护，不应与从空 collection 开始的 acquisition 方法直接排名 |
| SkillCAT | G1/G2；SpreadsheetBench→WikiTQ 按相邻表格功能可标 G4（survey-level 规范化）；DocVQA 为独立多模态 cell | 支持 held-out 增益、转换格式后的表格问答相邻迁移、以及独立 DocVQA/cross-model 复用；各 cell 需分开解释 |
| Trace2Skill | G1/G2；G3（DAPO→AIME、VRDU→VAREX、TSBench deck-disjoint）；G4（Spreadsheet→WikiTQ/HiTab、generated DOCX→OfficeBench）；另有 G7 cross-family author/user | 多个独立 source→target cell 提供当前较完整的同功能/相邻任务迁移证据；逐 cell 报告，注意 patch interaction 与 off-source regression；非 unrestricted G5 |
| SkillPyramid | ALFWorld/ScienceWorld 内 G1/G2；GAIA-Lite 为独立 web-mined 评测 cell，不作 G3 证据 | 支持环境内 seen→unseen 复用与效率提升，以及 web-mined skills 的层级组织收益；不证明跨环境/跨 harness collection 迁移 |
| SkillX | G1/G2；跨 schema 可视为弱 G6/多环境覆盖，而非严格固定 collection 的 schema-shift portability；另有经验 distillation 迹象，不宜写成完整 G7 | 三层 KB 在多个工具型环境中有检索/组合收益，尤其对较弱模型；按 benchmark 分开解释，不合并成 G5 |

## 关键页码证据索引

- SkillAdaptor：p.1–2（框架与初始化）、p.3–4（评测与结果）、p.5–6（结论/limitations）、p.9（benchmark setup、10 轮/早停）。
- SkillCAT：p.1–2（三阶段）、p.4（400→200/200 split、source-task replay）、p.5–6（WikiTQ/DocVQA/cross-model 协议）。
- Trace2Skill：p.3（formalization）、p.4（Spreadsheet split 与 OOD 转换）、p.5–6（math/DocVQA/cross-family）、p.9（broader application 概览）、p.18–19（VRDU/VAREX、TSBench、OfficeBench setup 与表格）。
- SkillPyramid：p.1（概览）、p.5–6（benchmark/seen-unseen 结果）、p.7（self-evolution 消融）、p.8（GAIA-Lite）、p.10–11（split 与 WebShop 细节）。
- SkillX：p.3–4（三层设计与提炼）、p.5–6（benchmark split 与主表）、p.7（模型迁移分析）、p.15（AppWorld 分布差与指标）。
