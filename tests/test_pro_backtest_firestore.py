"""FirestoreRunStore against an in-memory duck-typed client — no cloud
credentials anywhere near CI. The fake mirrors the small slice of the
google-cloud-firestore surface the store uses (collection/document/set/get/
delete, order_by+limit+stream)."""

import json

from tradingagents.pro.dashboard.backtest_firestore import FirestoreRunStore


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = None  # set by the query

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self._id = doc_id

    def set(self, data):
        self._collection._docs[self._id] = dict(data)

    def get(self):
        return _FakeDoc(self._id, self._collection._docs.get(self._id))

    def delete(self):
        self._collection._docs.pop(self._id, None)


class _FakeQuery:
    def __init__(self, collection, order_field=None, descending=False, limit=None):
        self._c = collection
        self._field = order_field
        self._desc = descending
        self._limit = limit

    def order_by(self, field, direction="ASCENDING"):
        return _FakeQuery(self._c, field, direction == "DESCENDING", self._limit)

    def limit(self, n):
        return _FakeQuery(self._c, self._field, self._desc, n)

    def stream(self):
        items = list(self._c._docs.items())
        if self._field:
            items.sort(key=lambda kv: kv[1].get(self._field) or "",
                       reverse=self._desc)
        if self._limit is not None:
            items = items[: self._limit]
        for doc_id, data in items:
            doc = _FakeDoc(doc_id, data)
            doc.reference = _FakeDocRef(self._c, doc_id)
            yield doc


class _FakeCollection(_FakeQuery):
    def __init__(self):
        self._docs: dict[str, dict] = {}
        super().__init__(self)

    def document(self, doc_id):
        return _FakeDocRef(self, doc_id)


class _FakeClient:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}

    def collection(self, name):
        return self._collections.setdefault(name, _FakeCollection())


def _record(run_id, created_at, status="done"):
    return {
        "id": run_id, "created_at": created_at, "status": status,
        "summary": {"id": run_id, "created_at": created_at, "status": status,
                    "symbol": "BTC-USD"},
        "view": {"status": status},
    }


def test_save_list_get_delete_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PRO_DATA", str(tmp_path))
    store = FirestoreRunStore(client=_FakeClient())
    store.save(_record("a", "2026-01-01"))
    store.save(_record("b", "2026-01-02"))
    listed = store.list()
    assert [r["id"] for r in listed] == ["b", "a"]  # newest first
    assert store.get("a")["id"] == "a"
    assert store.get("missing") is None
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert [r["id"] for r in store.list()] == ["b"]


def test_prune_evicts_oldest_beyond_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PRO_DATA", str(tmp_path))
    store = FirestoreRunStore(client=_FakeClient(), max_runs=3)
    for i in range(5):
        store.save(_record(f"r{i}", f"2026-01-0{i + 1}"))
    assert [r["id"] for r in store.list()] == ["r4", "r3", "r2"]
    assert store.get("r0") is None  # evicted doc really gone


def test_checkpoint_roundtrip():
    store = FirestoreRunStore(client=_FakeClient())
    assert store.read_checkpoint() is None
    store.write_checkpoint({"job_id": "x", "status": "running"})
    assert store.read_checkpoint()["job_id"] == "x"
    store.clear_checkpoint()
    assert store.read_checkpoint() is None


def test_legacy_import_once(tmp_path):
    legacy = tmp_path / "backtest_runs.json"
    legacy.write_text(json.dumps({"runs": [
        {"id": "old1", "created_at": "2025-12-01",
         "view": {"symbol": "XAUUSD", "equity_curve": [1, 2, 3],
                  "report": {"total_return": 0.01}}},
    ]}), encoding="utf-8")
    store = FirestoreRunStore(client=_FakeClient())
    assert store.import_legacy_file(legacy) == 1
    rec = store.get("old1")
    assert "equity_curve" not in rec["view"]  # bulk stripped on import
    assert store.list()[0]["symbol"] == "XAUUSD"  # legacy summary derived
    # second import is a no-op (collection non-empty)
    assert store.import_legacy_file(legacy) == 0


def test_import_missing_file_is_noop(tmp_path):
    store = FirestoreRunStore(client=_FakeClient())
    assert store.import_legacy_file(tmp_path / "nope.json") == 0
