# 第 4.2 节表格核验报告

核验对象：SkillWeaver、SkillOpt、SkillGen、SkillReducer、SkVM、Who Grades the Grader?  
依据：仓库内对应原始 PDF；页码为 PDF 页码。以下只列错误、遗漏、过强表述和建议修改，不修改主综述。

## SkillWeaver

- **错误：泛化层级把跨网站写成 G3/G6。** 论文明确说“exploration on each website environment separately”并据此为每个网站得到独立 API library；WebArena 的 5 个网站和 Online-Mind2Web 的 4 个真实网站不是同一个 library 从 source website 迁移到 target website。表格中的“跨网站 G3/G6”因此不能由论文实验支持。PDF p.5 说明逐网站单独探索；pp.6–8 给出 WebArena/真实网站结果及分析。
- **错误/过强：target 测试范围写成“WebArena、Online-Mind2Web、real websites”而未说明其实际子集。** 真实网站部分不是整个 Online-Mind2Web，而是 4 个可访问且至少有 8 个任务的网站，共 57 个任务；WebArena 结果也按 5 个站点分别评测。建议改为“WebArena 5 websites；Online-Mind2Web 中筛选的 4 个 live websites/57 tasks”。PDF p.5。
- **遗漏：应注明 source 经验是无外部监督的 website-specific exploration，而非目标测试集经验。** 每个网站进行 160 次 GPT-4o exploration iteration，既尝试 proposed skill，也测试已有 skill，并允许组合之前生成的 API。PDF p.6。
- **遗漏：所谓跨 agent transfer 实际是跨模型，不是跨网站。** 论文把 GPT-4o 生成的 API library 直接给 GPT-4o-mini，保持 agent 设计不变；这支持 G7-like model transfer，不支持 G6 harness transfer。PDF pp.6–8。
- **建议行修改：** `website-specific exploration -> same-website WebArena/live-site tasks；G1/G2-like within-site evaluation + G7-like GPT-4o→GPT-4o-mini transfer；不标 G3/G6 cross-website transfer`。
- **可支持结论应收窄为：** website-specific API collection 能提高同一网站/同一模拟站点内的任务成功率，并可在相同 agent 设计下从 GPT-4o 转移到 GPT-4o-mini；不能称为跨网站 skill reuse 或跨 harness portability。PDF pp.7–8。

## SkillOpt

- **遗漏：source 经验范围应明确为每个 benchmark 的 train split rollout，而非笼统“train rollout”。** 论文定义为 `D_train` 产生 rollout evidence，`D_selection` 只用于 validation gate，`D_test` 仅最终报告；默认数据集切分为 2:1:7（当 benchmark 未另行规定时）。PDF pp.4、8、20–21。
- **表格中的 G1/G2 标注基本可保留，但应说明它对应 benchmark 内 held-out test，而不是论文统一定义的单一 task-family split。** 论文报告的是各 benchmark 的 deterministic train/selection/test protocol，因而 G1/G2 需要依 benchmark 的实例/模板结构具体解释，不能仅由“unseen test”自动推出 G2。PDF pp.4、8、20。
- **遗漏：跨 benchmark transfer 只有 nearby math 的一个方向。** 实验是 OlympiadBench skill → Omni-MATH，且未进一步优化；这支持同功能/近邻任务的 G3-like transfer，不支持更宽的 cross-function transfer。PDF pp.8、12。
- **遗漏：跨 harness 的证据是 Codex↔Claude Code，且 target model 固定为 GPT-5.5；跨 model 的证据是 GPT-5.4→GPT-5.4-mini/nano。** 建议将 G6 与 G7 的证据分别写清，不合并成笼统 portability。PDF pp.8、12。
- **可支持结论应避免“泛化”无条件化。** 论文自己说明最终 artifact 是单一 benchmark/domain skill；其 transfer 只覆盖 model scale、两个 harness 和 nearby math。建议改为“支持有限的 cross-model、cross-harness 与同功能近邻 benchmark transfer”，不要扩写为一般 artifact portability。PDF pp.12、16、20。

## SkillGen

