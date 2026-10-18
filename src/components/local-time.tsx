"use client";

/**
 * Renders a UTC timestamp in the viewer's own timezone. The server renders
 * UTC; the browser re-renders in local time on hydration.
 */
export function LocalTime({
  iso,
  dateOnly = false,
  fallback = "—",
}: {
  iso: string | null | undefined;
  dateOnly?: boolean;
  fallback?: string;
}) {
  if (!iso) return <span className="text-muted-foreground">{fallback}</span>;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return <span>{iso}</span>;
  const text = dateOnly
    ? d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
    : d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
  return (
    <time dateTime={iso} suppressHydrationWarning>
      {text}
    </time>
  );
}
