# cf_ai_Site-Doctor

An agentic “edge SRE” that audits any domain you enter, chats or talks with you about issues, and auto-creates a fix plan.

## Running locally

```bash
pnpm wrangler dev
```

The Worker now serves a single-page UI at `/`:

* Enter a full URL (including protocol) and trigger an audit.
* Review header and HTML findings along with an AI-generated remediation plan.
* Recent runs for the same domain are persisted via a Durable Object and displayed in the history panel.

APIs remain available directly under `/api/audit` and `/api/history` if you want to integrate the service elsewhere.
