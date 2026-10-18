import { Brand } from "@/components/brand";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 p-6">
      <Brand className="text-lg" />
      <div className="w-full max-w-sm">{children}</div>
      <p className="text-muted-foreground max-w-sm text-center text-xs">
        Uses Bambu Lab&apos;s unofficial cloud API. Not affiliated with Bambu Lab.
      </p>
    </main>
  );
}
