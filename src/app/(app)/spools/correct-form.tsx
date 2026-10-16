"use client";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { Input } from "@/components/ui/input";
import { correctSpool } from "../actions";

/** Enter the weighed grams left; the server records the difference. */
export function CorrectForm({ spoolId }: { spoolId: number }) {
  return (
    <ActionForm action={correctSpool} resetOnSuccess className="flex items-center gap-2">
      <input type="hidden" name="spool_id" value={spoolId} />
      <Input
        name="remaining_g"
        type="number"
        min={0}
        step={0.1}
        placeholder="Weighed g"
        aria-label="Grams left after weighing"
        className="h-8 w-28"
        required
      />
      <SubmitButton size="sm" variant="outline">
        Set
      </SubmitButton>
    </ActionForm>
  );
}
