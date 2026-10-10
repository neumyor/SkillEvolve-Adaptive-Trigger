# Agent Method Evaluation Audit: Skill Evolve Papers

审计对象：`/Users/yimingniu/Code/SkillEvolvePaperList/papers/` 中的 21 个原始 PDF。  
输出目的：逐篇核对 Skill Evolve 方法实际 evolve 的对象、载体、更新流程、经验暴露范围、feedback/evaluator、模型参数是否更新，以及这些设计与评测泛化粒度的关系。  
范围声明：本文件为独立审计，不修改主综述 `Skill_Evolve_Survey_Draft.docx`。

## 读取与证据约定

- 页码均为 PDF 内页码，以 `PDF p.` 表示；若论文印刷页码与 PDF 页码不同，以 PDF 页码为准。
- **E1**：PDF 明确写出或由算法/实验表格直接支持。
- **E2**：由方法或实验设计明确支持，但不是作者使用的同一术语。
- **E3**：为了跨论文比较而做的归一化，不应当当作论文作者的 ontology。
- **E4**：PDF 没有足够信息确认。
- “模型参数是否更新”只指被评测的基础 LLM/策略权重；不把 skill 文本、脚本、路由器、评测器或运行时配置误记为模型权重。

## 总体核对结论

1. **Evolve 对象并不统一。** 大多数论文更新的是外部 skill artifact 或 skill collection；SKILL0、SKILLRL 明确还更新模型参数；GEPA 主要更新 prompt/program；SkVM 主要更新编译/运行时表示；Who Grades the Grader? 主要把 evaluator 本身作为 evolve 对象。
2. **载体决定可迁移性。** 单一自然语言文档、`SKILL.md` 目录、多文件图/包、可执行 API、层级库、wiki、参数状态和编译产物对应不同的泛化单位，不能只按“有 skill/无 skill”合并。
3. **反馈暴露范围是评测可比性的关键。** 有些方法看完整成功/失败轨迹和答案，有些只看分数，有些使用 surrogate verifier，有些使用 opaque oracle pass/fail；同样的最终分数不代表同等的信息预算。
4. **泛化粒度至少要区分：** 同实例修复、同任务类型 held-out、同环境新任务、跨 artifact/文档、OOD 数据集、跨模型、跨 harness/工具 schema、跨网站/环境，以及跨 benchmark。论文常把其中多种粒度并列报告，不能折算成一个泛化数字。
5. **评测器本身可能成为方法对象。** CoEvoSkills、SkillCAT、SKILLGEN、Who Grades the Grader? 都把验证、路由、评测或审计闭环纳入方法；应分开报告 artifact 质量和 evaluator/selection 质量。

## 逐篇审计

### 1. CoEvoSkills

- **Evolve 对象与载体（E1）：** 不是单段 prompt，而是结构化的多文件 skill package；同时 co-evolve skill generator 与 surrogate verifier。作者区分 tool 与 skill，skill 是可包含过程文档、脚本和资源的 package（PDF pp. 1-4）。
- **更新流程（E1）：** 交替进行 skill refinement 与 verifier/test escalation。surrogate 失败时固定 verifier、用 failure diagnostic 改 skill；surrogate 通过但 ground-truth oracle 失败时升级 verifier；最终保留通过条件的 package（PDF pp. 4-7；Algorithm 1 在 p. 5）。
- **经验暴露与 feedback/evaluator（E1）：** 演化可见实例数据和背景文档，但不应看到 hidden oracle 内容；surrogate verifier 产生结构化失败反馈，ground-truth oracle 只给 opaque pass/fail（PDF pp. 4, 6-7）。
- **模型参数：** 不更新基础模型参数；变化发生在 package、generator/verifier 的上下文与测试资产。
- **泛化粒度关系：** SkillsBench 的 held-out task 检验同 benchmark 泛化；Claude Opus 4.6 生成的 skill 在 GPT-5.2、Claude、Qwen、DeepSeek、Mistral 等模型上测试，检验跨模型；Claude Code/Codex 等 harness/执行环境的 portability 另行检验（PDF pp. 8, 11-12）。因此其核心主张是“多文件 artifact + 验证闭环”的任务级、跨模型/跨 harness 可迁移，而不是 skill collection 规模或 retrieval 质量。

