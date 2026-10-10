# Question Answering Skill

## Core Principles

1. **Evidence Synthesis & Cross-Referencing**: Do not rely on a single sentence or document. Scan all provided passages to find corroborating evidence. If multiple documents mention the same fact or entity, use this convergence to increase confidence. Combine clues from titles and body text.

- **Common Denominator Resolution**: If the question asks for a shared trait, species, or category between two or more entities mentioned in different documents, identify each entity first, then determine their commonality. Do not stop at identifying just one entity.

- **Minimal Entity List Intent**: If the question consists only of a list of entities connected by '&', ',', or 'and' (e.g., 'Entity A & Entity B'), it typically asks for their **shared location**, **category**, or **origin** (e.g., 'Monaco'), **NOT** their relationship (e.g., 'sisters'). 
     - **Action**: Identify the common geographic, organizational, or categorical attribute linking the entities. Do not output the relationship type (e.g., 'siblings', 'colleagues') unless the question explicitly asks 'What is the relationship?'.
     - **Example**: 'Princess Caroline & Princess Stephanie' -> Answer: 'Monaco' (Shared Origin/Location), NOT 'sisters'.
   - **Numeric & Unique Identifier Matching**: Treat specific numbers (e.g., distances, dates, counts) as high-confidence unique identifiers. If a question cites a specific value (e.g., "51.5 kilometers"), scan all documents for this exact value to locate the relevant entity, even if the entity name is not explicitly linked in the question.

- **Fragmentary Query Resolution**: If the question consists only of facts, dates, or locations without a clear interrogative structure (e.g., "February 6, 1911 in Tampico, Illinois"), treat these as unique identifiers. Identify the single entity that satisfies *all* provided constraints simultaneously. Do not attempt to answer a missing question; instead, assume the intent is to identify the subject defined by the conjunction of these facts.
2. **Keyword & Identifier Matching**: For trivia, definition, or Jeopardy-style questions, identify unique phrases, nicknames, or specific descriptors in the question (e.g., "Happiest Place on Earth"). Scan the context for these exact or synonymous phrases to locate the relevant passage.
- **Verbatim Clue Detection & Format Parsing**: In trivia datasets, context passages (especially **flashcards**, glossaries, study guides, social media posts, or forum snippets) often contain the *exact wording* of the question or clue. Look for structured formats like `Clue | Answer`, `Question: ... Answer: ...`, or `Q: ... A: ...`. Treat these verbatim matches as high-confidence signals and extract the associated answer directly, ensuring you parse the delimiter correctly to separate the clue from the solution. 

- **Descriptive Phrase & Quote Matching**: For trivia questions that define an entity via a unique quote, nickname, or descriptive phrase (e.g., "Nature's most labor-intensive fruit", "America's Sherlock Holmes in Sneakers"), scan the context for this exact phrasing. The entity associated with this specific description in the text is the answer, even if the entity's common name is not the primary subject of the sentence.
     - **Metadata & Title Scanning**: Also scan document **titles**, **filenames**, and **metadata** (e.g., YouTube video titles, archive labels, GitHub paths, J! Archive entries) for exact question matches. These often serve as direct pointers to the answer key or the relevant passage, even if the body text is sparse.
- **Cross-Document Entity Linking**: When no single document contains all required information, use one document to **identify an entity** (e.g., find the author of a book) and another to **verify it meets specific constraints** (e.g., confirm the author wrote another specific book or fits a biographical detail). Synthesize these separate facts to confirm the answer. This is crucial when the question combines multiple facts (e.g., "Author of X who also wrote Y").

- **Constraint-Specific Co-occurrence**: When a question uses a common noun or polysemous term (e.g., 'dipper', 'shack'), do not rely on the most frequent definition. Instead, scan for the document where this term **co-occurs** with the other specific constraints in the question (e.g., 'sticky substance', 'pub'). The correct answer is found in the intersection of these specific contexts, not in general definitions.

- **Polysemous Riddle Resolution**: For riddle-style questions asking for a term that fits two different descriptions (e.g., 'Term for X, or what Y is put to'), identify a single word that satisfies *both* semantic roles. Scan the text for words that appear in contexts matching *each* part of the clue, even if they are not defined as the primary subject of a document. Prefer the word that bridges the gap between the two constraints (e.g., 'Test' for both 'international match' and 'put to the test').
   - **Multi-Attribute Verification**: When a question imposes multiple distinct constraints (e.g., "Played Role A in Movie X" AND "Played Role B in Show Y"), do not assume a match based on a single attribute. Explicitly verify that the candidate entity satisfies *every* constraint, even if this requires synthesizing facts from separate documents. Reject candidates that match only a subset of the criteria.
   - **Acronym & Fragment Decomposition**: For questions involving acronyms or multi-part identifiers (e.g., 'What does the S in LSUS stand for?'), break the query into components. Use one document to establish the full name/entity associated with the acronym, and another to isolate the specific component requested. Do not assume the full name is the answer if only a part is requested.
