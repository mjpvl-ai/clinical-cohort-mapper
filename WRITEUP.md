# Clinical Cohort Mapper: Design & Reasoning Write-up

This document provides a comprehensive technical write-up of the **Consensus-Driven Graph Reflexion (CDGR)** architecture, detailed analysis of system performance, cost, and robustness, diagnostics on scaling to 3M+ records, and an enterprise production engineering roadmap.

---

## 1. Core Architecture: Consensus-Driven Graph Reflexion (CDGR)

Standard clinical text parsers rely on single-pass heuristic keyword extraction or direct LLM mappings. These approaches fail in clinical environments due to semantic "hallucinations," vocabulary boundary violations (e.g., mixing LOINC with ICD-10), and a lack of clinical specificity (e.g., selecting an "unspecified" parent code instead of a highly specific clinical stage).

The **CDGR architecture** solves this by establishing a multi-agent consensus network governed by a directed graph state machine.

```mermaid
graph TB
    subgraph Input
        Q["🧑‍⚕️ Clinical Query"]
    end

    subgraph LangGraph["Orchestration Engine (engine.py)"]
        Linguist["🗣️ Medical Linguist (parser.py)"]
        Informatician["🔎 Medical Informatician (retriever.py)"]
        Auditor["🛡️ Clinical Auditor (auditor.py)"]

        Linguist -->|"ClinicalIntent"| Informatician
        Informatician -->|"Ranked CandidateCodes"| Auditor
        Auditor -- "❌ Rejected (is_approved=False)" --> Linguist
    end

    subgraph Backends
        APIs["NIH / NLM REST APIs"]
        LocalDB["Local SQLite Vocab Cache"]
        LLM["Gemini / Ollama Fallback"]
    end

    Q --> Linguist
    Informatician --> APIs & LocalDB
    Linguist & Auditor -.-> LLM
    Auditor -->|"✅ Approved"| OUT["MappingResult JSON"]
```

### Component Breakdown
1. **Medical Linguist (Parser)**: Converts unstructured text into a structured, grammar-enforced `ClinicalIntent` (Pydantic model) containing domains, entities, constraints, and negative constraints.
2. **Medical Informatician (Retriever)**: Queries public vocabulary APIs and local databases, performs class expansion (e.g., resolving GLP-1 agonists to active ingredients), and applies a deterministic scoring function.
3. **Clinical Auditor (Critic)**: Serves as a clinical validator. If a code violates query constraints, the Auditor rejects the concept, generating exclusion parameters and triggering a retry.

---

## 2. In-Depth Step-by-Step Flow

### A. Intent Parsing & Synonym Expansion
*   **Parsing**: We use a two-stage parsing approach. The first pass applies regular expressions to capture trivial constraints (e.g. `> 7%`). The second pass calls the LLM in structured JSON mode to map concepts, synonyms, and negative constraints.
*   **Synonym Resolution**: Synonyms are resolved using:
    1.  *Rule-Based Mapping*: Hardcoded lookup for common acronyms (`HbA1c` $\rightarrow$ `Hemoglobin A1c`, `T2D` $\rightarrow$ `Type 2 Diabetes`).
    2.  *Ontology Cache*: Querying local SQLite tables to expand synonyms like `renal failure` $\rightarrow$ `kidney disease`.
    3.  *Approximate API Matching*: Querying the NIH RxNorm API for medication brand-to-generic conversions.

### B. Terminology Retrieval & Deterministic Ranking
Candidates are fetched from LOINC, ICD-10-CM, RxNorm, and local SNOMED subsets. Once fetched, the Informatician calculates a deterministic relevance score:

$$\text{Score} = \text{Auditor Selection Boost} (200) + \text{Domain Match} (20) + \text{Entity Match} (15\text{-}25) + \text{Synonym Match} (8\text{-}13) + \text{Specificity Match} (15) - \text{API Rank Decay} (0.5 \times \text{rank})$$

This prevents the system from relying purely on LLM sorting, which is prone to recency bias and hallucinations.

### C. Self-Correction Reflexion Loop
If the Auditor finds a candidate that represents a device (e.g. "HbA1c Measurement Device") rather than an analyte, or an unspecified parent category (e.g., `N18.9` for CKD) when specific stages were requested, it:
1.  Sets `is_approved = False`.
2.  Appends the incorrect concept codes or keywords to `suggested_exclusions`.
3.  Injects a clinical critique explaining why the selection failed.
The LangGraph engine routes the state back to the Linguist, which parses the query again with `negative_constraints` configured, forcing the retriever to fetch alternative, specific codes.

---

## 3. Performance, Cost & Robustness Profile

