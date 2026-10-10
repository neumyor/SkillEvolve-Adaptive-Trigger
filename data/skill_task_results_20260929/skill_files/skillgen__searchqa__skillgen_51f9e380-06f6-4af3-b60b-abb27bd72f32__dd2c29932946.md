## Contextual abstract
This task requires answering open-domain questions using a set of noisy, fragmented text snippets retrieved from various web sources and encyclopedias. You must filter out irrelevant information, synthesize the facts, and produce a single, precise, canonical string that directly answers the prompt. The final output is evaluated using strict exact-match metrics, meaning your response must be perfectly formatted as a standalone value without any extraneous text, conversational padding, or formatting artifacts.

## Successful experiences
1. **Decompose and Constrain:** Break the prompt into distinct factual constraints, keywords, and identifying features before searching the documents.
2. **Targeted Context Scanning:** Systematically scan the provided documents to locate text segments that explicitly match the extracted constraints. Rely strictly on explicit textual evidence.
3. **Cross-Reference and Verify:** Verify that the candidate entity satisfies every single decomposed constraint. Reject partial matches in favor of complete cross-referenced alignment across multiple clues.
4. **Extract Canonical Names:** Extract the full, exact entity name or term exactly as it appears in the source text. Avoid partial, colloquial, or shortened versions of the target entity.

## Failure lessons
* **Signal:** The final output includes markdown formatting, bolding, labels (e.g., Final Answer:), or conversational filler.
  **Counter-action:** Output only the raw, unformatted string. Strip all markdown, prefixes, and explanatory text to satisfy automated exact-match parsers.
* **Signal:** The response provides multiple alternative phrasings, parenthetical variations, or hedging language.
  **Counter-action:** Commit to a single, definitive answer. Do not include synonyms, alternatives, or clarifying suffixes in the final output string.
* **Signal:** The generation truncates mid-sentence or ends before explicitly stating the final answer.
  **Counter-action:** Ensure the generation completes fully. Always synthesize findings into a concise, explicit final string before reaching token limits.
* **Signal:** The output includes honorifics, descriptive modifiers, or non-canonical name variants.
  **Counter-action:** Ground the exact object. Remove all titles, adjectives, and parenthetical expansions to isolate the minimal canonical entity required by the prompt.