# 强→弱迁移·纯 Prompt/Skill 载体：扩大范围调研

调研日期：2026-10-09。范围：**强模型在开发/构建阶段产生经验，以文本技能、笔记、记忆、
工具模块或 harness 等 prompt 层产物保存；弱模型参数保持冻结，在新任务上使用这些产物**。
参数蒸馏（SFT/RL/on-policy distillation/activation steering）一律排除。

本报告是 `docs/terminalbench_training_free_teacher_student_survey_20261008.md` 的**全域扩检**：
不再限定 Terminal-Bench 场景，目标是确认该方向已发表、值得关注、有影响力的工作全貌。
与 2026-10-08 报告重复的条目只在此保留索引，细节以该报告为准。

## 检索方法与证据等级

1. arXiv API 16 条查询轴（strong-to-weak / training-free distillation / teacher–student
   agent / privileged feedback / weak model skill / smaller model reusable / self-improve
   web agent / guidelines from trajectories / capability transfer / frozen model experience
   / teacher agent student agent 等），按相关度取前 20–30，共去重浏览约 300 条标题；
2. Semantic Scholar 批量核对 28 篇短名单的引用数与发表 venue（2026-10-09 数据）；
3. 证据标记：**F** = 曾核对过全文（沿袭 2026-10-08 报告）；**A** = 本次核对在线摘要；
   **L** = 本地有原文。引用数对 2026 年新论文严重低估，只用于横向感受，不作为质量判据。

## 一、核心清单：强→弱 + 冻结学生 + prompt/skill 载体

### 1. 已发表、影响力最高的一批

