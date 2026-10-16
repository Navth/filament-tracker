"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import { fail, ok, type ActionResult } from "@/lib/action-result";
import { isEmailAllowed } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

const credentials = z.object({
  email: z.string().trim().toLowerCase().email(),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

async function origin() {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host");
  const proto = h.get("x-forwarded-proto") ?? "https";
  return process.env["SITE_URL"] ?? `${proto}://${host}`;
}

export async function signIn(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = credentials.safeParse({ email: form.get("email"), password: form.get("password") });
  if (!parsed.success) return fail("Enter a valid email and password.");
  if (!isEmailAllowed(parsed.data.email)) return fail("This app is invite-only for now.");

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword(parsed.data);
  if (error) return fail(error.message);
  redirect("/");
}

export async function signUp(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = credentials.safeParse({ email: form.get("email"), password: form.get("password") });
  if (!parsed.success) {
    return fail(parsed.error.issues[0]?.message ?? "Enter a valid email and password.");
  }
  if (!isEmailAllowed(parsed.data.email)) return fail("This app is invite-only for now.");

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    ...parsed.data,
    options: { emailRedirectTo: `${await origin()}/auth/callback` },
  });
  if (error) return fail(error.message);
  if (data.session) redirect("/"); // email confirmation disabled in Supabase
  return ok("Check your inbox to confirm your email, then sign in.");
}

export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
