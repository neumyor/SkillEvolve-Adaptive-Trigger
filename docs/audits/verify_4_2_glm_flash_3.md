# 第 4.2 节表格核验：批次 3（WikiSkill、SKILLRL、SkillEvolver、SkillEvo、SkillHone）

范围：对照 `papers/` 下原始 PDF 与 `skill_evolve_survey.md` 第 4.2 节当前表格，逐列核对 evolve setting、source 经验范围、target 测试范围、G0-G8 泛化 setting、可支持结论与 PDF 页码证据。页码均为 PDF 页码。以下不修改主综述，只列正确、错误、过强或缺证据表述，并给出建议替换文本。

## WikiSkill

**核对结果概览**

- **evolve setting：基本正确。** 论文是 W→SU/SC 式的双层演化：skill set 从空集开始，Raw Layer 保存 immutable traces，Wiki Layer 持续累计 patterns/evolution logs，Skill Proposer 提出单 skill 原子更新，validation gating 接受或回滚 skill，但 wiki 不回滚。PDF pp.2-6；Algorithm 1 在 p.19。
- **source 经验范围：方向正确，但应改为“per-benchmark 经验”。** 每个数据集各自有 train/val/test，skill set 也按数据集从空开始演化；wiki 累计发生在单个 benchmark 的演化循环内，而不是跨五个 benchmark 的统一经验池。PDF pp.3-7, 19-20。
- **target 测试范围：正确但缺 split 细节。** 五个 benchmark 分别是 LiveMath 35/18/124、SealQA 16/10/85、SpreadSheet 80/40/280、OfficeQA 50/24/172、ALFWorld 39/18/134，最终测 test split；报告三次完整演化 run 平均。PDF p.20, pp.7-8。
- **G1/G2：可保留。** 对应同一 benchmark 内 train→unseen test。
- **G6：错误，应删除或降级为缺证据。** 论文没有 cross-harness 或 environment/tool-schema shift 实验。五个 benchmark 使用各自固定工具与 evaluator；跨模型实验是同一 artifact 在不同 inference/source model 上的结果，应归 G7，而不是 G6。PDF pp.7-10。
- **G7：正确，且证据明确。** Table 2 显示 Qwen-3.5-4B、Qwen-3.6-27B、Gemini-3.5-Flash 作为 skill source 与不同 inference model 的 transfer，并有负迁移案例，如 Qwen-3.5-4B skill 使 Gemini-3.5-Flash SpreadSheet 从 50.5 降至 18.1。PDF p.9-10。
- **G8：过强，应改为“候选/机制证据，不足以判 G8”。** 论文有 persistent wiki、skill rollback 和多次迭代，但没有 chronological deployment stream、old-task retention probe、遗忘/非平稳环境变化实验；Gating 也只作用于 skill，不回滚 wiki。Algorithm 1 中的 rollback 是演化循环内的候选控制，不等同于 G8 的维护协议。PDF pp.4-6, 19。
- **可支持结论：需收窄。** “持久状态支持多功能 benchmark 的 skill evolution”成立，但五个 benchmark 是独立 evaluation cells；不能合并为同一 skill/SC 的 G5。还应补充负迁移与 OfficeQA/Qwen-3.5-4B 小幅退化。PDF pp.8-10。

**建议替换行**

`WikiSkill | per-benchmark 空集启动的 W→SU/SC compilation：immutable traces→persistent wiki→skill proposal→validation gating；skill 可回滚而 wiki 持续 | 各 benchmark 独立 D_train 的成功/失败 rollout traces；wiki 在该 benchmark 演化循环内累计 | 各 benchmark 的 unseen test split；另做 cross-model skill transfer | G1/G2；G7；G8 仅机制候选，未做 chronological retention/rollback protocol | 在五个独立 benchmark cells 与多个模型上支持 persistent wiki 辅助的 skill evolution；不得合并为 G5；存在 cross-model negative transfer`

**页码证据：** pp.2-7（方法与 split）、pp.8-10（main/cross-model 与负迁移）、p.11（wiki ablation）、pp.19-21（Algorithm 1、benchmark 统计）。

