import { notFound } from "next/navigation";

import { ColorDot } from "@/components/spool-ring";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getActiveSpool, getSettings } from "@/lib/data";
import { LoadSpoolForm } from "./load-form";

export default async function LoadSpoolPage({ params }: PageProps<"/spools/load/[slot]">) {
  const slot = Number((await params).slot);
  const settings = await getSettings();
  if (!Number.isInteger(slot) || slot < 1 || slot > settings.slot_count) notFound();
  const current = await getActiveSpool(slot);

  return (
    <div className="mx-auto grid max-w-xl gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        {current ? "Change" : "Load"} spool · slot {slot}
      </h1>

      {current && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ColorDot color={current.color} /> {current.material}
              {current.brand && <span className="text-muted-foreground font-normal">· {current.brand}</span>}
            </CardTitle>
            <CardDescription>
              Current spool, will be archived: {current.remaining_g} g left of {Math.round(current.initial_g)} g ·{" "}
              {current.print_count} print{current.print_count === 1 ? "" : "s"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Progress value={current.pct_left} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>New spool</CardTitle>
          <CardDescription>
            Prints that start after now are counted against this spool.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoadSpoolForm slot={slot} hasCurrent={!!current} />
        </CardContent>
      </Card>
    </div>
  );
}
