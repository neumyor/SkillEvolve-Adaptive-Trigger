# Skill Evolve Paper Method and Evaluation Evidence

本文件保存 21 篇原始 PDF 的详细证据，供主综述复核。页码为 PDF 内页码。`E1` 表示 PDF 明示，`E2` 表示由实验设计直接支持，`E3` 表示本文规范化映射，`E4` 表示 PDF 未充分报告。

完整逐篇审计已由论文审计文件整理；本文件强调与 benchmark 泛化和公平比较直接相关的事实。

## 1. Object-to-evaluation summary

| 工作 | 实际 evolve 对象 | 主要载体 | 经验/反馈 | 主要 evaluation cell | 参数更新 |
|---|---|---|---|---|---|
| CoEvoSkills | multi-file skill package + surrogate verifier | package、scripts、references、tests | trajectory、surrogate diagnostics、opaque oracle pass/fail | SkillsBench held-out；cross-model/harness | 否 |
| EvoSkill | individual skill folders + accumulating frontier/repository | structured folders | failures、ground-truth answers、validation score | OfficeQA/SealQA held-out；SealQA→BrowseComp | 否 |
| GEPA | prompt/program components | prompt text、compound-system programs | textual feedback、train/validation scores | six prompt-system benchmarks | 否 |
| MetaSkill-Evolve | task skill + meta-skill process | skill files、meta components | trajectories、branch scores、held-out evaluation | OfficeQA/SealQA/ALFWorld held-out | 否 |
| SKILL0 | model/policy internalization | parameters + temporary skill context | RL reward、environment trajectories | ALFWorld/WebShop/search QA | 是 |
| SkillAdaptor | local skill repair within existing collection | external files/collection | failed trajectory、fault attribution、task score | WebShop/PinchBench/Claw-Eval | 否 |
| SkillCAT | skill patches + topology/routing | patch、collection graph | success/failure contrast、patch assessment、runtime validation | SpreadsheetBench/DocVQA/WikiTableQuestions | 否 |
| SkillEvo | directed skill graph + governance/history | graph、routing table、references | multi-turn simulated users、fact/structure checks | chronological production tickets | 否 |
| SkillEvolver | on-demand task/domain skill | files、scripts、references | bounded training and validation trials | SkillsBench、KernelBench | 否 |
| SKILLGEN | one auditable skill | text/code/reference bundle | paired with-skill/without-skill intervention | ALFWorld IOD/OOD、multi-benchmark suite | 否 |
| SkillHone | loadable skill bundle + persistent decision history | bundle、wiki/history | probes、validators、evaluation reports | GAIA/WebWalkerQA open-web | 否 |
| SkillOpt | one external skill document | single document | scored rollouts、held-out selection gate | six benchmark/model/harness cells | 否 |
| SkillPyramid | hierarchical skill collection/topology | hierarchical library | trajectories、environment success | ALFWorld/ScienceWorld/WebShop/GAIA-Lite | 否 |
| SkillReducer | skill text/routing compression | descriptions、bodies | functional retention、token/latency | 600 skills + SkillsBench | 否 |
| SKILLRL | skill bank + policy | hierarchical bank + weights | success/failure trajectories、RL reward | ALFWorld/WebShop/search QA | 是 |
| SkillWeaver | executable API/skill collection | APIs + tests | website traces、functional checks、human judgment | WebArena/Online-Mind2Web/real sites | 否 |
| SkillX | multi-level procedural/declarative KB | planning/functional/atomic levels | generated experience、benchmark score | AppWorld/BFCL/τ²-Bench | 否 |
| SkVM | runtime/compiler representation | compiled skill/runtime | completion、tokens、latency、compatibility | SkillsBench/PinchBench/118 tasks | 否 |
| Trace2Skill | consolidated skill directory | `SKILL.md` + references/scripts/assets | labeled success/failure traces、held-out pass rate | Spreadsheet/Math/Doc transfer cells | 否 |
| Who Grades the Grader? | evaluator metric + skill lifecycle | detector expression、skill bank | anchors、locked test、independent judge | MBPP+/Spider/report evaluator cells | 否 |
| WikiSkill | wiki state → executable skill collection | persistent wiki + directories | train experience、validation gate、rollback | five benchmark/model cells | 否 |

## 2. Detailed evidence by work

### CoEvoSkills

- PDF pp. 1–4 explicitly distinguish a tool as a self-contained function and a skill as a structured multi-file package.
- PDF pp. 4–7 describe co-evolution of a skill generator and surrogate verifier.
- PDF pp. 7–8 report 85 SkillsBench tasks with deterministic verifiers and an opaque oracle pass/fail signal.
- PDF pp. 11–12 evaluate portability across Claude Code/Codex and multiple models.
- Interpretation: package generation and evaluator co-evolution are central. This is not evidence for collection scaling or retrieval quality.

