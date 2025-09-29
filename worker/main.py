# worker/main.py
import json
from urllib.parse import urlparse
from workers import WorkerEntrypoint, Response

from durable import SiteStateDO  # re-export DO class
from tools import fetch_url, analyze_headers, analyze_html, make_fix_prompt, call_workers_ai

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        path = urlparse(str(request.url)).path

        if request.method == "POST" and path == "/api/audit":
            try:
                body = await request.json()
            except Exception:
                return Response("Invalid JSON", {"status": 400})

            target = body.get("url")
            if not target:
                return Response("Missing 'url'", {"status": 400})

            http_res = await fetch_url(target)
            text = await http_res.text()
            header_findings = analyze_headers(http_res.headers)
            html_findings = analyze_html(text)

            domain = urlparse(target).netloc
            do_id = env.SITE_STATE.idFromName(domain)
            stub = env.SITE_STATE.get(do_id)
            await stub.fetch(
                "/save",
                {
                    "method": "POST",
                    "body": json.dumps({
                        "domain": domain,
                        "ts": 0,
                        "headers": header_findings,
                        "html": html_findings,
                    }),
                },
            )

            plan = await call_workers_ai(env, make_fix_prompt(target, header_findings, html_findings))
            return Response(json.dumps({
                "ok": True,
                "target": target,
                "summary": {"headers": header_findings, "html": html_findings},
                "fix_plan": plan,
            }), {"status": 200, "headers": {"content-type": "application/json"}})

        if request.method == "GET" and path == "/api/history":
            q = urlparse(str(request.url))
            params = dict(p.split("=", 1) for p in q.query.split("&") if "=" in p) if q.query else {}
            domain = params.get("domain")
            if not domain:
                return Response("Missing 'domain'", {"status": 400})
            do_id = env.SITE_STATE.idFromName(domain)
            stub = env.SITE_STATE.get(do_id)
            res = await stub.fetch("/list")
            return Response(await res.text(), {"status": 200, "headers": {"content-type": "application/json"}})

        if path == "/":
            return Response("Site Doctor Agent up", {"status": 200})

        return Response("Not found", {"status": 404})