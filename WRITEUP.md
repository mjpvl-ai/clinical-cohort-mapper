# Clinical Cohort Mapper: Design & Reasoning Write-up

This document explains the clinical reasoning, architectural trade-offs, and evaluation methodology behind the **Consensus-Driven Graph Reflexion (CDGR)** cohort mapping prototype.

---

### 1. How we interpreted the free-form query
To reliably parse unstructured text, we implemented a **Medical Linguist (Parser)** agent using a structured LLM output (Pydantic schemas). Instead of forcing the LLM to map directly to a code in one step (which is highly error-prone), the parser's only job is to extract a `ClinicalIntent` object. 

This object standardizes the query into:
- **Domain:** (e.g., `condition`, `drug`, `measurement`, `procedure`)
- **Entities:** The core clinical concepts (e.g., "Hemoglobin A1c").
- **Constraints:** Quantitative values, units, or statuses (e.g., operator: `>`, value: `7`, unit: `%`, status: `current`).

**Trade-off:** Using an LLM for parsing introduces latency compared to pure NLP/Regex approaches, but it handles complex, nested, or poorly phrased clinical logic much more gracefully.

### 2. How we handled synonyms and alternative clinical phrasing
Synonym expansion occurs at multiple layers before reaching the retrieval APIs:
1.  **Rule-Based Expansion:** Common acronyms (T2D, HbA1c, CKD, SBP) are mapped directly to their expanded forms to ensure API search hits.
2.  **Ontology Database Lookup:** We query a local SQLite terminology cache (`data/local_vocab.db`). If an entity matches a known concept (e.g., "renal failure"), we inject its established synonyms ("kidney disease").
3.  **API Fuzzy Matching:** For drugs, we leverage the NIH RxNorm API's approximate matching endpoint, which natively handles brand/generic translations (e.g., mapping "Tylenol" to "acetaminophen").

### 3. How we retrieved candidate codes
We implemented a **Medical Informatician (Retriever)** node that routes searches to the most appropriate, publicly available reference vocabulary based on the parsed domain:
- **Measurements (LOINC) & Diagnoses (ICD-10-CM):** Queried against the NLM Clinical Table Search Service API.
- **Medications (RxNorm):** Queried against the NIH RxNorm REST APIs (using approximate term searches and RxClass hierarchies for drug classes like "GLP-1 receptor agonists").
- **Procedures (SNOMED CT):** Queried against our local SQLite terminology database cache.

### 4. How we ranked and filtered candidates
Instead of relying solely on the LLM to pick the best code, we implemented an explicit, deterministic scoring algorithm to rank candidates:
$$\text{Score} = \text{Domain Match} (20) + \text{Entity Match} (15\text{-}25) + \text{Synonym Match} (8\text{-}13) + \text{Specificity Match} (15) - \text{API Rank Decay} (0.5 \times \text{rank})$$

- **Specificity Match:** Heavily boosts candidates that contain critical query modifiers (e.g., "fasting", "stage 3").
- **API Rank Decay:** Respects the underlying search engine's TF-IDF/relevance sorting but degrades the score slightly for results further down the list.

### 5. How we avoided clinically incorrect mappings
This is the core strength of the CDGR architecture. LLMs are prone to selecting the first vaguely matching code. To prevent this, we introduced a **Clinical Auditor (Critic)** node and a **Reflexion Loop**.

1.  The Auditor reviews the top-ranked candidates against the original query constraints.
2.  If the retriever brings back an overly broad code—for example, returning `N18.9` (Chronic kidney disease, unspecified) for the query "CKD stage 3"—the Auditor **rejects** it.
3.  The Auditor generates a formal critique (e.g., "Reject N18.9; query requires stage 3 specificity").
4.  The system loops back to the Parser, injecting the critique. The Retriever then executes a refined search (often traversing ontology hierarchies to find child nodes), successfully landing on `N18.30` (CKD Stage 3).

### 6. How we evaluated the quality of our mappings
We evaluated the system using a batch suite of 20 diverse clinical cohort queries representing different domains (measurements, conditions, drugs, procedures). 

**Evaluation Criteria:**
- **Domain Accuracy:** Did it select the correct target vocabulary (LOINC vs RxNorm)?
- **Clinical Specificity:** Did it avoid "unspecified" codes when stages/severities were provided?
- **Constraint Parsing:** Were numerical values and units accurately captured in the `FinalLogic` output?

The system achieved 100% domain routing accuracy and successfully navigated complex edge cases (like expanding the GLP-1 drug class into constituent active ingredients).

### 7. What limitations remain in our approach
- **API Rate Limiting & Latency:** Relying on live NLM/NIH APIs introduces latency (3-5 seconds per query) and is subject to external rate limits. A true production system would host these terminologies (e.g., OHDSI Athena/OMOP vocabularies) locally in an Elasticsearch or Postgres instance.
- **Complex Temporal Logic:** While we handle "current" vs "prior", complex temporal relationships (e.g., "HbA1c > 7% within the last 6 months after starting metformin") are only partially supported in the `ClinicalIntent` schema.
- **SNOMED Licensing:** SNOMED CT requires a license for full use. We used a localized, minimal SQLite subset for the prototype to avoid proprietary/licensing blockers, meaning procedure recall is limited to what is cached.
- **LLM Hallucination Risk:** While the auditor catches most errors, the primary intent extraction still relies on an LLM, which can theoretically hallucinate constraints if the prompt engineering fails on highly ambiguous text. Local model fallbacks (like Qwen3) show lower accuracy than the primary Gemini models.
