def test_agent_info_endpoint_does_not_expose_key(client, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-deploy")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret")

    res = client.get("/api/agent/info")
    assert res.status_code == 200

    data = res.json()
    assert data["deployment_name"] == "gpt-deploy"
    assert data["api_version"] == "2024-10-21"
    assert data["endpoint"] == "https://example.openai.azure.com/"
    assert data["endpoint_host"] == "example.openai.azure.com"
    assert data["auth_mode"] == "api_key"
    assert data["tenant_id"] == "tenant-123"
    assert "api_key" not in data
