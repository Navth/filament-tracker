# Security

## Model

- **Authentication** is handled by Supabase Auth. The session lives in
  HTTP-only cookies, refreshed by `src/proxy.ts`. Pages and server actions
  verify the user again (`getUser()` in `src/lib/data.ts`) before touching
  data.
- **Isolation between users** is enforced by Postgres row-level security
  on every table, a `security_invoker` view, and `SECURITY INVOKER`
  functions. The server queries Supabase with the user's own session, never
  a service-role key. Composite foreign keys prevent rows from referencing
  another user's spool. See `supabase/tests/test_schema.sql`.
- **Bambu Cloud tokens** are encrypted with AES-256-GCM before they're
  stored. The key (`TOKEN_ENC_KEY`) is only in the server environment;
  keep it in a secret manager. Bambu passwords are sent once to Bambu's
  login endpoint and never stored.
- **Bambu API calls happen only on the server**; tokens never reach the
  browser.
- **Invite-only mode**: set `ALLOWED_EMAILS`, and for a hard guarantee also
  disable new sign-ups in Supabase (Authentication → Sign In / Providers).

## Reporting a vulnerability

Open a GitHub issue without exploit details and ask for a private contact,
or use GitHub's private vulnerability reporting if enabled on the repo.
