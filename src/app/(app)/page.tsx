import Link from "next/link";
import { AlertTriangleIcon, CloudIcon, CloudOffIcon, PlusIcon } from "lucide-react";

import { LocalTime } from "@/components/local-time";
import { PrintsTable } from "@/components/prints-table";
import { ColorDot, SpoolRing } from "@/components/spool-ring";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getPrints, getSettings, getSlots, getUnassignedCount, type SlotView } from "@/lib/data";
import { SyncButton } from "./sync-button";

export default async function DashboardPage() {
  const [settings, slots, recent, unassigned] = await Promise.all([
    getSettings(),
    getSlots(),
    getPrints(10),
    getUnassignedCount(),
  ]);

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground flex items-center gap-2 text-sm">
            {settings.connected ? (
              <>
                <CloudIcon className="size-4 text-primary" /> Bambu Cloud connected
                {settings.last_sync && (
                  <>
                    {" · last sync "}
                    <LocalTime iso={settings.last_sync} />
                  </>
                )}
              </>
            ) : (
              <>
                <CloudOffIcon className="size-4" /> Not connected —{" "}
                <Link href="/settings" className="text-primary underline underline-offset-4">
                  connect Bambu Cloud
                </Link>
              </>
            )}
          </p>
        </div>
        <SyncButton disabled={!settings.connected} />
      </div>

      {unassigned > 0 && (
        <Alert variant="warning">
          <AlertTriangleIcon />
          <AlertTitle>
            {unassigned} print{unassigned === 1 ? " isn't" : "s aren't"} assigned to a spool
          </AlertTitle>
          <AlertDescription>
            <p>
              Older prints and prints from empty slots don&apos;t count against any spool.{" "}
              <Link href="/prints" className="text-foreground underline underline-offset-4">
                Review them
              </Link>
              .
            </p>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {slots.map((s) => (
          <SlotCard key={s.slot} view={s} />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent prints</CardTitle>
          <CardDescription>The last 10 jobs, newest first.</CardDescription>
          <CardAction>
            <Button asChild variant="outline" size="sm">
              <Link href="/prints">View all</Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {recent.length ? (
            <PrintsTable prints={recent} />
          ) : (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No prints yet. Sync from Bambu Cloud or add one on the Prints page.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SlotCard({ view }: { view: SlotView }) {
  const { slot, spool } = view;
  return (
    <Card>
      <CardHeader>
        <CardDescription>Slot {slot}</CardDescription>
        <CardAction>
          <Button asChild variant={spool ? "outline" : "default"} size="sm">
            <Link href={`/spools/load/${slot}`}>
              {spool ? "Change spool" : (<><PlusIcon /> Load spool</>)}
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {spool ? (
          <div className="flex items-center gap-5">
            <SpoolRing pct={spool.pct_left} color={spool.color} />
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <ColorDot color={spool.color} />
                <span className="font-medium">{spool.material}</span>
                {spool.brand && <Badge variant="secondary">{spool.brand}</Badge>}
              </div>
              <div className="text-2xl font-semibold tabular-nums">
                {spool.remaining_g} g{" "}
                <span className="text-muted-foreground text-sm font-normal">of {Math.round(spool.initial_g)} g</span>
              </div>
              <p className="text-muted-foreground text-xs">
                {spool.used_g} g used · {spool.print_count} print{spool.print_count === 1 ? "" : "s"} · loaded{" "}
                <LocalTime iso={spool.started_at} dateOnly />
              </p>
            </div>
          </div>
        ) : (
          <p className="text-muted-foreground py-8 text-center text-sm">No spool loaded in this slot.</p>
        )}
      </CardContent>
    </Card>
  );
}
