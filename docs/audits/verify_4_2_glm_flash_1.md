# 第 4.2 节核验批次 1：CoEvoSkills、EvoSkill、GEPA、MetaSkill-Evolve、SKILL0

范围：逐篇对照 `papers/` 下原始 PDF 与 `skill_evolve_survey.md` 第 4.2 节当前表格，检查 `evolve setting`、`source 经验范围`、`target 测试范围`、G0-G8 泛化 setting、可支持结论及 PDF 页码证据。页码为 PDF 物理页；凡本轮未能完全核验处均明确写“证据不足”。本报告不修改主综述。

关键区分：G3-G5 是任务泛化；G6 是 environment/tool schema/harness 可移植性；G7 是 model/model family 可移植性；G8 是时间顺序/持续部署。多 benchmark 并列或 cross-model 结果不能自动升级为 G3/G5。

## 逐篇结论与建议替换文本

### 1. CoEvoSkills

**PDF 页码证据（已核验）**
- p.1：SkillsBench 评估；Claude Code 与 Codex 上超过五个 baseline，并向六个额外 LLM 泛化。
- p.4：method 表述为 skill + surrogate verifier co-evolution；ground-truth oracle 在 fresh environment 中 re-execute，仅返回 opaque success/failure signal。
- p.6：Skill Generator 输入为 task instruction、observable task inputs、initial background knowledge 和 meta-skill；Surrogate Verifier 只使用 task instruction、observable inputs、current outputs 和自身 previous verifier script，不接触 oracle criteria/test content/failure details。
- p.7：SkillsBench 为唯一 evaluation suite；85 个 task；主指标为 task 级 pass rate（reward = 1.0）。同页说明 evolution 从 task-relevant background knowledge 开始，但没有 task-instance solution procedures 或 hidden oracle information。
- p.8：主要 backbone 为 Claude Opus 4.6 与 GPT-5.2；另有 transferability 实验把 Opus-evolved skills 转到 GPT-5.2、Claude Sonnet 4.5、Claude Haiku 4.5、Qwen3-Coder-480B、DeepSeek V3-671B、Mistral Large 3-675B。Table 2 明确不同模型使用 Claude-Code、Codex 或 Terminus-2 harness。
- pp.8-9：cross-model transfer 的绝对提升约 35-44 pp；论文声称“portable across model families”。同时 harness 随模型一起改变，因此这也是 G6/G7 混合 portability cell。
- p.10：分域结果覆盖 11 个 professional domains；域级结果是同一 SkillsBench 协议下的 domain breakdown，不是同一 skill 的跨 domain source→target transfer matrix。
- p.14：Skill-Creator baseline 的 human-interactive steps 被改为 autonomous equivalents；因此 baseline 比较不是原始 interactive skill-creator 协议。

**逐列判定**
- `evolve setting`——当前表格“multi-file SP + verifier co-evolution”**基本正确**，但过短：遗漏了 ground-truth oracle 的 opaque pass/fail gate 和 surrogate verifier 的 test escalation。  
  建议替换为：**multi-file skill package + 独立 surrogate verifier co-evolution；surrogate 通过后由 fresh-environment ground-truth oracle 仅返回 pass/fail，并触发 verifier test escalation。**
- `source 经验范围`——当前“task execution、surrogate diagnostics、opaque oracle”**基本正确但不完整**。论文的初始信息还包括 task instruction、observable task inputs 和 task-relevant background knowledge；diagnostic 主要来自 surrogate verifier，oracle 只返回 opaque pass/fail。  
  建议替换为：**每 task 的 instruction、observable inputs/background docs、task rollouts；独立 surrogate verifier 的 per-assertion diagnostics；fresh-env oracle 的 opaque pass/fail。无 hidden oracle criteria/test content。**
