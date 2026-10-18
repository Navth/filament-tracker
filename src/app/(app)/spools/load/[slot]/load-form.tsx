"use client";

import Link from "next/link";
import { useState } from "react";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { loadSpool } from "../../../actions";

const MATERIALS = ["PLA", "PLA Matte", "PLA Silk", "PLA-CF", "PETG", "PETG HF", "TPU", "ABS", "ASA", "Other"];
const SIZES = [250, 500, 750, 1000, 2000];

export function LoadSpoolForm({ slot, hasCurrent }: { slot: number; hasCurrent: boolean }) {
  const [grams, setGrams] = useState("1000");
  return (
    <ActionForm action={loadSpool} className="grid gap-5">
      <input type="hidden" name="slot" value={slot} />
      <div className="grid gap-2">
        <Label htmlFor="initial_g">Filament on the spool (g)</Label>
        <Input
          id="initial_g"
          name="initial_g"
          type="number"
          min={1}
          step={1}
          value={grams}
          onChange={(e) => setGrams(e.target.value)}
          required
        />
        <div className="flex flex-wrap gap-2">
          {SIZES.map((g) => (
            <Button
              key={g}
              type="button"
              size="sm"
              variant={grams === String(g) ? "secondary" : "outline"}
              onClick={() => setGrams(String(g))}
            >
              {g >= 1000 ? `${g / 1000} kg` : `${g} g`}
            </Button>
          ))}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <div className="grid gap-2">
          <Label htmlFor="material">Material</Label>
          <NativeSelect id="material" name="material" defaultValue="PLA">
            {MATERIALS.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="color">Colour</Label>
          <Input id="color" name="color" type="color" defaultValue="#22aa55" className="h-9 w-20 p-1" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="brand">Brand</Label>
          <Input id="brand" name="brand" placeholder="Bambu, Sunlu, eSun…" maxLength={60} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="note">Note</Label>
          <Input id="note" name="note" placeholder="Batch, purchase date…" maxLength={200} />
        </div>
      </div>
      <div className="flex gap-2">
        <SubmitButton>{hasCurrent ? "Swap spool" : "Load spool"}</SubmitButton>
        <Button asChild variant="ghost">
          <Link href="/">Cancel</Link>
        </Button>
      </div>
    </ActionForm>
  );
}
