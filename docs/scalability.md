# Production Scalability & Improvement Plan

This document details the engineering roadmap, performance profiling, scalability strategies for massive databases, and extensions of the Clinical Cohort Query Mapper.

---

## Performance, Cost & Robustness Profile

| Metric | Current Prototype Profile | Primary Bottlenecks | Production Recommendations |
| :--- | :--- | :--- | :--- |
| **Latency** | **Single-Pass**: 7–10s<br/>**Self-Correction**: 20–35s | Synchronous external network calls (`urllib.request`) and sequential LLM inference times. | • Implement local vocabulary caches.<br/>• Use asynchronous parallel processing.<br/>• Set up Redis semantic caching. |
| **Cost** | **~$0.001 – $0.003** per query (~5k input/output tokens total). | Tokens scale linearly with the number of candidate codes audited and self-correction iterations. | • Fine-tune an on-premise local model (e.g., Llama-3-8B).<br/>• Eliminate LLM calls entirely for cached matches. |
| **Robustness** | **High precision** for complex criteria.<br/>**Low robustness** on external outages and small fallback models. | Dependency on NIH/NLM REST APIs. Fallback to `qwen3:0.6b` fails structured parsing tasks. | • Host vocabularies locally (no external APIs).<br/>• Use larger local fallbacks (e.g., Llama-3-70B).<br/>• Human-in-the-Loop review queue. |

---

## Extending to Proprietary Vocabularies

When adapting to support an additional proprietary clinical vocabulary containing Code IDs, Display names, Domains, Synonyms, Hierarchy (parent/child relationships), and Mappings to public vocabularies, we must design the ingestion and retrieval flow to preserve **both high recall and high precision**:

### 1. Database Schema & Indexing Adaptation
We ingest the proprietary vocabulary into our relational store using a structured schema:
*   `proprietary_concepts`: Maps `code_id`, `display_name`, and `domain` (routed to standard categories: measurement, condition, drug, procedure, observation).
*   `proprietary_synonyms`: A child table containing text alternatives for each `code_id`.
*   `proprietary_hierarchy`: A self-referential closure table mapping ancestral paths (`parent_code_id`, `child_code_id`, `distance`).
*   `proprietary_public_mappings`: A bridge table linking `proprietary_code_id` to public concept codes (`vocabulary`, `code`).

To support fast lookup, we index `display_name` and `synonyms` using SQLite FTS5 (Full-Text Search) and generate semantic embeddings for semantic search.

### 2. Maintaining High Recall
To guarantee we fetch all relevant candidate concepts, our `MedicalInformatician` (Retriever) implements a two-pronged search strategy:
*   **Lexical & Semantic Match Expansion**: The search query is matched against the proprietary `display_name` and `synonyms` index. Any synonyms linked to the query are extracted, boosting candidates that match clinical acronyms or variants.
*   **Bridged Search**: If the user query is mapped to a public vocabulary code (e.g. LOINC `4548-4` for HbA1c), the retriever queries the `proprietary_public_mappings` bridge table. It immediately resolves and retrieves any corresponding proprietary `code_id`, resolving terminology mismatch gaps.
*   **Descendant Class Expansion**: Using the `proprietary_hierarchy` table, if a matched concept has descendants (child concepts), all children are recursively fetched to ensure sub-types are included in the recall pool.

### 3. Maintaining High Precision
To filter out false positives and ensure the final mapping is strictly correct:
*   **Domain/Category Enforcement**: Candidates are automatically pre-filtered in the SQL query by the parser-extracted `domain` (e.g., measurement vs drug), immediately pruning cross-domain false positives.
*   **Ancestral Hierarchy Auditing**: The `ClinicalAuditor` evaluates the lineage of the candidates. By checking the parent/child hierarchy, the Auditor detects if a code is overly broad (e.g. a parent concept like "unspecified renal disease") when the query specified details (e.g. "stage 3"). If so, it rejects the code, triggers the reflexion loop, and sets a negative constraint to target specific child codes.
*   **Bridge Mapping Consensus Verification**: For mappings resolved via public vocabularies, the Auditor verifies that the display name and semantics of the resolved proprietary code match the clinical intent of the public code, eliminating LLM hallucinations.

---

