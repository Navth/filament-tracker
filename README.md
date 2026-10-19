# 🧵 Filament Tracker for Bambu Lab

A multi-user web app that tracks how much filament is left on every spool,
by syncing your print history (grams per print) from Bambu Cloud.

**Stack:** Next.js 16 (App Router, Server Actions) · TypeScript · shadcn/ui ·
Tailwind CSS 4 · Supabase (Auth + Postgres with row-level security) ·
Firebase App Hosting

> **AI chat-ops agent:** [`agent/`](agent/) adds an assistant you can ask
> things like *"do I have enough PETG for this 180 g job?"*. It's built with Gemini or Claude,
> LangGraph and an MCP server over your spools and prints, asks for approval before
> any change, and comes with an eval suite that measures how often it's right.

## Features

- **Accounts.** Email sign-up and login with Supabase Auth. Optional
  invite-only mode with an email allowlist.
- **Automatic tracking.** Pulls finished print jobs from Bambu Cloud; each
  job carries the slicer's estimated filament weight.
- **Spool management.** Load or swap a spool per slot. The old spool is
  archived with its totals and the new one starts from zero.
- **AMS Lite support.** 1 to 4 slots; multi-colour jobs are split per slot.
- **Corrections.** Weigh a spool and enter the real grams left, mark failed
  prints as ignored, or move a print to the spool it actually used.

## Architecture

```
Browser ──► Next.js on Firebase App Hosting ──► Supabase Postgres (RLS)
             │  Server Components read data
             │  Server Actions write data
             └─► Bambu Cloud API (server-side only)
```

- **Every request runs as the signed-in user.** The server talks to
  Supabase with the user's own session, so Postgres
  [row-level security](supabase/migrations/20261017000000_multi_user.sql) decides what
  they can see. A bug in the app can't leak another user's data.
- **Composite foreign keys** (`spool_id, user_id`) stop a print or
  correction from ever pointing at someone else's spool.
- **Business logic lives in the database** as `SECURITY INVOKER` functions
  (`import_prints`, `change_spool`, `set_remaining`) and a
  `security_invoker` view (`spool_stats`), so it's atomic and still
  RLS-checked.
- **Bambu tokens are encrypted at rest** with AES-256-GCM. The key lives
  only in the server's environment (Cloud Secret Manager). Bambu
  passwords are never stored.
- **One data access layer** ([`src/lib/data.ts`](src/lib/data.ts)) handles
  every read and write and verifies the user first. The AI agent's tools
  will call the same functions.

## Run it locally

You need Node 22 and a Supabase project (the free tier is fine).

1. In the Supabase dashboard, open **SQL Editor** and run
   [`supabase/migrations/20261017000000_multi_user.sql`](supabase/migrations/20261017000000_multi_user.sql).
2. Copy `.env.example` to `.env.local` and fill it in:
   ```bash
   node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"  # TOKEN_ENC_KEY
   ```
3. In **Authentication → URL Configuration**, add
   `http://localhost:3000/auth/callback` to the redirect URLs.
4. Start it:
   ```bash
   npm install
   npm run dev
   ```
