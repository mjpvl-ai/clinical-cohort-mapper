import pytest
import httpx
import json
import uuid
from fastapi.testclient import TestClient

import os
import sys

# Ensure project root is importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, agent_card
from a2a.client import create_client, ClientConfig
from a2a.utils.constants import TransportProtocol
from a2a.types import SendMessageRequest, Message, Role, Part, TaskState
from a2a.helpers import new_text_part

def test_well_known_agent_card():
    client = TestClient(app)
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "clinical-cohort-mapper"
    assert "concept-mapping" in [skill["id"] for skill in data["skills"]]

@pytest.mark.anyio
async def test_a2a_agent_execution_rest():
    # Use REST protocol binding by configuring client to only support HTTP+JSON
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http_client:
        client_config = ClientConfig(
            httpx_client=http_client,
            supported_protocol_bindings=[TransportProtocol.HTTP_JSON],
            streaming=True
        )
        
        # Create client using the agent_card directly
        client = await create_client(agent=agent_card, client_config=client_config)
        
        # Prepare message request with required message_id and context_id
        request_message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            context_id=str(uuid.uuid4()),
            parts=[new_text_part(text="Patients with HbA1c above 7%")]
        )
        request = SendMessageRequest(message=request_message)
        
        events = []
        async for event in client.send_message(request):
            events.append(event)
            
        assert len(events) >= 1
        
        # Verify the sequence of events
        task_event = next((e for e in events if e.WhichOneof("payload") == "task"), None)
        assert task_event is not None
        
        status_events = [e.status_update for e in events if e.WhichOneof("payload") == "status_update"]
        assert len(status_events) >= 2
        
        # Check first status update is WORKING
        assert status_events[0].status.state == TaskState.TASK_STATE_WORKING
        
        # Check last status update is COMPLETED
        assert status_events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        
        # Check artifact update has MappingResult
        artifact_events = [e.artifact_update for e in events if e.WhichOneof("payload") == "artifact_update"]
        assert len(artifact_events) >= 1
        
        artifact = artifact_events[0].artifact
        assert artifact.name == "MappingResult"
        
        # Read the artifact content
        result_text = "".join(part.text for part in artifact.parts)
        result_data = json.loads(result_text)
        assert result_data["query"] == "Patients with HbA1c above 7%"
        assert any(code["code"] == "4548-4" for code in result_data["selected_codes"])

@pytest.mark.anyio
async def test_a2a_agent_execution_jsonrpc():
    # Use jsonrpc protocol binding by configuring client to only support JSONRPC
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http_client:
        client_config = ClientConfig(
            httpx_client=http_client,
            supported_protocol_bindings=[TransportProtocol.JSONRPC],
            streaming=True
        )
        
        client = await create_client(agent=agent_card, client_config=client_config)
        
        # Prepare message request with required message_id and context_id
        request_message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            context_id=str(uuid.uuid4()),
            parts=[new_text_part(text="Patients currently taking metformin")]
        )
        request = SendMessageRequest(message=request_message)
        
        events = []
        async for event in client.send_message(request):
            events.append(event)
            
        assert len(events) >= 1
        
        task_event = next((e for e in events if e.WhichOneof("payload") == "task"), None)
        assert task_event is not None
        
        status_events = [e.status_update for e in events if e.WhichOneof("payload") == "status_update"]
        assert len(status_events) >= 2
        assert status_events[0].status.state == TaskState.TASK_STATE_WORKING
        assert status_events[-1].status.state == TaskState.TASK_STATE_COMPLETED
        
        artifact_events = [e.artifact_update for e in events if e.WhichOneof("payload") == "artifact_update"]
        assert len(artifact_events) >= 1
        
        artifact = artifact_events[0].artifact
        assert artifact.name == "MappingResult"
        
        result_text = "".join(part.text for part in artifact.parts)
        result_data = json.loads(result_text)
        assert result_data["query"] == "Patients currently taking metformin"
        assert any(code["code"] == "6809" for code in result_data["selected_codes"])