Below is a detailed diagnostic matrix of the current prototype.

| Metric | Current Prototype Profile | Primary Bottlenecks | Production Recommendations |
| :--- | :--- | :--- | :--- |
| **Latency** | **Single-Pass**: 7 – 10 seconds<br/>**Self-Correction**: 20 – 35 seconds | Synchronous external network calls (`urllib.request`) and sequential LLM inference times. | • Implement local vocabulary caches.<br/>• Use asynchronous parallel processing.<br/>• Set up Redis semantic caching. |
| **Cost** | **~$0.001 – $0.003** per query (~5k input/output tokens total). | Tokens scale linearly with the number of candidate codes audited and self-correction iterations. | • Fine-tune an on-premise local model (e.g., Llama-3-8B).<br/>• Eliminate LLM calls entirely for cached matches. |
| **Robustness** | **High precision** for complex criteria.<br/>**Low robustness** on external outages and small fallback models. | Dependency on NIH/NLM REST APIs. Fallback to `qwen3:0.6b` fails structured parsing tasks. | • Host vocabularies locally (no external APIs).<br/>• Use larger local fallbacks (e.g., Llama-3-70B).<br/>• Human-in-the-Loop review queue. |

---

## 4. Scalability Analysis: 3M+ Record Scenario

If the database is scaled to **3 million records** (e.g., full UMLS Metathesaurus or OHDSI OMOP vocabulary containing LOINC, SNOMED, and ICD-10), the current implementation fails to scale.

### A. SQLite Lexical Search Bottlenecks
*   **The Issue**: The prototype database queries use string matching:
    ```sql
    SELECT * FROM local_concepts WHERE LOWER(display) LIKE '%term%'
    ```
    With 3 million records, SQL `LIKE '%term%'` patterns prevent the use of standard indexes, forcing database engine full-table scans. A single lookup would take several seconds, locking the thread.
*   **The Solution**: Upgrade to **SQLite FTS5 (Full-Text Search)** virtual tables. This indexes words into tokens, changing the lookup complexity from $O(N)$ scans to $O(\log N)$ indexed lookups. Alternatively, migrate to **Elasticsearch** or **PostgreSQL** with GIN indexes (`pg_trgm`).

### B. In-Memory Python Scoring Bottlenecks
*   **The Issue**: The `_rank_candidates` function loops over all candidate codes returned and applies text matches in Python:
    ```python
    for c in candidates:
        if ent_lower in c.display.lower():
            score += 15.0
    ```
    If the retriever fetches hundreds of thousands of candidate codes, this loop will block the CPU. Storing 3M `CandidateCode` Pydantic objects in RAM consumes gigabytes of memory, risking Out-Of-Memory (OOM) crashes.
*   **The Solution**:
    1.  **Database Pre-Filtering**: Restrict the search scope directly in the database using `WHERE` clauses (e.g., filtering by vocabulary name or domain code) to prune the search space.
    2.  **Top-K Retrieval**: Ensure the database query limits returns to a maximum of 100–200 candidates. Do not pull millions of records into memory for sorting.
    3.  **Push Down Scoring**: Shift basic scoring factors (e.g., exact matches and synonym weights) directly into the database engine using ranking score functions (such as BM25 in Elasticsearch or `ts_rank` in Postgres).

### C. Graph Traversal Bottlenecks
*   **The Issue**: Iteratively traversing multi-level hierarchical concepts (parent/child/ancestor paths) in Python using single-step SQL queries creates high database round-trip overhead.
*   **The Solution**: Write **recursive SQL Common Table Expressions (CTEs)** to resolve paths in a single query execution, or migrate to a graph-native store like **Neo4j**.

---

## 5. Production Engineering Roadmap

To transition this prototype into a production-grade, enterprise-scale clinical cohort mapper, we recommend the following five-stage roadmap:

```
  Stage 1: Local Ingestion ──► Stage 2: Database Search ──► Stage 3: Async & Cache ──► Stage 4: Local LLM ──► Stage 5: CITL Review
```

### Stage 1: Local Terminology Cluster
*   Ingest standard OMOP/Athena vocabularies entirely into a local database cluster (e.g., PostgreSQL or Elasticsearch).
*   Eliminate external NIH and NLM REST API dependencies.

### Stage 2: Database-Level Retrieval & Scoring
*   Implement full-text search indexes (PostgreSQL GIN or Elasticsearch BM25) and push text-scoring weights into the query.
*   Enforce `LIMIT 100` on the database query before objects are parsed into Pydantic models.

