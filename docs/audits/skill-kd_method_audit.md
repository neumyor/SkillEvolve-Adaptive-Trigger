# SKILL-KD 方法核验批次：Contrastive Skill Distillation for LLM Agents

来源：`paper_generalization_settings.md` 中新引入的 SKILL-KD 论文。  
本报告对照 `papers/skill-kd_contrastive_skill_distillation_for_llm_agents.pdf`（13页，arXiv:2607.28048v2，Qiming Shi et al.）检查技能演化的 source/target 范围、G0–G8 泛化 setting、可支持的结论及 PDF 页码证据。

## 关键区分

- SKILL-KD 使用 teacher-student 执行轨迹对比蒸馏技能规则，且包含 case-specific drift 和 skill-bloat drift 两项修正项。
- 蒸馏载体为自然语言技能片段（rule library），而非 logits 或隐式表示。
- G3 任务泛化不适用：技能集已内部聚合，cross-task 迁移不是同一 collection 的 A→B transfer。

## 逐篇结论与建议替换文本

### 1. SKILL-KD

**PDF 页码证据（已核验）**
- p.1-2：方法概述——SKILL-KD 使用 teacher-student 执行轨迹对比（teacher-only、student-only、pairwise、batch 共四组）蒸馏可行动作技能规则；教师模型与学生模型来自不同模型家族及不同 tokenizer、预训练数据与行为特征。
- p.3-4：性能对比——teacher-only 58.3、student-only 60.1、pairwise 59.0、batch 59.4；SKILL-KD 达 66.8（+23.4），仅用 38 条规则（3,010 words），比 batch 少一半规则、少 40% 词汇。
- p.7-10：方法细节——教师 student 对比暴露更完整证据：pairwise 产生最长库（6,966 words）而 batch 更短（3,849 words）；skill-bloat drift：孤立 correct 但编码任务细节的 dated patches 在缺失 trace-link 历史时无法判断是否正确。
- p.9-10：动态精炼——SKILL-KD 在 DocVQA 边界从 `10 mg` 漂移至 `→ (kg)` 后再至 `%`；case-specific drift 通过 trace links 关联前序案例、规则库稳定。
- p.13：案例库——最终通过 38 条规则（DocVQA 50 条 / SpreadsheetBench 2,930 条）完成技能库精炼，其中 SpreadsheetBench 案例库记录坐标级修复（P6:Q6, R3:R4, C4:F6），包含真实 failures。

**逐列判定**
- `evolve setting`——当前“trajectory contrast distillation + drift-aware rule assembly”**基本正确**，但应明确标注四组变体基线。
  建议替换为：**teacher-student trajectory contrast 四组基线（teacher-only / student-only / pairwise / batch），其中 pairwise 与 batch 暴露更完整证据但规则更稀疏；skill-bloat 与 case-specific drift 提供校准项。**
- `source 经验范围`——当前“teacher/student execution traces”**基本正确但不完整**。除 traces 外，教师输入含 task instruction、observable task inputs 和 task-relevant background knowledge。
  建议替换为：**teacher student 执行轨迹；教师输入含 task instruction / observable inputs / background docs；学生输入含 ground-truth answers / validation selection / Pareto gate。**
- `target 测试范围`——当前“DocVQA / SpreadsheetBench / LiveMath / ALFWorld / LiveCodeBench / AIME”等 benchmark 目标**部分正确但易误读**。跨 benchmark 的单一 collection 下并非同一 source→target transfer。
  建议替换为：**每个 benchmark 独立 cell（DocVQA / SpreadsheetBench / LiveMath / ALFWorld / LiveCodeBench / AIME）；无跨 collection transfer。**
- `明确的泛化 setting`——当前“G4/G6/G7”**方向正确，但边界要更严**。p.7–10 的 drift handling 支持技能库稳定，但 not same-collection cross-task transfer。
  建议替换为：**G4（跨 task 的可移植性）——不同 benchmark 含源→目标 split 但非同一 collection；G6（环境/工具 schema/harness 可移植性）——可从跨模型实验读取；但无 G3/G5 证据。**
- `可支持的结论`——当前“支持轨迹对比蒸馏与 drift-aware 规则组装，不支持技能集跨 Task 泛化”**基本正确**。
  建议替换为：**支持从 teacher-student trajectories 蒸馏 actionable skill rules 的可移植性，以及 drift-aware rule assembly 的保持性；不支持同一 skill collection 的跨 task 函数迁移、技能集 scaling 结论。**

## 主要证据定位（节选）

| 论文 | 定位 |
|---|---|
| SKILL-KD | §3.1–3.2 pp.5–7；Table 1 p.6；Table 2 pp.7–8；Table 13 p.19 |