5. Optional, the **Chat** page: start the agent service on demo data
   (setup in [`agent/README.md`](agent/README.md#run-it)) and point the app at it.
   Add `AGENT_URL=http://127.0.0.1:8000` to `.env.local`, then:
   ```bash
   cd agent
   ft-agent serve --demo
   ```
   Drop `--demo` to chat about your real spools (the agent then needs the same
   `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` in `agent/.env`).

## Deploy to Firebase App Hosting

App Hosting builds and runs the Next.js server for you and redeploys on
every push to your live branch. It needs the Blaze (pay-as-you-go) plan;
a small app like this normally stays within the free usage tier.
Config lives in [`apphosting.yaml`](apphosting.yaml).

1. Push this repo to GitHub.
2. Create a Firebase project (or use an existing GCP one) and upgrade it
   to Blaze.
3. Install the CLI and create the secrets the app reads at runtime:
   ```bash
   npm install -g firebase-tools
   firebase login
   firebase use --add            # pick your project
   firebase apphosting:secrets:set supabase-url
   firebase apphosting:secrets:set supabase-publishable-key
   firebase apphosting:secrets:set token-enc-key
   ```
   For `token-enc-key`, paste the output of
   `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"`.
4. In the Firebase console, open **Build → App Hosting → Create backend**,
   connect the GitHub repo, set the root directory to `/` and the live
   branch to `main`. Pick a region close to you (e.g. `asia-southeast1`).
   If the secrets prompt asks, grant the new backend access to all three.
5. When the first rollout finishes, copy the `*.hosted.app` URL. In
   Supabase, open **Authentication → URL Configuration**, set **Site URL**
   to it and add `https://<your-url>/auth/callback` to the redirect URLs.

**Custom domain later:** App Hosting → your backend → **Settings → Domains
→ Add custom domain**, add the DNS records it shows, then update the
Supabase Site URL and redirect URL (and `SITE_URL` in `apphosting.yaml`).

The [`Dockerfile`](Dockerfile) still works for Cloud Run or any other
container host if you'd rather not use App Hosting.

## Deploy the chat agent (Cloud Run)

The `/chat` page talks to the Python agent in [`agent/`](agent/), which runs as
its own Cloud Run service. It checks each request's Supabase access token and
works with that token, so it sees only the caller's data. Skip this section if
you don't want the chat; the page then says it isn't set up.

1. Create a Postgres database for conversation state. Supabase's own database
   works: copy the **session pooler** (or direct) connection string from
   **Connect** in the dashboard. The agent keeps its tables in a separate
   `agent` schema that the Supabase API doesn't expose.
2. Store the secrets (same project as App Hosting, so the Supabase secrets
   from above can be reused):
   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
   printf %s "YOUR_GEMINI_KEY" | gcloud secrets create gemini-api-key --data-file=-
   printf %s "postgresql://..." | gcloud secrets create agent-database-url --data-file=-
   ```
   Give the Cloud Run runtime service account (by default
   `PROJECT_NUMBER-compute@developer.gserviceaccount.com`) the **Secret
   Manager Secret Accessor** role on these secrets and on `supabase-url` and
   `supabase-publishable-key`.
3. Build and deploy from [`agent/Dockerfile`](agent/Dockerfile):
   ```bash
   gcloud run deploy filament-agent --source agent --region asia-southeast1 \
     --allow-unauthenticated --max-instances 2 --timeout 300 \
     --set-secrets SUPABASE_URL=supabase-url:latest,SUPABASE_PUBLISHABLE_KEY=supabase-publishable-key:latest,GEMINI_API_KEY=gemini-api-key:latest,FT_AGENT_DATABASE_URL=agent-database-url:latest
   ```
   `--allow-unauthenticated` only opens the URL; every chat request still
   needs a valid Supabase session. To use Claude instead of Gemini, store
   `ANTHROPIC_API_KEY` and add `--set-env-vars FT_AGENT_PROVIDER=claude`. If
   you use `ALLOWED_EMAILS` in the app, set the same value here.
4. Copy the service URL that the deploy prints. Set it as `AGENT_URL` in
   [`apphosting.yaml`](apphosting.yaml) (uncomment the block), then push to
   roll out the web app.

## Tests

```bash
npm test          # unit tests: Bambu task parsing, token encryption
npm run lint
npm run typecheck
```

Database tests run the migration against a plain Postgres with a small
stand-in for Supabase's `auth` schema, then check every RLS rule and
function as two different users:

```bash
createdb ft_test
psql -d ft_test -f supabase/tests/supabase_stub.sql
psql -d ft_test -f supabase/migrations/20261017000000_multi_user.sql
psql -d ft_test -f supabase/tests/test_schema.sql   # ends with "ALL SQL TESTS PASSED"
```

## How the math works

```
remaining = spool grams − Σ(counted prints) − Σ(corrections)
```

- Prints are charged to a spool only if they **started after it was
  loaded**. Older history is imported as *unassigned*.
- Jobs still printing are skipped and imported on a later sync.
- Grams are *slicer estimates*, so purges and failures cause drift. Weigh
  the spool and correct it on the Spools page (empty spools weigh about
  130–250 g).

## Disclaimers

- **Unofficial API.** Bambu Lab's cloud API is undocumented and may change
  or break at any time. This project is not affiliated with or endorsed by
  Bambu Lab.
- **Hosting for others.** Users hand this app a Bambu Cloud token. Run it
  invite-only (`ALLOWED_EMAILS`, or disable sign-ups in Supabase) unless
  you're prepared to look after other people's credentials.

## Project layout

```
src/app/(auth)/         login, sign-up, auth actions
src/app/(app)/          dashboard, spools, prints, chat, settings + server actions
src/app/auth/callback/  email confirmation handler
src/lib/data.ts         data access layer (all reads/writes, user-checked)
src/lib/agent.ts        client for the chat agent service (forwards the user's session)
src/lib/bambu/          Bambu Cloud client and task → row mapping
src/lib/crypto.ts       AES-256-GCM token encryption
src/proxy.ts            session refresh + sign-in redirect
src/components/ui/      shadcn/ui components
supabase/migrations/    schema, RLS policies, functions
supabase/tests/         database tests
agent/                  Python chat agent + its HTTP API and Dockerfile
```

Version 1 was a single-user Flask + SQLite app for local use. It's still in
the git history at commit `aa39801` if you want a local-only version.

## License

[MIT](LICENSE)
