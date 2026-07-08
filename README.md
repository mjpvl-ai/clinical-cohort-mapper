# Clinical Cohort Query Mapper (CDGR)

[![CI](https://github.com/mjpvl-ai/clinical-cohort-mapper/actions/workflows/ci.yml/badge.svg)](https://github.com/mjpvl-ai/clinical-cohort-mapper/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Protocol: A2A](https://img.shields.io/badge/Protocol-A2A%201.0-orange.svg)](https://srotas.ai)
[![Telemetry: OpenTelemetry](https://img.shields.io/badge/Telemetry-OpenTelemetry-blueviolet.svg)](https://opentelemetry.io)
[![Linter: Ruff](https://img.shields.io/badge/Linter-Ruff-black.svg)](https://github.com/astral-sh/ruff)
[![Code Style: Ruff-format](https://img.shields.io/badge/Formatter-Ruff--format-black.svg)](https://github.com/astral-sh/ruff)
[![Package Manager: uv](https://img.shields.io/badge/Package%20Manager-uv-de5fe9.svg)](https://docs.astral.sh/uv/)

An **agentic AI system** that maps free-form clinical cohort queries to standardized medical terminology codes using a self-correcting **Consensus-Driven Graph Reflexion (CDGR)** pipeline.

It serves as a production-grade Agent-to-Agent (A2A) microservice that parses clinical query constraints, performs hybrid lexical and semantic code searches, and validates mappings against ontology hierarchies to prevent clinical mismatch errors.

---

## Detailed Documentation

To make the documentation easy to navigate, we have structured it into separate detailed guides:

*   📖 **[Architecture & CDGR Pipeline](docs/architecture.md)** — Deep-dive into the multi-agent system, LangGraph orchestrator, agent schemas, and scoring heuristics.
*   📊 **[Evaluation & Sample Queries](docs/evaluation.md)** — Review the 20 assessment sample queries and the generated validation results matrix.
*   🔌 **[REST API & A2A Protocol](docs/api.md)** — Learn about HTTP/JSON-RPC integration, Agent Card, and asynchronous task execution via `AgentExecutor`.
*   🔍 **[Observability & Tracing](docs/observability.md)** — Setup local distributed tracing with Otelite or full Grafana+Tempo stacks.
*   🚀 **[Production Scalability & Improvement Plan](docs/scalability.md)** — Inspect the 5-stage production engineering roadmap, 3M+ record database optimizations, and Healthcare MCP integrations.

---

## Supported Vocabularies

The system performs real-time queries against public, official APIs and a local relational cache:

| Domain | Vocabulary | Source |
|---|---|---|
| Measurements / Observations | **LOINC** | NLM Clinical Table Search |
| Conditions / Diagnoses | **ICD-10-CM** | NLM Clinical Table Search |
| Drugs / Medications | **RxNorm** | NIH RxNorm REST API |
| Procedures | **SNOMED CT** | Local vocabulary cache |

---

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mjpvl-ai/clinical-cohort-mapper.git
   cd clinical-cohort-mapper
   ```

2. **Create virtual environment and install dependencies**:
   ```bash
   uv venv
   uv pip install pydantic langgraph opentelemetry-api opentelemetry-sdk fastapi uvicorn httpx a2a-sdk pytest
   ```

3. **Configure your API Key**:
   Create a `.env` file in the root directory:
   ```bash
   echo 'GEMINI_API_KEY=your_gemini_api_key_here' > .env
   ```

### Usage

#### Command Line Interface (CLI)

- **Single Query Execution**:
  ```bash
  python run.py --query "Patients with HbA1c above 7%"
  ```

- **Batch Execution (All 20 Sample Queries)**:
  Runs the pipeline sequentially, displays a live markdown summary table, and saves the detailed result payload to a JSON file.
  ```bash
  python run.py --batch --output results.json
  ```

#### Starting the A2A Server
Start the FastAPI server on port `8000`:
```bash
python app.py
```
Refer to the **[A2A Endpoints Section](docs/api.md#querying-via-a2a-endpoints)** for detailed query request payloads.

### Running Tests

Run the test suite to verify agent execution and tracing logic:
```bash
.venv/bin/pytest tests/
```

---

## License

This project was built as a clinical take-home assessment prototype. See [LICENSE](LICENSE) for details.
