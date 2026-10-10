# G2 论文数据集核验汇总

来源：`paper_generalization_settings.md` 中严格、已支持的 G1/G2 论文级覆盖共 14 篇。  
本汇总只记录「在哪里 evolve / 训练 / 内化」与「在哪里测试」，并区分：

- **A→A**：在 A 上 evolve，并在 A 的 held-out / test split 上测试。
- **A→B**：在 A / task A 上 evolve，在 B / task B 上测试。
- 跨模型、跨 harness 不计为任务泛化，只单独说明。

## 汇总矩阵

| 论文 | Skill evolution / prompt evolution / training 的数据 | 测试数据 | 演化→测试关系 |
|---|---|---|---|
| SkillGen | 各 benchmark 自身的 construction data / base-agent 成功失败轨迹；例如 ALFWorld construction 150/255 → ALFWorld held-out test 500 | ALFWorld IOD/OOD；LiveCodeBench；MCPBench；Mind2Web；PubMedQA；ScienceWorld；SocialMaze；τ-Bench；ChemLLMBench | 全部 A→A；没有 A→B。跨模型仅在 4 个 benchmark 上另测 |
| SkillOpt | 各 benchmark 自身的 D_train rollouts + D_selection gate；SearchQA、SpreadsheetBench、OfficeQA、DocVQA、LiveMath、ALFWorld 分别 evolve | 对应 benchmark 的 held-out test | 主实验 A→A。另有 OlympiadBench→Omni-MATH 的 A→B transfer cell |
| EvoSkill | OfficeQA 自身 train split（5/10/15%）evolve；SealQA seal-0 train split（10%）evolve | OfficeQA held-out test；SealQA held-out test | 各自 A→A。另有 SealQA→BrowseComp 128 题的 A→B zero-shot transfer |
| MetaSkill-Evolve | OfficeQA、SealQA、ALFWorld 分别用自身 train failure + validation selection 做 task/meta-skill evolution | 各自 benchmark held-out test | 三个独立 A→A；无 A→B，无跨模型 |
| SkillCAT | SpreadsheetBench-Verified 200 个 evolution samples；DocVQA validation split 前 2,700 例（独立 cell） | SpreadsheetBench held-out 200 / full；WikiTQ；DocVQA 剩余 2,649 例 | Spreadsheet 和 DocVQA 分别 A→A；另有 SpreadsheetBench→WikiTQ 的 A→B OOD cell |
| Trace2Skill | SpreadsheetBench 200；DAPO 400；DocVQA 50；VRDU Registration；TSBench training decks；合成 DOCX traces | 对应同源 held-out 或跨任务 target：WikiTQ/HiTab、AIME 2026、VAREX Flat、OfficeBench DOCX 等 | 同源 cell 为 A→A；SpreadsheetBench→WikiTQ/HiTab、DAPO→AIME、VRDU→VAREX、Synthetic DOCX→OfficeBench 为 A→B |
| SkillPyramid | ALFWorld / ScienceWorld / WebShop 各自环境内 incoming task 流 + training split 初始库；GAIA-Lite 用 web-mined skills 分析 | ALFWorld seen/unseen；ScienceWorld seen/unseen；WebShop；GAIA-Lite 独立 cell | 三个主 benchmark 各自 A→A；GAIA-Lite 是 web skills 分析 cell，不是同一 collection 的 A→B transfer |
| SkillX | BFCL-v3 / AppWorld / τ²-Bench 各自 training split 上的 rollout + skill extraction/refinement/expansion | BFCL-v3 test；AppWorld Test Normal；τ²-Bench test splits | 三个 benchmark 各自 A→A；没有 A→B；跨模型只单独说明 |
| WikiSkill | 5 个 benchmark 分别从空集开始，用自身 train split 的 execution traces 演化 | 对应 benchmark test split | 5 个 cell 全部 A→A；没有 A→B；跨模型只单独说明 |
| SKILLRL | ALFWorld / WebShop 各自环境 rollout + failed validation trajectories + GRPO；Search-QA 用 NQ + HotpotQA 训练 | ALFWorld；WebShop；NQ/HotpotQA；TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle | ALFWorld、WebShop 为 A→A；NQ、HotpotQA 为 A→A；NQ+HotpotQA→其他五个 QA 为 A→B |
| SKILL0 | ALFWorld training split、WebShop 1000 tasks、Search-QA NQ+HotpotQA 上做 RL / policy internalization | ALFWorld；WebShop 128 fixed validation tasks；NQ/HotpotQA；TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle | ALFWorld、WebShop 为 A→A；NQ/HotpotQA 为 A→A；NQ+HotpotQA→其他五个 QA 为 A→B |
| SkillEvolver | SkillsBench 每个任务自身 T_train；KernelBench 3 个任务自身 | 同任务 T_val；KernelBench 同任务 speedup | SkillsBench 和 KernelBench 都是任务级 A→A；没有 A→B |
| SkillWeaver | WebArena 5 sites 与 4 个 live websites 分别做 pre-hoc exploration / API synthesis；经验来源为各自网站交互 | 对应网站任务：WebArena；Online-Mind2Web 筛出的 4 sites / 57 tasks | 按站点各自 A→A；没有 site A→site B transfer；GPT-4o→GPT-4o-mini 只算跨模型 |
| GEPA | 六个 benchmark 分别用各自 train split / feedback 做 prompt evolution；validation 做 Pareto selection | HotpotQA、IFBench、HoVer、PUPA、AIME-2025、LiveBench-Math 各自 test | 六个主 cell 均为 A→A（IFBench 用 IF-RLVR train 源，但同属 instruction-following 的设计性 OOD split）；另有 Qwen3-8B→GPT-4.1 Mini 跨模型 |

