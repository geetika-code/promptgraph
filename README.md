# PromptGraph

Debugger for hierarchical LLM workflows: visualise the graph, run it, inspect per-node traces, audit prompts for conflicts, get a suggested fix, and **test the fix against the same cases before accepting it**.

## Run locally

```bash
cp .env.example .env                       # loaded automatically by the backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000

cd frontend && npm install && npm run dev  # http://localhost:5173 (proxies /api to :8000)
```

## How it works

**You write everything; the model does the work.** PromptGraph ships with no sample workflow, no canned replies and no simulated mode. If no model is configured, runs show a clear error instead of fake output.

- **Workflow** = nodes (a prompt each) and edges. An edge with condition `always` is always followed; any other condition is a routing label the source node must output. A router that has no fallback route (`other`, `misc`, …) is flagged by the audit.
- **Run**: nodes execute in topological order. Each node's system prompt is assembled from separate labelled sections (role, global rules, guardrails, the node's own instructions, output format). The text of every tool-owned prompt lives in `backend/prompts/*.md`, so you can read and edit it.
- **Guardrails**: describe the domain, click *Suggest guardrails* (the model proposes rules, checks and probe questions), review, accept. Accepted guardrails are injected into every prompt, enforced on the final reply at Run time (one model rewrite, then a labelled block notice), and each probe becomes a test.
- **Audit**: plain-code static checks (contradictory absolute instructions, router without fallback, near-duplicate prompts, missing purpose or guardrails) plus a model audit when the model is reachable.
- **Suggest improved prompt** asks the model to rewrite one node; it is a proposal until **Evaluate** or **Run tests** shows it passes the same cases. Pass/fail is decided by deterministic assertions (`contains`, `not_contains`, `regex`, `not_regex`), never by the model grading itself.
- **Versions**: saving stores a new prompt version per changed node. Traces show `vN`, or `vN draft` for unsaved prompts.
- **Limits**: 30 nodes, depth 10, `LLM_TIMEOUT_SECONDS` per call (1 retry), 600 s per run.
- Unsaved editor changes are what Run/Audit/Suggest/Tests use; the baseline in Evaluation is always the *saved* workflow.

## Tests

```bash
pytest backend/tests
cd frontend && npm test && npm run build
```

## Deploy (Docker, e.g. Render)

The backend serves `frontend/dist` if it exists, so one service is enough:

```bash
cd frontend && npm ci && npm run build
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Set `LLM_*` and `DATABASE_URL` as host environment secrets (put the SQLite file on a persistent volume). If you host the frontend separately, set `CORS_ORIGINS` and proxy `/api` to the backend. Keys are never stored in workflows or the database, or returned by the API.

## Known limits

Runs need a working model. 
No authentication, a single shared SQLite database, and sequential execution only.

### One-click-ish on Render (free)

1. Push this folder to a GitHub repo (`.env` and `.venv` are git-ignored).
2. On render.com: **New → Blueprint**, pick the repo. `render.yaml` and the `Dockerfile` do the rest.
3. A hosted server cannot reach a model on your laptop. Point `LLM_BASE_URL` at a hosted OpenAI-compatible endpoint, or temporarily expose local Ollama with a tunnel (`cloudflared tunnel --url http://localhost:11434`, then `LLM_BASE_URL=<tunnel-url>/v1`). The tunnel is public: remove it afterwards.
