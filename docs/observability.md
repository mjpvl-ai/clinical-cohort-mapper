# Observability & Distributed Tracing

The CDGR mapping pipeline is instrumented with the **OpenTelemetry (OTel)** standard. Spans are logged locally to `telemetry.log` as structured JSON lines and exported via OTLP to a collection engine.

---

## Option 1: Lightweight Observability with Otelite (Recommended)

[Otelite](https://github.com/planetf1/otelite) is a lightweight, zero-dependency OpenTelemetry receiver and dashboard designed for local LLM development.

### 1. Install Otelite
*   **Via curl installer (Linux/macOS):**
    ```bash
    curl --proto '=https' --tlsv1.2 -LsSf https://github.com/planetf1/otelite/releases/latest/download/otelite-installer.sh | sh
    ```
*   **Via Cargo (Rust):**
    ```bash
    cargo install otelite
    ```

### 2. Start the Receiver & Dashboard
```bash
otelite serve
```
This launches:
- An OTLP HTTP receiver on `localhost:4318`
- A real-time Web Dashboard at [http://localhost:3000](http://localhost:3000)

### 3. Run a Query
The clinical mapper auto-detects `otelite` listening on port `4318` and exports traces automatically.

---

## Option 2: Full Observability Stack (Grafana + Tempo)

Alternatively, launch an enterprise-style stack running Grafana and Tempo via Docker.

### 1. Start the Stack
```bash
docker compose up -d
```
This starts:
- **Grafana** → [http://localhost:3000](http://localhost:3000) (anonymous Admin mode)
- **Tempo** → receives OTLP traces on port `4318` (HTTP)

### 2. Run a Query and View Traces
1. Execute your query using the mapper CLI or REST endpoints.
2. Open [http://localhost:3000/explore](http://localhost:3000/explore) and select **Tempo** as the datasource.
3. Switch to **Search** mode, filter by service `clinical-cohort-mapper`, and run the query to inspect the trace waterfall.

---

## Trace Context Propagation & Attributes

Traces propagate W3C headers (`traceparent`, `tracestate`) across decoupled agent endpoint requests.

```text
MapClinicalQuery (Root Span)  [==================================================] (145ms)
  ├── Linguist.extract_intent  [====] (12ms)
  ├── Informatician.retrieve   [==========] (30ms)
  └── Auditor.validate_codes                 [============================] (95ms)
        ├── DB.get_concept_relations   [==] (5ms)
        └── Refinement.loop_iteration_1           [==================] (85ms)
              ├── Linguist.re_extract      [===] (10ms)
              └── Informatician.retrieve   [====] (12ms)
```

### Custom Attributes:
- `clinical.query`: The raw natural language input query.
- `clinical.domain`: The routed category (`measurement`, `drug`, `condition`, etc.).
- `clinical.attempts`: The number of self-correction loop iterations triggered before resolution.
- `clinical.top_code`: The primary standard concept mapped (`vocabulary:code`).
- `clinical.status`: Mapped status (`success` or `unverified`).
