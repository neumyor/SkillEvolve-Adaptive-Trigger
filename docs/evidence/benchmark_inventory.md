# Skill Evolve Benchmark Inventory

## 0. Scope and method

本文件只调研 `papers/` 目录中 21 篇论文实际使用的 benchmark、数据集或生产评测场景。所有事实优先依据对应论文原始 PDF；PDF 页码使用文件内页码。本文的“任务功能簇”是综述规范化分类，不是 benchmark 作者的官方分类。

需要区分三种关系：

- **同一任务功能、不同数据集**：例如 NQ、TriviaQA、PopQA 都是开放域事实问答；它们可以用于检验数据集迁移，但不能自动证明跨任务泛化。
- **同一数据集、不同泛化 split**：例如 ALFWorld 的 `valid_seen` 与 `valid_unseen`，测试的不是同一个泛化难度。
- **真正不同任务功能的跨 benchmark**：例如 spreadsheet manipulation → table QA、document extraction → document editing、search QA → embodied interaction。这类迁移更接近跨功能泛化，但还需要检查共享的工具、格式和推理模板。

## 1. Task-function taxonomy

| 任务功能簇 | 核心任务 | 代表性 benchmark / 数据集 | 典型输出或反馈 |
|---|---|---|---|
| **F1：交互式家庭/具身操作** | 在状态化环境中完成取放、清洁、加热、冷却等多步目标 | ALFWorld；ScienceWorld | simulator state、任务完成、动作合法性 |
| **F2：网页导航与网站工作流** | 浏览、点击、搜索、填写、购买、跨网站操作 | WebShop；WebArena；Mind2Web；Online-Mind2Web | 页面状态、功能正确性、人工/自动成功判断 |
| **F3：工具调用与多轮用户交互** | 按工具 schema 执行 API，处理用户澄清、约束和多轮对话 | AppWorld；BFCL-v3；τ-Bench / τ²-Bench；MCPBench；Claw-Eval；PinchBench | tool execution、状态变化、Pass@k、人工或规则评测 |
| **F4：电子表格与办公文档操作** | 修改 xlsx/docx/pptx，保持结构并满足内容约束 | SpreadsheetBench / SpreadsheetBench-Verified；OfficeBench；TSBench；VRDU→VAREX | 文件/结构验证、JSON/视觉抽取、ANLS、功能测试 |
| **F5：文档理解与文档问答** | 从长文档、表格、表单或图像文档中检索、抽取和回答 | OfficeQA；DocVQA；WikiTableQuestions；HiTab | exact match、ANLS、结构化答案 |
| **F6：开放域搜索与研究问答** | 搜索网页、整合证据、回答单跳或多跳问题 | SealQA；BrowseComp；GAIA；WebWalkerQA；NQ；TriviaQA；PopQA；HotpotQA；2Wiki；MuSiQue；Bamboogle；Bamboogle | exact match、证据正确性、检索/引用质量 |
| **F7：数学推理与竞赛问题** | 多步数学推理、计算、证明或选择题 | LiveMathematicianBench / LiveMath；AIME；DAPO；LiveBench-Math；OlympiadBench；Omni-MATH | exact/answer accuracy、Avg@k |
| **F8：代码与程序合成/优化** | 生成函数、SQL、GPU kernel 或可执行程序 | LiveCodeBench；KernelBench；MBPP+；Spider 2.0-Snow | hidden unit tests、execution comparison、functional correctness |
| **F9：科学与生物医学问答/预测** | 科学知识问答、化学属性/产率预测、生物医学 QA | ChemLLMBench；PubMedQA | answer accuracy、property/yield accuracy |
| **F10：开放式报告生成与评测器可靠性** | 生成没有唯一答案的报告，或演化评价指标本身 | reference-free report generation；Who Grades the Grader? 的 MBPP+/Spider/报告任务 | rubric、independent judge、anchor/generalization |

### 1.1 哪些 benchmark 实质上属于同一类任务

**开放域搜索/问答：** NQ、TriviaQA、PopQA、HotpotQA、2Wiki、MuSiQue、Bamboogle、SealQA、BrowseComp、GAIA、WebWalkerQA 都涉及搜索或证据整合，但并非同质。NQ/TriviaQA/PopQA 更接近单跳事实问答；HotpotQA/2Wiki/MuSiQue/Bamboogle 更接近多跳组合；SealQA/BrowseComp/GAIA/WebWalkerQA 的网页开放性、搜索栈和答案验证方式不同。

