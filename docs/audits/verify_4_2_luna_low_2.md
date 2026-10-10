# 第 4.2 节表格核验：SkillAdaptor、SkillCAT、Trace2Skill、SkillPyramid、SkillX

范围：逐篇对照本地原始 PDF，检查表格的 `evolve setting`、`source 经验范围`、`target 测试范围`、G0-G8 层级和“可支持的结论”。以下只列错误、遗漏、过强表述及修改建议；不修改主综述。

## SkillAdaptor

- **G8 标注过强/缺少证据。** 表格写为 `G0/G8`，但论文的实验是固定 benchmark 上反复执行 skill adaptation，最多 10 轮，并以 collection 不变 3 轮早停；没有按真实时间顺序切分未来 ticket、旧任务 retention、遗忘、回滚或非平稳流的实验。因此最多可称为“迭代维护/多轮 adaptation”，不能据此归入严格的 chronological continual generalization G8。（PDF pp. 2, 9）
  - **建议：** 改为 `G0；迭代维护（不足以判 G8）`。若保留 G8，应明确标注“仅方法形态上的 G8 候选，论文未完成 chronological protocol”。

- **`source 经验范围` 写得过窄且缺少初始化条件。** “failed trajectory、故障步骤、候选 skill responsibility”描述了输入信号，但没有说明方法从一个已有 skill bank/skill collection 出发，并使用成功/失败结果和运行轨迹进行局部归因、修改与 qualification；它不是仅由失败轨迹驱动的单向修复。（PDF pp. 1-4, 9, 12）
  - **建议：** 改为“已有 skill bank 中的 skill + WebShop/PinchBench/Claw-Eval 的运行轨迹（失败定位、责任归因、成功/失败分数）”。

- **`target 测试范围` 的“后续任务”表述不准确。** 原文报告的是 WebShop、PinchBench、Claw-Eval 上的 benchmark 任务和多轮 adaptation 结果，不是明确的跨时间 future-task test split。（PDF pp. 3-4, 9, 11）
  - **建议：** 改为“同三类 benchmark 的任务评测；多轮适应后的任务分数”，不要写成 chronological target。

- **“能否维护现有 skill”基本正确，但结论边界遗漏。** 实验同时依赖局部失败归因、qualification gate 和固定工具/执行环境；结果不能单独证明跨 tool schema、跨 harness 或跨环境维护能力，也不能与从空库 acquisition 方法直接按同一泛化 setting 排名。（PDF pp. 2-4, 9-11）
  - **建议：** 在结论中补充“固定 benchmark/工具执行条件下的 local repair；不证明跨环境 portability，也不等价于从零 skill acquisition”。

## SkillCAT

- **`source 经验范围` 缺少数量和 mixed-outcome 条件。** 表格只写“SpreadsheetBench-Verified evolution split；成功/失败多 seed”，遗漏了论文明确的 200 个 evolution examples、每任务多 seed 产生 success/failure 对，以及 candidate patch 在 source-task clones 上的 assessment。（PDF pp. 2, 4-6）
  - **建议：** 改为“SpreadsheetBench-Verified 的 200 个 evolution examples；每任务多 seed 的成功/失败轨迹对；在 source-task clones 上 replay/筛选 patch”。

- **`target 测试范围` 将不同实验 cell 混在一行，且遗漏 split 语义。** 200 个 held-out SpreadsheetBench-Verified examples、full SpreadsheetBench、WikiTableQuestions OOD、DocVQA disjoint split 和 cross-model reuse 并非同一个 source→target 协议；DocVQA 还是多模态目标，cross-model 是 artifact/user-model portability 维度。（PDF pp. 5-7）
  - **建议：** 分写为“同 benchmark held-out：SpreadsheetBench-Verified；同功能 OOD：WikiTableQuestions；独立文档/视觉任务：DocVQA；另有 cross-model reuse”，不要把四者合成单一 target 范围。

- **G4 标注偏强。** 表格写 `G1/G2；G3；G4`，但论文没有把 SpreadsheetBench→WikiTableQuestions 或 DocVQA 明确构造成严格的同一 artifact、相邻功能 source→target transfer matrix；它报告的是 OOD/cross-domain/cross-model 结果。把 WikiTableQuestions 直接定为 G3 尚可作为 survey normalization，把 DocVQA 定为 G4 需要注明这是相邻功能解释而非论文原生层级。（PDF pp. 1-2, 5-7）
  - **建议：** 改为 `G1/G2；G3（WikiTableQuestions，规范化）；DocVQA 为相邻任务/独立 cell，G4 仅作弱解释`。

