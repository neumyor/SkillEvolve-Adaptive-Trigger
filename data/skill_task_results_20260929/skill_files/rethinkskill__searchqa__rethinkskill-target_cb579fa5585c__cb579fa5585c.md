---
name: "rethinkskill-target"
description: "Dynamic skill for the current native QA task."
---

# RethinkSkill Target Guidance

Ground the answer in `task.md` and follow its output contract.

## Dynamic guidance

# Question Answering Skill

## Extraction Guidelines
1. **Entity-Value Differentiation**: When parsing structured data or contextual lists, isolate the concrete answer entity rather than extracting generic headers, categories, or labels. Prioritize specific named entities, numbers, or dates over descriptive class names.
2. **Minimal Span Priority**: Preserve integral geographical prefixes and multi-word canonical titles. Aggressively strip non-intrinsic administrative, corporate, or locative modifiers (`University`, `Radio`, `Party`, `Desert`, `Island`, `City`, `State`, `Park`, `Road`, `College`, `Institute`, `Magazine`, `Journal`, `Center`, `Complex`, `Campus`, `Facility`) and redundant contextual classifiers (`Power`, `River`, `Gravy`, `Vitamins`, `Types`, `Kind`). Drop middle initials and secondary forenames for personal identifiers (e.g., drop `J.` or `Junius`), and reduce historical figures to their mononym or surname where standard usage permits (e.g., `Napoleon Bonaparte` → `Napoleon`). Conversely, strictly preserve essential geographic prefixes (e.g., `Lake Superior`, `San Francisco`) and retain all honorifics (`Sir`, `Lord`, `Dr.`, `King`, `Queen`) without exception.
3. **Form & Spacing Mirroring**: Mirror source spelling, punctuation, capitalization, and exact plurality verbatim. Strictly prohibit any form of normalization, lemmatization, or morphological adjustment (e.g., do not change 'Meandering' to 'Meander', 'Bears' to 'Bear', or 'Pineapples' to 'Pineapple'). Enforce strict source fidelity regarding plurality: if the source text uses plural forms, the extraction must remain plural; do not infer singular forms, nor add missing articles or suffixes. Correct only obvious typographical spacing errors (merge split words). Do not expand contractions or merge adjacent distinct entities. Return the single most direct answer token; never enumerate lists or provide multiple alternatives separated by commas or conjunctions.
4. **Determiner & Connector Filtering**: Strip standalone articles (`a`, `an`, `the`), trailing prepositions, and coordinating conjunctions (`and`, `or`) from extracted spans, unless they are legally or culturally integral to a fixed proper name (e.g., *The Beatles*, *A Tale of Two Cities*). 
5. **Zero-Noise Output Protocol**: Return absolutely nothing but the refined token(s). Strictly prohibit appended sentences, explanations, confidence scores, quotation marks, metadata, or conversational text.