### EvoSkill

- PDF pp. 1–2 define structured reusable skill folders with instructions, trigger metadata and helper scripts; the underlying model remains frozen.
- PDF pp. 3–5 use failures, ground-truth answers and a disjoint train/validation/test protocol.
- PDF pp. 6–10 evaluate OfficeQA and SealQA and report SealQA→BrowseComp transfer.
- Interpretation: strong frozen external-skill baseline, but feedback is stronger than opaque pass/fail methods because ground-truth diagnosis is available.

### GEPA

- PDF pp. 1–5 frame the method as reflective prompt optimization, not ordinary external skill evolution.
- PDF pp. 6–9 use textual execution feedback and validation selection.
- PDF pp. 8–16 cover HotpotQA, AIME, LiveBench-Math, IFBench, HoVer and PUPA.
- Interpretation: useful prompt/program optimization track; do not compare its headline score directly with skill artifact acquisition.

### MetaSkill-Evolve

- PDF pp. 1–4 distinguish task skill and meta-skill roles.
- PDF pp. 4–9 use a fast task-skill loop and slow meta-skill loop involving Analyzer, Retriever, Allocator, Proposer and Evolver.
- PDF pp. 6–10 evaluate OfficeQA, SealQA and ALFWorld held-out splits.
- Interpretation: gains combine artifact improvement with process/search improvement; meta-agent calls must be budgeted.

### SKILL0

- PDF pp. 1–3 state that the goal is to internalize skill context into model parameters.
- PDF pp. 5–9 evaluate ALFWorld, search-based QA and WebShop.
- PDF pp. 6, 18–19 distinguish NQ/HotpotQA in-domain training from other search datasets used for OOD evaluation.
- Interpretation: parameter-learning track, not frozen external-skill track.

### SkillAdaptor

- PDF pp. 1–4 describe first actionable failure localization and responsibility attribution within an existing skill collection.
- PDF pp. 3–9 use WebShop, PinchBench and Claw-Eval/OpenClaw with frozen base models.
- Interpretation: local maintenance/repair; not equivalent to building a library from scratch.

### SkillCAT

- PDF pp. 1–3 define CCE, AAE and TTE as separate lifecycle stages.
- PDF p. 5 reports 200 evolution and 200 held-out SpreadsheetBench-Verified examples, plus a disjoint DocVQA split.
- PDF pp. 5–7 include WikiTableQuestions OOD and cross-model experiments.
- Interpretation: final score mixes extraction, assessment, topology and routing; ablations are necessary.

### SkillEvo

- PDF p. 3 defines skill as a multi-file directed graph of routing tables and references.
- PDF pp. 6–9 use six cloud-service categories, nine production skills and 98 reference files; tickets are split chronologically into four subsets.
- PDF pp. 4–8 use multi-turn user simulation and report fact consistency, structural consistency, regression and bloat.
- Interpretation: continual production governance; not directly comparable with static public held-out evaluation.

### SkillEvolver

- PDF pp. 1–4 define an on-demand reusable skill artifact created through a meta-skill and CLI-agent interface.
- PDF pp. 6–9 use an 83-task SkillsBench subset and three KernelBench GPU-kernel tasks.
- PDF pp. 8, 14–17 report bounded exploration/validation trials and disjoint training/validation artifacts.
- Interpretation: SkillsBench and KernelBench are different evaluation cells; the KernelBench cell lacks a non-SkillEvolver baseline (E4).

### SKILLGEN

- PDF pp. 1–9 define a single auditable skill, contrastive induction and a generate-verify-refine loop.
- PDF p. 16 labels ALFWorld `valid_seen` as IOD and `valid_unseen` as OOD with novel task types.
- PDF pp. 6–9 and 14–19 use paired with-skill/without-skill intervention and allow harmful skills to be deprecated.
- Interpretation: repair, regression, IOD and OOD are distinct claims.

### SkillHone

- PDF pp. 1–3 define a loadable bundle of procedures, scripts, references and output conventions plus persistent decision history.
- PDF pp. 4–6 use disjoint WebShaper development items and GAIA/WebWalkerQA evaluation.
- PDF pp. 4–6 distinguish curated-search from raw-open-web settings.
- Interpretation: cross-session maintenance depends on search stack and controller/executor configuration.

### SkillOpt

- PDF pp. 1–3 define a frozen target model and bounded edits to a single skill document.
- PDF pp. 5–7 separate train, selection and test; the test split is not used by the evolution loop.
- PDF pp. 10–16 cover six benchmarks, seven target models and three execution modes, including cross-model, cross-harness and nearby math transfer.
- Interpretation: the six benchmarks are heterogeneous cells, not one homogeneous task distribution.