- `target 测试范围`——当前“SkillsBench held-out；跨模型/跨 harness”**部分正确但易误读**。论文明确实验对象是 SkillsBench 的 85 个 task；cross-model transfer 是把 Opus-evolved skills 用于六个其他模型/harness 组合。但本轮未核验 SkillsBench 原始 benchmark 是否本身定义了 source/target split，因此“held-out”一词证据不足，应降级为“evaluation tasks”。  
  建议替换为：**SkillsBench 85-task evaluation（是否为原生 held-out split：证据不足）；同 suite 的 domain breakdown；另设 Opus-evolved skills 到六个其他 model/harness 组合的 transfer cell。**
- `明确的泛化 setting`——当前“G1/G2；G6/G7”**方向正确，但边界要更严**。p.8-9 支持跨 model/harness portability；p.10 的多域结果只是同一 suite 内多个 domain cell，不构成跨 domain transfer matrix。G1/G2 的具体 held-out/template 语义证据不足。  
  建议替换为：**task-level evaluation + G6/G7 mixed portability（跨 model 且多数目标 harness 同时改变）；domain breakdown 不作为 G3/G5 证据。**
- `可支持的结论`——当前“package 与验证闭环的可迁移性；不证明 SC scaling”**基本正确但可更精确**。论文支持的是：Opus-evolved packages 在其他 model/harness 上提高 task pass rate，且代理验证闭环有效。它不证明同一泛化抽象跨任务功能迁移，也不证明 skill collection scaling；oracle 是 task-level deterministic verifier，transferability 也没有单独隔离“同 harness 换模型”或“同模型换 harness”的完整矩阵。  
  建议替换为：**支持 multi-file package + surrogate-verifier loop 在 SkillsBench task-level 的收益，以及向其他 model/harness 组合的 package portability；不支持把 domain breakdown 解读为同一 artifact 的跨功能迁移，也不支持 SC scaling 结论。**

### 2. EvoSkill

**PDF 页码证据（已核验）**
- p.1：OfficeQA exact match 60.6%→67.9%（+7.3%）；SealQA 26.6%→38.7%（+12.1%）；SealQA-evolved skill 零改动迁移到 BrowseComp，+5.3%。
- p.2：方法为 failure-driven textual feedback、Pareto frontier、skill folders、held-out validation selection、frozen model；明确对比 GEPA/AlphaEvolve 等 artifact-level 优化。
- p.4：数据协议为 train / validation / held-out test 三段切分；validation 用于 frontier selection，test 从不在 evolution 中暴露。
- p.5：OfficeQA 使用 Claude Code + Opus 4.5；validation 17 例（约 7%）；train sizes 5%/10%/15%，1.5 epochs。
- p.6：OfficeQA 结果与 merge-unique skills；单 run 限制和 variance analysis 不足被明确承认。
- p.7：SealQA 使用 seal-0 split（111 questions）、Claude Code + Opus 4.5、10% train split；剩余为 held-out test。同一页给出唯一明确 transfer 实验：SealQA 上发现的 search-persistence-protocol skill 零改动用于 BrowseComp 的 128 例 stratified sample。
- p.9：论文自己把 SealQA→BrowseComp称为“direct evidence”，但也承认需要更多 diverse task pairs。

**逐列判定**
- `evolve setting`——当前“多轮 SU discovery，多个 skill 可累积”**基本正确但遗漏监督条件**。Proposer 使用 ground-truth answers 做 failure diagnosis；这不是无监督 self-evolution。  
  建议替换为：**多轮 failure-driven skill discovery/refinement，skill folders 可累积；Pareto/validation gate 选择 skill；Proposer 可访问 ground-truth answers 做错误诊断。**
- `source 经验范围`——当前“OfficeQA/SealQA training subset；ground-truth failure diagnosis”**正确且需要补充 split 语义**。OfficeQA 与 SealQA 是两个独立 evolution cell，不应合并成单一 source distribution。  
  建议替换为：**OfficeQA：5%/10%/15% train split，17 例 validation；SealQA seal-0：10% train split；二者为独立 cells。Proposer 使用 ground-truth answers 诊断执行失败。**
