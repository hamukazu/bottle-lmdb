"""Tests for LMDBPlugin integration with Bottle."""

from io import BytesIO
from wsgiref.util import setup_testing_defaults

import lmdb
import pytest
from bottle import Bottle

from bottle_lmdb import LMDBPlugin


def call_app(app, path="/"):
    """Call a Bottle WSGI app directly and return (status, body)."""
    environ = {}
    setup_testing_defaults(environ)
    environ["PATH_INFO"] = path
    environ["wsgi.input"] = BytesIO(b"")
    result = {}

    def start_response(status, headers, exc_info=None):
        result["status"] = status

    body = b"".join(app(environ, start_response))
    return result["status"], body


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.lmdb")


@pytest.fixture
def app(db_path):
    """A Bottle app with the plugin installed and a route using the db."""
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

    return app


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


def test_route_receives_env_via_default_keyword(app):
    status, body = call_app(app, "/write/foo/bar")
    assert status.startswith("200")
    assert body == b"ok"

    status, body = call_app(app, "/read/foo")
    assert status.startswith("200")
    assert body == b"bar"


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

    status, body = call_app(app, "/put/baz")
    assert status.startswith("200")
    assert body == b"ok"

    with plugin.env.begin() as txn:
        assert txn.get(b"key") == b"baz"
    plugin.env.close()


def test_data_persists_across_requests(app):
    call_app(app, "/write/hello/world")
    status, body = call_app(app, "/read/hello")
    assert status.startswith("200")
    assert body == b"world"

    status, body = call_app(app, "/read/missing")
    assert status.startswith("200")
    assert body == b"not found"