## Scalability Analysis for 3M+ Records

If the database is scaled to **3 million records** (e.g., full UMLS Metathesaurus or OHDSI OMOP vocabulary containing LOINC, SNOMED, and ICD-10), the current implementation will hit significant limitations:

1. **SQLite Lexical Search Bottleneck**:
   - *Current issue*: Uses `LIKE '%term%'` patterns, which bypasses indexes and causes slow full-table scans.
   - *Production Solution*: Upgrade to **SQLite FTS5** virtual tables for tokenized search, or migrate to **Elasticsearch / PostgreSQL GIN** indexing to perform queries in $O(\log N)$ log time.
2. **In-Memory Python Ranking Bottleneck**:
   - *Current issue*: String matching and candidate sorting in Python loops consume excessive RAM and CPU when handling thousands of candidates.
   - *Production Solution*:
     - **Database Pre-filtering**: Restrict domain and vocabulary directly in the database query.
     - **Top-K Retrieval**: Enforce a strict `LIMIT 100` on the database query before objects are parsed into Pydantic models.
     - **Push Down Scoring**: Shift lexical match ranking directly into the database engine (e.g. BM25 or Postgres `ts_rank`).
     - **Vector Search**: Use pgvector or Milvus for Approximate Nearest Neighbor (ANN) vector searches.
3. **Graph Traversal Bottleneck**:
   - *Current issue*: Multi-level relationship lookups (parent/child/ancestor paths) in Python create recursive database round-trip overhead.
   - *Production Solution*: Use recursive SQL **Common Table Expressions (CTEs)** to resolve paths in a single query execution, or migrate to a graph database like **Neo4j**.

---

## 5-Stage Production Engineering Roadmap

```
  Stage 1: Local Ingestion ──► Stage 2: Database Search ──► Stage 3: Async & Cache ──► Stage 4: Local LLM ──► Stage 5: CITL Review
```

- **Stage 1: Local Terminology Cluster**: Ingest standard OMOP/Athena vocabularies entirely into a local database cluster (e.g. PostgreSQL or Elasticsearch) to eliminate external NIH/NLM REST dependencies.
- **Stage 2: Database-Level Retrieval & Scoring**: Implement full-text search indexes and push text-scoring weights into the query. Limit candidate returns to 100 before model parsing.
- **Stage 3: Asynchronous Orchestration & Caching**: Refactor LangGraph workflows and database connectors using Python's `asyncio` for concurrent execution. Implement a **Redis Semantic Cache** to bypass LLM execution for duplicate queries.
- **Stage 4: Self-Hosted LLMs**: Replace external Gemini API dependencies with local, self-hosted LLM instances (e.g., Llama-3-70B-Instruct), keeping clinical data secure on-premise.
- **Stage 5: Clinician-in-the-Loop (CITL) UI**: Build a reviewer UI where low-confidence mappings ($<0.85$ confidence) are flagged for manual review, with overridden mappings fed back to improve the model.

---

## Integrating Healthcare MCP Servers

To expand capabilities, the orchestrator can integrate Model Context Protocol (MCP) servers, such as the open-source [healthcare-mcp-public](https://github.com/Cicatriiz/healthcare-mcp-public) server.

```
 [Linguist]    [Informatician]    [Auditor]  (A2A Agents)
     │                │               │
     └────────────────┼───────────────┘
                      ▼
            [ A2A Gateway Layer ]
                      │
                      ▼ (MCP Client Connection via STDIO/SSE)
         [ Healthcare MCP Server ]
           ├── FDA Drug Tool (fda-tool.js)
           ├── ICD-10 Terminology Tool (medical-terminology-tool.js)
           └── PubMed Research Tool (pubmed-tool.js)
```

1. **ICD-10-CM Candidate Expansion**: The Informatician invokes `lookupICDCode` from the MCP server to search codes and names from the NLM ClinicalTables API.
2. **Clinical trials & FDA Label Checks**: The Clinical Auditor queries `fda-tool.js` to extract ingredients and indications for unknown drug inputs to resolve domain classification.
3. **Medical Research Reference**: For complex or ambiguous conditions, the auditor queries PubMed (`pubmed-tool.js`) to back up reflexion decisions with clinical literature search results.
