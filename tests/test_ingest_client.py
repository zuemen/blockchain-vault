import io
import json
import urllib.error

import pytest

from ingest_client import Client, ApiError


class FakeServer:
    """記錄收到的請求，依序回傳預先設定的回應（dict 或 Exception）。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req, timeout):
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.requests.append((req.get_method(), req.full_url, body, req.get_header("X-ingest-token")))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(json.dumps(r).encode("utf-8"))


def http_error(code):
    return urllib.error.HTTPError("https://s/api/ingest", code, "err", {}, io.BytesIO(b"boom"))


def ok(inserted=1, clusters=None):
    return {"inserted": inserted, "duplicates": 0, "ai_failed": 0, "errors": [], "clusters": clusters or {}}


def test_recent_follows_pages():
    srv = FakeServer([{"items": [{"id": 1}], "next_page": 1}, {"items": [{"id": 2}], "next_page": None}])
    c = Client("https://s/", "tok", opener=srv)
    assert c.recent(14) == [{"id": 1}, {"id": 2}]
    assert srv.requests[1][1] == "https://s/api/news/recent?days=14&page=1"
    assert srv.requests[0][3] == "tok"


def test_recent_raises_on_http_error():
    c = Client("https://s", "tok", opener=FakeServer([http_error(503)]))
    with pytest.raises(ApiError, match="503"):
        c.recent(14)


def test_new_cluster_split_across_batches_reuses_real_id():
    items = [{"url_canonical": f"u{i}", "cluster_ref": "new:1"} for i in range(3)]
    srv = FakeServer([ok(2, {"new:1": 77}), ok(1)])
    total = Client("https://s", "tok", opener=srv).ingest(items, "run", batch_size=2)
    assert [it["cluster_ref"] for it in srv.requests[1][2]["items"]] == [77]
    assert total["inserted"] == 3 and total["failed_batches"] == 0


def test_retries_then_counts_failed_batch():
    items = [{"url_canonical": "a", "cluster_ref": "new:1"}, {"url_canonical": "b", "cluster_ref": "new:2"}]
    sleeps = []
    srv = FakeServer([http_error(500), ok(1), http_error(500), http_error(500), http_error(500)])
    total = Client("https://s", "tok", opener=srv, sleep=sleeps.append).ingest(items, "run", batch_size=1, retries=2)
    assert total["inserted"] == 1
    assert total["failed_batches"] == 1
    assert sleeps == [5, 5, 10]


def test_skip_ai_flag_is_sent():
    srv = FakeServer([ok()])
    Client("https://s", "tok", opener=srv).ingest([{"url_canonical": "a", "cluster_ref": 3}], "r", skip_ai=True)
    assert srv.requests[0][2]["skip_ai"] is True