## SKILLRL

**核对结果概览**

- **evolve setting：正确，但应强调三个独立训练域。** 方法是 SKILLBANK 的 hierarchical general/task-specific skills、cold-start SFT、GRPO RL，以及在 validation 失败后动态新增/修订 skill；policy 和 skill library co-evolve。PDF pp.3-5。
- **source 经验范围：需修正为“分环境/分任务组”。** ALFWorld、WebShop、search QA 是三套分开的实验；search QA 训练只用 NQ+HotpotQA。表格当前“多任务 trajectory pool”可能被误读为一个大池。PDF pp.5-7。
- **target 测试范围：正确。** ALFWorld/WebShop 为各自环境评测；search QA 中 NQ、HotpotQA 为 in-domain，TriviaQA、PopQA、2Wiki、MuSiQue、Bamboogle 为 OOD。PDF pp.5-7。
- **NQ/HotpotQA→TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle：确认为同一 search-augmented QA 功能簇的 G3。** 这是本批中最明确的同功能跨数据集证据；不应升级为 G5。PDF p.7。
- **“同环境 task-type” G1/G2：正确。** ALFWorld 报告 Pick/Look/Clean/Heat/Cool/Pick2 子任务，WebShop 报告 score/success rate；skill growth 也按任务类别监控。PDF pp.6-7。
- **可支持结论：基本正确，但应补两点。** 第一，这是 SFT+RL 的 policy/skill 联合学习，不能与 frozen external skill 直接排名；第二，论文的跨 QA 泛化结论是 search strategy abstraction 的 OOD 保持，而不是同一外部 skill artifact 的 transfer。PDF pp.6-7。
- **continual：不成立。** 递归 skill evolution 是 RL 训练内的 validation-triggered 更新，不构成 G8 chronological deployment。

**建议替换行**

`SKILLRL | SKILLBANK + policy co-evolution；cold-start SFT 后 GRPO；validation 失败驱动新增/修订 skill | ALFWorld、WebShop、NQ+HotpotQA 分别构造经验和训练 | ALFWorld task types/WebShop；search QA OOD：TriviaQA、PopQA、2Wiki、MuSiQue、Bamboogle | ALFWorld/WebShop 内 G1/G2；search QA G3；无 G8 | 同功能搜索策略 OOD 和 policy/skill 联合学习有效；不与 frozen external skill 直接排名`

**页码证据：** pp.3-5（方法）、pp.5-7（setup、Table 1、Table 2 与 OOD 标注）。

## SkillEvolver

**核对结果概览**

- **evolve setting：正确。** 这是一个 meta-skill，驱动 CLI-agent 对单个 newly-arrived task 做 strategy-diversified exploration、contrastive patch、fresh-session Auditor 和 deploy-then-refine；R=2 时 13 Harbor trials，K=4、V=5。PDF pp.3-7, 14, 16。
- **source 经验范围：正确，但可补“单任务”。** 每次只针对一个 task 的 T_train 产生 K 次成功/失败 trial，然后 patch domain skill；不做跨任务 pooled trajectories。PDF pp.3-6, 14。
- **target 测试范围：基本正确。** SkillsBench 为 83-task paper scope 的 T_val/avg@5；KernelBench 为 3 个任务、correctness-weighted speedup。PDF pp.7-8。
- **SkillsBench 与 KernelBench：必须保持独立 evaluation cells，主表判断正确。** 论文明确说 KernelBench 的 metric、reward、任务性质不同，样本只有 3 个，且未跑 baselines，“不应被当作与 SkillsBench 平行的 second main benchmark”。PDF pp.7, 19-20。
- **G1/G2：可保留。** 每个 task 的 train→val 属于同任务内 unseen variants；SkillsBench 覆盖 15+ domains 是方法层面的 breadth，不是同一 skill 的跨 domain transfer。PDF pp.1-2, 9-10, 14。
- **“多 domain breadth”：正确。** 每个任务作者自己的 domain skill；不构成同一 artifact 跨 domain 复用。PDF pp.1-2, 9-10。
- **可支持结论：正确，但建议补负例。** 论文记录 invoice-fraud-detection 的 R=1→R=2 regression 和 pptx-reference-formatting 的全失败案例；headline 增益来自扩大可解集，而非逐任务 dominance。PDF p.19。
- **无 G6/G7：主表未标是对的。** headline 结果只有 Claude Opus 4.6 + Claude Code；GPT+Codex 只是 spot tests，不能写成 benchmark-scale cross-model 证据。PDF p.10。

