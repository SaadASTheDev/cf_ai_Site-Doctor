# worker/main.py
import json
import time
from urllib.parse import urlparse
from workers import WorkerEntrypoint, Response

from durable import SiteStateDO  # re-export DO class
from tools import (
    analyze_headers,
    analyze_html,
    call_workers_ai,
    fetch_url,
    make_fix_prompt,
)


HTML_PAGE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Site Doctor</title>
  <style>
    :root {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      color: #1f1f1f;
      background: #f4f6f8;
    }
    body {
      margin: 0;
      padding: 2rem 1rem 4rem;
      max-width: 720px;
      margin-inline: auto;
      line-height: 1.5;
      background: inherit;
    }
    header {
      text-align: center;
      margin-bottom: 2rem;
    }
    h1 {
      font-size: clamp(2rem, 4vw, 2.75rem);
      margin: 0;
      letter-spacing: -0.02em;
    }
    form {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      padding: 1rem;
      border: 1px solid #d9dee3;
      border-radius: 12px;
      background: #fff;
    }
    input[type=url] {
      flex: 1 1 320px;
      padding: 0.65rem 0.85rem;
      border-radius: 8px;
      border: 1px solid #ccd3da;
      background: #fff;
      font-size: 1rem;
    }
    button {
      padding: 0.65rem 1.5rem;
      border-radius: 8px;
      border: 1px solid #2f80ed;
      background: #2f80ed;
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    button[disabled] {
      opacity: 0.65;
      cursor: wait;
    }
    .panel {
      background: #fff;
      border: 1px solid #d9dee3;
      border-radius: 12px;
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }
    h2 {
      margin-top: 0;
      font-size: 1.25rem;
    }
    h3 {
      margin-bottom: 0.25rem;
      font-size: 1rem;
    }
    ul {
      margin: 0;
      padding-left: 1.25rem;
    }
    .issues {
      color: #b03a2e;
    }
    .passes {
      color: #1e8449;
    }
    pre {
      white-space: pre-wrap;
      background: #f0f2f5;
      padding: 1rem;
      border-radius: 8px;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid #e2e6ea;
      text-align: left;
      font-size: 0.95rem;
    }
    .history-empty {
      opacity: 0.7;
      font-style: italic;
    }
    a {
      color: #2f80ed;
    }
    #status {
      min-height: 1.5rem;
      margin-bottom: 1.5rem;
      font-weight: 500;
    }
    #status.success { color: #1e8449; }
    #status.error { color: #b03a2e; }
  </style>