- **错误：表格中的“部分 G6/G7”包含了论文没有报告的 G6。** 论文的 transfer analysis 是把某一 source model 生成的 skill 在另一 evaluator model 上执行；没有 cross-harness 或 environment-schema 变更实验。因此这里应删除 G6，只保留 G7-like cross-model transfer。PDF pp.1、7、13。
- **source 经验范围不够准确。** 论文把 skill-training data 分成 induction subset 和 construction-time verification subset；verification subset 用于 candidate refinement/selection，不能与最终 held-out test 混写。PDF pp.2–3、16。
- **遗漏：ALFWorld IOD/OOD 的含义有明确协议。** `valid_seen` 是 task types 与 train overlap 的 in-distribution split；`valid_unseen` 是 novel task types 的 OOD split。建议把当前“ALFWorld IOD/OOD”改成“ALFWorld valid_seen/valid_unseen；其中 valid_unseen 更接近 G2-like unseen task family”。PDF p.16。
- **G0 表述需要限定。** paired with/without-skill evaluation 确实逐实例记录 repair 与 regression，但论文的主要 construction/evaluation 不是“同一失败实例的 repair”这一狭义 G0 setting；它是固定 skill intervention 在 held-out instance 上的 paired comparison。建议将 `G0` 改成“paired intervention / G0-like evaluation”，避免把全部结果称为 same-instance repair。PDF pp.1、3、6–7。
- **可支持结论应补充负迁移限制。** 论文报告 accepted skill 在 ALFWorld OOD 和 ChemLLMBench yield prediction 上仍可能造成 regression，verification gate 并不能保证最终 test 无回归。当前“能否修复失败且不伤害原本成功的实例”若被读成已保证“不伤害”，表述过强。建议改为“显式测量 repair/regression，并在平均 held-out 上取得正增益，但仍存在 held-out regression”。PDF pp.13、19。

## SkillReducer

- **错误：source 经验范围把两个不同规模混在一起。** 55,315 是用于生态/经验分析的 Wild skill corpus；实际两阶段压缩与 Gate 2 task evaluation 作用于 600 skills，另有 198 wild skills 只做规模/Stage 1 相关验证。建议改为“55,315-skill corpus for empirical study; 600 skills for end-to-end compression evaluation”。PDF pp.1、3、9–10。
- **错误/遗漏：target 测试范围不是笼统“functional retention、SkillsBench、cross-model/framework”。** Gate 2 为每个 skill 生成 5 个 evaluation tasks；SkillsBench 是独立的 87-task deterministic pytest check；cross-model evaluation 是 30 skills、5 models/4 families；独立 framework 是 OpenCode。建议把这些拆开写。PDF pp.9–11。
- **G6/G7 标签需要更精确。** 跨 5 个 model、4 个 family 支持 G7-like model portability；迁移到 OpenCode 支持 framework/harness portability，可记 G6-like，但论文明确说明所有 600 skills 都使用 Anthropic skill protocol，Cursor/Windsurf 未测试，因此不能外推为一般平台 portability。PDF pp.11、13。
- **可支持结论过强：`compression retention` 不等同于 discovery 或 task-generalization。** 论文测的是压缩后相对原 skill 的功能保持，以及固定的 generated task/SkillsBench checks；它不是从 source 任务学到 skill 后在独立 task family 上进行 acquisition/generalization 的实验。当前表格末尾“不是 discovery 泛化”方向正确，建议进一步写成“压缩保真/跨模型与有限 framework retention”，不要将其与普通 G1/G2 skill evolution 结果并列。
- **建议行修改：** `existing skill compression; 600 evaluation skills (55,315 only corpus analysis) -> 5 generated tasks/skill, SkillsBench 87 tasks, 30-skill cross-model set, OpenCode; G6-like/G7-like retention`。PDF pp.3、9–11。

## SkVM

