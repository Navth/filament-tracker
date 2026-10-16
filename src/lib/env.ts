import "server-only";

/**
 * Runtime configuration. Read with a dynamic key so values come from the
 * container's environment at request time (Cloud Run), not from build time.
 * The NEXT_PUBLIC_* names are accepted as fallbacks for convenience; the
 * app only talks to Supabase from the server, so nothing here is sent to
 * the browser.
 */
function read(...names: string[]): string | undefined {
  for (const name of names) {
    const value = process.env[name];
    if (value) return value;
  }
  return undefined;
}

function required(...names: string[]): string {
  const value = read(...names);
  if (!value) {
    throw new Error(`Missing environment variable: ${names[0]}`);
  }
  return value;
}

export const env = {
  get supabaseUrl() {
    return required("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL");
  },
  get supabaseKey() {
    return required(
      "SUPABASE_PUBLISHABLE_KEY",
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
      "SUPABASE_ANON_KEY",
    );
  },
  /** 32-byte key, base64-encoded, used to encrypt Bambu tokens at rest. */
  get tokenEncKey() {
    return required("TOKEN_ENC_KEY");
  },
  /** Optional comma-separated allowlist of emails that may use the app. */
  get allowedEmails(): string[] {
    return (read("ALLOWED_EMAILS") ?? "")
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean);
  },
};

export function isEmailAllowed(email: string | undefined | null): boolean {
  const list = env.allowedEmails;
  if (list.length === 0) return true;
  return !!email && list.includes(email.toLowerCase());
}
