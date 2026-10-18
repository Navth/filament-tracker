import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";

import { BambuCloud, type BambuRegion } from "@/lib/bambu/client";
import { decryptSecret } from "@/lib/crypto";
import { isEmailAllowed } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * Data access layer. Every read and write in the app goes through here, and
 * every function starts by establishing who the user is. Queries run with
 * the user's own session, so Postgres RLS is the final gatekeeper.
 *
 * The AI agent (phase 2) will call these same functions as its tools.
 */

export type User = { id: string; email: string };

export type Settings = {
  slot_count: number;
  device_id: string;
  bambu_email: string;
  bambu_region: BambuRegion;
  connected: boolean;
  last_sync: string | null;
};

export type SpoolStats = {
  id: number;
  slot: number;
  brand: string;
  material: string;
  color: string;
  initial_g: number;
  note: string;
  started_at: string;
  ended_at: string | null;
  active: boolean;
  used_g: number;
  remaining_g: number;
  print_count: number;
  pct_left: number;
};

export type Print = {
  id: number;
  task_key: string | null;
  title: string;
  status: number | null;
  start_time: string | null;
  end_time: string | null;
  weight: number;
  slot: number;
  spool_id: number | null;
  counted: boolean;
  source: "cloud" | "manual";
  spool: { color: string; material: string; slot: number } | null;
};

/** The signed-in user, verified against Supabase Auth. Redirects if absent. */
export const getUser = cache(async (): Promise<User> => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (!claims?.sub) redirect("/login");
  const email = typeof claims.email === "string" ? claims.email : "";
  if (!isEmailAllowed(email)) {
    await supabase.auth.signOut();
    redirect("/login?error=not-allowed");
  }
  return { id: claims.sub, email };
});

/** A Supabase client for the verified user. */
export async function db() {
  await getUser();
  return createClient();
}