### 2. EvoSkill

- **Evolve 对象与载体（E1）：** 冻结 agent 上的 structured reusable skill folders，包含 instructions、trigger metadata 和 helper scripts；同时保留一个由程序/skill 组成的 Pareto frontier（PDF pp. 1-2）。
- **更新流程（E1）：** 从执行失败收集 failure cases，proposer 分析并提出新 skill 或 refinement，skill builder 将其物化到目录；只有在 held-out validation 上有改进的程序/skill 才保留，支持 merge/selection（PDF pp. 2, 4-5）。
- **经验暴露与 feedback/evaluator（E1）：** 失败轨迹、agent 输出、ground-truth answer 和 validation score 都用于进化；训练/验证/最终测试分开，测试集只用于最终报告（PDF pp. 3-5）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** OfficeQA/SealQA 等 benchmark 内的 train-validation-held-out test 是任务实例级泛化；从 SealQA skill 转移到 BrowseComp 是跨 benchmark/domain 的更强粒度（PDF pp. 6-10）。但 ground-truth diagnosis 与 validation-query budget 是方法能力的一部分，必须与其他 frozen external-skill 方法对齐。

### 3. GEPA

- **Evolve 对象与载体（E1）：** 主要优化 system prompt/instruction，以及 compound AI system 中各模块的 program-level prompt components；不是独立 external skill collection（PDF pp. 4-6）。
- **更新流程（E1）：** 从 evaluation trace 和 textual feedback 做 reflective mutation，维护 Pareto candidates，并按 candidate 在不同任务上的优势进行选择/merge；算法在 `D_feedback` 与 `D_pareto` 上分工（PDF pp. 6-8）。
- **经验暴露与 feedback/evaluator（E1）：** evaluator 返回分数和可选 textual execution feedback，feedback 可 module-specific；优化器访问 train/feedback 数据，validation 用于选择，test 用于最终评测（PDF pp. 6-9, 25-30）。
- **模型参数：** 不更新 LLM 参数；更新的是 prompt/program state。
- **泛化粒度关系：** AIME、LiveBench-Math、HotpotQA、IFBench、HoVer、PUPA 等设置以 train/validation/test task split 检验任务级泛化，并报告 validation-to-test gap（PDF pp. 8-9, 25-30）。GEPA 应作为 prompt/program optimization baseline，不应直接归入 external skill acquisition leaderboard。

### 4. MetaSkill-Evolve

- **Evolve 对象与载体（E1）：** 两层对象：fast loop 的 task skill，以及 slow loop 的 meta-skill/过程控制器，包括 Analyzer、Retriever、Allocator、Proposer、Evolver 等角色；共享 frozen backbone（PDF pp. 1-4）。
- **更新流程（E1）：** 持久化 evolution graph 选择要扩展的 branch；快速循环更新 task skill，每隔 H 次迭代慢循环重新应用反馈来更新 meta-skill，形成 two-timescale co-evolution（PDF pp. 4-9）。
- **经验暴露与 feedback/evaluator（E1）：** 主要使用任务轨迹、候选分支分数和 held-out evaluation；meta-skill 影响如何分析、检索、分配和提出 skill。
- **模型参数：** 不更新基础模型参数。
- **泛化粒度关系：** OfficeQA、SealQA、ALFWorld 的 held-out split 主要检验同 benchmark 的任务级泛化（PDF pp. 6-10）。由于 meta-skill 也在变，收益包含“skill 内容”与“搜索/分配过程改进”两部分；与单层 skill rewrite 比较时必须计入额外的 meta-agent 调用和更新机会。

