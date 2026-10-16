"use client";

import Link from "next/link";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ActionResult } from "@/lib/action-result";

export function AuthForm({
  mode,
  action,
  notice,
}: {
  mode: "login" | "signup";
  action: (prev: ActionResult, form: FormData) => Promise<ActionResult>;
  notice?: string;
}) {
  const isLogin = mode === "login";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{isLogin ? "Welcome back" : "Create your account"}</CardTitle>
        <CardDescription>
          {isLogin
            ? "Sign in to see your spools and prints."
            : "Track every spool across your Bambu printers."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {notice && (
          <p className="text-destructive mb-4 text-sm" role="alert">
            {notice}
          </p>
        )}
        <ActionForm action={action} className="grid gap-4">
          {({ result }) => (
            <>
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" autoComplete="email" required />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  minLength={8}
                  autoComplete={isLogin ? "current-password" : "new-password"}
                  required
                />
              </div>
              {result.ok && result.message && (
                <p className="text-primary text-sm">{result.message}</p>
              )}
              <SubmitButton className="w-full">{isLogin ? "Sign in" : "Create account"}</SubmitButton>
              <p className="text-muted-foreground text-center text-sm">
                {isLogin ? "New here? " : "Already have an account? "}
                <Link
                  href={isLogin ? "/signup" : "/login"}
                  className="text-foreground underline underline-offset-4"
                >
                  {isLogin ? "Create an account" : "Sign in"}
                </Link>
              </p>
            </>
          )}
        </ActionForm>
      </CardContent>
    </Card>
  );
}
