import { LocalTime } from "@/components/local-time";
import { ColorDot } from "@/components/spool-ring";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getSpools } from "@/lib/data";
import { cn } from "@/lib/utils";
import { CorrectForm } from "./correct-form";

export default async function SpoolsPage() {
  const spools = await getSpools();
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Spools</h1>
      <Card>
        <CardHeader>
          <CardTitle>Spool history</CardTitle>
          <CardDescription>
            Grams are slicer estimates, so they drift over time. Weigh an active spool and set the real
            amount to correct it (empty spools weigh about 130–250 g).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {spools.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Spool</TableHead>
                  <TableHead>Slot</TableHead>
                  <TableHead>Loaded</TableHead>
                  <TableHead>Ended</TableHead>
                  <TableHead className="min-w-44">Usage</TableHead>
                  <TableHead>Correct</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {spools.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <ColorDot color={s.color} />
                        <span className="font-medium">{s.material}</span>
                        {s.brand && <Badge variant="secondary">{s.brand}</Badge>}
                        {s.active && <Badge variant="success">active</Badge>}
                      </div>
                      {s.note && <div className="text-muted-foreground mt-1 text-xs">{s.note}</div>}
                    </TableCell>
                    <TableCell className="tabular-nums">{s.slot}</TableCell>
                    <TableCell className="text-muted-foreground">
                      <LocalTime iso={s.started_at} dateOnly />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <LocalTime iso={s.ended_at} dateOnly />
                    </TableCell>
                    <TableCell>
                      <div className="text-sm tabular-nums">
                        {s.remaining_g} g left{" "}
                        <span className="text-muted-foreground">/ {Math.round(s.initial_g)} g</span>
                      </div>
                      <Progress
                        value={s.pct_left}
                        className="mt-1.5"
                        indicatorClassName={cn(
                          s.pct_left < 10 && "bg-destructive",
                          s.pct_left >= 10 && s.pct_left < 25 && "bg-warning",
                        )}
                      />
                    </TableCell>
                    <TableCell>
                      {s.active ? <CorrectForm spoolId={s.id} /> : <span className="text-muted-foreground">—</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-muted-foreground py-8 text-center text-sm">
              No spools yet. Load one from the dashboard.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