### 5. SKILL0

- **Evolve 对象与载体（E1）：** 外部 structured skill package 只作为临时上下文/teacher；真正目标是把 skill internalize 到模型参数或 policy 中，并逐步撤掉 skill context（PDF pp. 1-3）。
- **更新流程（E1）：** 在 skill-augmented context 下进行 agentic RL，随着训练逐渐减少外部 skill 依赖，比较 internalization 前后和 context withdrawal 阶段（PDF pp. 5-9）。
- **经验暴露与 feedback/evaluator（E1）：** 使用环境交互轨迹和 RL reward；ALFWorld、search QA、WebShop 等环境的任务反馈作为训练信号，search QA 还区分 in-domain 与 OOD（PDF pp. 5-9, 18-19）。
- **模型参数：** 更新，明确属于 parameter/policy learning。
- **泛化粒度关系：** search QA 的 in-domain/OOD 是数据集级泛化；ALFWorld/WebShop 更偏环境内任务泛化（PDF pp. 6, 18-19）。应按“skill-assisted parameter learning”单独比较，不能直接与 frozen external-skill rewrite 的推理时结果混排。

### 6. SkillAdaptor

- **Evolve 对象与载体（E1/E2）：** 现有 external skill collection 中的局部 skill；不是从零生成一套全新库。基础模型冻结，重点是 first actionable failure localization、责任归因和局部 revision（PDF pp. 1-4）。
- **更新流程（E1）：** 从失败 trajectory 找到最早可操作失败点，判断是模型、工具还是某个 skill 负责，再局部修改候选 skill，并通过 qualification/score 决定是否保留（PDF pp. 2-9）。
- **经验暴露与 feedback/evaluator（E1）：** failed trajectories、task score 和 runtime traces；实验在 WebShop、PinchBench、Claw-Eval/OpenClaw 上进行（PDF pp. 3-9）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** 核心评测是 local repair 和 continual maintenance；它更接近“在一个已有 collection 上维护”的泛化，而不是从零 skill discovery。工具 schema、harness 和失败归因范围必须固定，否则无法分离 repair gain 与环境差异。

### 7. SkillCAT

- **Evolve 对象与载体（E1）：** skill patches 加上可路由的 topology/collection；方法包含 Contrastive Causal Extraction、Assessment-Augmented Evolution、Topology-Aware Task Execution（PDF pp. 1-3）。
- **更新流程（E1）：** 对成功/失败 trajectory 做 contrastive patch extraction，进行 patch assessment，再 merge、组织 topology、执行时 route 到相关 skill；runtime validation 参与筛选（PDF pp. 1-3）。
- **经验暴露与 feedback/evaluator（E1）：** successful/failed trajectories、patch assessment、runtime validation；评测使用 SpreadsheetBench-Verified、DocVQA 和 WikiTableQuestions，并报告 held-out、OOD、cross-model（PDF pp. 5-7）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** SpreadsheetBench 的 200 evolution/200 held-out，以及 DocVQA disjoint partition 检验同数据集任务泛化；WikiTableQuestions 是 OOD，另有跨模型测试（PDF p. 5-7）。总分同时混合 extraction、assessment、merge/topology、routing，需用 ablation 拆解，不能把 composite score 等同于单个 skill 的迁移能力。

### 8. SkillEvo

- **Evolve 对象与载体（E1）：** multi-file directed skill graph，包含 routing table、references、history 等；方法也持续更新其治理状态（PDF p. 3）。
- **更新流程（E1）：** 生产交互中持续 revise，按 fact consistency、structural consistency、regression、bloat 等约束做治理与回归检查；不是一次性生成后冻结（PDF pp. 4-9）。
- **经验暴露与 feedback/evaluator（E1）：** multi-turn user simulation、生产 ticket、事实/结构检查；六类 cloud-service、9 个 production skills、98 个 reference files，ticket 按时间切成四个子集（PDF pp. 6-9）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** chronological held-out tickets 与 continual interaction 检验持续维护和时间外推；其 proprietary production setting 不等同于 public single-turn benchmark 的 task split，不能直接按单次 held-out 分数比较。

