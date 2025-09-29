import json
import re

# Platform fetch is available in Python Workers
async def fetch_url(url: str):
    return await fetch(url)

def analyze_headers(headers) -> dict:
    h = {k.lower(): v for k, v in headers.items()}
    findings = {"passes": [], "issues": []}

    def has(name): return name in h

    required = [
        ("strict-transport-security", "Enable HSTS to enforce HTTPS"),
        ("content-security-policy", "Add a CSP to mitigate XSS"),
        ("x-content-type-options", "Add 'nosniff' to prevent MIME sniffing"),
        ("referrer-policy", "Add a restrictive Referrer-Policy"),
        ("permissions-policy", "Restrict powerful features"),
    ]
    for name, msg in required:
        if has(name):
            findings["passes"].append(f"{name} present")
        else:
            findings["issues"].append(msg)

    cache = h.get("cache-control", "")
    if cache and any(t in cache for t in ["max-age", "s-maxage"]):
        findings["passes"].append("Cache-Control tuned")
    else:
        findings["issues"].append(
            "Add Cache-Control max-age or s-maxage for static assets"
        )
    return findings

def analyze_html(html: str) -> dict:
    findings = {"passes": [], "issues": []}

    if re.search(r'<meta[^>]+name="description"[^>]*>', html, re.I):
        findings["passes"].append("Meta description present")
    else:
        findings["issues"].append("Add meta description for SEO")

    # Simple heuristics; extend as needed
    if re.search(r"<style>.*?</style>", html, re.S):
        findings["issues"].append("Move large inline CSS to static file with hashing")
    if re.search(r"<script>.*?</script>", html, re.S | re.I):
        findings["issues"].append("Avoid large inline scripts; prefer CSP with nonces")
    if not re.search(r'<link[^>]+rel="preload"[^>]+as="(style|font)"', html, re.I):
        findings["issues"].append("Preload critical CSS/fonts")

    return findings

def make_fix_prompt(target: str, headers: dict, html: dict) -> str:
    return (
        f"You are an expert web performance and security engineer. "
        f"Analyze issues for {target} and produce a prioritized fix plan. "
        f"Group by Security, Performance, SEO. Provide concrete config/code: "
        f"CSP sample, HSTS value, caching rules, image strategy, and a short PR diff.\n\n"
        f"Headers findings: {json.dumps(headers)}\n\nHTML findings: {json.dumps(html)}\n"
    )

async def call_workers_ai(env, prompt: str) -> str:
    # Binding-only path (fallback removed)
    try:
        if hasattr(env, "AI"):
            result = await env.AI.run(
                env.AI_MODEL, {"messages": [{"role": "user", "content": prompt}]}
            )
            return result.get("response", "")
    except Exception:
        pass
    return "[Workers AI binding not available; configure env.AI]"