**网页交互：** WebShop、WebArena、Mind2Web 和 Online-Mind2Web 都属于网页任务，但 WebShop 偏电商商品检索与购买，WebArena 是多应用网站工作流，Mind2Web 更偏真实网页导航/操作轨迹。因此可以放入同一 F2 大类，但不能默认属于同一个 matched cell。

**具身/状态化交互：** ALFWorld 与 ScienceWorld 都是长程交互环境，但 ALFWorld 主要是家庭物体操作，ScienceWorld 是科学实验/世界状态操作。二者属于同一交互式任务大类，而不是同一 task family。

**表格/文档处理：** SpreadsheetBench、TSBench、OfficeBench、VRDU、VAREX、DocVQA、WikiTableQuestions、HiTab 都处理表格或文档信息，但操作目标不同：文件编辑、演示文稿编辑、结构化抽取、视觉问答和表格问答不能只用一个“document transfer”标签。

**工具调用：** AppWorld、BFCL-v3、τ-Bench/τ²-Bench、MCPBench、Claw-Eval、PinchBench 均有工具调用成分，但工具 schema、用户交互和环境状态不同。它们适合组成 tool-agent track，不适合直接合并为一个任务分布。

## 2. Benchmark-by-paper inventory

| 工作 | 实际使用的 benchmark / 场景 | 任务功能簇 | 评测或 split 事实 | 主要泛化解释 |
|---|---|---|---|---|
| CoEvoSkills | SkillsBench | 多专业技能增强任务；包含软件、科学分析等专业领域 | 85 tasks；每 task 有 deterministic verifier；opaque pass/fail oracle（PDF pp. 7–8） | benchmark 内 held-out；另测跨模型和跨 harness |
| EvoSkill | OfficeQA、SealQA、BrowseComp | F5 文档问答 + F6 搜索问答 | OfficeQA/SealQA 使用 train、validation、held-out test；SealQA skill 转移到 BrowseComp（PDF pp. 1–10） | 同 benchmark held-out；SealQA→BrowseComp 是相邻/跨 benchmark 搜索型迁移，不是跨任务功能 |
| GEPA | HotpotQA、AIME-2025、LiveBench-Math、IFBench、HoVer、PUPA | F6、F7，以及 instruction following、隐私委派、检索验证 | 六个任务分别有 train/validation/test；优化 prompt/program（PDF pp. 1–16） | 任务级 held-out；跨 benchmark 是多功能 prompt-system breadth，不是 external skill transfer |
| MetaSkill-Evolve | OfficeQA、SealQA、ALFWorld | F5、F6、F1 | 三个 benchmark；held-out test；task-skill fast loop + meta-skill slow loop（PDF pp. 1–10） | 同 benchmark task-level；覆盖三个功能簇，但不是一个 learned skill 在三类任务间的迁移 |
| SKILL0 | ALFWorld、Search-based QA（NQ、HotpotQA 训练；其余搜索数据集 OOD）、WebShop | F1、F2、F6 | ALFWorld 有 3,827 instances、六类家庭活动；NQ/HotpotQA in-domain，其余 search QA OOD（PDF pp. 5–9、18–19） | 环境内 task generalization；同功能搜索数据集 OOD；参数内化 |
| SkillAdaptor | WebShop、PinchBench、Claw-Eval | F2 + F3 | 三个 backbone；OpenClaw runtime；温度为 0；WebShop 遵循官方设置（PDF pp. 1、3–9） | 现有技能集合上的 local repair/continual maintenance；不是跨功能迁移 |
| SkillCAT | SpreadsheetBench-Verified、SpreadsheetBench、WikiTableQuestions、DocVQA | F4 + F5 | SpreadsheetBench-Verified 200 evolution/200 held-out；DocVQA 使用 disjoint split；WikiTableQuestions 作为 OOD（PDF pp. 1–7） | spreadsheet 内 held-out、table QA OOD、文档视觉问答 transfer；部分是相邻功能而非完全不同功能 |
| SkillEvo | Tencent Cloud technical-support production data | F3/F6 的多轮技术支持 | 六类 cloud-service、9 production skills、98 reference files；tickets 按时间分四份；multi-turn simulation（PDF pp. 3–9） | chronological/continual generalization；不是公开 benchmark 的随机 held-out |
| SkillEvolver | SkillsBench；KernelBench | F1–F10 混合专业任务；F8 GPU kernel 优化 | SkillsBench 83-task subset、15+ domains；KernelBench 3 tasks：deepnarrowmlp、shufflenet、gru（PDF pp. 6–9） | task-level/family-level adaptation；KernelBench 是独立代码优化 cell，不能和 SkillsBench 合并 |
| SKILLGEN | ALFWorld IOD/OOD、ScienceWorld、Mind2Web、SocialMaze、LiveCodeBench、MCPBench、ChemLLMBench、PubMedQA | F1–F9 多功能 suite | ALFWorld valid_seen=IOD、valid_unseen=OOD；逐实例 with/without skill paired intervention；多模型 transfer（PDF pp. 7–9、16） | 同环境 IOD/OOD、跨 benchmark、跨模型；suite 的 breadth 不等于一个统一泛化率 |
| SkillHone | GAIA validation subset、WebWalkerQA-EN、WebShaper development data | F6 开放域研究/搜索 | WebShaper development 与测试 disjoint；curated search 与 raw open-web 两种 setting（PDF pp. 1–6） | cross-session refinement；search stack 改变时需视为不同 cell |
| SkillOpt | SearchQA、SpreadsheetBench、OfficeQA、DocVQA、LiveMathematicianBench、ALFWorld | F6、F4、F5、F7、F1 | 六 benchmark、七 target models、三 execution modes；train/selection/test；另测 cross-model/harness/nearby math benchmark（PDF pp. 1–16） | benchmark 内 held-out + cross-model/harness；跨 benchmark 多为功能相邻或仅 breadth |
| SkillPyramid | ALFWorld、ScienceWorld、WebShop、GAIA-Lite | F1、F2、F6 | ALFWorld seen/unseen 140/134；ScienceWorld 194/211 variations、24 task types；GAIA-Lite 75 tasks（PDF pp. 1–10） | 主要是 environment-internal seen→unseen；多 benchmark 并列不等于同一 collection 跨环境迁移 |
| SkillReducer | 55,315 public skills；600-skill controlled study；SkillsBench | 外部技能内容压缩；SkillsBench mixed professional tasks | 600 skills 分 original/compressed/no-skill；SkillsBench 87 tasks、deterministic pytest；跨 5 models/4 families（PDF pp. 1–12） | functional retention/compression transfer；不是 discovery benchmark |
| SKILLRL | ALFWorld、WebShop、NQ、TriviaQA、PopQA、HotpotQA、2Wiki、MuSiQue、Bamboogle | F1、F2、F6 | 9 benchmarks；search QA 用 NQ/HotpotQA 训练，TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle OOD；bank 55→100（PDF pp. 6–14） | 同环境 task-type；同功能 search QA 数据集 OOD；同时有 policy update |
| SkillWeaver | WebArena、Online-Mind2Web、真实网站 | F2 | WebArena 812 tasks/5 application domains；Online-Mind2Web 300 tasks/136 websites；实际 online 4 websites/57 tasks；自动与人工 evaluator 不同（PDF pp. 1–6） | website-specific/cross-website；不能把 simulated 与 real-site score 合并 |
| SkillX | AppWorld、BFCL-v3、τ²-Bench；另有相关 cross-benchmark cases | F3 工具调用与多轮用户交互 | BFCL-v3 50 train/150 test；AppWorld 90 training instances；按 initial query retrieval；Avg@4/Pass@4/Pass@1（PDF pp. 1–8） | cross-tool-schema/environment；不同 benchmark 交互协议异质 |
| SkVM | SkillsBench、PinchBench、118 representative skill tasks | mixed skill execution | 8 models、3 harnesses；每 task 生成 5 diverse input instances；completion/tokens/latency（PDF pp. 1–10） | cross-model/harness portability；不是 skill acquisition 泛化 |
| Trace2Skill | SpreadsheetBench-Verified、WikiTableQuestions、HiTab、DAPO、AIME、DocVQA、VRDU→VAREX、TSBench、OfficeBench | F4、F5、F7 | SpreadsheetBench 200 evolution/200 held-out；DAPO→AIME；VRDU→VAREX；TSBench deck-disjoint；generated DOCX→OfficeBench（PDF pp. 3–5、13–18） | 是当前少数明确报告跨数据集、部分跨功能的工作；但很多迁移仍共享文档/表格/程序结构 |
| Who Grades the Grader? | MBPP+、Spider 2.0-Snow、reference-free report generation | F8 + F10 | train/large unlabeled、tiny anchored dev、locked held-out test；independent judge audit（PDF pp. 1–6） | evaluator reliability/anchor generalization，不是普通 skill transfer |
| WikiSkill | LiveMathematicianBench、SealQA、SpreadsheetBench、OfficeQA、ALFWorld | F7、F6、F4、F5、F1 | 五 benchmark、五 models；train/validation/test；wiki 持久化、gating/rollback（PDF pp. 1–14） | 多功能 breadth + cross-model；需区分 wiki-to-skill 与跨任务 transfer |