## 明确的 A→B 任务迁移 cell

1. **SkillOpt**：OlympiadBench → Omni-MATH。
2. **EvoSkill**：SealQA → BrowseComp。
3. **SkillCAT**：SpreadsheetBench → WikiTableQuestions。
4. **Trace2Skill**：
   - SpreadsheetBench → WikiTQ / HiTab；
   - DAPO → AIME 2026；
   - VRDU Registration → VAREX Flat；
   - Synthetic DOCX tasks → OfficeBench DOCX。
5. **SKILLRL**：NQ + HotpotQA → TriviaQA / PopQA / 2Wiki / MuSiQue / Bamboogle。
6. **SKILL0**：NQ + HotpotQA → TriviaQA / PopQA / 2Wiki / MuSiQue / Bamboogle。

除以上外，本批 G2 论文的主实验均应归类为「在 A 上 evolve，并在 A 的 held-out/test split 上测试」，或按环境/站点/任务分别构造的独立 A→A cell。

## 关键注意事项

- 多 benchmark 并列不等于同一个 skill / artifact 的 A→B transfer。
- SkillGen、MetaSkill-Evolve、WikiSkill、SkillX、SkillEvolver 均未报告真正的 A→B 任务迁移实验。
- Trace2Skill 和 SkillCAT 的 OOD cell 是把 target 数据转换为 compatible task format 后再测试，应按论文原文定位为跨数据集/跨任务泛化 cell。
- SkillWeaver 的 “Generalization across Website” 不是 website A→website B 的 skill transfer；每个网站都使用各自 pre-hoc exploration 得到的 API library。
- GEPA 的 IFBench 设置使用了 IF-RLVR train 源，但仍是同一 instruction-following 体系内的设计性 OOD split，不应与完全不同任务功能混淆。

## 主要证据定位（节选）

| 论文 | 定位 |
|---|---|
| SkillGen | Table 1 p.7；Table 3 / Appendix C.2–C.4 pp.16–17；Figure 4 p.8 |
| SkillOpt | Table 1 pp.7–8；Table 4 p.9；Appendix C p.20 |
| EvoSkill | §3.1–3.3 pp.5–7；Table 1 p.6 |
| MetaSkill-Evolve | §4.1 pp.6–7；Table 1 p.8；Appendix F p.13 |
| SkillCAT | Experimental Setup pp.4–5；Table 1 p.5；Figure 3 p.6 |
| Trace2Skill | Table 1 p.4；Table 2 p.6；Table 3 p.6；Table 13 p.19；Appendix A pp.13–14 |
| SkillPyramid | §3.1 p.5；Table 1 p.6；Appendix A.1 pp.10–11；GAIA-Lite Table 4 p.8 |
| SkillX | §5.1 p.5；Table 1 p.6；Table 2 p.9；Appendix A.1 p.15 |
| WikiSkill | Problem Setup p.3；Table 1 p.8；Table 2 p.10；Table 6 pp.19–20 |
| SKILLRL | Table 1 p.6；Table 2 p.7；Algorithm 1 p.4；Figure 3 p.7；Appendix B.1 Table 4 p.14 |
| SKILL0 | Sec. 4.1 pp.5–6；Table 1 p.6；Table 2 p.6；Table 7 p.19 |
| SkillEvolver | §4.1 p.6；p.7；Table 1 p.8；Appendix A.3/A.6/A.8 pp.13–18 |
| SkillWeaver | §3.1–3.2 p.5；§3.4 p.6；Table 1/Table 2 p.7；Appendix B/C pp.26–29 |
| GEPA | Section 4 p.8；Table 1/Table 2 p.8；Appendix E.1 pp.23–25；Appendix E.4 p.27 |
