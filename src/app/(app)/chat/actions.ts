"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { AgentError, approveAgent, askAgent, type TurnResult } from "@/lib/agent";

/**
 * Chat server actions. They forward to the agent service with the user's
 * own Supabase session; the agent decides nothing based on what the browser
 * claims about who the user is.
 */

export type ChatResult = { ok: true; turn: TurnResult } | { ok: false; error: string };

const threadId = z.string().regex(/^[A-Za-z0-9_-]{1,64}$/);

function failure(e: unknown): ChatResult {
  if (e instanceof AgentError) return { ok: false, error: e.message };
  console.error("chat action failed", e);
  return { ok: false, error: "Something went wrong talking to the agent." };
}

const askSchema = z.object({ threadId, message: z.string().trim().min(1).max(4000) });

export async function sendChatMessage(input: { threadId: string; message: string }): Promise<ChatResult> {
  const parsed = askSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: "Type a message (up to 4000 characters)." };
  try {
    return { ok: true, turn: await askAgent(parsed.data.threadId, parsed.data.message) };
  } catch (e) {
    return failure(e);
  }
}

const approveSchema = z.object({ threadId, decisions: z.record(z.string().max(128), z.boolean()) });

export async function answerApproval(input: {
  threadId: string;
  decisions: Record<string, boolean>;
}): Promise<ChatResult> {
  const parsed = approveSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: "Invalid approval." };
  try {
    const turn = await approveAgent(parsed.data.threadId, parsed.data.decisions);
    if (Object.values(parsed.data.decisions).some(Boolean)) {
      // An approved change may have touched spools or prints shown elsewhere.
      revalidatePath("/", "layout");
    }
    return { ok: true, turn };
  } catch (e) {
    return failure(e);
  }
}
