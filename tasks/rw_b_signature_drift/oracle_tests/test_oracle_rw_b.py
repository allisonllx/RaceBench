"""Oracle: format_article requires locale; reading-time works."""
import inspect

from conduit.serializers.article_format import format_article


def test_format_article_requires_locale():
    sig = inspect.signature(format_article)
    params = list(sig.parameters)
    assert params == ["article", "locale"], params
    out = format_article(
        {"slug": "s", "title": "T", "description": "", "body": "x",
         "author_id": 1, "tag_list": [], "favorites_count": 0},
        "fr",
    )
    assert out["title"].startswith("[FR]")


def test_reading_time_endpoint(client):
    u = client.post("/api/users", json={"username": "ada", "email": "a@x.com"}).json()
    client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": "Long", "description": "", "body": "word " * 400,
              "tag_list": []},
    )
    r = client.get("/api/articles/long/reading-time")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "long"
    assert body["minutes"] >= 2
    assert "title" in body


def test_get_article_still_works(client):
    u = client.post("/api/users", json={"username": "bob", "email": "b@x.com"}).json()
    client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": "Hi", "description": "", "body": "hello world",
              "tag_list": []},
    )
    r = client.get("/api/articles/hi")
    assert r.status_code == 200
    assert r.json()["article"]["title"] == "Hi"
