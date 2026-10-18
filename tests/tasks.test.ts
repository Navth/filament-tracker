import { describe, expect, it } from "vitest";

import { amsEntries, tasksToRows } from "@/lib/bambu/tasks";

const done = { startTime: "2026-02-01T10:00:00Z", endTime: "2026-02-01T11:00:00Z" };

describe("tasksToRows", () => {
  it("skips jobs that are still printing", () => {
    const rows = tasksToRows([{ id: 1, weight: 10, startTime: "2026-02-01T10:00:00Z" }], 1);
    expect(rows).toEqual([]);
  });

  it("maps a finished job to one slot-1 row", () => {
    const [row] = tasksToRows([{ id: 42, title: "Benchy", weight: 12.5, status: 2, deviceId: "X1", ...done }], 1);
    expect(row).toEqual({
      task_key: "42",
      title: "Benchy",
      device_id: "X1",
      status: 2,
      start_time: done.startTime,
      end_time: done.endTime,
      weight: 12.5,
      slot: 1,
    });
  });

  it("splits multi-material jobs per AMS slot when several slots are configured", () => {
    const task = {
      id: 7,
      weight: 30,
      amsDetailMapping: [
        { ams: 0, weight: 20 },
        { ams: 2, weight: 10 },
      ],
      ...done,
    };
    const rows = tasksToRows([task], 4);
    expect(rows.map((r) => [r.task_key, r.slot, r.weight])).toEqual([
      ["7-s1", 1, 20],
      ["7-s3", 3, 10],
    ]);
  });

  it("ignores AMS data when only one slot is configured", () => {
    const task = { id: 7, weight: 30, amsDetailMapping: [{ ams: 2, weight: 30 }], ...done };
    expect(tasksToRows([task], 1)).toMatchObject([{ task_key: "7", slot: 1, weight: 30 }]);
  });

  it("drops duplicate task keys", () => {
    const rows = tasksToRows([{ id: 1, weight: 5, ...done }, { id: 1, weight: 6, ...done }], 1);
    expect(rows).toHaveLength(1);
    expect(rows[0].weight).toBe(6);
  });

  it("defaults missing titles and weights", () => {
    expect(tasksToRows([{ id: 3, ...done }], 1)[0]).toMatchObject({ title: "Untitled", weight: 0 });
  });
});

describe("amsEntries", () => {
  it("keeps only valid AMS slots 0-3 with positive grams", () => {
    expect(
      amsEntries({
        id: 1,
        amsDetailMapping: [
          { ams: 0, weight: 5 },
          { ams: 4, weight: 5 },
          { ams: 1, weight: 0 },
          { weight: 3 },
          { ams: 3, weight: 2.5 },
        ],
      }),
    ).toEqual([
      { slot: 1, grams: 5 },
      { slot: 4, grams: 2.5 },
    ]);
  });
});