### Stage 3: Asynchronous Orchestration & Caching
*   Refactor the LangGraph workflows and database connect sessions using Python's `asyncio` to allow concurrent execution of thousands of streams.
*   Implement a **Redis Semantic Cache** mapping search queries to historical approved mappings to bypass LLM execution entirely for recurring queries (e.g., "Patients on Metformin").

### Stage 4: Self-Hosted LLMs
*   Replace external Gemini API dependencies with local, self-hosted LLM instances (e.g., Llama-3-8B-Instruct or Llama-3-70B-Instruct).
*   Fine-tune the local parser and auditor models using synthetic mapping datasets, keeping clinical data secure on-premise and eliminating API token costs.

### Stage 5: Clinician-in-the-Loop (CITL) UI
*   Build a monitoring dashboard that visualizes active queries, candidate mappings, and telemetry traces.
*   Route mappings with low confidence scores ($<0.85$) to a manual clinician review queue for override, feeding decisions back to improve the model.

---

## 6. Distributed Microservices: The Need and Advantages of the A2A Protocol

To transition the CDGR mapping engine from a local pipeline into a production healthcare microservices mesh, we have adopted the **Agent-to-Agent (A2A)** protocol. 

### Why A2A is Needed in Clinical Cohort Mapping
1. **Bridging Network & Security Boundaries**: In real-world hospital networks (EHR domains, proprietary data warehouses), clinical terminology databases reside behind strict firewalls and security zones. A centralized monolithic mapping tool cannot directly connect to all these databases. Exposing each database via an A2A-compliant agent allows them to run locally in their secure zones while receiving queries via the standard A2A API.
2. **Heterogeneous Runtimes**: The *Linguist* and *Auditor* agents rely on heavy LLM inference engines (requiring GPU environments), while the *Informatician* is database/search index-heavy (requiring CPU/RAM optimized environments). Decoupling them prevents resource contention and allows hosting each agent in an environment tailored to its resource profile.
3. **Standardized Interoperability**: Healthcare environments contain systems built on diverse stacks (Python, Go, Java). A2A establishes a standard communication interface using JSON-RPC/REST and **Agent Cards** that guarantees any standard agent can collaborate without sharing proprietary internal code.

### Advantages of the A2A Protocol
*   **Federated Discovery via Agent Cards**: Agents publish their capability definitions via the `/.well-known/agent-card.json` endpoint. The gateway dynamically resolves agent metadata, versions, and skill schemas at runtime, eliminating hardcoded orchestrator configurations.
*   **End-to-End Trace Propagation**: Using W3C Trace Context headers (`traceparent`/`tracestate`) wrapped in A2A request envelopes, trace IDs remain linked as calls bounce between microservices, providing a complete waterfall trace of the reflexion loop in tools like **Otelite** or **Grafana/Tempo**.
*   **Decoupled Scaling**: High-volume query periods can trigger horizontal scaling for the retrieval agent (*Informatician*) independently of the LLM parser/validator agents, minimizing cloud hosting costs.
*   **Asynchronous Task Orchestration**: For long-running batch cohort mapping pipelines, the A2A protocol natively handles task state management (`submitted`, `working`, `completed`), allowing clients to check status asynchronously rather than blocking connections.

### A2A Communication & Architecture Flow

The diagrams below describe how the client discovers agent capabilities via the **Agent Card**, how the orchestrator gateway utilizes the **A2A protocol envelope** for messaging, and where standard **W3C Trace Context Propagation** lies.

#### 1. A2A Component Architecture Diagram
This diagram shows the network boundaries, API routes, and where the A2A communication layer sits in relation to the agents and the client:

```mermaid
graph TD
    subgraph Client Application Layer
        Client["🧑‍💻 Clinical Client / Portal"]
    end

    subgraph A2A Gateway Layer
        Gateway["🌐 REST API Gateway (app.py)"]
        Discovery["🔍 Agent Card Resolver (a2a-sdk)"]
    end

    subgraph "A2A Communication Layer (HTTP REST / W3C Trace Headers)"
        LinguistAPI["POST /api/v1/agent/linguist"]
        InformaticianAPI["POST /api/v1/agent/informatician"]
        AuditorAPI["POST /api/v1/agent/auditor"]
        CardAPI["GET /.well-known/agent-card.json"]
    end

    subgraph Decoupled Microservice Agents
        LinguistAgent["🗣️ Medical Linguist Agent"]
        InformaticianAgent["🔎 Medical Informatician Agent"]
        AuditorAgent["🛡️ Clinical Auditor Agent"]
    end

    subgraph Databases & External Services
        LocalDB["🗄️ Local Vocabulary (SQLite)"]
        NLM["🌐 Public NIH/NLM APIs"]
        LLM["🧠 LLM Provider (Gemini / Local Fallback)"]
    end

    %% Client Interactions
    Client -->|"1. Fetch Capabilities"| CardAPI
    Client -->|"2. Submit Query"| Gateway
    Gateway --> Discovery

    %% Gateway to A2A API
    Gateway -->|"A2A Wrap & Trace Inject"| LinguistAPI
    Gateway -->|"A2A Wrap & Trace Inject"| InformaticianAPI
    Gateway -->|"A2A Wrap & Trace Inject"| AuditorAPI

    %% A2A API to Agents
    LinguistAPI --> LinguistAgent
    InformaticianAPI --> InformaticianAgent
    AuditorAPI --> AuditorAgent

    %% Agent Interactions
    LinguistAgent -.-> LLM
    InformaticianAgent --> LocalDB
    InformaticianAgent --> NLM
    AuditorAgent -.-> LLM
```