- `target 测试范围`——当前“held-out validation/test；SealQA skill→BrowseComp”**有一处术语错误**：validation 不是 target，真正的 target 是 held-out test；BrowseComp 是零改动 transfer cell。  
  建议替换为：**OfficeQA held-out test；SealQA seal-0 held-out test；另设 SealQA-derived search-persistence skill → BrowseComp 128-example sample 的 zero-shot transfer。**
- `明确的泛化 setting`——当前“G1/G2；G3/G4 边界”**方向正确但应更明确**。OfficeQA/SealQA 各自 held-out 属于 G1/G2；SealQA→BrowseComp 是同属 search/fact-seeking workflow 的跨 dataset 迁移，可规范化为 G3，不宜写成含糊的“G3/G4 边界”。  
  建议替换为：**G1/G2（各自 benchmark held-out）；SealQA→BrowseComp 规范化为同 search/fact-seeking 功能簇的 G3 transfer cell。**
- `可支持的结论`——当前“同 benchmark 泛化；搜索/问答相邻数据集迁移；不能称完全跨功能”**基本正确，但“搜索/问答相邻数据集”可更准确**。论文只有一个 transfer skill（search persistence）和 BrowseComp 128 例；不能推广成整个 skill library 的跨数据集迁移。  
  建议替换为：**支持各 benchmark held-out 内的 skill gain；支持单一 SealQA-derived search-persistence skill 到 BrowseComp 的 zero-shot gain。不能推广为整个 evolved skill library 的跨任务/跨功能迁移，也不能称 G5。**

### 3. GEPA

**PDF 页码证据（已核验）**
- p.1：定义 GEPA 为 reflective prompt optimizer；六个 tasks；与 GRPO/MIPROv2 比较。
- p.2：六个任务为 HotpotQA、AIME、LiveBench-Math、IFBench、HoVer、PUPA；模型为 Qwen3 8B 和 GPT-4.1 Mini。
- p.4：明确 GEPA 只 evolves prompts，LLM weights fixed。
- p.6：Algorithm 1 使用 train/feedback 与 Pareto validation；p.8 说明 standard train/validation/test split，optimizer 可用 train 内容，validation 用于 selection，test 评估。
- pp.8-9：Qwen3 8B 与 GPT-4.1 Mini 的六个 benchmark 结果；GPT-4.1 Mini 表新增“GEPA-Qwen-Opt”——用 Qwen3-8B 优化 prompts 后直接评估 GPT-4.1 Mini，+9.00 aggregate。
- p.11：Observation 6 明确称 cross-model generalization，并给出 HotpotQA 最高 +27.67%。
- pp.23-25：benchmark split 细节：HotpotQA 150/300/300；IFBench 用 IF-RLVR Train 作 train/val，IFBench 294 作 test；AIME 用 2022-2024 train/val、AIME-2025 test；LiveBench-Math 368 例三等分；HoVer 150/300/300；PUPA 111/111/221。
- pp.12-15：另有 inference-time search / kernel 生成和 adversarial prompt search 扩展应用，但不是主 skill-evolution 协议。

**逐列判定**
- `evolve setting`——当前“prompt/program optimization”**部分准确，但主协议应写成 prompt optimization**。p.4 明确 weights fixed、只更新 prompt；program-level inference-time search 是扩展应用而非主表协议。  
  建议替换为：**reflective prompt evolution / prompt optimization for compound AI systems；主协议中模型权重固定，仅更新 module prompts。**
- `source 经验范围`——当前“train examples、textual feedback、validation scores”**正确且可保留**。可补充：train 用于 rollout feedback，Pareto validation 用于 candidate selection；feedback 可含 evaluator textual traces。  
  建议替换为：**per-benchmark train/feedback examples、execution/evaluation textual feedback，以及 validation/Pareto scores for candidate selection。**
