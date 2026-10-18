import { LocalTime } from "@/components/local-time";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getPrints, getSettings, getSpools } from "@/lib/data";
import { cn } from "@/lib/utils";
import { AddPrintForm } from "./add-print-form";
import { CountedToggle, SpoolPicker, type SpoolOption } from "./print-controls";

export default async function PrintsPage() {
  const [prints, spools, settings] = await Promise.all([getPrints(200), getSpools(), getSettings()]);
  const options: SpoolOption[] = spools.map((s) => ({
    id: s.id,
    label: `#${s.id} ${s.material}${s.brand ? ` (${s.brand})` : ""} · slot ${s.slot}${s.active ? " · active" : ""}`,
  }));

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Prints</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add a print manually</CardTitle>
          <CardDescription>For prints that didn&apos;t go through Bambu Cloud (SD card, LAN mode).</CardDescription>
        </CardHeader>
        <CardContent>
          <AddPrintForm slotCount={settings.slot_count} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>All prints</CardTitle>
          <CardDescription>
            Mark failed prints as ignored, or move a print to the spool it actually used.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {prints.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Print</TableHead>
                  <TableHead>When</TableHead>
                  <TableHead className="text-right">Grams</TableHead>
                  <TableHead>Counted</TableHead>
                  <TableHead>Spool</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {prints.map((p) => (
                  <TableRow key={p.id} className={cn(!p.counted && "text-muted-foreground")}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="max-w-56 truncate font-medium">{p.title}</span>
                        {p.source === "manual" && <Badge variant="outline">manual</Badge>}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <LocalTime iso={p.start_time} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.weight} g</TableCell>
                    <TableCell>
                      <CountedToggle printId={p.id} counted={p.counted} />
                    </TableCell>
                    <TableCell>
                      <SpoolPicker printId={p.id} spoolId={p.spool_id} options={options} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-muted-foreground py-8 text-center text-sm">Nothing here yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
