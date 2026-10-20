"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";
import { BotIcon, CheckIcon, Loader2Icon, PlusIcon, SendIcon, ShieldAlertIcon, XIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { AgentAnswer, Approval, ApprovalAction, TurnResult } from "@/lib/agent";
import { cn } from "@/lib/utils";
import { answerApproval, sendChatMessage, type ChatResult } from "./actions";

type Message =
  | { role: "user"; text: string }
  | { role: "agent"; text: string; answer?: AgentAnswer }
  | { role: "note"; text: string; tone?: "error" };

const SUGGESTIONS = [
  "How much filament is left on each spool?",
  "Do I have enough PETG for a 200 g print?",
  "When will my spools run out at my current pace?",
];

export function ChatView({
  threadId,
  history,
  pendingApproval,
  pendingQuestion,
  loadError,
}: {
  threadId: string;
  history: { question: string; answer: string }[];
  pendingApproval: Approval | null;
  pendingQuestion: string | null;
  loadError: string | null;
}) {
  const [messages, setMessages] = useState<Message[]>(() => [
    ...history.flatMap((t): Message[] => [
      { role: "user", text: t.question },
      { role: "agent", text: t.answer },
    ]),
    ...(pendingQuestion ? [{ role: "user" as const, text: pendingQuestion }] : []),
    ...(loadError ? [{ role: "note" as const, text: loadError, tone: "error" as const }] : []),
  ]);
  const [approval, setApproval] = useState<Approval | null>(pendingApproval);
  const [draft, setDraft] = useState("");
  const [busy, startTransition] = useTransition();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, approval, busy]);

  function apply(result: ChatResult, note?: string) {
    if (!result.ok) {
      setMessages((m) => [...m, { role: "note", text: result.error, tone: "error" }]);
      return;
    }
    const turn: TurnResult = result.turn;
    setMessages((m) => [
      ...m,
      ...(note ? [{ role: "note" as const, text: note }] : []),
      ...(turn.answer ? [{ role: "agent" as const, text: turn.answer.answer, answer: turn.answer }] : []),
    ]);
    setApproval(turn.status === "needs_approval" ? turn.approval : null);
  }

  function send(text: string) {
    const message = text.trim();
    if (!message || busy || approval) return;
    setDraft("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    // Keep the conversation in the URL so a reload picks it up again.
    if (!new URLSearchParams(window.location.search).has("thread")) {
      window.history.replaceState(null, "", `/chat?thread=${threadId}`);
    }
    startTransition(async () => apply(await sendChatMessage({ threadId, message })));
  }

  function decide(approved: boolean) {
    if (!approval || busy) return;
    const decisions = Object.fromEntries(approval.actions.map((a) => [a.id, approved]));
    startTransition(async () =>
      apply(
        await answerApproval({ threadId, decisions }),
        approved ? "You approved the change." : "You declined the change.",
      ),
    );
  }

  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Chat</h1>
        <Button variant="outline" size="sm" asChild>
          <Link href="/chat">
            <PlusIcon />
            New chat
          </Link>
        </Button>
      </div>

      <Card className="gap-0 py-0">
        <div className="flex max-h-[65svh] min-h-80 flex-col gap-4 overflow-y-auto p-4 sm:p-6">
          {messages.length === 0 && !approval && (
            <div className="text-muted-foreground m-auto grid max-w-md gap-4 text-center text-sm">
              <BotIcon className="mx-auto size-8" />
              <p>
                Ask about your spools and prints. The agent can also log prints and correct spool weights,
                but only after you approve each change.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} variant="secondary" size="sm" className="h-auto whitespace-normal py-1.5" onClick={() => send(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} />
          ))}

          {approval && <ApprovalCard approval={approval} busy={busy} onDecide={decide} />}

          {busy && (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader2Icon className="size-4 animate-spin" />
              Thinking…
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="flex items-end gap-2 border-t p-4"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send(draft);
              }
            }}
            placeholder={approval ? "Approve or decline the change first" : "Ask about your filament…"}
            aria-label="Message"
            maxLength={4000}
            rows={1}
            className="max-h-40 min-h-9 resize-none"
            disabled={!!approval}
          />
          <Button type="submit" size="icon" disabled={busy || !!approval || !draft.trim()} aria-label="Send">
            <SendIcon />
          </Button>
        </form>
      </Card>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === "note") {
    return message.tone === "error" ? (
      <Alert variant="destructive">
        <AlertDescription>{message.text}</AlertDescription>
      </Alert>
    ) : (
      <p className="text-muted-foreground text-center text-xs">{message.text}</p>
    );
  }
  const mine = message.role === "user";
  return (
    <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "grid max-w-[85%] gap-2 rounded-xl px-4 py-2.5 text-sm",
          mine ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
        {message.role === "agent" && message.answer && <AnswerChips answer={message.answer} />}
      </div>
    </div>
  );
}

