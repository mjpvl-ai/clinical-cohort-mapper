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

When adapting to support an additional proprietary clinical vocabulary containing Code IDs, Display names, Domains, Synonyms, Hierarchy, and Mapping relations:

1. **Schema Ingestion & Indexing**: Ingest the proprietary database into a standard representation storing mappings to standard public codes:
    ```json
    {
      "code_id": "PROP_90210",
      "display_name": "HbA1c level measurement",
      "domain": "measurement",
      "synonyms": ["A1c level test", "glycated hemoglobin"],
      "parents": ["PROP_8888"],
      "mappings": [{ "vocabulary": "LOINC", "code": "4548-4" }]
    }
    ```
2. **Hybrid Ingestion**: Add the display names and synonyms into the lexical FTS5 indexes and create embeddings for semantic search.
3. **Retrieval Resolution**:
   - **Direct Search**: Retrieve candidates directly from proprietary terms.
   - **Bridged Search**: If a query matches standard public codes (e.g. LOINC `4548-4`), query the relationship table to map the standard code to corresponding proprietary IDs.
4. **Precision Check**: Feed parent/child lineage into the Auditor to verify exact alignment with the query's clinical constraints.

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