### 9. SkillEvolver

- **Evolve 对象与载体（E1）：** 可复用 task/domain skill artifact，可含 prose、scripts、references；通过 meta-skill 在 CLI-agent interface 中按需 author/refine/audit（PDF pp. 1-4）。
- **更新流程（E1）：** 用 training trials 探索并生成 skill，再用 validation trials 审核和选择，基础模型不重新训练（PDF pp. 8, 14-17）。
- **经验暴露与 feedback/evaluator（E1）：** agent trial trajectories、task outcomes、validation artifacts；SkillsBench 使用 83-task subset，KernelBench 另外包含 3 个 GPU-kernel optimization tasks（PDF pp. 6-9）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** SkillsBench 更接近跨专业 task-level held-out；KernelBench 更像单独的 domain transfer cell。论文未为 KernelBench 报非 SkillEvolver baseline（E4），因此不能把两个 cell 合并成一个泛化结论。

### 10. SkillGen

- **Evolve 对象与载体（E1）：** 单个 auditable skill artifact，可编码 instructions、executable code、domain knowledge；不是权重或 prompt search（PDF pp. 1-6）。
- **更新流程（E1）：** 先记录 baseline，再对成功/失败 trajectories 做 contrastive induction；进入 generate-verify-refine loop；候选 skill 只有在 with-skill/without-skill paired intervention 的 net effect 为正时才通过 gate，可 deprecate harmful candidate（PDF pp. 6-9, 14-19）。
- **经验暴露与 feedback/evaluator（E1）：** 成功和失败的完整 trajectories、task diagnostics、paired verification subset；feedback 来自 generation agent 和 verification agent，最终选择依据 held-out performance（PDF pp. 6-9）。
- **模型参数：** 不更新基础 LLM；作者明确强调 cross-model transfer without parameter updates（PDF pp. 1-2, 16）。
- **泛化粒度关系：** paired same-instance repair/regression 先验证局部干预是否有效；ALFWorld `valid_seen` 是 IOD、`valid_unseen` 是 OOD；另有 cross-benchmark/cross-model transfer（PDF p. 16 及 pp. 14-19）。IOD 与 OOD 不能合并为一个“泛化”标签，且 accepted candidate 仍可能制造 held-out regression。

### 11. SkillHone

- **Evolve 对象与载体（E1）：** loadable skill bundle，含 procedures、scripts、references、output conventions；另有 persistent decision history，作为跨会话状态（PDF pp. 1-3）。
- **更新流程（E1）：** continual diagnose -> propose -> evaluate -> retain history；evaluation reports、probes、validators 和 regressions 共同决定 skill 是否更新（PDF pp. 4-6）。
- **经验暴露与 feedback/evaluator（E1）：** GAIA validation、WebWalkerQA-EN、20 个 disjoint WebShaper development items；curated-search 与 raw-open-web 使用不同 search stack，raw-open-web 共享 portable bundle interface（PDF pp. 4-6）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** cross-session 与 open-web setting transfer 是主张重点；但 search stack、controller/executor 配置会改变可用能力，跨 setting 分数不能直接视作 skill-only transfer。

### 12. SkillOpt

- **Evolve 对象与载体（E1）：** 单个 natural-language skill document；冻结 target agent 通过 bounded add/delete/replace 编辑更新（PDF pp. 1-3）。
- **更新流程（E1）：** 对 scored rollouts 做有限 rewrite，经过 selection/validation gate；另有较慢的 meta update，但主产物仍是 skill document（PDF pp. 3, 5-7）。
- **经验暴露与 feedback/evaluator（E1）：** train rollouts、selection score 和 held-out gate；test split 仅用于最终报告，避免把 test 作为搜索反馈（PDF pp. 5-7）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** 六个 benchmark、七个 target model、三种 execution mode，分别覆盖 benchmark-held-out、cross-model、cross-harness、nearby benchmark transfer（PDF pp. 10-16）。这些 benchmark 是异质 evaluation cells，不应求一个代表单一任务分布的 pooled score。