- `target 测试范围`——当前“six prompt-system benchmark test sets”**正确**。  
  建议替换为：**六个独立 benchmark 的 held-out test sets：HotpotQA、IFBench、HoVer、PUPA、AIME-2025、LiveBench-Math；另有 Qwen3-8B-optimized prompts 在 GPT-4.1 Mini 上的 cross-model cell。**
- `明确的泛化 setting`——当前“G1/G2；多功能 breadth”**不完整，漏掉最重要的 cross-model G7 evidence**。六个 benchmark 内的 train→test 是 G1/G2；多 benchmark 是独立 evaluation cells；GEPA-Qwen-Opt → GPT-4.1 Mini 是明确的 G7 prompt portability。  
  建议替换为：**G1/G2 per benchmark；六个 benchmark 为多功能 breadth/独立 cells，不是 G5；另有明确 G7 cross-model prompt portability（Qwen3-8B optimized → GPT-4.1 Mini）。**
- `可支持的结论`——当前“prompt/program adaptation；不是 SU/SC acquisition”**正确但应补 cross-model 边界**。GEPA 支持样本效率更高的 prompt adaptation、跨六个 prompt-system test sets 的 gain，以及 prompt 跨模型迁移；但这些不是外部 skill acquisition，也不是 agent skill package 的 G3/G5。  
  建议替换为：**支持 compound-system prompt adaptation 与样本效率优势，以及 optimized prompts 的 G7 cross-model portability；不构成 SU/SC acquisition，也不应把多 benchmark breadth 解读为同一 skill 的跨功能迁移。**

### 4. MetaSkill-Evolve

**PDF 页码证据（已核验）**
- p.1：两时间尺度框架；task skill fast loop，meta-skill slow loop；三个 benchmark 为 OfficeQA、SealQA、ALFWorld；提升为 +23.54、+16.09、+1.92。
- p.2：每个 branch 携带 task skill 与 meta-skill；meta-skill 由同一五-agent pipeline 递归优化。
- pp.4-6：算法与 DAG/frontier；fast loop 用 train worst case 驱动 edit，child 在 validation 上打分；slow loop 每 H iterations 更新 meta-skills。
- p.6：每个 benchmark file 按类别 stratified split 成 train（failure mining）、validation（child scoring and best-skill selection）、held-out test；test 由 loop never observes，随后 benchmark-mode pass。
- p.7：所有 pipeline agents 共享 frozen Gemma-4 31B；baselines 为 No-Skill、Static Skill、Single-Level Evolution。
- pp.7-8：Table 1 held-out test accuracy：OfficeQA 31.78→55.32，SealQA 29.17→45.26，ALFWorld 92.31→94.23；ALFWorld 靠近 ceiling，static skill 略降。
- p.8：component ablations；OfficeQA 中 allocator 最重要，SealQA 中 proposer 最重要。
- p.13：Appendix F 重复 held-out protocol；Appendix G 使用 common held-out subset 做 split-ratio sensitivity。

**逐列判定**
- `evolve setting`——当前“task-SU fast loop + meta-SU slow loop”**正确**。建议补上“同一 frozen backbone”和“branch-local meta-skill”。  
  建议替换为：**task-skill fast loop + branch-local meta-skill slow loop；同一 frozen Gemma-4 31B 作为五个 pipeline agents。**
- `source 经验范围`——当前“task trajectories 和 branch scores”**基本正确但过于简略**。实际驱动信号是 train worst-case failure、validation child score、frontier/meta-productivity、cross-branch inspirations。  
  建议替换为：**每个 benchmark 的 train failures/worst-case trajectories、validation scores/ΔU、frontier 与 branch history；cross-branch inspiration 只来自同一 benchmark 的 evolution DAG。**
- `target 测试范围`——当前“OfficeQA、SealQA、ALFWorld held-out”**正确**，但应避免把三者合并成一个跨任务泛化范围。  
  建议替换为：**三个独立 held-out cells：OfficeQA、SealQA、ALFWorld；test partition 在 evolution loop 中不可见。**
