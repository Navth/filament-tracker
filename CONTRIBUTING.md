# Contributing

Thanks for your interest! This is a small project, so keep changes focused.

## Setup

See **Run it locally** in the [README](README.md). Then:

```bash
npm run dev        # http://localhost:3000
npm test           # unit tests
npm run lint && npm run typecheck
```

## Guidelines

- All data access goes through `src/lib/data.ts`. Don't query Supabase
  directly from pages or components.
- Server Actions must validate their input (zod) and never trust IDs from
  the client; RLS is the backstop, not the only check.
- Schema changes go in a new file under `supabase/migrations/`, with tests
  in `supabase/tests/test_schema.sql`.
- UI uses shadcn/ui components in `src/components/ui/`.
- One feature or fix per pull request.
- If you touch `src/lib/bambu/`, test against a real Bambu Cloud account;
  the API is unofficial and behaviour matters more than docs.
- Never include real tokens, emails, serial numbers or keys in code, tests,
  issues or screenshots.

## Reporting bugs

Use the bug report template. Include your printer model, whether you use
AMS Lite, and the error message, with any tokens or emails redacted.