function num(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function toSpool(row: Record<string, unknown>): SpoolStats {
  const initial = num(row.initial_g);
  const remaining = num(row.remaining_g);
  return {
    id: num(row.id),
    slot: num(row.slot),
    brand: String(row.brand ?? ""),
    material: String(row.material ?? ""),
    color: String(row.color ?? ""),
    initial_g: initial,
    note: String(row.note ?? ""),
    started_at: String(row.started_at ?? ""),
    ended_at: (row.ended_at as string | null) ?? null,
    active: Boolean(row.active),
    used_g: num(row.used_g),
    remaining_g: remaining,
    print_count: num(row.print_count),
    pct_left: initial > 0 ? Math.max(0, Math.min(100, Math.round((remaining / initial) * 100))) : 0,
  };
}

function toPrint(row: Record<string, unknown>): Print {
  const spool = row.spool as Record<string, unknown> | null;
  return {
    id: num(row.id),
    task_key: (row.task_key as string | null) ?? null,
    title: String(row.title ?? "Untitled"),
    status: row.status === null || row.status === undefined ? null : num(row.status),
    start_time: (row.start_time as string | null) ?? null,
    end_time: (row.end_time as string | null) ?? null,
    weight: num(row.weight),
    slot: num(row.slot),
    spool_id: row.spool_id === null || row.spool_id === undefined ? null : num(row.spool_id),
    counted: Boolean(row.counted),
    source: row.source === "manual" ? "manual" : "cloud",
    spool: spool
      ? { color: String(spool.color ?? ""), material: String(spool.material ?? ""), slot: num(spool.slot) }
      : null,
  };
}

// ---------------------------------------------------------------- settings

export const getSettings = cache(async (): Promise<Settings> => {
  const supabase = await db();
  const cols = "slot_count, device_id, bambu_email, bambu_region, bambu_token_enc, last_sync";
  const first = await supabase.from("user_settings").select(cols).maybeSingle();
  if (first.error) throw first.error;
  let data = first.data;
  if (!data) {
    // First visit: create the row (user_id defaults to auth.uid()).
    const created = await supabase.from("user_settings").upsert({ slot_count: 1 }, { onConflict: "user_id", ignoreDuplicates: true }).select(cols).maybeSingle();
    if (created.error) throw created.error;
    data = created.data ?? (await supabase.from("user_settings").select(cols).single()).data;
  }
  return {
    slot_count: num(data?.slot_count) || 1,
    device_id: String(data?.device_id ?? ""),
    bambu_email: String(data?.bambu_email ?? ""),
    bambu_region: data?.bambu_region === "china" ? "china" : "global",
    connected: Boolean(data?.bambu_token_enc),
    last_sync: (data?.last_sync as string | null) ?? null,
  };
});

export async function updateSettings(patch: Partial<{
  slot_count: number;
  device_id: string;
  bambu_email: string;
  bambu_region: BambuRegion;
  bambu_token_enc: string | null;
}>) {
  await getSettings(); // make sure the row exists
  const supabase = await db();
  const { id } = await getUser();
  const { error } = await supabase.from("user_settings").update(patch).eq("user_id", id);
  if (error) throw error;
}

/** Bambu Cloud client using the user's decrypted token (server-only). */
export async function getBambuClient(): Promise<BambuCloud> {
  const supabase = await db();
  const { data, error } = await supabase
    .from("user_settings")
    .select("bambu_region, bambu_token_enc")
    .maybeSingle();
  if (error) throw error;
  const region: BambuRegion = data?.bambu_region === "china" ? "china" : "global";
  const token = data?.bambu_token_enc ? decryptSecret(String(data.bambu_token_enc)) : undefined;
  return new BambuCloud(region, token);
}

// ---------------------------------------------------------------- spools

export async function getSpools(): Promise<SpoolStats[]> {
  const supabase = await db();
  const { data, error } = await supabase
    .from("spool_stats")
    .select("*")
    .order("active", { ascending: false })
    .order("id", { ascending: false });
  if (error) throw error;
  return (data ?? []).map(toSpool);
}

export type SlotView = { slot: number; spool: SpoolStats | null };

/** One entry per configured slot with its active spool (or null). */
export async function getSlots(): Promise<SlotView[]> {
  const settings = await getSettings();
  const supabase = await db();
  const { data, error } = await supabase.from("spool_stats").select("*").eq("active", true);
  if (error) throw error;
  const active = (data ?? []).map(toSpool);
  return Array.from({ length: settings.slot_count }, (_, i) => ({
    slot: i + 1,
    spool: active.find((s) => s.slot === i + 1) ?? null,
  }));
}

export async function getActiveSpool(slot: number): Promise<SpoolStats | null> {
  const supabase = await db();
  const { data, error } = await supabase
    .from("spool_stats")
    .select("*")
    .eq("active", true)
    .eq("slot", slot)
    .maybeSingle();
  if (error) throw error;
  return data ? toSpool(data) : null;
}

export async function changeSpool(input: {
  slot: number;
  initial_g: number;
  material: string;
  color: string;
  brand: string;
  note: string;
}): Promise<number> {
  const supabase = await db();
  const { data, error } = await supabase.rpc("change_spool", {
    p_slot: input.slot,
    p_initial_g: input.initial_g,
    p_material: input.material,
    p_color: input.color,
    p_brand: input.brand,
    p_note: input.note,
  });
  if (error) throw error;
  return num(data);
}

export async function setRemaining(spoolId: number, measuredG: number, note?: string) {
  const supabase = await db();
  const { data, error } = await supabase.rpc("set_remaining", {
    p_spool_id: spoolId,
    p_measured_g: measuredG,
    p_note: note ?? "manual correction",
  });
  if (error) throw error;
  return num(data);
}

// ---------------------------------------------------------------- prints

const PRINT_COLS = "*, spool:spools(color, material, slot)";

export async function getPrints(limit = 200): Promise<Print[]> {
  const supabase = await db();
  const { data, error } = await supabase
    .from("prints")
    .select(PRINT_COLS)
    .order("start_time", { ascending: false, nullsFirst: false })
    .order("id", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return (data ?? []).map(toPrint);
}

export async function getUnassignedCount(): Promise<number> {
  const supabase = await db();
  const { count, error } = await supabase
    .from("prints")
    .select("id", { count: "exact", head: true })
    .is("spool_id", null)
    .eq("counted", true);
  if (error) throw error;
  return count ?? 0;
}

export async function addManualPrint(title: string, weight: number, slot: number) {
  const spool = await getActiveSpool(slot);
  const supabase = await db();
  const { error } = await supabase.from("prints").insert({
    title: title || "Manual entry",
    weight,
    slot,
    spool_id: spool?.id ?? null,
    start_time: new Date().toISOString(),
    source: "manual",
  });
  if (error) throw error;
}

export async function setPrintCounted(printId: number, counted: boolean) {
  const supabase = await db();
  const { error } = await supabase.from("prints").update({ counted }).eq("id", printId);
  if (error) throw error;
}

export async function assignPrint(printId: number, spoolId: number | null) {
  const supabase = await db();
  const { error } = await supabase.from("prints").update({ spool_id: spoolId }).eq("id", printId);
  if (error) throw error;
}

export async function importPrints(rows: unknown[]): Promise<{ inserted: number; updated: number }> {
  const supabase = await db();
  const { data, error } = await supabase.rpc("import_prints", { p_rows: rows });
  if (error) throw error;
  const r = (Array.isArray(data) ? data[0] : data) as Record<string, unknown> | null;
  return { inserted: num(r?.inserted), updated: num(r?.updated) };
}