#### 2. Agent-to-Agent Communication Sequence Diagram
This diagram explains the step-by-step messaging protocol, including trace propagation and the reflexion loop retry cycles:

```mermaid
sequenceDiagram
    autonumber
    actor Client as 🧑‍💻 Clinical Client / User
    participant Gateway as 🌐 API Gateway (Orchestrator)
    participant SDK as 📦 Official A2A SDK
    participant Linguist as 🗣️ Medical Linguist Agent
    participant Informatician as 🔎 Medical Informatician Agent
    participant Auditor as 🛡️ Clinical Auditor Agent

    Note over Client, Auditor: Discovery Phase
    Client->>Gateway: GET /.well-known/agent-card.json (Fetch capabilities)
    Gateway-->>Client: Returns AgentCard JSON (name, version, skills, interfaces)

    Note over Client, Auditor: Orchestration & Mapping Phase
    Client->>Gateway: POST /api/v1/map-cohort (JSON: query)
    Note over Gateway: Start root OTel trace span (MapClinicalQuery)

    loop Reflection Cycle (up to max_retries)
        Gateway->>SDK: Wrap context & Inject W3C Trace Headers (traceparent)
        SDK->>Linguist: POST /api/v1/agent/linguist (A2A Message Envelope)
        Note over Linguist: Start child trace span<br/>Extract intent / generate critique
        Linguist-->>Gateway: Return ClinicalIntent JSON

        Gateway->>SDK: Wrap intent & Inject W3C Trace Headers
        SDK->>Informatician: POST /api/v1/agent/informatician (A2A Message Envelope)
        Note over Informatician: Start child trace span<br/>Retrieve candidates (lexical/semantic)
        Informatician-->>Gateway: Return CandidateCodes JSON

        Gateway->>SDK: Wrap intent + candidates & Inject W3C Trace Headers
        SDK->>Auditor: POST /api/v1/agent/auditor (A2A Message Envelope)
        Note over Auditor: Start child trace span<br/>Validate domain/hierarchy consensus
        Auditor-->>Gateway: Return AuditorResponse (is_approved, critique, selected)
        
        alt is_approved == True
            Note over Gateway: Break loop
        else is_approved == False
            Note over Gateway: Increment correction_attempts
        end
    end

    Gateway-->>Client: Return final MappingResult JSON (including trace metadata)
```

---

## 7. Integrating Healthcare MCP (Model Context Protocol) Servers

To expand the capabilities of the CDGR pipeline, the orchestrator and agents can integrate standard healthcare Model Context Protocol (MCP) servers, such as the open-source [healthcare-mcp-public](https://github.com/Cicatriiz/healthcare-mcp-public) server.

### Architecture Integration
Rather than writing custom API wrappers for every external medical registry, agents act as MCP clients to delegate queries to the MCP server.

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

1. **ICD-10-CM Candidate Expansion**: The `MedicalInformatician` invokes the `lookupICDCode` tool from the MCP server to search codes and names from the NLM ClinicalTables API.
2. **Clinical trials & FDA Label Checks**: The `ClinicalAuditor` queries the `fda-tool.js` to extract ingredients and indications for unknown drug inputs to resolve domain category classification.
3. **Medical Research Reference**: For complex or ambiguous conditions, the auditor queries PubMed (`pubmed-tool.js`) to back up its reflexion decisions with clinical literature search results.

### Advantages
* **Interoperable Interface**: The LLM uses standardized JSON-RPC schemas to invoke functions, separating data parsing logic from agent flow.
* **Extensibility**: Adding new clinical modules (e.g. DICOM image metadata parsing) requires registering a new tool on the MCP server without updating agent pipelines.
