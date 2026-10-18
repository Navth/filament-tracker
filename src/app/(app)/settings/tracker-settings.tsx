"use client";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { saveSettings } from "../actions";

export function TrackerSettings({
  slotCount,
  deviceId,
  devices,
}: {
  slotCount: number;
  deviceId: string;
  devices: { id: string; name: string }[];
}) {
  return (
    <ActionForm action={saveSettings} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="slot_count">Spool slots</Label>
          <NativeSelect id="slot_count" name="slot_count" defaultValue={String(slotCount)}>
            <option value="1">1 · single external spool</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4 · full AMS Lite</option>
          </NativeSelect>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="device_id">Printer</Label>
          {devices.length ? (
            <NativeSelect id="device_id" name="device_id" defaultValue={deviceId}>
              <option value="">All my printers</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </NativeSelect>
          ) : (
            <Input id="device_id" name="device_id" defaultValue={deviceId} placeholder="Serial number (optional)" />
          )}
        </div>
      </div>
      <div>
        <SubmitButton>Save</SubmitButton>
      </div>
    </ActionForm>
  );
}