- `明确的泛化 setting`——当前“G1/G2；多功能 breadth”**正确且边界判断恰当**。三者是分别 evolved / evaluated 的多功能适用性证据，不是同一 skill 跨 QA/embodied 任务迁移。  
  建议替换为：**G1/G2 per benchmark；OfficeQA/SealQA/ALFWorld 为多功能 breadth，不是同一 artifact 的 G3/G5 transfer。**
- `可支持的结论`——当前“task skill 与 evolution process 在多个功能簇上有效；不是同一 skill 跨三类功能迁移”**正确且应保留**。可补充两点：ALFWorld 处于接近 ceiling，+1.92 幅度小且 static skill 为负；meta-skill slow-loop 的贡献通过与 Single-Level baseline 对比支持，但没有跨 benchmark 的 meta-skill transfer 实验。  
  建议替换为：**支持 task-skill evolution 与 meta-skill slow loop 在三个独立 held-out cells 上的增益；不支持同一 task skill 或同一 meta-skill 跨 OfficeQA/SealQA/ALFWorld 迁移；ALFWorld 增益受 ceiling 限制。**

### 5. SKILL0

**PDF 页码证据（已核验）**
- p.1：SKILL0 是 in-context RL，用于 skill internalization；训练时提供 skill context，推理时 zero-shot。
- p.2：skills during training、zero at inference；dynamic curriculum 根据 on-policy helpfulness 逐阶段撤除 skill。
- p.3：SkillBank 组织为 general/task-specific skills；p.4 给出 context rendering。
- p.5：Algorithm 1 依据 validation sub-task 的 with/without skill helpfulness 进行 filter/rank/select，并线性衰减 budget。
- p.5：benchmarks 为 ALFWorld、Search-based QA、WebShop。
- p.6：训练/评估细节：ALFWorld 用 GiGPO split；Search-QA 用 Search-R1 setup，E5 retriever；Search-QA 训练来自 NQ 与 HotpotQA，因此 NQ/HotpotQA 为 in-domain，其余 Search-QA datasets 为 out-of-domain。WebShop 用 1000 training tasks；validation subset 1000；curriculum stages 3；SkillBank initialized from SkillRL。
- p.6：主表包含 Qwen2.5-(VL)-3B/7B；SKILL0 在 ALFWorld/Search-QA 上优于 GRPO/AgentOCR/SkillRL 等。
- p.7：声称 gains 来源于 internalized knowledge 而非 skill prompts；也给出 token efficiency。
- p.8：training dynamics 中 with-skill 更快，without-skill 后期追上；helpfulness rise-then-fall。
- p.9：ablation 显示 dynamic curriculum 的 with/without skill 表现；Limitations 明确依赖 initial SkillBank quality，并且 new domain 需要重新 partition。
- p.19：Table 7 明确标注 NQ、HotpotQA 为 in-domain；TriviaQA、PopQA、2Wiki、MuSiQue、Bamboogle 为 out-of-domain。
- pp.21-22：列出 representative SkillBank skills，但它们是 SkillRL-initial SkillBank 的内容示例；本轮未核验每个 skill 的完整来源或 evolution history。

**逐列判定**
- `evolve setting`——当前“PP internalization，外部 skill context 逐步撤除”**基本正确但应补 SkillBank 来源**。SKILL0 本身不是从零发现外部 skill artifacts；SkillBank 由 SkillRL 初始化，训练过程中做 helpfulness-driven selection/withdrawal，参数随 RL 更新。  
  建议替换为：**parameter/policy internalization via in-context RL；SkillBank initialized from SkillRL，训练中按 on-policy helpfulness filter/rank/select 并逐步撤至零 skill context。**
- `source 经验范围`——当前“ALFWorld、WebShop、search QA trajectories/rewards”**基本正确但可更明确**。Search-QA 的 source 是 NQ + HotpotQA；ALFWorld/WebShop 各自独立训练 cell；skill selection 还依赖 validation sub-tasks。  
  建议替换为：**ALFWorld training split、WebShop 1000 training tasks、Search-QA NQ+HotpotQA training；加上 per-skill validation sub-task 的 with/without skill helpfulness。三者是独立 source cells。**
