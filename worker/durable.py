# worker/durable.py
import json
from workers import DurableObject, Response

class SiteStateDO(DurableObject):
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env

    def fetch(self, request):
        url = str(request.url)
        path = url.split("?", 1)[0]

        if request.method == "POST" and path.endswith("/save"):
            data = request.json()  # DO fetch is sync; Request is FFI-backed
            ts = data.get("ts", 0)
            key = f"run:{ts}"
            self.ctx.storage.sql.exec(
                "INSERT INTO kv (key, value) VALUES (?1, ?2) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [key, json.dumps(data)]
            )
            self.ctx.storage.sql.exec(
                "INSERT INTO kv (key, value) VALUES ('latest', ?1) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [json.dumps(data)]
            )
            return Response(json.dumps({"ok": True}), {"status": 200})

        if request.method == "GET" and path.endswith("/list"):
            rows = self.ctx.storage.sql.exec("SELECT key, value FROM kv WHERE key LIKE 'run:%'").all()
            entries = [json.loads(r.value) for r in rows]
            entries.sort(key=lambda x: x.get("ts", 0), reverse=True)
            latest = self.ctx.storage.sql.exec("SELECT value FROM kv WHERE key='latest'").one()
            latest_val = json.loads(latest.value) if latest else None
            return Response(json.dumps({"latest": latest_val, "history": entries[:20]}),
                            {"status": 200, "headers": {"content-type": "application/json"}})

        return Response("Not found", {"status": 404})