### 13. SkillPyramid

- **Evolve 对象与载体（E1）：** hierarchical skill library；操作包括 atomic skill extraction、abstract induction、consolidation 和 retrieval，collection topology 是主要对象（PDF pp. 1-4）。
- **更新流程（E1）：** 从 task trajectories 提取原子单元，归纳更高层 abstraction，合并/组织层级，再按任务检索使用（PDF pp. 1-4）。
- **经验暴露与 feedback/evaluator（E1）：** task trajectories、environment success；ALFWorld 和 ScienceWorld 都按 seen/unseen 任务或 variation 报告（PDF p. 10 及实验附录）。
- **模型参数：** 不更新基础模型；skill library 从训练 split 构造。
- **泛化粒度关系：** ALFWorld 140 seen/134 unseen、ScienceWorld 194 seen/211 unseen variations 主要检验 environment-internal seen-to-unseen；多环境 breadth 不自动等于 cross-environment transfer，除非同一 learned library 真正跨环境迁移（PDF p. 10）。

### 14. SkillReducer

- **Evolve 对象与载体（E1）：** pre-packaged instruction skills 的 routing descriptions 与 skill bodies；主目标是压缩而不是发现新 procedural knowledge（PDF pp. 1-3）。
- **更新流程（E1）：** 对 55,315 个 public skills 做压缩/重写，支持 progressive disclosure；600-skill controlled evaluation 比较 no-skill、original-skill、compressed-skill（PDF pp. 1-3, 5-10）。
- **经验暴露与 feedback/evaluator（E1）：** functional evaluator、token count、latency/runtime measurements；SkillsBench 87 tasks，另外跨 5 个模型、4 个 model family 和另一个 agent framework（PDF pp. 8-12）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** 重点是 functional retention under compression、cross-model/framework retention 与效率，不是 skill discovery quality。应把 token reduction、pass-rate retention、latency 分开报告。

### 15. SKILLRL

- **Evolve 对象与载体（E1）：** hierarchical SKILLBANK，包含 general/task-specific skills；同时更新 policy/model weights，因此是 collection + PP 的 co-evolution（PDF pp. 1-4）。
- **更新流程（E1）：** 从 trajectory outcomes/distilled experience 扩展和 refine skill bank，并进行 SFT/RL policy update；报告 bank 从 55 增长到 100 skills（PDF pp. 6-7, 10-14）。
- **经验暴露与 feedback/evaluator（E1）：** failed/success trajectories、environment outcomes、RL reward；在 ALFWorld、WebShop 和 7 个 search-QA 数据集上迭代（PDF pp. 6-7, 10-14）。
- **模型参数：** 更新，明确包含 policy learning。
- **泛化粒度关系：** ALFWorld general skills 目标是同环境跨 task type；search QA 明确区分 in-domain/OOD（PDF pp. 7, 13）。与 frozen external collection 比较时必须隔离 policy-update compute、训练数据和 inference context，否则 skill-bank gain 与 weight-learning gain 混在一起。

### 16. SkillWeaver

