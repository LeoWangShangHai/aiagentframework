def test_hello_default(client):
    r = client.get("/api/hello")
    assert r.status_code == 200
    assert r.json().get("message")


def test_hello_name_param(client):
    r = client.get("/api/hello", params={"name": "World"})
    assert r.status_code == 200
    assert "World" in r.json().get("message", "")
