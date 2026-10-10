# Fair Comparison Matrix for Skill Evolve

## 1. Comparison unit

论文级比较过于粗糙。最小比较单位应是一个 **evaluation cell**：

```text
Pi = (T, C, U, G, F, A, H, B, Q)
```

- `T`: evolve target，SU、SC、PP、RT、EV。
- `C`: carrier，单文档、目录、多文件 package、API、wiki、weights、compiled artifact。
- `U`: update operator，create、rewrite、repair、consolidate、retrieve、compress、internalize、compile。
- `G`: source→target 泛化几何。
- `F`: feedback information。
- `A`: model、environment、tool schema、harness。
- `H`: experience horizon，same query、task、family、dataset pool、continual stream。
- `B`: rollout、LLM calls、tokens、verifier、wall-clock、money budget。
- `Q`: evaluator type and access。

只有在这些坐标大体匹配时，最终 success/accuracy 才适合做严格数值比较。

## 2. Generalization levels

| Level | Source→target relation | Can support | Cannot support alone |
|---|---|---|---|
| G0 | same-instance retry/repair | 当前实例的修复和回归控制 | 未见任务泛化 |
| G1 | same template, new inputs | 输入变化下的局部 workflow 稳定性 | 新 task family |
| G2 | same environment/domain, unseen task template | 组合 workflow 或结构泛化 | 跨环境 portability |
| G3 | same functional family, new dataset/files | 同功能跨数据集或 artifact 泛化 | 跨功能通用 skill |
| G4 | related functional family | 相邻任务功能迁移 | 完全开放的跨功能能力 |
| G5 | different task function | 更强的跨功能 skill reuse | 若没有统一 artifact/预算，则不能归因于 skill transfer |
| G6 | environment/tool schema/harness changes | 执行载体 portability | task-function generalization |
| G7 | model or model family changes | artifact/model portability | 新任务上的语义泛化 |
| G8 | chronological stream / continual deployment | 维护、遗忘、回滚、非平稳适应 | 一次性 acquisition 的静态泛化 |

## 3. Fair-comparison groups

### Green: potentially direct comparison

| Group | Candidate cells | Required controls |
|---|---|---|
| A. Frozen single-skill adaptation | SkillOpt、SkillGen、SkillEvolver、EvoSkill 的 single-skill cell、MetaSkill-Evolve 的 task-skill-only ablation | 同一 base model、同一 initial artifact、同一 source/validation/test、同一 feedback、同一 authoring budget、同一 harness |
| B. Trajectory consolidation | Trace2Skill、WikiSkill 的 compiled-skill cell、SkillCAT 的 patch/consolidation ablation | 同一 success/failure trajectory pool、同一 collection size、同一 downstream model、同一 target family |
| C. Collection retrieval/composition | SkillPyramid、SkillX、WikiSkill、SkillWeaver 的同一 environment/tool track | 同一工具 schema、同一 retrieval budget、同一 collection size、同一 target tasks |
| D. Continual maintenance | SkillEvo、SkillAdaptor、SkillHone、WikiSkill 的 continual cell | 同一 chronological stream、update opportunities、old-task probes、storage/history budget、rollback policy |

“Green”不表示论文原始结果已经公平，而是表示经过重跑或重构后有可能构成 matched cell。

### Yellow: profile-adjacent comparison

- `ALFWorld` 与 `ScienceWorld`：同为状态化交互，但 task function、world dynamics 和 action space 不同。
- `OfficeQA`、`SealQA`、`BrowseComp`：都可含搜索/文档证据，但 information source、search stack、evaluator 不同。
- `SpreadsheetBench`、`WikiTableQuestions`、`HiTab`：共享结构化表格，但一个偏文件操作，另一些偏表格问答。
- `WebArena`、`Mind2Web`、`WebShop`：都属 web task，但 website set、task objective、browser/tool interface 不同。
- `NQ/HotpotQA` → `TriviaQA/2Wiki/MuSiQue/Bamboogle`：可比较同功能 search QA 的 transfer，但不能作为跨功能 skill 结论。
- `SkillsBench` multi-domain suite：可用于 breadth summary；必须逐 benchmark/family 报告，不能与单一 ALFWorld cell 的分数直接排序。

