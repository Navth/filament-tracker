"use client";

import { useActionState, useEffect, useRef, type ReactNode } from "react";
import { toast } from "sonner";

import { idle, type ActionResult } from "@/lib/action-result";
import { cn } from "@/lib/utils";

type Action = (prev: ActionResult, formData: FormData) => Promise<ActionResult>;

/**
 * A <form> wired to a server action. Shows the action's message as a toast
 * and exposes `pending` / the latest result to its children.
 */
export function ActionForm({
  action,
  children,
  className,
  resetOnSuccess = false,
  silentSuccess = false,
  onResult,
}: {
  action: Action;
  children: ReactNode | ((state: { pending: boolean; result: ActionResult }) => ReactNode);
  className?: string;
  resetOnSuccess?: boolean;
  silentSuccess?: boolean;
  onResult?: (result: ActionResult) => void;
}) {
  const [result, formAction, pending] = useActionState(action, idle);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!result.at) return;
    if (!result.ok) toast.error(result.message ?? "Something went wrong");
    else if (result.message && !silentSuccess) toast.success(result.message);
    if (result.ok && resetOnSuccess) formRef.current?.reset();
    onResult?.(result);
    // Only react to new results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.at]);

  return (
    <form ref={formRef} action={formAction} className={cn(className)}>
      {typeof children === "function" ? children({ pending, result }) : children}
    </form>
  );
}