**建议替换行**

`SkillEvolver | single-task/on-demand domain SU authoring by meta-skill；K=4 exploration、contrastive patch、Auditor、R<=2 refinement | 每个新任务 bounded T_train trials；无跨任务 pooled source | SkillsBench 83-task T_val avg@5；KernelBench 3-task speedup 为独立 cell | G1/G2；多 domain breadth；KernelBench 不可与 SkillsBench 合并 | bounded trial 内作者可复用 domain skill；非同一 skill 跨 domain transfer，非 benchmark-scale cross-model`

**页码证据：** pp.1-2、pp.3-7（method/setup）、pp.7-9（Tables 1-2）、pp.10（limitations）、pp.14-16（algorithm/protocol）、pp.19-20（KernelBench caution）。

## SkillEvo

**核对结果概览**

- **evolve setting：基本正确。** 对已有 production Skill 做多轮 self-renewing evolution；对象是 Tencent Cloud 的 9 个 production Skills / 98 reference files，Skill 被视为含 routing/knowledge 节点的 directed graph，配合 fact/structure governance。PDF pp.1-6。
- **source 经验范围：正确，但建议补“human-handled ticket”和 simulated interaction。** source 是 escalated-to-human 的 production tickets；由 Scenario Synthesizer 重建 constrained user，再做多轮 User Agent/Service Agent interaction，之后 Verifier 与 attribution 只把 Knowledge Gap 送入 revision。PDF pp.1-7。
- **target 测试范围：正确，且是真正的 chronological protocol。** 每个 scenario/skill 内 tickets 按时间排序，前 3/4 为 development，最后 1/4 作为 evaluation set；evaluation set 不进入演化循环，版本选择只用 dev。PDF p.7。因此 G8 成立。
- **“后续 ticket”表述可保留，但应写成 chronological held-out future tickets。**
- **fact/structure/regression/bloat probes：正确。** 指标包括 Overall TSR、exposed-intent accuracy、intent coverage、cross-round regression rate RegR 和知识 bloat。PDF pp.7-9。
- **可支持结论：基本正确。** 支持 multi-turn feedback 的持续演化、治理防退化和防膨胀；但应注明这是 simulation-based offline evaluation 加生产部署背景，dataset 不能公开，且 evaluation loop 终止于 reviewed candidate，经 human confirmation 后才上线。PDF pp.9-10, 27-28。
- **范围限制：** 结果属于 6 个 cloud-service 类别、9 个 skills，2,000 tickets；没有公共 benchmark 对照，不能外推为通用 skill-evolution 结论。PDF pp.1, 6-7, 13。

**建议替换行**

`SkillEvo | production Skill/graph continual update；multi-turn user simulation feedback + attribution + bounded edit + governance | escalated production tickets，按 scenario/skill 的时间流重建 simulated interactions | 同 scenario 内 chronological held-out future tickets；报告 TSR、RegR、bloat 等维护 probes | G8 | 时间外推、maintenance 与 governance 有效；属生产客服领域 9-skill 证据，不能泛化为公共 benchmark 或静态 held-out 结论`

**页码证据：** pp.1-7（method/setup/chronological split）、pp.8-9（Table 2/5/6）、pp.10（deployment/ethics）、pp.13（数据规模）、pp.27-28（架构与 human confirmation）。

## SkillHone

**核对结果概览**

