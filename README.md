# bottle-lmdb
Lightning Memory-Mapped Database (LMDB) plugin for Bottle.

Usage:

```python
from bottle import Bottle
from bottle_lmdb import LMDBPlugin

app = Bottle()
plugin = LMDBPlugin("/path/to/db")
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
```