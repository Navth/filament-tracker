import type { BambuTask } from "./client";

/** One row for the import_prints() database function. */
export type PrintRow = {
  task_key: string;
  title: string;
  device_id: string | null;
  status: number | null;
  start_time: string | null;
  end_time: string | null;
  weight: number;
  slot: number;
};

/** Per-AMS-slot (slot, grams) pairs, if the task carries usable AMS data. */
export function amsEntries(task: BambuTask): { slot: number; grams: number }[] {
  const out: { slot: number; grams: number }[] = [];
  for (const m of task.amsDetailMapping ?? []) {
    const grams = Number(m.weight ?? 0);
    const ams = m.ams;
    if (grams > 0 && ams !== undefined && ams !== null && ams >= 0 && ams <= 3) {
      out.push({ slot: Number(ams) + 1, grams });
    }
  }
  return out;
}

/**
 * Turn Bambu Cloud tasks into rows to import.
 *
 * - Jobs still printing (no end time) are skipped; they're imported on a
 *   later sync, so a job at 0% isn't charged its full estimate.
 * - With more than one slot configured, multi-material jobs are split per
 *   AMS slot (task key gets a "-s<slot>" suffix).
 * - Duplicate keys are dropped (a single upsert can't touch a row twice).
 */
export function tasksToRows(tasks: BambuTask[], slotCount: number): PrintRow[] {
  const rows = new Map<string, PrintRow>();
  for (const t of tasks) {
    if (!t.endTime) continue;
    const base = {
      title: t.title || "Untitled",
      device_id: t.deviceId ?? null,
      status: t.status ?? null,
      start_time: t.startTime || null,
      end_time: t.endTime || null,
    };
    const perSlot = slotCount > 1 ? amsEntries(t) : [];
    if (perSlot.length > 0) {
      for (const { slot, grams } of perSlot) {
        const key = `${t.id}-s${slot}`;
        rows.set(key, { ...base, task_key: key, slot, weight: grams });
      }
    } else {
      const key = String(t.id);
      rows.set(key, { ...base, task_key: key, slot: 1, weight: Number(t.weight ?? 0) });
    }
  }
  return [...rows.values()];
}