- `target 测试范围`——当前“ALFWorld/WebShop test；search QA in-domain/OOD”**基本正确**。注意 Search-QA 的 OOD 指 Search-R1 协议下非训练 datasets，而不是跨环境/跨 harness portability。  
  建议替换为：**ALFWorld evaluation；WebShop evaluation；Search-QA 中 NQ/HotpotQA 为 in-domain，TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle 为 OOD。**
- `明确的泛化 setting`——当前“G1/G2；search QA G3；参数内化”**大体正确，但 G3 应限定**。Search-QA 的 NQ/HotpotQA→其他 search-QA datasets 是同一 search/fact-seeking 功能簇内的 G3 cell；ALFWorld/WebShop 是 G1/G2；没有 G6/G7 artifact portability，因为最终比较对象是更新后的模型。  
  建议替换为：**G1/G2 for ALFWorld/WebShop；Search-QA NQ/HotpotQA→其他 search-QA datasets 为 G3；核心 setting 是 policy internalization / context withdrawal，不是 external artifact transfer。**
- `可支持的结论`——当前“能力是否从外部 skill 转入权重；不是 external artifact transfer”**正确且应保留**。可补充边界：internalization 结论依赖初始 SkillBank 质量；论文 limitation 也承认 new domain 需要重新 partition；不能与 frozen-model external-skill 方法在同一性能榜直接比较。  
  建议替换为：**支持在给定 SkillBank/RL 协议下将 skill-guided 能力转入 Qwen2.5-VL 参数并在 zero-skill inference 中保持增益；Search-QA 的 OOD 支持同功能 G3。不证明外部 skill artifact 的 G6/G7 portability，也不能与 frozen external-skill 方法直接同榜排名。**

## 表格替换建议（按当前 4.2 表行顺序）

