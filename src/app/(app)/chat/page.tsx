import { randomUUID } from "node:crypto";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { agentConfigured, AgentError, getThread, type ThreadState } from "@/lib/agent";
import { ChatView } from "./chat-view";

const THREAD_ID = /^[A-Za-z0-9_-]{1,64}$/;

export default async function ChatPage({ searchParams }: { searchParams: Promise<{ thread?: string }> }) {
  if (!agentConfigured()) {
    return (
      <div className="grid gap-6">
        <h1 className="text-2xl font-semibold tracking-tight">Chat</h1>
        <Alert>
          <AlertTitle>The chat agent isn&apos;t set up</AlertTitle>
          <AlertDescription>
            Run the agent service (see agent/README.md) and set AGENT_URL to its address.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const { thread } = await searchParams;
  const existing = thread && THREAD_ID.test(thread) ? thread : null;
  let state: ThreadState | null = null;
  let loadError: string | null = null;
  if (existing) {
    try {
      state = await getThread(existing);
    } catch (e) {
      loadError = e instanceof AgentError ? e.message : "Couldn't load this conversation.";
    }
  }
  const threadId = existing ?? randomUUID();

  return (
    <ChatView
      key={threadId}
      threadId={threadId}
      history={state?.history ?? []}
      pendingApproval={state?.pending_approval ?? null}
      pendingQuestion={state?.pending_question ?? null}
      loadError={loadError}
    />
  );
}