3. **Title Leverage**: Document titles often contain high-value keywords or direct answers. Check titles first if the question matches a specific entity name or topic.
   - **Titles as Direct Answers**: For fill-in-the-blank or minimal trivia clues, treat the document title itself as a potential candidate for the final answer (e.g., if the question asks for a "season" and a document is titled "Fall", the answer is likely "Fall").
   - **Metadata & Clue Matching**: For trivia or Jeopardy-style questions, check if any document title or metadata (e.g., search queries, archive labels) contains the *exact wording* of the question or clue. These often serve as direct pointers to the answer key or the relevant passage, even if the body text is sparse.
- **Implicit Intent Inference**: If the question is minimal (e.g., only a movie title, year, catchphrase, or person's name), infer the most likely requested attribute. 
     - **Catchphrase & Title Resolution**: For minimal clues consisting of a famous quote, catchphrase, or slogan (e.g., "Yabba Dabba Do!", "Just Do It"), prefer the **Source Work** (Show, Movie, Brand) or **Origin** over the specific character or speaker, unless the question explicitly asks "Who said...?". (e.g., "Yabba Dabba Do!" -> "The Flintstones", NOT "Fred Flintstone").
     - **Caution**: Do not default to **director** for films or **medium** for series unless the clue explicitly asks for "who directed" or "what format". Often, minimal clues ask for the **subject**, **theme**, or **source material** (e.g., "West Side Story" -> "Romeo and Juliet").
     - Check if the clue describes the entity itself (e.g., "This classic...") rather than its creator. If ambiguous, prioritize the **main subject** or **inspiration** over metadata like directors or publishers.
4. **Noise Filtering**: Ignore irrelevant documents or passages. Focus only on sections that contain potential answers or semantic matches to the question.

- **Constraint-Based Filtering**: When multiple documents contain similar keywords, prioritize the document that satisfies *all* constraints in the question (e.g., if asking for a "molecule structure," prefer documents describing geometry over those only mentioning chemical usage).
   - **Multi-Constraint Intersection**: When disambiguating between entities, do not rely on a single matching keyword. Identify all distinct constraints in the question (e.g., "Former First Lady" AND "1992 Candidate") and verify that the candidate entity satisfies **every** constraint. Reject entities that match only a subset of the criteria.
5. **Answer Precision & Minimal Match**:
- **Exact Form Matching**: Provide the answer exactly as it appears in the source text or as required by the question's grammar. 

- **Syntactic Slot Filling**: For fill-in-the-blank or riddle-style questions (e.g., "It's the traditional color..." or "...relative of this rare aquatic mammal"), ensure the answer fits grammatically into the question's sentence structure. Include articles (a/an/the) if the question stem implies them or if the gold standard requires them for natural phrasing.

- **Parenthetical Constraints**: Pay close attention to numbers or symbols in parentheses at the end of trivia questions (e.g., "(4)", "(7 letters)"). These often indicate the required **character count** or **word count** of the answer. Use this constraint to filter candidates (e.g., prefer 'Moll' over 'Moll Flanders' if '(4)' is specified).
     - **Pluralization & Articles**: If the question or context implies a plural (e.g., "these fruits") or includes an article (e.g., "the South Sea Bubble"), include them. Do not arbitrarily singularize or strip articles if they are part of the standard name or required for grammatical fit.
     - **Capitalization**: Preserve the capitalization of proper nouns and specific terms as found in the evidence.
     - **No Unnecessary Truncation**: Do not shorten multi-word proper names (e.g., use "Brown pelican" not just "pelican") unless the question explicitly asks for a generic category.

- **Compound Name Integrity & Trivia Brevity**: For entities with standard compound names, provide the full name ONLY if the question or context explicitly requires it (e.g., fill-in-the-blank with multiple slots). 
     - **Trivia Short-Form Preference**: In Jeopardy-style or trivia contexts, prefer the **common short form** or **nickname** if it is the primary way the entity is referred to in the clue or popular culture (e.g., 'Studio 60' instead of 'Studio 60 on the Sunset Strip', 'Bull Moose' instead of 'Bull Moose Party', 'Pyre' instead of 'funeral pyre').
     - **Generic Term Retention vs. Stripping**: 
       - **Retain** generic terms if they are part of the standard proper noun and essential for disambiguation or canonical recognition (e.g., 'Lake Superior' not 'Superior', 'Bear Market' not 'Bear', 'Eagle Scout' not 'Eagle').
       - **Strip** generic terms if the core name is sufficient and widely recognized as the canonical entity (e.g., 'Showboat' not 'Show Boat', 'Roanoke' not 'Roanoke Island').
       - **Check Context**: If the source text or clue uses a specific phrasing (e.g., 'the bear', 'an Eagle Scout'), mirror that grammatical structure including articles.
     - **Canonical Form & Brevity**: For Jeopardy-style or minimal clues, prefer the **shortest common canonical form** of the answer that satisfies all constraints. If the gold standard is a single word or short phrase (e.g., 'laundries' vs 'hand laundries'), prefer the broader or simpler term unless the modifier is critical to the definition.

- **Spelling Variants & Standardization**: If multiple spellings exist (e.g., 'filo' vs 'phyllo'), prefer the most common standard dictionary spelling or the one explicitly used in the question's source material if identifiable. Do not default to the first variant found in the text if a more standard form exists.
       - **Name Formatting**: For historical figures, prefer the common name without middle initials (e.g., 'Lyndon Johnson' over 'Lyndon B. Johnson') unless the initial is required for disambiguation or explicitly requested.
       - **Proper Noun Phrasing**: For geographic features or titled works, prefer the common colloquial proper noun phrase including articles if standard (e.g., 'the Adirondacks' over 'Adirondack Mountains', 'Phone Booth' over 'phone booths'). Match the capitalization and singular/plural form of the title/entity as it is commonly cited.
       - **Mononyms**: Prefer single-name references (e.g., 'Fragonard' over 'Jean-Honoré Fragonard') unless the question explicitly asks for the full name or disambiguation is required.
- **Simplification**: Prefer simple categorical terms over technical compounds if both fit (e.g., 'a balloon' over 'speech balloon') unless the specific modifier is the key differentiator.
       - **Strip Generic Suffixes**: For proper nouns, remove generic geographic or organizational suffixes (e.g., 'Island', 'City', 'Company', 'Satellite Radio') if the core name is sufficient and canonical (e.g., prefer 'Roanoke' over 'Roanoke Island', 'Sirius' over 'Sirius Satellite Radio') unless the question explicitly asks for the full formal title.
       - **Singular Default for Trivia**: For Jeopardy-style or definition clues asking for a category, fruit, or phenomenon, default to the **singular** form (e.g., 'strawberry', 'tsunami') unless the question phrasing explicitly demands a plural (e.g., 'these fruits').
       - **Grammatical Precision**: Match the exact grammatical number (singular/plural) and capitalization of the term as it appears in the defining context. Do not arbitrarily singularize plural proper nouns (e.g., use 'Fungi' not 'fungus') or lowercase formal categories.
       - **No Disjunctions**: Do not provide multiple options (e.g., 'A or B'). Select the single most precise canonical term supported by the evidence.
       - **Strip Descriptors**: Remove honorifics, titles, and extra descriptors (e.g., 'Sir', 'Dr.', 'the') unless they are part of the required proper noun structure.
   - **Trivia Context**: For questions resembling Jeopardy clues or riddles, look for the specific entity or term that fits the blank or description exactly. Avoid summarizing the context; extract the precise answer key.
   - **Ambiguity**: If multiple entities match a keyword, prioritize the one that fits the specific constraints of the question (e.g., "French thief" vs just "thief") rather than the most frequent mention in the text.

- **Specific Constraint Priority**: When multiple entities are mentioned in relation to a keyword (e.g., "split in half"), prioritize the entity that is *explicitly* described with that constraint in the text over entities that are merely associated with it generally. Do not default to the most famous brand or entity if a less famous one is the direct subject of the descriptive clause.

- **Answer Type Verification**: Before finalizing, verify if the question asks for a *specific entity* (Name) or a *descriptor/category* (Role, Time Period, Type).

- **Clue Intent Analysis**: For quotes or riddles ending in "this" or similar pointers (e.g., "...pail and this"), determine if the clue asks for the *missing word* in the quote or the *source* of the quote. If the quote is incomplete, the answer is likely the missing word/phrase (e.g., 'rag'), not the title of the work. If the clue describes an object via a quote (e.g., "trapped in one of these"), answer with the specific object (e.g., 'Phone Booth'), not the film title or category.

- **Contextual Alias Resolution**: If a question asks what an entity is *called* by a specific group or in a specific context (e.g., "What did the Waltons call Zeb?"), prioritize the relational title or nickname used in that context (e.g., "Grandpa") over the entity's formal name (e.g., "Zebulon Walton"). Verify that the text explicitly links the alias to the entity within the specified social or narrative frame.
     - If the question uses phrases like "This person...", "This role...", or "This period...", ensure the answer matches that type. For example, if asked for the role of a person described, answer with the title (e.g., "The editor") rather than their name, if the context supports that abstraction.

## Step-by-Step Strategy

1. **Analyze the Question**: Identify the key entity, fact, or constraint being requested. Determine if it is a direct factual query, a definition, or a trivia clue.
2. **Search Context**: 
   - Check document titles for direct matches.
   - Scan passages for keywords, unique identifiers, or semantic matches from the question.
3. **Verify Evidence**: Ensure the selected passage directly supports the answer. Cross-reference with other documents if available to resolve ambiguity or confirm facts.
4. **Extract Answer**: Isolate the specific entity that satisfies the question's constraints (e.g., if asking for a "country", do not answer with a city).
5. **Format Output**: Wrap the final concise answer in `<answer>...</answer>` tags. Ensure no explanatory text exists inside these tags.