| 工作 | arXiv | 引用¹ | venue/组织 | 机制要点 | 证据 |
|---|---|---|---|---|---|
| SkillWeaver | [2504.07079](https://arxiv.org/abs/2504.07079) | 177 | CMU 等 | 强模型探索网站→合成/调试可执行 API 技能→弱模型（GPT-4o-mini）直接调用 | F |
| SkillsBench | [2602.12670](https://arxiv.org/abs/2602.12670) | 298 | 大协作组（含 Dawn Song 组） | 87 任务×8 域配对评测"技能到底有没有用"；结论：curated Skills 使 18 种模型-harness 配置平均 +16.6pp，**弱模型加技能可追平无技能强模型** | A |
| AgentDistill | [2506.14728](https://arxiv.org/abs/2506.14728) | 28 | UIUC 等 | 教师 agent 自主产出可复用 MCP-Box 工具模块→小模型学生复用，全程无训练 | F |
| LEAP（Privileged AI Feedback） | [2410.05434](https://arxiv.org/abs/2410.05434) | 24 | ICLR，Cornell | 特权状态反馈教弱学生——**注意：学生要 fine-tune，按本调研标准排除**，仅作为"教师特权信息设计"的思想来源 | A |

### 2. 2026 年直接同设定的新工作（引用尚少，属当前活跃前沿）

| 工作 | arXiv | 机制要点 | 与其他工作的差异 | 证据 |
|---|---|---|---|---|
| AgentBrew | [2607.16851](https://arxiv.org/abs/2607.16851) | 失败触发教师→学生感知 note→Ralph 环境验证准入→终身记忆→冻结 serve，教师退出 | 唯一同时强调"学生感知合成"+"环境验证准入"耦合的；TB2.0 有实验 | F |
| SKILL-KD | [2607.28048](https://arxiv.org/abs/2607.28048) | 学生失败+教师轨迹对比→技能补丁→学生重跑验证→防漂移整合 | 教师非 oracle；五域评测，4B 学生宏平均 43.5→66.8 | F |
| AMD | [2608.07169](https://arxiv.org/abs/2608.07169) | 教师成功轨迹→Workflow/Subtask/Function 三层记忆→冻结学生 | 严格 cross-split 下 Qwen3-4B 在 AppWorld 16→41；中间粒度贡献最大 | F |
| Concept Distillation | [2408.09365](https://arxiv.org/abs/2408.09365) | 弱模型错误→强模型归纳规则→验证集筛选→入提示 | NAACL 2024；该方向最早期的文本规则 strong-to-weak 先例 | F |
| Inference-Time Distillation | [2512.02543](https://arxiv.org/abs/2512.02543) | 教师只在小子集出 demo→学生检索 demo 做 ICL + 自一致性级联 | Stanford；"部署敏捷性"视角：教师小规模采样后立即退出，工程性强 | A |
| MemCollab | [2603.23234](https://arxiv.org/abs/2603.23234) | 对比不同 backbone 的轨迹蒸馏出**跨模型共享记忆**，剥离模型特异偏差 | 首个正面处理"记忆与 backbone 耦合"的工作；对应 AgentBrew Figure 1 的模型特异性发现 | A |
| AI4AI at Test-Time | [2608.12307](https://arxiv.org/abs/2608.12307) | 强 builder 构建路由/prompt/确定性程序/检查器→冻结弱 target | 载体是整个 harness；理论-of-mind benchmark | F |
| SkillX | [2604.04804](https://arxiv.org/abs/2604.04804) | GLM-4.6 轨迹→planning/functional/atomic 分层技能库→弱 agent | 72 引用，传播较快 | L |
| TED | [2603.26778](https://arxiv.org/abs/2603.26778) | 教师对比学生推理与正解→生成压缩上下文经验 | 多模态推理域 | F |
| ASDA | [2603.16112](https://arxiv.org/abs/2603.16112) | 教师诊断学生错误→流程/代码模板/例题技能 | 金融推理域 | F |
| SPARK（Evidence over Plans） | [2605.09192](https://arxiv.org/abs/2605.09192) | 教师 Docker 实测→SKILL.md；PDI 指数区分"环境证据"vs"未验证计划" | 强调技能必须在交互后形成 | F |
| SkillsVote | [2605.18401](https://arxiv.org/abs/2605.18401) | 历史 TB-Pro 轨迹技能库→新终端任务离线复用 | GPT-5.4 mini +5.8pp（avg@5） | F |
| VaG（When Self-Evolution Backfires） | [2608.05810](https://arxiv.org/abs/2608.05810) | 技能**预提交门控**防污染，冻结库跨模型迁移，TB2 严格留出 | 安全准入视角，与 Ralph 验证互补 | F |
| P2Skill | [2608.14094](https://arxiv.org/abs/2608.14094) | 云端大模型迭代修订本地 SLM 的路由技能 | 隐私场景；云端教师测试时仍参与 | F |
| RSI-Router | [2609.34712](https://arxiv.org/abs/2609.34712) | 大小模型轨迹对比→模型特异技能+子任务路由 | 测试时大模型仍承担部分步骤 | F |
| Trace2Skill | [2603.25158](https://arxiv.org/abs/2603.25158) | 批量轨迹→技能目录/SOP，跨模型跨任务测试 | 含弱→强方向，非纯 strong-to-weak | L |
| From Multi-Agent to Single-Agent | [2604.01608](https://arxiv.org/abs/2604.01608) | 分析性工作：何时技能蒸馏有益 | 10 引用 | L |

### 3. 同模型（无强弱不对称）、但机制与 AgentBrew 组件直接相邻

这批工作不在"强→弱"范围内，但去掉教师后就是 AgentBrew 的对应物，写 related work 时应引用并划清边界：

| 工作 | arXiv | 对应 AgentBrew 的哪个组件 | 证据 |
|---|---|---|---|
| ExpeL | [2308.10144](https://arxiv.org/abs/2308.10144) | 经验→insight→检索（1079 引，AAAI，奠基） | A |
| Agent Workflow Memory | [2409.07429](https://arxiv.org/abs/2409.07429) | 轨迹→可复用 workflow 记忆（377 引，ICML） | A |
| Mistake Notebook Learning | [2512.11485](https://arxiv.org/abs/2512.11485) | 失败聚类→结构化"错误笔记"，批次改善才准入（≈无教师的 Ralph 准入），training-free，ACL | A |
| DIVE | [2608.12486](https://arxiv.org/abs/2608.12486) | 冻结模型技能演化，明确**无教师**；多种群防过拟合 | A |
| EDV（Execute-Distill-Verify） | [2606.24428](https://arxiv.org/abs/2606.24428) | "自证陷阱"：第三方蒸馏+验证，防错误经验入库 | A |
| What Deserves Memory | [2508.03341](https://arxiv.org/abs/2508.03341) | 自适应记忆蒸馏，什么值得入库（38 引，ACL） | A |
| SkillRevise | [2606.01139](https://arxiv.org/abs/2606.01139) | 轨迹条件化技能修订（EMNLP 2026 Findings） | A |
| ReasoningBank / ACE / SkillHone / SkillOpt 等 | 见 2026-10-08 报告第三节 | 终身记忆 / 上下文维护 / 技能演化 | L |

### 4. 评测与生态资源（判断"技能迁移有效性"的证据基础）

- **SkillsBench**（[2602.12670](https://arxiv.org/abs/2602.12670)，298 引）：当前"技能是否真有用"最系统的配对评测；其"弱模型+技能≈强模型裸跑"的结论是整个方向的 headline 证据，也是必须对照的评测协议。
- **What Keeps Agent Skills from Being Reusable?**（[2608.08453](https://arxiv.org/abs/2608.08453)）：138K 公开 SKILL.md 实证审计，91.8% 含缺陷（路由元数据弱、正文臃肿等）——说明**技能质量本身是瓶颈**，直接支撑"学生感知合成 + 环境验证"的必要性。
- **Distilling Agentic Systems: A Roadmap**（[2609.36630](https://arxiv.org/abs/2609.36630)，2026-09）：新综述，把 "Agent Distillation" 定义为按知识保留位置分类（模型内/工件/harness/跨基底），是写 related work 的现成组织框架。
- **Rethinking the Evaluation of Harness Evolution**（[2607.12227](https://arxiv.org/abs/2607.12227)）：负面证据（框架演化不优于匹配预算的 test-time scaling），沿 2026-10-08 报告。

### 5. 明确排除（名字像但不满足"无参数更新"或"强→弱"）

- **LEAP / Privileged AI Feedback**（[2410.05434](https://arxiv.org/abs/2410.05434)，ICLR）：摘要自述 "iterative **fine-tuning** framework"——教师设计再好，学生靠梯度更新，排除；
- **Causal Distillation**（[2505.19511](https://arxiv.org/abs/2505.19511)）："train the smaller model"，排除；
- **LLMs Can Self-Improve at Web Agent Tasks**（[2405.20309](https://arxiv.org/abs/2405.20309)）：合成数据 SFT 到小模型，排除；
- **AgentTuning / on-policy distillation 家族**（含 2605.13643 Prefix Teach、2607.04763、Skill-SD、SIKeD 等 2026 批量涌现的 OPD 论文）：梯度更新，排除；
- **Neural Procedural Memory**（[2606.29824](https://arxiv.org/abs/2606.29824)）：activation steering，非 prompt 层，排除；
- **SkillFM / SkillOS / Write-Execute-Refine**：训练生成器或 RL 优化，排除；
- **WESE**（[2404.07456](https://arxiv.org/abs/2404.07456)）：弱探索助强利用，方向相反。

## 二、影响力判断（回答"值得关注的有影响力工作"）

按"已发表 + 传播度 + 与设定直接相关"排序，建议重点精读：

1. **SkillsBench**（298 引）——方向有效性 headline 证据 + 评测协议；
2. **SkillWeaver**（177 引）——可执行技能载体 + 弱模型部署的最成熟完整工作；
3. **AgentDistill**（28 引）——training-free agent 蒸馏的命名性工作，工具模块载体；
4. **Concept Distillation**（NAACL 2024）——文本规则 strong-to-weak 的源头，引用会继续涨；
5. **MemCollab** ——"记忆与 backbone 解耦"问题与 AgentBrew Figure 1 呼应，潜在高影响；
6. **Inference-Time Distillation**（Stanford）——工程部署视角（成本/敏捷性），实务影响力大；
7. **AgentBrew / SKILL-KD / AMD / VaG**——2026 直接同设定核心，引用尚少但在涨；
8. 背景必引：**ExpeL**（1079 引）、**AWM**（377 引）、**Voyager**（技能库源头）。

行业脉络补充：Anthropic 的 Agent Skills（SKILL.md 规范，2025-10 发布）是该方向的产业催化
剂——SkillsBench、138K 审计、SPARK 的 SKILL.md 载体都建立在该规范上。

## 三、与 2026-10-08 报告的关系及新增结论

- 2026-10-08 报告回答"Terminal-Bench 上有没有先例"；本报告回答"全域有哪些已发表强→弱
  prompt/skill 工作"。两者结论一致：**设定已存在多条先例，新颖性必须落在机制或受控比较上**。
- 本次扩检的净新增：Inference-Time Distillation、MemCollab、MNL、DIVE、EDV、SkillRevise、
  SkillsBench（作为独立评测工作）、138K 技能审计、Agent Distillation roadmap 综述，
  以及 LEAP 等"看似相关实则参数蒸馏"的排除边界。
- 值得注意的两个趋势：(a) 2026 下半年"记忆跨模型可移植性"（MemCollab）与"技能质量
  审计"（138K）开始成为独立问题；(b) 排除名单中的 on-policy distillation 论文数量
  爆炸（≥10 篇/季），说明"参数蒸馏 vs prompt/skill 载体"是当前社区正面的分岔口，
  相关工作写作时值得显式讨论。

¹ Semantic Scholar 引用数，2026-10-09 查询；2026 年论文严重低估，仅作相对参考。