- **遗漏：source 不是“经验范围”意义上的 trajectory pool。** SkVM 的输入主要是原始 skill/code、capability profiling 和 model-harness profile；论文做的是 compilation/runtime adaptation，不是从 rollout experience 学 skill。表格当前写“capability profiling、skill code、model-harness profile”基本准确，但建议显式标注“无 skill acquisition source trajectories”。PDF pp.1–2、6–7。
- **遗漏：target 测试范围应区分总 task 数与 staged skill evaluation。** 论文总评估覆盖 8 个 LLM、3 个 harness、SkillsBench 与 PinchBench，共 118 tasks；其中 compilation effectiveness 的 staged breakdown 重点展示 14 个 skill categories/skills，并对每个 task 生成 5 个 diverse input instances。不要把“118 tasks”读成 118 个独立 evolved skill。PDF pp.1、7、10。
- **G6/G7 基本准确，但结论必须限定为 execution portability/efficiency。** 模型和 harness 是实验轴，SkVM 还改变了编译产物、environment binding 和 runtime；这支持跨载体执行效果，不证明固定语义 skill 在不同任务功能上泛化。PDF pp.1–2、10–13。
- **建议补充负面结果，避免只写“portability/efficiency”。** 原始 skill 在约 15% tasks 上因启用 skill 反而降分，另有约 17% 不变；SkVM 的目标正是修复 model/harness mismatch。表格结论可改为“在异质 model/harness 上改善 skill execution compatibility、completion、tokens 和 latency，且原始 skill 存在显著 mismatch”。PDF pp.1、2、10。

## Who Grades the Grader?

- **source 经验范围表述不完整。** 论文使用三种 disjoint split：large unlabeled train outputs、10-item anchored dev/reference set，以及 locked held-out test；dev 的 ten anchors 是唯一 supervised signal，train 还用于 detector consensus 和 co-evolution skill-loop grading。当前“train outputs、tiny anchor dev”遗漏了 large unlabeled train 在 metric evolution 中的作用。PDF pp.2–3。
- **target 测试范围应拆成三类 task family。** locked test 覆盖 MBPP+、Spider 2.0-Snow 和 reference-free report generation；报告生成没有 accurate metric，使用 RAQS 作为 imperfect reference，并另加 independent stronger LLM judge 做外部 audit。当前“locked test、independent judge、reference-free reports”方向正确，但建议明确 independent judge 主要是 report-generation outer audit，不是所有 locked-test 的统一 evaluator。PDF pp.1–3、Appendix A pp.6–7。
- **错误/过强：`evaluator G3/G5-like reliability`。** 论文没有做 source task family → disjoint target task family 的 artifact transfer，也没有证明 G3/G5 task transfer；它做的是同一 task family 内 train/dev/test 的 evaluator validity/transfer，以及 skill-loop lift 相对 oracle/rubric 的 recovery。建议改为“evaluator validity on locked held-out splits; not task-transfer G3/G5”。PDF pp.2–3、Appendix A pp.6–7。
- **可支持结论应避免把 88–110% 写成普通泛化。** 该比例是 Double Ratchet 相对 ground-truth-driven oracle 或 best-available rubric 的 held-out lift retention；在 report task 上 reference 是 imperfect RAQS，不能解释为 metric 在跨任务上泛化。PDF p.1、Appendix G pp.20–21。
- **建议行修改：** `metric + skill-loop co-evolution; unlabeled train outputs + 10 anchored dev items + locked test; MBPP+/Spider 2.0-Snow/report held-out, report additionally audited by independent judge; evaluator validity/Goodhart resistance on held-out task families, not G3/G5 task transfer`。PDF pp.2–3、Appendix A/D/G。

## 汇总建议

最需要在主表中改动的标签是：

1. SkillWeaver：删除“跨网站 G3/G6”，改为 website-specific G1/G2-like，并单列 GPT-4o→GPT-4o-mini 的 G7-like transfer。
2. SkillGen：删除 G6；将 G0 改成 paired intervention/G0-like，并明确 valid_seen/valid_unseen 与 held-out regression。
3. SkillReducer：区分 55,315 corpus analysis 与 600 end-to-end evaluation。
4. Who Grades the Grader?：删除 G3/G5-like task-transfer 说法，改成 evaluator held-out validity/Goodhart audit。
5. SkillOpt 与 SkVM 的 G6/G7 方向基本成立，但均应把 model transfer、harness transfer、nearby-benchmark transfer 分列，避免合并成无条件 portability。
