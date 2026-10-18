import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

/**
 * Landing page for links in Supabase Auth emails (sign-up confirmation).
 * Handles both the PKCE `code` flow and the `token_hash` flow.
 */
export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;

  const supabase = await createClient();
  let error: { message: string } | null = null;

  if (code) {
    ({ error } = await supabase.auth.exchangeCodeForSession(code));
  } else if (tokenHash && type) {
    ({ error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash }));
  } else {
    error = { message: "Missing confirmation code" };
  }

  const to = url.clone();
  to.search = "";
  if (error) {
    to.pathname = "/login";
    to.searchParams.set("error", "confirm-failed");
  } else {
    to.pathname = "/";
  }
  return NextResponse.redirect(to);
}
