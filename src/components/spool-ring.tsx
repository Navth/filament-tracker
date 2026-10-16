import { cn } from "@/lib/utils";

/** Circular gauge showing % of filament left, tinted with the spool colour. */
export function SpoolRing({
  pct,
  color,
  className,
}: {
  pct: number;
  color?: string;
  className?: string;
}) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const tone = pct < 10 ? "var(--destructive)" : pct < 25 ? "var(--warning)" : color || "var(--primary)";
  return (
    <div className={cn("relative size-28 shrink-0", className)}>
      <svg viewBox="0 0 100 100" className="size-full -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--muted)" strokeWidth="10" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(100, pct)) / 100)}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center leading-tight">
        <div>
          <div className="text-xl font-semibold tabular-nums">{pct}%</div>
          <div className="text-muted-foreground text-xs">left</div>
        </div>
      </div>
    </div>
  );
}

export function ColorDot({ color, className }: { color?: string; className?: string }) {
  return (
    <span
      className={cn("inline-block size-3 shrink-0 rounded-full border border-white/20", className)}
      style={{ background: color || "var(--muted-foreground)" }}
    />
  );
}