- **Evolve 对象与载体（E1）：** executable APIs with tests，作为 growing API/skill library；对象不仅是 prose skill，也包含可执行接口和可靠性测试（PDF pp. 1-3）。
- **更新流程（E1）：** website exploration -> skill/API proposal -> API synthesis -> automated test/debug -> library expansion（PDF pp. 1-6）。
- **经验暴露与 feedback/evaluator（E1）：** website interaction traces、automated functional checks；WebArena 使用 automated functional correctness，real-website success 使用 human judgment（PDF pp. 5-6）。
- **模型参数：** 不更新基础 LLM；默认 agent 配置和执行环境固定在方法实验中。
- **泛化粒度关系：** WebArena 的五个应用域检验 benchmark 内 transfer；Online-Mind2Web 涉及 136 websites，但 reported online subset 只用 4 websites/57 tasks；另有 simulated-to-real/cross-website 维度（PDF p. 5）。由于 evaluator 从自动检查切换为人工判断，两个结果必须分开。

### 17. SkillX

- **Evolve 对象与载体（E1）：** three-level skill knowledge base：planning、functional、atomic；既有 procedural knowledge，也可能编码 tool/environment-specific declarative knowledge（PDF pp. 1-5）。
- **更新流程（E1）：** 从 seed training trajectories/experiences 抽取 skill，filter、merge、decompose、retrieve、compose，并可做 exploratory expansion（PDF pp. 3-7, 19-24）。
- **经验暴露与 feedback/evaluator（E1）：** generated experience、task trajectories、benchmark evaluator；BFCL-v3、AppWorld、tau2-Bench 的 train/test 与 tool schema 不同，指标包括 Avg@4、Pass@4、Pass@1（PDF pp. 5-8）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** benchmark-held-out、cross-model/user、cross-tool-schema/environment 都被报告，但不同 benchmark 的交互模式不同，pooled average 只是 breadth summary，不是一个匹配任务分布上的泛化率。

### 18. SkVM

- **Evolve 对象与载体（E1）：** compiled/runtime-bound skill artifacts；把 skill 看作 code，把异质 LLM 看作 processors，主要更新 compilation、environment binding、DAG/concurrency representation 和 runtime execution（PDF pp. 1-5）。
- **更新流程（E1）：** capability profiling -> AOT/JIT compilation -> environment binding -> concurrency extraction -> runtime task variant selection/adaptive recompilation（PDF pp. 5-8）。
- **经验暴露与 feedback/evaluator（E1）：** completion、token、latency、compatibility measurements；实验覆盖多个模型、BareAgent/OpenCode/OpenClaw 三种 harness（PDF pp. 8-10）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** cross-model 与 cross-harness portability 是核心，而不是 procedural knowledge transfer。报告应将 task completion、token、latency 和 compatibility 分开，不能只用 success rate 把 runtime/compiler improvement 归入 skill quality。

### 19. Trace2Skill

- **Evolve 对象与载体（E1）：** 一个可移植的 filesystem skill directory：root `SKILL.md` 加 references/scripts/assets；多个 trajectory-local patches 最终 hierarchical merge 为一个 consolidated directory（PDF pp. 2-4）。
- **更新流程（E1）：** frozen agent rollout 收集 success/failure trajectories；error analyst 与 success analyst 并行提出 patches；再做 hierarchical consolidation 和 selection（PDF pp. 2-4, 8）。
- **经验暴露与 feedback/evaluator（E1）：** 完整 labeled trajectories、artifact-level failures/successes、held-out pass rate；SpreadsheetBench 200 evolution/200 held-out，并有 artifact-disjoint、OOD、cross-model/family 评测（PDF pp. 4-9, 13-14）。
- **模型参数：** 不更新基础 LLM；skill author 与 skill user 可使用不同 model size，论文显式评估 cross-model reuse。
- **泛化粒度关系：** source traces 到 held-out artifact、table/document/math domain、OOD data 和 cross-model 的关系分别报告；例如 PDF VRDU traces 到 VAREX、PPTX TSBench 到 deck-disjoint split（PDF p. 9）。必须注明 source-target relation，不能把 artifact-disjoint 误写成 cross-domain。

### 20. Who Grades the Grader?

