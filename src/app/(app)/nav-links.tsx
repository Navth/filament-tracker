"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboardIcon, MessageSquareIcon, PrinterIcon, SettingsIcon, DiscIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboardIcon },
  { href: "/spools", label: "Spools", icon: DiscIcon },
  { href: "/prints", label: "Prints", icon: PrinterIcon },
  { href: "/chat", label: "Chat", icon: MessageSquareIcon },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

export function NavLinks() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1 overflow-x-auto">
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            title={label}
            className={cn(
              "text-muted-foreground hover:text-foreground hover:bg-accent flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active && "bg-accent text-foreground",
            )}
          >
            <Icon className="size-4" />
            <span className="hidden lg:inline">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
