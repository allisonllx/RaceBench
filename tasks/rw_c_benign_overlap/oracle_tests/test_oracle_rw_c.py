"""Oracle: list_articles fully formatted; unfavorite works."""


def _seed(client):
    u = client.post("/api/users", json={"username": "ada", "email": "a@x.com"}).json()
    client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": "Hello", "description": "d", "body": "word " * 50,
              "tag_list": ["x"]},
    )
    return u["id"]


def test_list_articles_fully_formatted(client):
    _seed(client)
    r = client.get("/api/articles")
    assert r.status_code == 200
    arts = r.json()["articles"]
    assert len(arts) >= 1
    a = arts[0]
    assert "title" in a and a["title"] == "Hello"
    assert "body" in a and "tag_list" in a
    assert "favorites_count" in a


def test_unfavorite(client):
    uid = _seed(client)
    h = {"X-User-Id": str(uid)}
    client.post("/api/articles/hello/favorite", headers=h)
    before = client.get("/api/articles/hello").json()["article"]["favorites_count"]
    assert before == 1
    r = client.delete("/api/articles/hello/favorite", headers=h)
    assert r.status_code == 200
    assert r.json()["article"]["favorites_count"] == 0
