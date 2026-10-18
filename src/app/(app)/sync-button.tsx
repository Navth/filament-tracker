"use client";

import { RefreshCwIcon } from "lucide-react";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { syncPrints } from "./actions";

export function SyncButton({ disabled }: { disabled?: boolean }) {
  return (
    <ActionForm action={syncPrints}>
      <SubmitButton disabled={disabled}>
        <RefreshCwIcon />
        Sync prints
      </SubmitButton>
    </ActionForm>
  );
}
