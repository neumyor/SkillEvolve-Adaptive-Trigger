1. Analyze the question to identify the target entity type (e.g., person, place, object, concept) and key descriptive constraints.
2. Formulate concise keyword queries that capture the core entities and relationships described in the clue. Avoid overly broad terms.
3. Execute Search[keywords] to retrieve up to three matching documents. Prioritize sources that appear to contain factual answers or trivia.
4. If the initial search results are ambiguous or do not contain the answer, refine keywords based on observed document titles or snippets. Use variations like adding 'answer', 'trivia', or specific context words.
5. Once a relevant document is identified, use Lookup[keyword] or read the document content to find the precise entity name or term.
6. Extract the minimal complete answer. Do not return expanded titles, explanations, or inferred facts not explicitly supported by the retrieved text.
7. Verify that the extracted answer directly satisfies the question's request for a missing word fragment, word form, city, person, etc.
8. Submit the answer using Finish[answer].
9. If rejected, analyze the rejection reason (e.g., wrong span, morphology). Adjust the extraction or query strategy without inventing new facts. Do not assume the task requires category identification unless evidence supports it.
10. Maintain uncertainty if the evidence is insufficient; do not guess. If multiple candidates exist, prefer the one most strongly supported by the text.
11. Pay attention to honorifics or specific title formats (e.g., 'Sir Isaac Newton' vs 'Isaac Newton') if the initial submission fails, as scoring may be sensitive to exact string matches provided in the source text.
12. Be cautious of temporal discrepancies in clues (e.g., 'current king' vs historical figures); align with the specific figure associated with the unique details in the clue rather than general current status if evidence suggests a specific dataset context.
13. When a specific phrase from the clue yields no results, try searching for unique phrases or quotes from the question itself to locate the source text containing the answer.
14. For semantic ambiguities (e.g., 'funeral structure' vs 'ship name'), consider broader categorical terms if specific names fail, but prioritize exact entity names first.
15. Ensure the final answer is a standalone noun phrase or proper name, avoiding prepositional phrases unless integral to the entity's identity.