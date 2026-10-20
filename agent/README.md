# Filament Tracker chat-ops agent

Ask your filament data questions in plain English, and let the agent make
changes once you approve them. An example exchange:

```
you> I want to print a 200 g bracket on the white PETG. Is there enough?

It's tight. Spool #2 (white eSun PETG, slot 2) has 209.7 g left, so a 200 g print
fits only without the usual 10% safety margin. Weigh the spool first, or use the
blue PETG in slot 4 (600 g).
```

Built with **LangGraph**, an **MCP server**, **Pydantic**, a pluggable model layer
(**Gemini** via Google's Gen AI SDK by default, or **Claude** via the Anthropic SDK), and
an **eval suite** that measures how often the agent is right.

## How it works

```
                        ┌──────────────────────── LangGraph (checkpointed) ────────────────────────┐
question ─► prepare ─► call_model ─┬─► run_tools ───────────────────────────► call_model           │
            │                      ├─► approve ── interrupt() ── you: y/n ─► run_tools             │
            │                      ├─► verify ─┬─ checks fail ─► call_model (with the problems)    │
            │                      │           └─ checks pass ─► finish ─► answer                  │
            │                      └─► nudge / give_up                                             │
            └── layered context: summary + recent turns + spool snapshot + question                │
                        └──────────────────────────────────┬──────────────────────────────────────┘
                                                           │ MCP (tools/list, tools/call)
                                              ┌────────────▼────────────┐
                                              │  MCP server (ft-mcp)    │  7 typed tools
                                              │  FilamentService        │  all arithmetic here
                                              └────────────┬────────────┘
                                         Supabase PostgREST as the user (RLS) │ or in-memory demo data
```

**Design choices**

- **MCP server as the tool layer.** [`mcp_server.py`](src/filament_agent/mcp_server.py)
  exposes `list_spools`, `get_spool`, `list_prints`, `usage_summary`,
  `check_print_feasibility`, `log_print` and `correct_spool_weight`, each returning a
  Pydantic model as structured output. It's a normal MCP server, so `ft-mcp` also works
  from Claude Desktop or any other MCP client.
- **Arithmetic lives in code, not in the model.** "Do I have enough?" goes through
  `check_print_feasibility`, which applies a 10% safety margin (slicer estimates drift)
  and returns `yes` / `tight` / `no`.
- **Human-in-the-loop for writes.** Any tool the MCP server doesn't mark
  `readOnlyHint` pauses the graph with LangGraph's `interrupt()`. State is checkpointed
  (SQLite in the CLI), so an approval can be answered later and the turn resumes where it
  stopped. Declined writes are never run, and the model is told not to retry them.
- **Structured output plus deterministic gates.** Every turn ends with a strict
  `final_answer` tool call validated by Pydantic ([`AgentAnswer`](src/filament_agent/models.py)).
  Before the user sees it, [`verify`](src/filament_agent/graph.py) checks the fields
  against the data: cited spools exist, `grams_available` matches them, the verdict agrees
  with the feasibility check, and `actions_taken` matches the writes that actually
  succeeded. On a mismatch the problems go back to the model as a tool error (up to 2 retries).
- **Context engineering.** Each turn is a fresh request built in layers
  ([`context.py`](src/filament_agent/context.py)): a cached system prompt and tools, a
  rolling summary of older turns, the last few turns verbatim within a token budget, a
  snapshot of loaded spools (saves a tool call on most questions), then the question.
  Tool results go back as compact JSON. Within a turn, history is append-only.
- **Security.** Against your real data the agent runs as you: it uses your Supabase
  session, so Postgres row-level security applies exactly as in the web app. Print titles
  and notes are treated as data, and an eval case checks that instructions hidden in a
  print title are ignored.
- **Swappable models.** The graph stores messages in one neutral shape (text /
  tool_use / tool_result) and talks to the model through a two-method interface
  ([`llm.py`](src/filament_agent/llm.py)). [`gemini_llm.py`](src/filament_agent/gemini_llm.py)
  translates to Gemini function calling and replays Gemini's own parts, including thought
  signatures, exactly. It also rate-limits itself to stay inside the free tier.
  `ClaudeLLM` uses prompt caching, effort control and server-side refusal fallback.
  Switch with `FT_AGENT_PROVIDER=gemini|claude`.

## Run it

Needs Python 3.11+ and a Gemini API key (free tier is enough) or an Anthropic API key.

```bash
cd agent
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # macOS/Linux: .venv/bin/pip
cp .env.example .env                        # then set GEMINI_API_KEY
```

Try it on built-in demo data (5 spools, 17 prints):

```bash
ft-agent chat --demo -v        # -v shows tool calls and token usage
ft-agent ask --demo "When will my red PLA run out?"
```

Use your real Filament Tracker account (set `SUPABASE_URL` and
`SUPABASE_PUBLISHABLE_KEY` in `.env`, the same values as the web app):

```bash
ft-agent login                 # email + password; only the session is stored, never the password
ft-agent chat
```

Conversations are kept per `--thread` in `~/.filament-agent/`.

## Web API (`ft-agent serve`)

The web app's `/chat` page talks to the agent over HTTP
([`server.py`](src/filament_agent/server.py)):

| Endpoint | Body | Returns |
|---|---|---|
| `POST /chat` | `{thread_id, message}` | `{status: "answered" \| "needs_approval", answer, approval, ...}` |
| `POST /chat/approve` | `{thread_id, decisions}` (`true`/`false`, or `{action_id: bool}`) | same as `/chat` |
| `GET /chat/{thread_id}` | | recent turns and any pending approval |
| `GET /healthz` | | `{ok: true}` |

Every `/chat` request needs `Authorization: Bearer <Supabase access token>`. The
server checks the token with Supabase Auth, then runs the agent with that same
token, so RLS applies. The user id is never taken from the request: threads are
stored under `<verified user id>:<thread_id>`, so users can't open each other's
threads. `ALLOWED_EMAILS` (same as the web app) limits who can use it.

```bash
ft-agent serve --demo          # demo data, http://127.0.0.1:8000
ft-agent serve --port 8080     # real accounts (needs SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY)
```

With `--demo` each signed-in user gets their own in-memory copy of the demo data.
If `SUPABASE_URL` isn't set, `--demo` accepts any bearer token (demo data only).

Threads are checkpointed to SQLite in `~/.filament-agent/` by default. On Cloud Run,
where each instance has its own short-lived disk, set `FT_AGENT_DATABASE_URL` to a
Postgres connection string (`pip install -e ".[postgres]"`). Checkpoints go in their
own `agent` schema (`FT_AGENT_DB_SCHEMA`), which PostgREST doesn't expose. With
Supabase's database, use the direct or **session** pooler connection string, not the
transaction pooler. [`Dockerfile`](Dockerfile) builds the Cloud Run image; deploy
steps are in the [main README](../README.md#deploy-the-chat-agent-cloud-run).

## Evals

[`evals/cases.jsonl`](evals/cases.jsonl) has 25 cases: lookups, feasibility
(yes / tight / no / no matching spool), usage forecasts, writes (approved and
declined), safety (no unrequested writes, prompt injection in a print title),
clarifying questions, off-topic requests and multi-turn follow-ups.

```bash
ft-evals                       # all cases, 1 rep
ft-evals --reps 3              # repeats, for confidence intervals
ft-evals --tag write --case safety-injection
ft-evals --baseline null       # known-bad agent, to prove the grader isn't lenient
```

Each run uses a fresh copy of the demo data and scores separate checks:

| Check | What it verifies |
|---|---|
| `fields` | verdict, cited spools and grams in the structured answer match the data |
| `end_state` | spool weights after the turn (writes really happened, or really didn't) |
| `approval` | an approval was requested if and only if the user asked for a change |
| `actions` | `actions_taken` matches what happened |
| `judge` | the answer text against a per-case rubric, graded by a different model from the one under test (`gemini-3.5-flash-lite` or `claude-sonnet-5-5`) |

A case passes only if all its checks pass. API errors and timeouts go to
`errors.jsonl` and aren't scored. A row served by a different model than configured
is treated as an error. Results, full answers, tool traces, token usage and cost land
in `evals/results/<timestamp>/` with a `summary.md`.

## Tests

```bash
pytest
```

55 tests, no API calls. A scripted fake model drives the graph through tool use,
approve/decline, verifier rejections, nudges, step limits, refusals and history
compaction. There are also tests for the data math, the MCP tools, the HTTP API
(token checks, approvals, per-user thread isolation), and the grader itself:
correct answers pass, wrong ones fail, and the null baseline scores near zero.

## Layout

```
src/filament_agent/
  graph.py        LangGraph state machine (approval interrupt, verifier, give-up paths)
  agent.py        FilamentAgent: ask / resume / pending_approval per thread
  mcp_server.py   MCP server and tool annotations
  repository.py   FilamentService + Supabase and in-memory backends
  context.py      system prompt, layered context, token budgeting
  llm.py          model interface + Claude client (caching, effort, refusal fallback)
  gemini_llm.py   Gemini client (function calling, thought signatures, rate limit)
  models.py       Pydantic contracts, including AgentAnswer
  evals.py        eval runner and graders
  server.py       HTTP API for the web app (Supabase token auth, per-user threads)
  cli.py, auth.py command line and Supabase sign-in
evals/cases.jsonl eval cases
tests/            pytest suite and demo fixture
```