const VERDICTS = {
  yes: { label: "Enough filament", variant: "success" },
  tight: { label: "Tight", variant: "warning" },
  no: { label: "Not enough", variant: "destructive" },
  unknown: { label: "Can't tell", variant: "outline" },
} as const;

function AnswerChips({ answer }: { answer: AgentAnswer }) {
  const verdict = answer.verdict === "not_applicable" ? null : VERDICTS[answer.verdict];
  const grams = [
    answer.grams_needed != null && `${answer.grams_needed} g needed`,
    answer.grams_available != null && `${answer.grams_available} g available`,
  ].filter(Boolean);
  if (!verdict && !answer.spool_ids.length && !grams.length && !answer.actions_taken.length) {
    return answer.confidence === "low" ? <LowConfidence /> : null;
  }
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {verdict && <Badge variant={verdict.variant}>{verdict.label}</Badge>}
        {answer.spool_ids.map((id) => (
          <Badge key={id} variant="outline" asChild>
            <Link href="/spools">Spool #{id}</Link>
          </Badge>
        ))}
        {grams.length > 0 && <span className="text-muted-foreground text-xs tabular-nums">{grams.join(" · ")}</span>}
        {answer.confidence === "low" && <LowConfidence />}
      </div>
      {answer.actions_taken.length > 0 && (
        <ul className="grid gap-1 text-xs">
          {answer.actions_taken.map((a) => (
            <li key={a} className="text-success flex items-center gap-1.5">
              <CheckIcon className="size-3.5" />
              {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LowConfidence() {
  return <span className="text-muted-foreground text-xs">Low confidence</span>;
}

function describe(action: ApprovalAction): string {
  const i = action.input;
  if (action.tool === "log_print") {
    return `Log a ${i.grams} g print "${i.title}" on slot ${i.slot}`;
  }
  if (action.tool === "correct_spool_weight") {
    return `Set spool #${i.spool_id} to ${i.measured_g} g remaining`;
  }
  const args = Object.entries(i)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return `${action.tool}(${args})`;
}

function ApprovalCard({
  approval,
  busy,
  onDecide,
}: {
  approval: Approval;
  busy: boolean;
  onDecide: (approved: boolean) => void;
}) {
  const many = approval.actions.length > 1;
  return (
    <Card className="border-warning/40 gap-4 py-4">
      <CardHeader className="px-4">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ShieldAlertIcon className="text-warning size-4" />
          {many ? "Approve these changes?" : "Approve this change?"}
        </CardTitle>
        <CardDescription>Nothing is changed until you approve.</CardDescription>
      </CardHeader>
      <CardContent className="px-4">
        <ul className="grid gap-1 text-sm">
          {approval.actions.map((a) => (
            <li key={a.id} className="bg-muted rounded-md px-3 py-2">
              {describe(a)}
              {typeof a.input.note === "string" && a.input.note && (
                <span className="text-muted-foreground"> · note: {a.input.note}</span>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
      <CardFooter className="gap-2 px-4">
        <Button size="sm" disabled={busy} onClick={() => onDecide(true)}>
          <CheckIcon />
          Approve
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onDecide(false)}>
          <XIcon />
          Decline
        </Button>
      </CardFooter>
    </Card>
  );
}