- **Evolve 对象与载体（E1）：** evaluator metric 本身是第一类 evolve 对象，同时 co-evolve skill bank 的 create/revise/retire lifecycle；metric 表示为 drawback detectors 的组合（PDF pp. 1-3, 5-6）。
- **更新流程（E1）：** metric loop 在 train outputs 上搜索/组合 detector，并用小 anchored dev set、consensus regularization 和 locked test audit 防止 collapse；skill loop 用当前 metric 对训练尝试打分，外层 independent judge 只审计（PDF pp. 2-6, 10-13）。
- **经验暴露与 feedback/evaluator（E1）：** train solver outputs 可见；dev 为小 anchor；test reference locked 且 metric 不读取；MBPP+ hidden unit tests、Spider 2.0-Snow execution comparison 和 report-generation independent judge 构成不同强度的 reference/evaluator（PDF pp. 10-13, 19-24）。
- **模型参数：** 不更新基础 solver LLM；更新 metric expression、detector pool 和 skill bank。
- **泛化粒度关系：** 重点是 held-out metric reliability、anchor generalization、reference-free audit 和 Goodhart resistance，而非仅 agent final accuracy。论文报告 removing anchors 可能导致 metric collapse；因此评测 evaluator 质量时必须同时报告 train agreement、held-out agreement、outer audit 与 skill-loop outcome（PDF pp. 1-3, 19-24, 60-70）。

### 21. WikiSkill

- **Evolve 对象与载体（E1）：** 三种状态要分开：raw execution experience、persistent wiki knowledge、filesystem skill directories；方法是从 wiki 编译 skill，并用 gate/rollback 维护 collection（PDF pp. 1-4）。
- **更新流程（E1）：** accumulate wiki -> compile skill -> validation gate -> admit or rollback；被拒绝的 skill update 不应删除已经积累的 wiki knowledge（PDF pp. 2-7）。
- **经验暴露与 feedback/evaluator（E1）：** train trajectories/experience 进入 wiki；validation gate 选择可执行 skill；test evaluator 最终评测；覆盖 5 个 benchmark、5 个 model，并报告 cross-model transfer（PDF pp. 3, 7-14）。
- **模型参数：** 不更新基础 LLM。
- **泛化粒度关系：** held-out within benchmark、cross-model 和 cross-benchmark breadth 都有涉及，但必须分离“persistent wiki state 的收益”和“最终 compiled skill 的收益”。否则无法判断是可检索长期记忆、skill artifact，还是两者组合导致迁移（PDF pp. 1-4, 7-14）。

## 评测解读建议

对这 21 篇方法做横向表格时，至少保留以下独立列：

| 列 | 必须记录的区别 |
|---|---|
| evolve object | individual skill、skill collection/topology、meta-process、evaluator、prompt/program、runtime/compiler、policy/weights |
| carrier | text document、multi-file directory/package、executable API、hierarchical library、wiki、parameter state、compiled artifact |
| update operator | create/refine/merge/retrieve、repair、consolidate、co-evolve verifier、RL/SFT、prompt mutation、compile/bind |
| experience exposure | success only、failure only、paired success/failure、full trajectory、score only、ground-truth answer、opaque oracle、production multi-turn history |
| evaluator | deterministic test、LLM judge、surrogate verifier、human judgment、RL reward、held-out gate、outer audit |
| parameter update | yes/no；若 yes，另记 skill context 是否仍在推理时存在 |
| generalization unit | same-instance repair、within-task held-out、within-environment unseen、artifact-disjoint、OOD dataset、cross-model、cross-harness/tool schema、cross-website、cross-benchmark |

特别需要避免的三种误读：

1. 把“skill 文件被修改”写成“模型学会了该能力”；SKILL0/SKILLRL 才明确更新参数。
2. 把“跨模型运行”写成“跨任务泛化”；跨模型通常是在固定任务集合上测试 carrier portability。
3. 把“held-out score”写成同一种 evaluator 证据；ground-truth oracle、opaque pass/fail、surrogate verifier、LLM judge、human judgment 和 RL reward 的信息内容不同。

