import os
import pytest


@pytest.mark.skipif(
    not os.getenv("AZURE_OPENAI_ENDPOINT"),
    reason="Requires Azure OpenAI env (set config/azure_openai.env or env vars)",
)
def test_agent_multi_turn_conversation_id(client):
    r1 = client.post("/api/agent/run", json={"message": "My name is Bob."})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1.get("conversation_id")

    cid = body1["conversation_id"]
    r2 = client.post(
        "/api/agent/run",
        json={"message": "What is my name?", "conversation_id": cid},
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2.get("conversation_id") == cid
    assert isinstance(body2.get("output"), str)
    # Allow model variance; just ensure the response isn't empty.
    assert body2["output"].strip()