- **“同 spreadsheet workflow、表格问答相邻迁移”存在过强压缩。** 该结论把 extraction、assessment、topology/routing 和 cross-model 复用合并成一个泛化结论，而论文的消融只支持这些模块对结果的贡献，不证明同一模块分别学到了跨功能抽象。（PDF pp. 2-7）
  - **建议：** 改为“在 SpreadsheetBench 内 held-out、WikiTableQuestions OOD 和独立 DocVQA/cross-model cell 上表现出复用；不能把组合方法的总体收益归因于单一跨功能 skill abstraction”。

## Trace2Skill

- **`source 经验范围` 数值遗漏且把不同领域 source pool 并列为一个范围。** 表格只写“200 Spreadsheet evolution samples；另有 DAPO、VRDU、TSBench、generated DOCX source traces”，遗漏了 SpreadsheetBench 的 200 evolution/200 held-out 划分，并且这些是分别对应 spreadsheet、math、PDF/PPTX/DOCX transfer cell 的 source pool，不是一个 pooled experience distribution。（PDF pp. 4-6, 9, 19）
  - **建议：** 改为“SpreadsheetBench：200 evolution + 200 held-out；另设分开的 DAPO、VRDU、TSBench、generated DOCX source traces，各自对应独立 transfer cell”。

- **`target 测试范围` 需要按领域拆分，且“OfficeBench”不是所有 target 的统一终点。** 原文分别报告 SpreadsheetBench held-out/WikiTQ/HiTab、DAPO held-out/AIME、VRDU→VAREX、TSBench deck-disjoint OOD、generated DOCX→OfficeBench DOCX holdout；表格目前将它们串成单一 target 列，容易暗示所有 source 都迁移到所有 target。（PDF pp. 4-9, 19）
  - **建议：** 用分号列出独立 cell，并明确“每个 source→target 对单独评测”。

- **`G1/G2` 过于笼统，遗漏 G6/G7 维度。** 论文明确有 cross-model trace induction：由 Gemma-4 或 GPT-5.5 作为 author、Qwen3.5 作为 user 的实验；这不是单纯同 benchmark held-out，而是 model portability/author-user separation。现表只写 `G1/G2；G3；G4`，会漏掉重要的跨模型 setting。（PDF pp. 5-6, 15, 20-21）
  - **建议：** 改为 `G1/G2；G3；部分相邻功能 G4；另有 G7/cross-model portability`，并把 cross-model 从 target 任务泛化中分列。

- **“当前较完整的同功能跨数据集和相邻文档/表格迁移证据”略显过强。** 论文的结果确实覆盖多个 transfer cell，但附录同时记录 patch-induced off-source regression 和 patch interaction；因此不能只据 headline gain 概括为稳定、普适的迁移能力。（PDF pp. 9, 16, 18-19）
  - **建议：** 改为“提供多个分开的同功能/相邻任务 transfer cell；结果支持在这些协议下的迁移，但仍存在 patch interaction、off-source regression，且不构成 unrestricted G5”。

## SkillPyramid

- **`source 经验范围` 把“训练 split trajectories”写得过泛。** 论文还区分已有 skill consolidation/self-evolution 与 GAIA-Lite 的 web-mined skills；ALFWorld、WebShop、ScienceWorld 的任务协议并不应合并成单一 source distribution。（PDF pp. 5-6, 8-11）
  - **建议：** 改为“ALFWorld/ScienceWorld/WebShop 的任务轨迹分别用于层级 skill consolidation；GAIA-Lite 是另一个 web-mined skill/evaluation cell”。

- **`target 测试范围` 中 GAIA-Lite 的位置需要修正。** 表格把 `ALFWorld/ScienceWorld seen→unseen；WebShop；GAIA-Lite` 放入同一 target 列，但论文中 ALFWorld/ScienceWorld 的 seen/unseen 是明确的任务/variation split；WebShop 使用固定任务集；GAIA-Lite 是单独的 web-agent/knowledge-cell，不能被理解为 ALFWorld/ScienceWorld 的 held-out target。（PDF pp. 6, 8, 11）
  - **建议：** 拆成“ALFWorld/ScienceWorld seen→unseen；WebShop fixed evaluation；GAIA-Lite separate web-mined/evaluation cell”。