### Red: non-comparable as a single leaderboard

- SKILL0、SKILLRL 与 frozen external-skill methods：前两者更新模型参数或 policy。
- GEPA 与 external skill acquisition：主要更新 prompt/program，而不是独立 skill artifact。
- SkVM 与 skill discovery：主要优化 runtime/compiler portability and efficiency。
- SkillReducer 与 skill discovery：主要测 compression/retention/cost。
- Who Grades the Grader? 与普通 skill generation：主要测 evaluator reliability。
- CoEvoSkills 与普通 rewrite：verifier 本身 co-evolve，且 oracle 信息可能不同。
- SkillEvo/SkillHone 与静态 held-out：continual history、multi-turn interaction 和 search stack 改变了问题定义。
- SkillWeaver WebArena 自动分数与真实网站人工分数：evaluator 不同。

## 4. What the current papers actually establish

| Claim | Strongest supporting evidence in the 21 papers | Conservative interpretation |
|---|---|---|
| External skill can repair/augment an agent | SkillOpt、SkillGen、SkillAdaptor、EvoSkill | 在冻结模型和给定反馈/验证器下，外部 artifact 能改善相近 held-out 任务；需报告 regression |
| Skills transfer across datasets | Trace2Skill、SKILLRL、SKILLGEN、SkillOpt | 许多 transfer 是同功能或相邻功能数据集迁移；source-target function must be named |
| Skills transfer across multiple task functions | SKILLGEN、SkillOpt、WikiSkill、MetaSkill-Evolve 的多 benchmark breadth | 主要证明方法在多个 cell 可用；尚缺同一 artifact、统一预算下的严格 cross-functional factorial test |
| Skill collection is better than single skill | SkillPyramid、SkillX、Trace2Skill、WikiSkill、SKILLRL | 需要 coverage/reuse/routing/negative-transfer 指标；不能只用平均 success rate |
| Skill remains portable across models/harnesses | CoEvoSkills、SkillOpt、SKILLGEN、Trace2Skill、SkillReducer、SkVM | 主要是 carrier/runtime portability；不等于新任务泛化 |
| Continual skill maintenance works | SkillEvo、SkillHone、SkillAdaptor、WikiSkill | 应同时测 new-task gain、old-task retention、regression、history/storage cost |

## 5. Required reporting table for future papers

| Field | Minimum report |
|---|---|
| Evolve target | individual SU / collection / policy / prompt / runtime / evaluator |
| Carrier | format, file count, token count, executable dependencies |
| Source data | number of tasks, families, instances, success/failure ratio |
| Target split | same instance/template/family/function/domain/environment/harness |
| Functional relation | same / adjacent / different task function |
| Feedback | trajectory, answer, score, oracle, verifier, judge, human |
| Model state | frozen or updated; if updated, compute and parameter scope |
| Budget | rollouts, calls, tokens, verifier calls, latency, cost |
| Use intervention | loaded / retrieved / invoked / followed / causally helpful |
| Harm | regression rate, negative transfer, stale skill, evaluator failure |
| Statistics | micro, macro-family, worst family, confidence interval, multiple seeds |

## 6. Bottom line

当前文献最适合形成多个局部排行榜，而不是一个总榜：

1. frozen external single-skill adaptation；
2. trajectory-to-skill consolidation；
3. collection retrieval/composition；
4. continual maintenance；
5. parameter internalization；
6. prompt/program optimization；
7. compression/efficiency；
8. runtime portability；
9. evaluator co-evolution。

跨 benchmark 的 headline average 只能作为 breadth summary。严格比较必须回到 matched evaluation cell。

