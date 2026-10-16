import { cn } from "@/lib/utils";

/** Spool logo + wordmark. */
export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2 font-semibold tracking-tight", className)}>
      <svg viewBox="0 0 24 24" className="size-6 text-primary" aria-hidden="true">
        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" strokeWidth="2" opacity=".55" />
        <circle cx="12" cy="12" r="2" fill="currentColor" />
      </svg>
      <span>
        Filament<span className="text-primary">Tracker</span>
      </span>
    </span>
  );
}
