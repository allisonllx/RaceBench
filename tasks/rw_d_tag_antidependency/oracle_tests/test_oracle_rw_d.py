"""Oracle: case-insensitive tag list and matching feed tag counts."""


def _seed(client, title="Tagged", tag="python"):
    u = client.post("/api/users", json={"username": "ada", "email": "a@x.com"}).json()
    r = client.post(
        "/api/articles",
        headers={"X-User-Id": str(u["id"])},
        json={"title": title, "description": "", "body": "x", "tag_list": [tag]},
    )
    assert r.status_code == 200, r.text
    return r.json()["article"]


def test_list_filter_case_insensitive(client):
    art = _seed(client, tag="python")
    r = client.get("/api/articles", params={"tag": "PYTHON"})
    assert r.status_code == 200, r.text
    slugs = [a["slug"] for a in r.json()["articles"]]
    assert art["slug"] in slugs


def test_tag_count_matches_list(client):
    art = _seed(client, title="Count Me", tag="python")
    listed = client.get("/api/articles", params={"tag": "PYTHON"}).json()["articles"]
    counted = client.get("/api/feed/tags/PYTHON/count")
    assert counted.status_code == 200, counted.text
    body = counted.json()
    assert body["count"] == len(listed) == 1
    assert art["slug"] in [a["slug"] for a in listed]
    assert body["tag"] == "PYTHON"


def test_mixed_case_create_and_path(client):
    _seed(client, title="DevOps Post", tag="DevOps")
    listed = client.get("/api/articles", params={"tag": "devops"}).json()["articles"]
    counted = client.get("/api/feed/tags/devops/count")
    assert counted.status_code == 200, counted.text
    assert len(listed) == 1
    assert counted.json()["count"] == 1