</head>
<body>
  <header>
    <h1>Site Doctor</h1>
  </header>
  <main>
    <form id=\"audit-form\">
      <input id=\"url-input\" type=\"url\" name=\"url\" placeholder=\"https://example.com\" required />
      <button type=\"submit\">Run audit</button>
    </form>
    <div id=\"status\"></div>
    <section id=\"results\" hidden>
      <article class=\"panel\">
        <h2>Header findings</h2>
        <div class=\"passes\">
          <h3>Passes</h3>
          <ul id=\"header-passes\"></ul>
        </div>
        <div class=\"issues\">
          <h3>Issues</h3>
          <ul id=\"header-issues\"></ul>
        </div>
      </article>
      <article class=\"panel\">
        <h2>HTML findings</h2>
        <div class=\"passes\">
          <h3>Passes</h3>
          <ul id=\"html-passes\"></ul>
        </div>
        <div class=\"issues\">
          <h3>Issues</h3>
          <ul id=\"html-issues\"></ul>
        </div>
      </article>
      <article class=\"panel\">
        <h2>AI fix plan</h2>
        <pre id=\"fix-plan\"></pre>
      </article>
    </section>
    <section class=\"panel\">
      <h2>Recent audits</h2>
      <div id=\"history\" class=\"history-empty\">Run an audit to populate history.</div>
    </section>
  </main>
  <script>
    const form = document.getElementById('audit-form');
    const urlInput = document.getElementById('url-input');
    const statusEl = document.getElementById('status');
    const resultsEl = document.getElementById('results');
    const fixPlanEl = document.getElementById('fix-plan');

    function renderList(target, items) {
      target.innerHTML = '';
      if (!items || !items.length) {
        target.innerHTML = '<li>None</li>';
        return;
      }
      for (const item of items) {
        const li = document.createElement('li');
        li.textContent = item;
        target.appendChild(li);
      }
    }

    function setStatus(message, type = 'info') {
      statusEl.textContent = message;
      statusEl.className = type;
    }

    function formatTimestamp(ts) {
      if (!ts) return 'Unknown';
      const d = new Date(ts * 1000);
      return d.toLocaleString();
    }

    async function loadHistory(domain) {
      if (!domain) return;
      try {
        const res = await fetch(`/api/history?domain=${encodeURIComponent(domain)}`);
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        const historyRoot = document.getElementById('history');
        if (!data.history?.length) {
          historyRoot.textContent = 'No audits yet for this domain.';
          historyRoot.className = 'history-empty';
          return;
        }
        const table = document.createElement('table');
        table.innerHTML = `
          <thead>
            <tr><th>When</th><th>URL</th><th>Issues found</th></tr>
          </thead>
        `;
        const tbody = document.createElement('tbody');
        for (const entry of data.history) {
          const tr = document.createElement('tr');
          const totalIssues = (entry.headers?.issues?.length || 0) + (entry.html?.issues?.length || 0);
          tr.innerHTML = `
            <td>${formatTimestamp(entry.ts)}</td>
            <td><a href="${entry.url}" target="_blank" rel="noopener">${entry.url}</a></td>
            <td>${totalIssues}</td>
          `;
          tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        historyRoot.innerHTML = '';
        historyRoot.className = '';
        historyRoot.appendChild(table);
      } catch (err) {
        const historyRoot = document.getElementById('history');
        historyRoot.textContent = `Failed to load history: ${err}`;
        historyRoot.className = '';
      }
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const targetUrl = urlInput.value.trim();
      if (!targetUrl) return;
      let domain;
      try {
        domain = new URL(targetUrl).hostname;
      } catch (err) {
        setStatus('Enter a valid absolute URL, including https://', 'error');
        return;
      }
      form.querySelector('button').disabled = true;
      setStatus('Running audit…');
      try {
        const res = await fetch('/api/audit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: targetUrl })
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        renderList(document.getElementById('header-passes'), data.summary.headers.passes);
        renderList(document.getElementById('header-issues'), data.summary.headers.issues);
        renderList(document.getElementById('html-passes'), data.summary.html.passes);
        renderList(document.getElementById('html-issues'), data.summary.html.issues);
        fixPlanEl.textContent = data.fix_plan || 'No plan generated.';
        resultsEl.hidden = false;
        setStatus('Audit complete!', 'success');
        loadHistory(domain);
      } catch (err) {
        setStatus(`Audit failed: ${err}`, 'error');
      } finally {
        form.querySelector('button').disabled = false;
      }
    });
  </script>
</body>
</html>"""

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        path = urlparse(str(request.url)).path

        if request.method == "POST" and path == "/api/audit":
            try:
                body = await request.json()
            except Exception:
                return Response(
                    json.dumps({"error": "invalid JSON"}),
                    status=400,
                    headers={"content-type": "application/json"},
                )

            target = (body or {}).get("url") if isinstance(body, dict) else None
            if not target:
                return Response(
                    json.dumps({"error": "Missing 'url'"}),
                    status=400,
                    headers={"content-type": "application/json"},
                )

            try:
                http_res = await fetch_url(target)
                text = await http_res.text()
            except Exception as exc:
                return Response(
                    json.dumps({"error": f"Failed to fetch target: {exc}"}),
                    status=502,
                    headers={"content-type": "application/json"},
                )

            header_findings = analyze_headers(http_res.headers)
            html_findings = analyze_html(text)
            plan = await call_workers_ai(
                env, make_fix_prompt(target, header_findings, html_findings)
            )

            domain = urlparse(target).netloc
            ts = int(time.time())
            do_id = env.SITE_STATE.idFromName(domain)
            stub = env.SITE_STATE.get(do_id)
            record = {
                "domain": domain,
                "url": target,
                "ts": ts,
                "headers": header_findings,
                "html": html_findings,
                "fix_plan": plan,
            }
            await stub.fetch(
                "/save",
                {
                    "method": "POST",
                    "body": json.dumps(record),
                    "headers": {"content-type": "application/json"},
                },
            )

            return Response(
                json.dumps(
                    {
                        "ok": True,
                        "target": target,
                        "summary": {"headers": header_findings, "html": html_findings},
                        "fix_plan": plan,
                    }
                ),
                status=200,
                headers={"content-type": "application/json"},
            )

        if request.method == "GET" and path == "/api/history":
            q = urlparse(str(request.url))
            params = dict(p.split("=", 1) for p in q.query.split("&") if "=" in p) if q.query else {}
            domain = params.get("domain")
            if not domain:
                return Response(
                    json.dumps({"error": "Missing 'domain'"}),
                    status=400,
                    headers={"content-type": "application/json"},
                )
            do_id = env.SITE_STATE.idFromName(domain)
            stub = env.SITE_STATE.get(do_id)
            res = await stub.fetch("/list")
            return Response(
                await res.text(),
                status=200,
                headers={"content-type": "application/json"},
            )

        if path == "/":
            return Response(
                HTML_PAGE,
                status=200,
                headers={"content-type": "text/html; charset=utf-8"},
            )

        return Response("Not found", status=404)