## 3. What counts as genuinely cross-functional transfer?

### 3.1 Clearly same-function or adjacent-function transfers

- NQ/HotpotQA → TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle：都是 search-augmented QA，只是单跳/多跳和数据来源不同。
- SealQA → BrowseComp：都属于开放域搜索/研究型问答，属于相邻 benchmark/domain transfer，不是完全不同任务功能。
- SpreadsheetBench → WikiTableQuestions/HiTab：从 spreadsheet manipulation 到 table QA；任务接口不同，但共享表格、结构化数据和计算/检索能力。应标为“跨任务表格结构迁移”，而非 unrestricted cross-domain。
- VRDU → VAREX：都属于视觉文档结构化抽取，是真正的 cross-dataset，但仍是同一任务功能。
- TSBench → deck-disjoint TSBench：同一 PPT 编辑任务的文件级泛化，不是跨数据集功能迁移。
- DAPO → AIME：都是数学推理/竞赛数学，属于同功能数据集迁移。

### 3.2 More substantial functional shifts

- Trace2Skill 的 document workflow transfer：VRDU→VAREX、TSBench→deck-disjoint、generated DOCX→OfficeBench 覆盖 PDF/PPTX/DOCX 三种办公文档形态，但核心仍是文档操作/抽取，属于跨文档模态和格式，而非跨所有 agent task types。
- SKILLGEN 的 suite：同一 skill pipeline 在 ALFWorld、ScienceWorld、Mind2Web、LiveCodeBench、MCPBench、ChemLLMBench、PubMedQA、SocialMaze 上评测，覆盖具身、网页、代码、工具、化学和 biomedical QA。这是现有工作中最接近“跨多个任务功能”的 evaluation breadth；但每个 benchmark 通常使用独立 skill/独立 cell，不能解释成一个 skill 从一种功能迁移到所有功能。
- SkillOpt/WikiSkill/MetaSkill-Evolve 的多 benchmark 结果：覆盖多个任务功能，但主要是分别在每个 benchmark 上 evolution，再在其对应 held-out 上评价。它们证明的是框架在多任务套件上的适用性，不一定证明 cross-functional transfer。

### 3.3 What is still missing

在这 21 篇论文中，几乎没有一个公开、严格控制的 factorial experiment 同时满足：

1. 在任务功能 A 上演化一个明确的 SU/SC；
2. 保持 skill artifact、模型、工具预算和反馈协议不变；
3. 在完全不同任务功能 B/C/D 上测试同一 artifact；
4. 以 task-family macro average 和负迁移率报告结果。

因此，当前文献可以支持“多功能 benchmark breadth”，也有若干“相邻功能/跨数据集”迁移，但对**同一 skill artifact 的真正跨功能复用**仍缺少统一证据。

## 4. Inventory implications

1. benchmark 名称不是泛化粒度。必须记录 task function、task family、source/target split、工具和 evaluator。
2. 多 benchmark suite 不能直接求 pooled average 作为“通用 skill 泛化率”。
3. ALFWorld 的 `seen/unseen`、`valid_seen/valid_unseen`、random split 和 task-type split 应分别编码；它们都不是同一个 setting。
4. Search QA 数据集之间的跨数据集实验通常仍是同功能泛化；不能把它们写成跨任务功能。
5. 真正有价值的新 benchmark 应把“同功能跨数据集”“跨相关功能”“跨完全不同功能”设计成明确、可控的不同 track。