- **“同环境内 G3 的弱形式”不应保留为默认层级。** seen→unseen task/variation 更接近 G1/G2；G3 要求同功能不同 benchmark/dataset 的明确 source→target transfer。多 benchmark 并列（ALFWorld、WebShop、ScienceWorld、GAIA-Lite）也不等于跨数据集 artifact transfer。（PDF pp. 6-9, 11）
  - **建议：** 改为 `G1/G2；GAIA-Lite 为独立跨数据/环境 cell，不能仅凭并列结果升级为 G3`。

- **“collection organization 与 environment-internal transfer”结论需收窄。** 论文支持层级 consolidation、atomic/abstract skill ablation 和 seen/unseen 任务结果；不支持 unrestricted cross-environment generalization，也没有证明同一固定 collection 在不同 tool schema/harness 上的 portability。（PDF pp. 1-9）
  - **建议：** 改为“支持层级 collection organization 及 ALFWorld/ScienceWorld 内部 held-out transfer；WebShop/GAIA-Lite 结果应作为独立 evaluation cells，不合并成跨环境泛化”。

## SkillX

- **`source 经验范围` 与 `target 测试范围` 把三个 benchmark 的独立 train/test 协议合并了。** SkillX 从 seed training experience 构建三层 KB，但 BFCL-v3、AppWorld、τ²-Bench 的数据和 tool schema 各自不同；论文没有证明“一个在某 benchmark pooled training data 上构建的 KB”无修改迁移到另外两个 benchmark。（PDF pp. 3-6, 15-17）
  - **建议：** 改为“各 benchmark 的 seed/generated training experience 分别构建或扩展 KB；各 benchmark 的 test/评测 cell 分开报告”，不要写成统一 source→target。

- **表格把 `G6（tool schema/environment）` 写成泛化层级，但没有明确这是跨 benchmark 的接口可移植性证据。** 论文展示的是不同 tool-centric benchmark/interaction setting 下的结果，且使用各自的 skill extraction/filter/merge 和 benchmark evaluator；这不足以证明固定 collection 在不变成员、仅改变 schema/environment 的严格 G6 protocol。（PDF pp. 3-8, 15-17, 20）
  - **建议：** 改为“多工具 benchmark coverage；可视为弱 G6/跨 schema evidence，但不是严格固定 collection 的 schema-shift portability”。

- **“collection 在多工具环境中的覆盖和复用”基本可支持，但遗漏了 procedural/declarative 混合内容和 composition 约束。** 三层结构包含 planning、functional、atomic skill，且部分 skill 编码工具/环境特定知识；因此不能把全部收益归因于通用 procedural skill reuse。（PDF pp. 3-5, 17-18）
  - **建议：** 改为“多工具 benchmark 中三层 procedural/declarative KB 的检索与组合收益；需区分通用 workflow 复用和 tool/environment-specific knowledge”。

- **没有充分标注 `Avg@4/Pass@4/Pass@1` 的评测差异。** 不同 benchmark 使用不同指标与交互模式，不能将它们直接 pooled 成一个跨任务泛化结论。（PDF pp. 6-8, 15）
  - **建议：** 在 target/结论旁补充“按 benchmark、tool schema 和指标分别比较；不对异质指标求单一泛化等级”。

## 汇总性的表格修改建议

1. 将“明确的泛化 setting”与“可支持的结论”拆开写：`cross-model`、`cross-harness/tool schema` 是 portability 维度，不自动提升 G3/G4/G5。
2. 对 Trace2Skill、SkillCAT、SkillPyramid、SkillX，把多 benchmark 结果改写为独立 evaluation cells；只有论文明确给出 source→target split 时才写箭头式泛化。
3. 对 SkillAdaptor 删除或降级 G8；对 SkillPyramid 删除默认的 G3 弱形式；对 SkillCAT 将 DocVQA 的 G4 改为明确的 survey-level 弱解释；对 Trace2Skill 增补 G7/cross-model。
4. 所有“不能称 G5”“不等价于 acquisition”“不证明跨环境 portability”等边界判断应保留，它们与原论文实验协议一致，但必须同时注明各条边界对应的 PDF 页码。
