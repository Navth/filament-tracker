"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { fail, ok, type ActionResult } from "@/lib/action-result";
import { BambuCloud, BambuCloudError, NeedsVerifyCode } from "@/lib/bambu/client";
import { tasksToRows } from "@/lib/bambu/tasks";
import { encryptSecret } from "@/lib/crypto";
import {
  addManualPrint,
  assignPrint,
  changeSpool,
  getBambuClient,
  getSettings,
  getUser,
  importPrints,
  setPrintCounted,
  setRemaining,
  updateSettings,
} from "@/lib/data";

/**
 * Server actions. Each one re-checks the user (via the data layer) and
 * validates its input; never trust what the form sends.
 */

function errorMessage(e: unknown): string {
  if (e instanceof BambuCloudError) return e.message;
  if (e && typeof e === "object" && "message" in e && typeof e.message === "string") {
    return e.message;
  }
  return "Something went wrong";
}

function refreshAll() {
  revalidatePath("/", "layout");
}

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

// ---------------------------------------------------------------- sync

export async function syncPrints(): Promise<ActionResult> {
  try {
    const settings = await getSettings();
    if (!settings.connected) return fail("Connect your Bambu account in Settings first.");
    const bambu = await getBambuClient();
    const tasks = await bambu.getTasks(settings.device_id || undefined, 100);
    const rows = tasksToRows(tasks, settings.slot_count);
    const { inserted } = await importPrints(rows);
    refreshAll();
    return ok(inserted ? `Imported ${inserted} new print${inserted === 1 ? "" : "s"}.` : "Already up to date.");
  } catch (e) {
    return fail(errorMessage(e));
  }
}

// ---------------------------------------------------------------- settings

const settingsSchema = z.object({
  slot_count: z.coerce.number().int().min(1).max(4),
  device_id: z.string().trim().max(64).default(""),
});

export async function saveSettings(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = settingsSchema.safeParse({
    slot_count: form.get("slot_count"),
    device_id: form.get("device_id") ?? "",
  });
  if (!parsed.success) return fail("Check the settings and try again.");
  try {
    await updateSettings(parsed.data);
    refreshAll();
    return ok("Settings saved.");
  } catch (e) {
    return fail(errorMessage(e));
  }
}

const loginSchema = z.object({
  email: z.string().trim().email(),
  password: z.string().min(1),
  region: z.enum(["global", "china"]),
});

export async function bambuLogin(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = loginSchema.safeParse({
    email: form.get("email"),
    password: form.get("password"),
    region: form.get("region") ?? "global",
  });
  if (!parsed.success) return fail("Enter your Bambu email and password.");
  const { email, password, region } = parsed.data;
  try {
    await getUser();
    await updateSettings({ bambu_email: email, bambu_region: region });
    const token = await new BambuCloud(region).login(email, password);
    await updateSettings({ bambu_token_enc: encryptSecret(token) });
    refreshAll();
    return ok("Connected to Bambu Cloud.");
  } catch (e) {
    if (e instanceof NeedsVerifyCode) {
      return ok("Bambu emailed you a 6-digit code.", { next: "verify-code" });
    }
    return fail(errorMessage(e));
  }
}

const codeSchema = z.object({ code: z.string().trim().regex(/^\d{6}$/) });

export async function bambuVerify(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = codeSchema.safeParse({ code: form.get("code") });
  if (!parsed.success) return { ...fail("Enter the 6-digit code."), next: "verify-code" };
  try {
    const settings = await getSettings();
    if (!settings.bambu_email) return fail("Start the Bambu login again.");
    const token = await new BambuCloud(settings.bambu_region).loginWithCode(
      settings.bambu_email,
      parsed.data.code,
    );
    await updateSettings({ bambu_token_enc: encryptSecret(token) });
    refreshAll();
    return ok("Connected to Bambu Cloud.");
  } catch (e) {
    return { ...fail(errorMessage(e)), next: "verify-code" };
  }
}

export async function bambuDisconnect(): Promise<ActionResult> {
  try {
    await updateSettings({ bambu_token_enc: null });
    refreshAll();
    return ok("Disconnected from Bambu Cloud.");
  } catch (e) {
    return fail(errorMessage(e));
  }
}

// ---------------------------------------------------------------- spools

const spoolSchema = z.object({
  slot: z.coerce.number().int().min(1).max(4),
  initial_g: z.coerce.number().positive().max(100_000),
  material: z.string().trim().min(1).max(40),
  color: z.string().regex(HEX_COLOR).or(z.literal("")),
  brand: z.string().trim().max(60).default(""),
  note: z.string().trim().max(200).default(""),
});

export async function loadSpool(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = spoolSchema.safeParse({
    slot: form.get("slot"),
    initial_g: form.get("initial_g"),
    material: form.get("material"),
    color: form.get("color") ?? "",
    brand: form.get("brand") ?? "",
    note: form.get("note") ?? "",
  });
  if (!parsed.success) return fail("Check the spool details and try again.");
  try {
    const settings = await getSettings();
    if (parsed.data.slot > settings.slot_count) return fail("That slot isn't enabled in Settings.");
    await changeSpool(parsed.data);
  } catch (e) {
    return fail(errorMessage(e));
  }
  refreshAll();
  redirect("/?loaded=" + parsed.data.slot);
}

const adjustSchema = z.object({
  spool_id: z.coerce.number().int().positive(),
  remaining_g: z.coerce.number().min(0).max(100_000),
});

export async function correctSpool(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = adjustSchema.safeParse({
    spool_id: form.get("spool_id"),
    remaining_g: form.get("remaining_g"),
  });
  if (!parsed.success) return fail("Enter the weighed grams left on the spool.");
  try {
    const diff = await setRemaining(parsed.data.spool_id, parsed.data.remaining_g);
    refreshAll();
    return ok(diff === 0 ? "Already matches." : `Corrected by ${diff > 0 ? "−" : "+"}${Math.abs(diff)} g.`);
  } catch (e) {
    return fail(errorMessage(e));
  }
}

// ---------------------------------------------------------------- prints

const manualSchema = z.object({
  title: z.string().trim().max(120).default(""),
  weight: z.coerce.number().positive().max(10_000),
  slot: z.coerce.number().int().min(1).max(4),
});

export async function addPrint(_: ActionResult, form: FormData): Promise<ActionResult> {
  const parsed = manualSchema.safeParse({
    title: form.get("title") ?? "",
    weight: form.get("weight"),
    slot: form.get("slot") ?? 1,
  });
  if (!parsed.success) return fail("Enter the filament used in grams.");
  try {
    await addManualPrint(parsed.data.title, parsed.data.weight, parsed.data.slot);
    refreshAll();
    return ok("Print added.");
  } catch (e) {
    return fail(errorMessage(e));
  }
}

export async function togglePrint(printId: number, counted: boolean): Promise<ActionResult> {
  const id = z.number().int().positive().safeParse(printId);
  if (!id.success) return fail("Invalid print");
  try {
    await setPrintCounted(id.data, counted);
    refreshAll();
    return ok();
  } catch (e) {
    return fail(errorMessage(e));
  }
}

export async function reassignPrint(printId: number, spoolId: number | null): Promise<ActionResult> {
  const parsed = z
    .object({ printId: z.number().int().positive(), spoolId: z.number().int().positive().nullable() })
    .safeParse({ printId, spoolId });
  if (!parsed.success) return fail("Invalid selection");
  try {
    await assignPrint(parsed.data.printId, parsed.data.spoolId);
    refreshAll();
    return ok();
  } catch (e) {
    return fail(errorMessage(e));
  }
}