- **evolve setting：正确。** SkillHone 是 continual harness：skill repository + skill-evaluation repository，persistent decision history 记录 diagnosis/revision/evidence/outcome，role-separated optimization/evaluation subagents，redacted reports。PDF pp.1-4。
- **source 经验范围：正确，但应补数量与来源。** 只用 WebShaper 公开数据集的 20 items，且与 GAIA、WebWalkerQA-EN disjoint；同时 raw open-web 比较系统都从同一 ClawHub/SkillHub community skill pool 出发。PDF p.4-5, p.8。
- **target 测试范围：正确。** GAIA text-only validation subset 和 WebWalkerQA-EN；另在 raw open-web 与 curated search 两个条件下比较，并另做 7 个 internal tool-mediated analysis scenarios。PDF pp.4-6。
- **G8：可支持。** 论文标题与机制就是 continual/cross-session evolution；ablation 显示去掉 decision history 使 GAIA/WebWalkerQA 从 64.6/66.4 降至 51.2/55.5，且附录展示 5 次迭代中 scoped revert/recovery。PDF pp.4-6, 8-10。
- **G6（search stack）：过强，建议降级。** “raw open-web vs curated search”是评测条件/检索栈差异，但不是固定 artifact 在同一 skill 协议下跨 harness 的 controlled G6 experiment。真正做的 portability 实验是 development controller Qwen3.6-35B-A3B 与 execution backbone 的分离，以及 skill bundle 不再优化直接迁移到 Claude Sonnet 4.6；后者是 G7-like cross-backbone/model transfer，主表遗漏了。PDF pp.4-5。
- **多功能/跨任务：不构成 G5。** GAIA 与 WebWalkerQA-EN 都是 search/research QA 功能簇；internal analysis scenarios 是另一组独立 deployment cells，不与公共 benchmark 合并。PDF pp.4-6。
- **可支持结论：应补搜索栈限定与关键数字。** SkillHone 在 raw open-web 优于 baselines，并超过 curated deep-research agent；但不同 search stack 是不同 evaluation condition。建议直接写论文数字：GAIA 64.6、WebWalkerQA-EN 66.4，cross-backbone GAIA 72.4。PDF pp.5-6。

**建议替换行**

`SkillHone | SU/SC continual refinement + persistent decision history；role separation/redacted evaluation | WebShaper 20 disjoint dev items + shared community search-skill pool；search decisions/history | GAIA text-only 与 WebWalkerQA-EN；raw open-web vs curated search 为不同 evaluation conditions；另 7 个 internal analysis scenarios | G8；G7-like Qwen3.6→Claude Sonnet transfer；不标严格 G6 | cross-session maintenance 和 decision-history 有效性；search/research QA 范围，非 G5`

**页码证据：** pp.1-4（method/history）、pp.4-6（setup/Table 1/ablation）、pp.5（cross-backbone Figure 3）、pp.8-10（repository workflow 与 recovery/revert）。

## 汇总性修改建议

1. **删除 WikiSkill 的 G6，保留 G7；G8 降级为“机制候选”。** 其 persistent wiki/rollback 支持迭代演化，但没有 chronological retention protocol（PDF pp.4-6, 19）。
2. **SKILLRL 的 search QA 明确保留为 G3。** NQ/HotpotQA→TriviaQA、PopQA、2Wiki、MuSiQue、Bamboogle 是同功能 search-augmented QA 跨数据集迁移，不升级 G5（PDF p.7）。
3. **SkillEvolver 的 SkillsBench 与 KernelBench 保持独立 cells。** 论文自己警告 KernelBench 样本小、metric 不同、无 baseline（PDF pp.7, 19-20）。
4. **SkillEvo 是本批中 G8 证据最清楚的论文。** 时间排序 + last-quarter held-out + RegR/bloat probes 成立（PDF pp.7-9）。
5. **SkillHone 保留 G8，删除或降级 G6，补 G7-like cross-backbone。** raw open-web/curated search 不是严格 harness-shift transfer（PDF pp.4-6）。
6. **五个 benchmark 或多 benchmark 的 WikiSkill、SkillEvolver 均为 breadth / independent cells，不是同一 skill 的跨功能迁移。** SkillEvo、SkillHone 则属于 continual/chronological track，不能与静态 held-out 直接合并。
