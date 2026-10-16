import { LogOutIcon } from "lucide-react";

import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { getUser } from "@/lib/data";
import { signOut } from "../(auth)/actions";
import { NavLinks } from "./nav-links";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getUser();
  return (
    <div className="flex min-h-svh flex-col">
      <header className="bg-background/80 sticky top-0 z-10 border-b backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4">
          <Brand className="shrink-0" />
          <NavLinks />
          <div className="ml-auto flex items-center gap-2">
            <span className="text-muted-foreground hidden max-w-48 truncate text-sm md:inline">
              {user.email}
            </span>
            <form action={signOut}>
              <Button variant="ghost" size="icon-sm" title="Sign out" aria-label="Sign out">
                <LogOutIcon />
              </Button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
    </div>
  );
}
