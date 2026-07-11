"""Oracle: Article.summary required; comments expose it; feed includes it."""


def test_create_requires_summary(client):
    u = client.post("/api/users", json={"username": "ada", "email": "a@x.com"}).json()
    bad = client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": "T", "description": "", "body": "body", "tag_list": []},
    )
    assert bad.status_code == 422


def test_article_and_comments_carry_summary(client):
    u = client.post("/api/users", json={"username": "ada", "email": "a@x.com"}).json()
    a = client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": "Hello", "description": "d", "body": "body text",
              "tag_list": [], "summary": "A short summary"},
    )
    assert a.status_code == 200, a.text
    assert a.json()["article"]["summary"] == "A short summary"

    c = client.post(
        "/api/articles/hello/comments",
        headers={"X-User-Id": str(u["id"])},
        json={"body": "nice"},
    )
    assert c.status_code == 200, c.text
    assert c.json()["comment"]["article_summary"] == "A short summary"

    listed = client.get("/api/articles/hello/comments")
    assert listed.status_code == 200
    assert listed.json()["comments"][0]["article_summary"] == "A short summary"


def test_feed_summary_includes_summary(client):
    u = client.post("/api/users", json={"username": "bob", "email": "b@x.com"}).json()
    client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": "Feed Me", "description": "", "body": "x",
              "tag_list": [], "summary": "feed blurb"},
    )
    r = client.get("/api/feed/summary")
    assert r.status_code == 200, r.text
    feed = r.json()["feed"]
    assert any(item.get("slug") == "feed-me" and item.get("summary") == "feed blurb"
               for item in feed)
