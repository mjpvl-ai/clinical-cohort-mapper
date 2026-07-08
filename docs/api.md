# REST API & A2A Protocol Implementation

The CDGR mapping engine is exposed as a REST API and implements the official **Agent-to-Agent (A2A)** protocol for secure, federated clinical agent communication.

---

## Federated Discovery (Agent Card)

The microservice exposes its details, skills, and API routes via a standard A2A agent card at:
```http
GET /.well-known/agent-card.json
```

It returns structured metadata containing the provider organization, documentation URL, skills list, and protocol bindings:
```json
{
  "name": "clinical-cohort-mapper",
  "description": "Exposes a consensus-driven multi-agent clinical cohort query mapping engine...",
  "version": "1.0.0",
  "provider": {
    "organization": "Srotas Health",
    "url": "https://srotas.ai"
  },
  "skills": [
    { "id": "concept-mapping", "name": "Clinical Concept Mapping" },
    { "id": "linguistic-intent-parsing", "name": "Medical Linguistic Intent Parsing" },
    { "id": "consensus-driven-auditing", "name": "Consensus-Driven Cohort Auditing" }
  ]
}
```

---

## Asynchronous State Management (AgentExecutor)

Cohort mapping jobs can be executed asynchronously to prevent blocking network connections on long or batch executions. The server implements the `AgentExecutor` lifecycle patterns from the `a2a-sdk`:

1. **Task Submission**: A user submits a query message. A new task is generated and persisted in an `InMemoryTaskStore`.
2. **Lifecycle Tracking**: The worker thread starts the task inside `asyncio.to_thread` and updates the task state (`TASK_STATE_WORKING`).
3. **Event Queue**: Real-time event streams send status changes and artifacts (`MappingResult`) to connected listeners.

---

## Direct Agent Endpoints

The three CDGR agents are decoupled and can be queried directly:

- **Medical Linguist Agent**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/v1/agent/linguist \
       -H "Content-Type: application/json" \
       -d '{"query": "Patients with HbA1c above 7%"}'
  ```

- **Medical Informatician Agent**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/v1/agent/informatician \
       -H "Content-Type: application/json" \
       -d '{"intent": {"original_query": "Patients with HbA1c above 7%", "clinical_entities": ["HbA1c"], "synonyms": ["glycated hemoglobin"], "domain": "measurement", "status": "any", "constraint": {"operator": ">", "value": 7.0, "unit": "%"}}}'
  ```

- **Clinical Auditor Agent**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/v1/agent/auditor \
       -H "Content-Type: application/json" \
       -d '{"intent": {"original_query": "Patients with HbA1c above 7%", "clinical_entities": ["HbA1c"], "synonyms": ["glycated hemoglobin"], "domain": "measurement", "status": "any", "constraint": {"operator": ">", "value": 7.0, "unit": "%"}}, "candidates": [{"vocabulary": "LOINC", "code": "4548-4", "display": "Hemoglobin A1c/Hemoglobin.total in Blood", "rank": 1}]}'
  ```

---

## Querying via A2A Endpoints

### 1. HTTP+JSON REST Interface
To trigger the complete mapping loop:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/a2a/message:send \
     -H "Content-Type: application/json" \
     -H "A2A-Version: 1.0" \
     -d '{
       "message": {
         "role": "ROLE_USER",
         "message_id": "unique-msg-123",
         "context_id": "unique-ctx-456",
         "parts": [{"text": "Patients with HbA1c above 7%"}]
       }
     }'
```

### 2. JSON-RPC Interface
```bash
curl -X POST http://127.0.0.1:8000/api/v1/a2a/jsonrpc \
     -H "Content-Type: application/json" \
     -H "A2A-Version: 1.0" \
     -d '{
       "jsonrpc": "2.0",
       "method": "a2a.message.send",
       "params": {
         "message": {
           "role": "ROLE_USER",
           "message_id": "unique-msg-789",
           "context_id": "unique-ctx-101",
           "parts": [{"text": "Patients currently taking metformin"}]
         }
       },
       "id": 1
     }'
```
