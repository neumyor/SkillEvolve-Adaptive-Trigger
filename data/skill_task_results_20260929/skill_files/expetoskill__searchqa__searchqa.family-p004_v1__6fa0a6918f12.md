1. Analyze the query to determine if it seeks a lexical item (word/term) defined by meaning, origin, or relationship, rather than a named entity described by external facts.
2. Formulate search keywords focusing on the definition, synonyms, or etymological clues provided in the question (e.g., 'Latin root', 'sound of', 'synonym for').
3. Execute Search[keywords] to retrieve documents containing definitions or lexical databases.
4. If initial searches fail, try alternative synonyms or related terms (e.g., if 'Doppelgänger' fails, try 'lookalike').
5. Upon finding a potential candidate, verify it against the clue's constraints (part of speech, length, specific nuance).
6. If the first candidate is rejected or uncertain, consider morphological variants (e.g., noun vs. gerund: 'meander' vs. 'meandering') or single-word synonyms (e.g., 'Speech Bubble' vs. 'Balloon').
7. Use Lookup[keyword] within retrieved documents to confirm precise definitions or usage contexts if available.
8. Submit the minimal complete answer using Finish[answer]. Avoid expanded titles or explanations unless the answer itself requires them.
9. If evidence is ambiguous, prioritize the most direct lexical match found in the documents over external knowledge assumptions.
10. For spoonerisms or puns, identify the intended phrase by correcting the phonetic swap or wordplay, ensuring the answer is the full corrected idiom or phrase, not just a component word.
11. When searching for specific trivia or Jeopardy clues, include the source context (e.g., 'Jeopardy') in keywords if general lexical searches fail.
12. Prioritize exact string matches from source text over inferred variations; do not guess nicknames or aliases unless explicitly supported by the text.
13. Limit search iteration depth to one targeted adjustment based on initial snippet analysis; avoid excessive refinement loops.
14. Do not assume multi-hop reasoning or cross-document linking is required; rely on single-document verification where possible.
15. Exclude tasks requiring morphological normalization beyond standard naming conventions (e.g., case sensitivity, hyphenation) unless the source text explicitly varies them.
16. If a task involves a category label (e.g., 'insulator' vs 'nonconductor'), select the term most directly defined by the clue's phrasing in the source.
17. Verify that the answer fits the grammatical structure implied by the question (e.g., adjective vs. noun).
18. Reject candidates that require external knowledge not present in the retrieved documents.
19. Ensure the final answer is self-contained and does not rely on implicit context from the search query.
20. Maintain strict fidelity to the source text; if the source defines a term differently than common usage, follow the source.