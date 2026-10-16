"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { reassignPrint, togglePrint } from "../actions";

export type SpoolOption = { id: number; label: string };

export function CountedToggle({ printId, counted }: { printId: number; counted: boolean }) {
  const [pending, start] = useTransition();
  return (
    <Button
      size="sm"
      variant={counted ? "secondary" : "outline"}
      disabled={pending}
      title={counted ? "Counted against the spool. Click to ignore (e.g. failed print)" : "Ignored. Click to count it"}
      onClick={() =>
        start(async () => {
          const r = await togglePrint(printId, !counted);
          if (!r.ok) toast.error(r.message);
        })
      }
    >
      {counted ? "Counted" : "Ignored"}
    </Button>
  );
}

export function SpoolPicker({
  printId,
  spoolId,
  options,
}: {
  printId: number;
  spoolId: number | null;
  options: SpoolOption[];
}) {
  const [pending, start] = useTransition();
  return (
    <NativeSelect
      aria-label="Assign to spool"
      className="h-8 min-w-44 text-xs"
      value={spoolId ?? ""}
      disabled={pending}
      onChange={(e) => {
        const value = e.target.value ? Number(e.target.value) : null;
        start(async () => {
          const r = await reassignPrint(printId, value);
          if (!r.ok) toast.error(r.message);
        });
      }}
    >
      <option value="">Unassigned</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </NativeSelect>
  );
}