```markdown
| CoEvoSkills | multi-file skill package + 独立 surrogate verifier co-evolution；surrogate 通过后由 fresh-env oracle 仅返回 pass/fail，并触发 verifier test escalation | 每 task 的 instruction、observable inputs/background docs、task rollouts；独立 surrogate verifier 的 per-assertion diagnostics；fresh-env oracle 的 opaque pass/fail。无 hidden oracle criteria/test content | SkillsBench 85-task evaluation（是否为原生 held-out split：证据不足）；同 suite domain breakdown；另设 Opus-evolved skills 到六个其他 model/harness 组合的 transfer cell | task-level evaluation + G6/G7 mixed portability；domain breakdown 不作为 G3/G5 证据 | 支持 multi-file package + surrogate-verifier loop 在 SkillsBench task-level 的收益，以及向其他 model/harness 组合的 package portability；不支持把 domain breakdown 解读为同一 artifact 的跨功能迁移，也不支持 SC scaling |
| EvoSkill | 多轮 failure-driven skill discovery/refinement，skill folders 可累积；Pareto/validation gate 选择 skill；Proposer 可访问 ground-truth answers 做错误诊断 | OfficeQA：5%/10%/15% train split，17 例 validation；SealQA seal-0：10% train split；二者为独立 cells。Proposer 使用 ground-truth answers 诊断执行失败 | OfficeQA held-out test；SealQA seal-0 held-out test；另设 SealQA-derived search-persistence skill → BrowseComp 128-example sample 的 zero-shot transfer | G1/G2（各自 benchmark held-out）；SealQA→BrowseComp 规范化为同 search/fact-seeking 功能簇的 G3 transfer cell | 支持各 benchmark held-out 内的 skill gain；支持单一 SealQA-derived search-persistence skill 到 BrowseComp 的 zero-shot gain。不能推广为整个 evolved skill library 的跨任务/跨功能迁移，也不能称 G5 |
| GEPA | reflective prompt evolution / prompt optimization for compound AI systems；主协议中模型权重固定，仅更新 module prompts | per-benchmark train/feedback examples、execution/evaluation textual feedback，以及 validation/Pareto scores for candidate selection | 六个独立 benchmark 的 held-out test sets：HotpotQA、IFBench、HoVer、PUPA、AIME-2025、LiveBench-Math；另有 Qwen3-8B-optimized prompts 在 GPT-4.1 Mini 上的 cross-model cell | G1/G2 per benchmark；六个 benchmark 为多功能 breadth/独立 cells，不是 G5；另有明确 G7 cross-model prompt portability（Qwen3-8B optimized → GPT-4.1 Mini） | 支持 compound-system prompt adaptation 与样本效率优势，以及 optimized prompts 的 G7 cross-model portability；不构成 SU/SC acquisition，也不应把多 benchmark breadth 解读为同一 skill 的跨功能迁移 |
| MetaSkill-Evolve | task-skill fast loop + branch-local meta-skill slow loop；同一 frozen Gemma-4 31B 作为五个 pipeline agents | 每个 benchmark 的 train failures/worst-case trajectories、validation scores/ΔU、frontier 与 branch history；cross-branch inspiration 只来自同一 benchmark 的 evolution DAG | 三个独立 held-out cells：OfficeQA、SealQA、ALFWorld；test partition 在 evolution loop 中不可见 | G1/G2 per benchmark；OfficeQA/SealQA/ALFWorld 为多功能 breadth，不是同一 artifact 的 G3/G5 transfer | 支持 task-skill evolution 与 meta-skill slow loop 在三个独立 held-out cells 上的增益；不支持同一 task skill 或同一 meta-skill 跨 OfficeQA/SealQA/ALFWorld 迁移；ALFWorld 增益受 ceiling 限制 |
| SKILL0 | parameter/policy internalization via in-context RL；SkillBank initialized from SkillRL，训练中按 on-policy helpfulness filter/rank/select 并逐步撤至零 skill context | ALFWorld training split、WebShop 1000 training tasks、Search-QA NQ+HotpotQA training；加上 per-skill validation sub-task 的 with/without skill helpfulness。三者是独立 source cells | ALFWorld evaluation；WebShop evaluation；Search-QA 中 NQ/HotpotQA 为 in-domain，TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle 为 OOD | G1/G2 for ALFWorld/WebShop；Search-QA NQ/HotpotQA→其他 search-QA datasets 为 G3；核心 setting 是 policy internalization / context withdrawal，不是 external artifact transfer | 支持在给定 SkillBank/RL 协议下将 skill-guided 能力转入 Qwen2.5-VL 参数并在 zero-skill inference 中保持增益；Search-QA 的 OOD 支持同功能 G3。不证明外部 skill artifact 的 G6/G7 portability，也不能与 frozen external-skill 方法直接同榜排名 |
```

## 证据不足与未扩展项

1. **CoEvoSkills 的“held-out”语义**：论文反复使用 SkillsBench 85 tasks，但本轮没有核验 SkillsBench 原论文或 CoEvoSkills 对 task/train/test split 的更细定义。建议在主表中写“evaluation tasks”，或补充证据后再写“held-out”。
2. **CoEvoSkills 的 G6/G7 单变量隔离**：cross-model transfer 同时改变了 harness（Claude-Code/Codex/Terminus-2），当前只能称 mixed G6/G7 portability；不能拆成纯 G7。
3. **SKILL0 SkillBank 的逐 skill 来源/演化历史**：已知初始来自 SkillRL，并有 representative skills 示例；未核验全部 skill 文件的来源、更新与筛选轨迹。
4. **GEPA 扩展应用**：kernel/inference-time search 与 adversarial prompt search 未纳入主表格结论；若要加入，应作为 separate extended application cells，而不是 skill-evolution 证据。
5. **所有未在上述页码证据中列出的细节**，包括未逐页核对图表数值与附录协议细节，均不应据此新增结论。
