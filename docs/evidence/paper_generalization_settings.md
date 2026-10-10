# 22 篇 Skill Evolve 论文的实验泛化 Setting 汇总

本文件只回答一个问题：每篇论文在实验中“**从什么经验/对象进化，测试到什么目标**”，以及该实验 cell 在 Survey 规范下属于哪个泛化等级。

## 统计口径

- 以一篇论文中至少一个由原始 PDF 支持的实验 cell 为单位记录；同一论文可以覆盖多个等级，因此各等级计数会重叠。
- `G1/G2` 在多数论文中只报告 benchmark 内 train/validation/test 或 seen/unseen，而没有足够信息稳定地区分“同模板新实例”和“未见任务族”。故以下将其合并为 `G1/G2`，不分别制造 G1、G2 的伪精确计数。
- `G6` 是 environment/tool schema/harness 改变，`G7` 是 model/model-family 改变；两者都不是任务功能泛化。
- `弱 G6`、`G8 机制候选`、多 benchmark breadth 和独立 evaluation cells 不计入严格等级统计。
- `EV`（evaluator）是评测器有效性，不属于任务 artifact 的 G0-G8 几何。

## 逐篇实验 Setting

| 论文 | evolve 的对象与 source 经验 | target 测试 | 已支持的泛化等级 | 边界说明 |
|---|---|---|---|---|
| SkillGen | 单个外部 SU；各 benchmark 的 base-agent 成功/失败轨迹，经 induction 与 construction-time verification 后 refine | 同一实例的 with/without-skill paired replay；各 benchmark held-out；ALFWorld `valid_seen`/`valid_unseen`；跨模型执行 | G0；G1/G2；G7 | paired replay 是 G0；ALFWorld OOD 是同环境未见 task type；无 G6，且 accepted skill 仍可能在 held-out 回归 |
| SkillAdaptor | 初始 SC 由成功轨迹蒸馏；后续以失败轨迹、fault step 与责任 skill 做 revise/generate | WebShop、PinchBench、Claw-Eval 的同 benchmark test tasks，多轮 adaptation | G0 | 多轮更新不等于 G8：没有时间流、old-task retention 或非平稳协议 |
| SkillOpt | frozen model 上的单一外部 skill document；`D_train` rollout 用于重写，`D_selection` 用于接受候选 | benchmark held-out；OlympiadBench→Omni-MATH；Codex↔Claude Code；GPT-5.4→mini/nano | G1/G2；G3；G6；G7 | G3 只由 nearby math cell 支持；model、harness 与任务迁移应分开报告 |
| EvoSkill | failure-driven SU folder；OfficeQA/SealQA 分别用 train split、ground-truth answer diagnosis 和 validation frontier 演化 | 各自 held-out test；SealQA 中的 search-persistence skill 零改动部署到 BrowseComp 128 题 | G1/G2；G3 | SealQA→BrowseComp 是同 search/fact-seeking 功能簇的单 skill transfer，不是整个 library 的 G5 |
| MetaSkill-Evolve | task skill fast loop 与 branch-local meta-skill slow loop；每个 benchmark 内 train failures、validation scores、frontier/history | OfficeQA、SealQA、ALFWorld 的独立 held-out cells | G1/G2 | 三个 benchmark 是分别 evolve、分别测试的 breadth；没有同一 task/meta skill 跨功能迁移 |
| CoEvoSkills | multi-file skill package 与 surrogate verifier 共演化；task instruction、observable inputs、background docs、rollouts、surrogate diagnostics 和 opaque oracle pass/fail | SkillsBench 85 task evaluation；Opus-evolved package 到 6 个 model/harness 组合 | G6/G7（混合） | PDF 未充分说明 SkillsBench 是否为原生 held-out split；跨模型时往往同时改变 harness，不能拆成纯 G6 或纯 G7 |
| SkillCAT | SC；SpreadsheetBench-Verified 多 seed success/failure patches，经 replay assessment、hierarchy merge 和 topology routing；DocVQA 有独立 source split | SpreadsheetBench held-out/full；SpreadsheetBench→WikiTableQuestions；DocVQA held-out；跨模型复用 | G1/G2；G4；G7 | Spreadsheet→WikiTQ 是表格操作→表格问答的相邻功能 G4；DocVQA 是独立 cell，不是该 G4 transfer |
| Trace2Skill | fixed agent 的多轨迹 patch consolidation；Spreadsheet、DAPO、DocVQA、VRDU、TSBench、generated DOCX 均为独立 source cells | 同 benchmark held-out；DAPO→AIME；VRDU→VAREX；deck-disjoint TSBench；Spreadsheet→WikiTQ/HiTab；generated DOCX→OfficeBench；cross-family author/user | G1/G2；G3；G4；G7 | 当前最完整的多 cell transfer 证据；仍须逐 cell 处理 patch interaction 与 off-source regression |
| SkillPyramid | hierarchical SC consolidation、atomic/abstract induction 与 incremental self-evolution；环境内初始化/训练数据，GAIA-Lite 用 web-mined skills | ALFWorld seen/unseen、ScienceWorld seen/unseen、WebShop；GAIA-Lite 独立 cell | G1/G2 | seen→unseen 不是 G3；GAIA-Lite 也不是同一 collection 的跨环境 transfer |
| SkillX | planning/functional/atomic KB；各 benchmark 的 seed train rollout、refinement 和 expansion | BFCL-v3、AppWorld、τ²-Bench 各自 test split | G1/G2 | 三个工具 benchmark 是多环境覆盖；只有弱 G6 候选，未证明固定 KB 在仅改变 schema/environment 后迁移 |
| WikiSkill | 每 benchmark 从空集开始：immutable traces→persistent wiki→skill proposal→validation gating；skill 可 rollback、wiki 持续 | 每个 benchmark 的 unseen test；cross-model skill transfer | G1/G2；G7 | 五个 benchmark 是独立 cells；persistent wiki/rollback 是 G8 机制候选，未测 chronological retention，不能计为严格 G8 |
| SKILLRL | SC 与 policy/parameter co-evolution；ALFWorld、WebShop、search QA 分开训练，search QA source 为 NQ+HotpotQA | ALFWorld task types、WebShop；NQ/HotpotQA→TriviaQA、PopQA、2Wiki、MuSiQue、Bamboogle | G1/G2；G3 | G3 是 search QA 同功能跨数据集；policy 同时更新，不能与 frozen external-skill 方法直接排名 |
| SKILL0 | policy/parameter internalization；SkillBank 来自 SkillRL，训练中按 helpfulness 筛选并逐步撤除外部 skill context | ALFWorld、WebShop；NQ/HotpotQA in-domain 与其他 search-QA OOD datasets | G1/G2；G3 | 主要对象是更新后的参数与 context withdrawal；不支持 external artifact 的 G6/G7 portability |
| SkillEvolver | 单任务按需 SU authoring；每个新 task 的 bounded exploration trials、contrastive patch 与 Auditor | SkillsBench 的 task-level validation；KernelBench 3 task speedup 独立 cell | G1/G2 | SkillsBench 多 domain 是 per-task authoring breadth；KernelBench 指标和规模不同，不能合并 |
| SkillEvo | 生产 SC/graph；按时间排序的 escalated tickets，经 multi-turn simulation、attribution、bounded update 和 governance 演化 | 同 scenario/skill 的 chronological future tickets；TSR、RegR、bloat 等维护 probes | G8 | 这是明确时间外推 protocol；但数据集为生产客服领域，不能直接外推为公共 benchmark 结论 |
| SkillHone | SU/SC continual refinement；WebShaper development items、persistent decision history 与 search decisions | GAIA text-only、WebWalkerQA-EN；raw open-web/curated search 条件；Qwen3.6→Claude Sonnet | G8；G7 | raw/curated search 是不同 evaluation conditions，不是严格 G6；两个公共 benchmark 属于 search/research QA，而非 G5 |
| SKILL-KD | teacher-student execution traces（来自不同模型家族与 tokenizer）蒸馏可行动作技能规则，含 pairwise 与 batch 对比 | 各 benchmark 独立 cell（DocVQA / SpreadsheetBench / LiveMath / ALFWorld / LiveCodeBench / AIME），每 benchmark 拥有 own source→target split | G1/G2；G4；G6 | 无跨 collection transfer；drift-aware rule assembly 保持正确但无法证明同一 collection 的跨 task 功能迁移 |
| SkillWeaver | website-specific executable API collection；每个网站分别探索、practice 与 hone | WebArena 5 sites；4 个 live websites/57 tasks；GPT-4o→GPT-4o-mini | G1/G2；G7 | 不同网站均使用各自 pre-hoc API library，未证明 source-site API library 向 unseen website 转移；无 G3/G6 |
| GEPA | compound-system module prompts；每 benchmark 的 train examples、textual feedback 和 Pareto validation，模型权重冻结 | HotpotQA、IFBench、HoVer、PUPA、AIME-2025、LiveBench-Math 各自 held-out；Qwen3-8B optimized prompt→GPT-4.1 Mini | G1/G2；G7 | 是 prompt evolution，不是 SU/SC acquisition；六 benchmark 是独立 cells，不是 G5 |
| SkillReducer | 已有 skill 的 post-authoring compression；55,315 corpus 用于分析，600 skills 用于 end-to-end compression，198 wild skills 用于 compression-only check | generated-task retention、SkillsBench；30-skill cross-model 与 OpenCode framework cells | G6；G7 | 测的是压缩后 functional retention，不是 skill discovery 或任务功能迁移；portability cell 规模有限 |
| SkVM | skill-as-code 的 compiler/runtime adaptation；输入为现有 skill code 与 target model/harness profile | SkillsBench/PinchBench 118 tasks，8 models、3 harnesses | G6；G7 | compiler 为目标 model/harness 生成适配版本；不是 raw artifact 不变地直接迁移，也不是语义 G3-G5 |
| Who Grades the Grader? | evaluator/metric 及其 skill loop；unlabeled train outputs、10 anchored dev items、detector consensus | MBPP+、Spider 2.0-Snow、report generation locked tests；report task 由 independent judge audit | EV（不计入 G0-G8） | 测 evaluator held-out validity、anchor generalization 与 Goodhart resistance，不是 task artifact transfer |

