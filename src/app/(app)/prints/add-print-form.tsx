"use client";

import { PlusIcon } from "lucide-react";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { addPrint } from "../actions";

export function AddPrintForm({ slotCount }: { slotCount: number }) {
  return (
    <ActionForm action={addPrint} resetOnSuccess className="grid gap-4 sm:grid-cols-[1fr_9rem_7rem_auto] sm:items-end">
      <div className="grid gap-2">
        <Label htmlFor="title">Name</Label>
        <Input id="title" name="title" placeholder="Benchy" maxLength={120} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="weight">Filament (g)</Label>
        <Input id="weight" name="weight" type="number" min={0.1} step={0.1} required />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="slot">Slot</Label>
        <NativeSelect id="slot" name="slot" defaultValue="1">
          {Array.from({ length: slotCount }, (_, i) => (
            <option key={i + 1} value={i + 1}>
              {i + 1}
            </option>
          ))}
        </NativeSelect>
      </div>
      <SubmitButton>
        <PlusIcon /> Add
      </SubmitButton>
    </ActionForm>
  );
}
