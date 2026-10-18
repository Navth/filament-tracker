import { LocalTime } from "@/components/local-time";
import { ColorDot } from "@/components/spool-ring";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Print } from "@/lib/data";
import { cn } from "@/lib/utils";

/** Read-only table of prints, used on the dashboard. */
export function PrintsTable({ prints }: { prints: Print[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Print</TableHead>
          <TableHead>When</TableHead>
          <TableHead className="text-right">Grams</TableHead>
          <TableHead>Spool</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {prints.map((p) => (
          <TableRow key={p.id} className={cn(!p.counted && "opacity-45")}>
            <TableCell className="max-w-64 truncate font-medium">{p.title}</TableCell>
            <TableCell className="text-muted-foreground">
              <LocalTime iso={p.start_time} />
            </TableCell>
            <TableCell className="text-right tabular-nums">{p.weight} g</TableCell>
            <TableCell>
              {p.spool ? (
                <span className="flex items-center gap-2">
                  <ColorDot color={p.spool.color} /> {p.spool.material}
                </span>
              ) : (
                <Badge variant="outline" className="text-muted-foreground">
                  unassigned
                </Badge>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