## 全局分布

### 严格、已支持的论文级覆盖数

| 泛化等级 | 论文数 | 占 22 篇比例 | 覆盖论文 |
|---|---:|---:|---|
| G0 同实例修复/paired intervention | 2 | 9.5% | SkillGen、SkillAdaptor |
| G1/G2 同功能 benchmark 内 held-out | 14 | 63.6% | SkillGen、SkillOpt、EvoSkill、MetaSkill-Evolve、SkillCAT、Trace2Skill、SkillPyramid、SkillX、WikiSkill、SKILLRL、SKILL0、SkillEvolver、SkillWeaver、GEPA |
| G3 同功能跨数据集 | 5 | 23.1% | SkillOpt、EvoSkill、Trace2Skill、SKILLRL、SKILL0 |
| G4 相邻任务功能迁移 | 2 | 9.5% | SkillCAT、Trace2Skill |
| G5 完全跨功能迁移 | 0 | 0.0% | 无 |
| G6 environment/tool schema/harness portability | 5 | 22.7% | SkillOpt、CoEvoSkills、SkillReducer、SkVM、Skill-Have |
| G7 model/model-family portability | 11 | 50.0% | SkillGen、SkillOpt、CoEvoSkills、SkillCAT、Trace2Skill、WikiSkill、SkillHone、SkillWeaver、GEPA、SkillReducer、SkVM |
| G8 chronological/continual deployment | 2 | 9.5% | SkillEvo、SkillHone |
| EV evaluator validity（非 G0-G8） | 1 | 4.8% | Who Grades the Grader? |