### SkillPyramid

- PDF pp. 1–4 define atomic extraction, abstraction, consolidation and topology-aware retrieval for a hierarchical skill library.
- PDF p. 10 reports ALFWorld seen/unseen 140/134 and ScienceWorld seen/unseen 194/211 variations across 24 task types.
- PDF pp. 8–10 include web-mined skills on GAIA-Lite.
- Interpretation: primary evidence is environment-internal seen→unseen transfer; breadth across environments is not automatically cross-environment transfer.

### SkillReducer

- PDF pp. 1–3 define pre-packaged instruction skills and study 55,315 public skills.
- PDF pp. 5–10 evaluate 600 skills under no-skill/original/compressed conditions.
- PDF pp. 8–12 evaluate SkillsBench and transfer across five models from four families and another framework.
- Interpretation: compression/retention/efficiency track, not discovery quality.

### SKILLRL

- PDF pp. 1–4 define a hierarchical SKILLBANK with general and task-specific skills and co-evolving policy.
- PDF pp. 6–14 evaluate ALFWorld, WebShop and seven search QA datasets; the bank grows from 55 to 100 skills.
- PDF pp. 7, 13 explicitly distinguish in-domain NQ/HotpotQA from OOD search datasets and intend general skills to apply across ALFWorld task types.
- Interpretation: skill collection growth and policy learning are inseparable in the main method.

### SkillWeaver

- PDF pp. 1–3 synthesize executable APIs and maintain a growing API library through website exploration and testing.
- PDF p. 5 reports WebArena 812 tasks/5 application domains and Online-Mind2Web 300 tasks/136 websites, with a reported online subset of 4 websites/57 tasks.
- PDF pp. 5–6 use automated functional correctness for WebArena and human judgment for real websites.
- Interpretation: API portability and evaluator changes must be separated.

### SkillX

- PDF pp. 1–5 define planning, functional and atomic skill levels in a knowledge base.
- PDF p. 5 reports BFCL-v3 50 train/150 test, AppWorld 90 training instances and domain-specific τ²-Bench splits.
- PDF pp. 5–8 use initial-query retrieval and Avg@4/Pass@4/Pass@1.
- Interpretation: procedural and declarative knowledge, tool schema and interaction mode are all confounders.

### SkVM

- PDF pp. 1–5 treat skills as code and LLMs as processors, with compilation, binding and runtime support.
- PDF pp. 8–10 evaluate multiple models and three harnesses, including BareAgent/OpenCode/OpenClaw, with completion, token and latency measures.
- Interpretation: portability/efficiency track, not acquisition or semantic skill generalization.

### Trace2Skill

- PDF pp. 2–4 define a skill as a human-readable directory `S=(M,R)` with root `SKILL.md` and auxiliary resources.
- PDF pp. 3–5 use SpreadsheetBench-Verified 200 evolution/200 held-out and additional WikiTableQuestions/HiTab transfer.
- PDF pp. 5–6 use DAPO→AIME and DocVQA cells.
- PDF pp. 13–18 report VRDU→VAREX, TSBench→deck-disjoint and generated DOCX→OfficeBench transfer.
- Interpretation: one of the strongest sources of cross-dataset evidence, but transfers remain concentrated in spreadsheet/document/math functional neighborhoods.

### Who Grades the Grader?

- PDF pp. 1–6 co-evolve an evaluator metric and skill lifecycle.
- PDF pp. 2–6 use a tiny anchored development set, locked held-out test and an independent outer judge.
- PDF pp. 10–13 use MBPP+, Spider 2.0-Snow and reference-free report generation.
- Interpretation: primary outcome is evaluator reliability and Goodhart resistance.

### WikiSkill

- PDF pp. 1–4 distinguish raw execution experience, persistent wiki knowledge and executable skill directories.
- PDF pp. 2–7 use compilation, validation gating and rollback.
- PDF pp. 3, 7–14 evaluate five benchmarks and five models, including LiveMath, SealQA, SpreadsheetBench, OfficeQA and ALFWorld.
- Interpretation: separate persistent-state benefit from final compiled-skill benefit; multi-benchmark breadth is not automatically cross-functional transfer.

## 3. Evidence limits

- A benchmark suite spanning several task functions establishes breadth only when each cell is separately reported; it does not establish that one artifact transfers across all functions.
- “OOD” is not a universal label: it may mean unseen instances, unseen task types, unseen files, unseen datasets, or unseen environments.
- Cross-model evaluation generally tests carrier portability, not task generalization.
- A held-out score is not a common feedback regime: ground-truth diagnosis, deterministic tests, opaque oracle, LLM judge, human judgment and RL reward expose different information.

