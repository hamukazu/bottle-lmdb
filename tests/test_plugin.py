"""Tests for LMDBPlugin integration with Bottle."""

import httpx
import lmdb
import pytest
from bottle import Bottle

from bottle_lmdb import LMDBPlugin


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.lmdb")


@pytest.fixture
def client(db_path):
    """An httpx client wrapping a Bottle app with the plugin installed."""
    plugin = LMDBPlugin(db_path)
    app = Bottle()
    app.install(plugin)

    @app.get("/write/<key>/<value>")
    def write(key, value, db):
        with db.begin(write=True) as txn:
            txn.put(key.encode(), value.encode())
        return "ok"

    @app.get("/read/<key>")
    def read(key, db):
        with db.begin() as txn:
            value = txn.get(key.encode())
        return value.decode() if value else "not found"

    transport = httpx.WSGITransport(app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client


def test_plugin_attributes(db_path):
    plugin = LMDBPlugin(db_path)
    assert plugin.name == "lmdb"
    assert plugin.api == 2


def test_env_is_created_lazily(db_path):
    plugin = LMDBPlugin(db_path)
    assert plugin._env is None
    env = plugin.env
    assert isinstance(env, lmdb.Environment)
    assert plugin.env is env  # second access returns the same instance
    env.close()


def test_env_kwargs_are_forwarded(tmp_path):
    db_path = str(tmp_path / "kwargs.lmdb")
    plugin = LMDBPlugin(db_path, map_size=10 * 1024 * 1024, max_dbs=2)
    info = plugin.env.info()
    assert info["map_size"] == 10 * 1024 * 1024
    plugin.env.close()


def test_route_receives_env_via_default_keyword(client):
    res = client.get("/write/foo/bar")
    assert res.status_code == 200
    assert res.text == "ok"

    res = client.get("/read/foo")
    assert res.status_code == 200
    assert res.text == "bar"


def test_route_receives_env_via_custom_keyword(tmp_path):
    db_path = str(tmp_path / "custom.lmdb")
    plugin = LMDBPlugin(db_path, keyword="store")
    app = Bottle()
    app.install(plugin)

    @app.get("/put/<value>")
    def put(value, store):
        assert isinstance(store, lmdb.Environment)
        with store.begin(write=True) as txn:
            txn.put(b"key", value.encode())
        return "ok"

    transport = httpx.WSGITransport(app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        res = client.get("/put/baz")
    assert res.status_code == 200
    assert res.text == "ok"

    with plugin.env.begin() as txn:
        assert txn.get(b"key") == b"baz"
    plugin.env.close()


def test_data_persists_across_requests(client):
    client.get("/write/hello/world")
    res = client.get("/read/hello")
    assert res.status_code == 200
    assert res.text == "world"

    res = client.get("/read/missing")
    assert res.status_code == 200
    assert res.text == "not found"


def test_route_with_view_decorator(tmp_path):
    """Endpoints wrapped by @view (or similar decorators) still receive the env."""
    from bottle import view

    db_path = str(tmp_path / "view.lmdb")
    plugin = LMDBPlugin(db_path)
    app = Bottle()
    app.install(plugin)

    @app.get("/read/<key>")
    @view("{{result}}")
    def read(key, db):
        with db.begin() as txn:
            value = txn.get(key.encode())
        return dict(result=value.decode() if value else "not found")

    transport = httpx.WSGITransport(app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        res = client.get("/read/foo")
    assert res.status_code == 200
    assert res.text == "not found"

    plugin.env.close()


def test_route_with_custom_keyword_per_route(tmp_path):
    """Route-level config can override the plugin keyword."""
    db_path = str(tmp_path / "per_route.lmdb")
    plugin = LMDBPlugin(db_path)
    app = Bottle()
    app.install(plugin)

    @app.get("/put/<value>", lmdb={"keyword": "store"})
    def put(value, store):
        with store.begin(write=True) as txn:
            txn.put(b"key", value.encode())
        return "ok"

    transport = httpx.WSGITransport(app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        res = client.get("/put/baz")
    assert res.status_code == 200
    assert res.text == "ok"

    with plugin.env.begin() as txn:
        assert txn.get(b"key") == b"baz"
    plugin.env.close()