注：`G1/G2` 是联合统计。表中比例以 21 篇论文为分母；同一论文可同时出现在多行，故不能相加为 100%。

### 统计解释

1. **主流是 benchmark 内泛化，而不是跨任务泛化。** 14/21 篇有 `G1/G2` cell，但通常是每个 benchmark 各自拥有 source/evolution/test split。
2. **跨数据集证据有限且高度集中。** 严格 `G3` 只覆盖 5 篇，主要集中在 search QA、math、文档抽取和 deck-disjoint 文档任务。
3. **相邻功能迁移更少。** `G4` 只有 SkillCAT 和 Trace2Skill 的表格/文档相关实验；没有论文提供严格 `G5` 的同一 artifact 跨完全不同功能测试。
4. **G7 多于 G6。** 11 篇报告跨模型或 cross-family 结果，但这主要说明载体可移植性，不能替代 G3-G5 的任务功能泛化。
5. **严格 continual protocol 稀缺。** SkillEvo 的 chronological future-ticket split 与 SkillHone 的 cross-session history 是唯一可计入 G8 的实验；SkillAdaptor 的多轮 repair、WikiSkill 的 rollback 仅是机制或迭代证据。

## 未纳入严格计数的常见情形

| 情形 | 涉及论文 | 原因 |
|---|---|---|
| 多 benchmark breadth | MetaSkill-Evolve、WikiSkill、GEPA、SkillX、SkillPyramid、SkillEvolver 等 | 各 benchmark 通常有自己的 source/evolution/test cell，不能据此称同一 artifact 跨功能 G5 |
| 弱 G6 / 多环境覆盖 | SkillX、SkillWeaver | 没有固定 artifact 在只改变 schema/environment 的受控 source→target protocol |
| G8 机制候选 | WikiSkill、SkillAdaptor | 有 persistent state、rollback 或多轮 update，但没有时间排序 target、旧任务 retention 或非平稳 probe |
| 混合 G6/G7 portability | CoEvoSkills | 目标模型变化时 harness 往往同时变化，不能做单变量归因 |
| evaluator 的 held-out validity | Who Grades the Grader? | 演化对象是 evaluator/metric，需单列 EV，而不是套用任务 artifact 的 G3/G5 |

## 证据来源

逐篇 PDF 页码、逐列核验与可替换表述见：

- [verify_4_2_glm_flash_1.md](verify_4_2_glm_flash_1.md)
- [verify_4_2_glm_flash_2.md](verify_4_2_glm_flash_2.md)
- [verify_4_2_glm_flash_3.md](verify_4_2_glm_flash_3.md)
- [verify_4_2_glm_flash_4.md](verify_4_2_glm_flash_4.md)

主综述中的方法论与 benchmark 功能聚类见 [skill_evolve_survey.md](skill_evolve_survey.md)。
