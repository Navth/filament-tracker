import "server-only";

import { getUser } from "@/lib/data";
import { env } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * Client for the chat agent service (agent/, `ft-agent serve`). Requests
 * carry the signed-in user's Supabase access token; the agent verifies it
 * and reads and writes with it, so RLS applies there as it does here.
 */

export type Verdict = "yes" | "tight" | "no" | "not_applicable" | "unknown";

export type AgentAnswer = {
  answer: string;
  verdict: Verdict;
  grams_needed: number | null;
  grams_available: number | null;
  spool_ids: number[];
  actions_taken: string[];
  confidence: "high" | "medium" | "low";
};

export type ApprovalAction = { id: string; tool: string; input: Record<string, unknown> };
export type Approval = { type: "approval"; actions: ApprovalAction[] };

export type TurnResult = {
  status: "answered" | "needs_approval";
  answer: AgentAnswer | null;
  approval: Approval | null;
};

export type ThreadState = {
  thread_id: string;
  history: { question: string; answer: string }[];
  pending_approval: Approval | null;
  pending_question: string | null;
};

export class AgentError extends Error {}

export function agentConfigured(): boolean {
  return !!env.agentUrl;
}

async function accessToken(): Promise<string> {
  await getUser();
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new AgentError("Your session expired. Sign in again.");
  return token;
}

async function call<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const base = env.agentUrl;
  if (!base) throw new AgentError("The chat agent isn't configured (AGENT_URL).");
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method: init?.method ?? "GET",
      headers: {
        Authorization: `Bearer ${await accessToken()}`,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
      body: init?.body ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
      // Agent turns can take a while (several model and tool calls).
      signal: AbortSignal.timeout(120_000),
    });
  } catch (e) {
    if (e instanceof AgentError) throw e;
    throw new AgentError("Couldn't reach the chat agent. Try again in a moment.");
  }
  const data = (await res.json().catch(() => null)) as (T & { error?: string }) | null;
  if (!res.ok || !data) {
    throw new AgentError(data?.error ?? `The chat agent returned an error (${res.status}).`);
  }
  return data;
}

export function askAgent(threadId: string, message: string) {
  return call<TurnResult>("/chat", { method: "POST", body: { thread_id: threadId, message } });
}

export function approveAgent(threadId: string, decisions: Record<string, boolean>) {
  return call<TurnResult>("/chat/approve", { method: "POST", body: { thread_id: threadId, decisions } });
}

export function getThread(threadId: string) {
  return call<ThreadState>(`/chat/${encodeURIComponent(threadId)}`);
}
