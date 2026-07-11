def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_and_create_article(client):
    u = client.post("/api/users", json={
        "username": "ada", "email": "ada@example.com",
    })
    assert u.status_code == 200
    user_id = u.json()["id"]

    a = client.post(
        "/api/articles",
        headers={"X-User-Id": str(user_id)},
        json={
            "title": "Hello World",
            "description": "intro",
            "body": "one two three four five",
            "tag_list": ["intro"],
        },
    )
    assert a.status_code == 200
    article = a.json()["article"]
    assert article["slug"] == "hello-world"
    assert article["title"] == "Hello World"
    assert "intro" in article["tag_list"]

    g = client.get("/api/articles/hello-world")
    assert g.status_code == 200
    assert g.json()["article"]["body"] == "one two three four five"
