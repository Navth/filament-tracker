import * as React from "react";
import { ChevronDownIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** shadcn/ui NativeSelect: a styled <select> that works without JS. */
function NativeSelect({
  className,
  ...props
}: React.ComponentProps<"select">) {
  return (
    <div className="relative w-full" data-slot="native-select-wrapper">
      <select
        data-slot="native-select"
        className={cn(
          "border-input dark:bg-input/30 h-9 w-full min-w-0 appearance-none rounded-md border bg-transparent pr-9 pl-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none disabled:cursor-not-allowed disabled:opacity-50",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          "[&>option]:bg-popover [&>option]:text-popover-foreground",
          className,
        )}
        {...props}
      />
      <ChevronDownIcon
        aria-hidden="true"
        className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2"
      />
    </div>
  );
}

export { NativeSelect };
