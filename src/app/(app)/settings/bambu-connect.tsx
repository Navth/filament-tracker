"use client";

import { useState } from "react";
import { CloudIcon } from "lucide-react";

import { ActionForm } from "@/components/action-form";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { bambuDisconnect, bambuLogin, bambuVerify } from "../actions";

export function BambuConnect({
  connected,
  email,
  region,
}: {
  connected: boolean;
  email: string;
  region: "global" | "china";
}) {
  const [step, setStep] = useState<"login" | "code">("login");

  if (connected) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="success">
            <CloudIcon /> Connected
          </Badge>
          <span className="text-sm font-medium">{email}</span>
        </div>
        <ActionForm action={bambuDisconnect}>
          <SubmitButton variant="outline" size="sm">
            Disconnect
          </SubmitButton>
        </ActionForm>
      </div>
    );
  }

  if (step === "code") {
    return (
      <ActionForm
        action={bambuVerify}
        className="grid max-w-sm gap-4"
        onResult={(r) => r.ok && !r.next && setStep("login")}
      >
        <p className="text-muted-foreground text-sm">
          Bambu sent a 6-digit code to <span className="text-foreground font-medium">{email}</span>. Check
          your inbox and spam folder.
        </p>
        <div className="grid gap-2">
          <Label htmlFor="code">Verification code</Label>
          <Input
            id="code"
            name="code"
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            autoComplete="one-time-code"
            autoFocus
            required
            className="w-40 text-center font-mono text-lg tracking-[0.4em]"
          />
        </div>
        <div className="flex gap-2">
          <SubmitButton>Verify</SubmitButton>
          <Button type="button" variant="ghost" onClick={() => setStep("login")}>
            Start over
          </Button>
        </div>
      </ActionForm>
    );
  }

  return (
    <ActionForm
      action={bambuLogin}
      className="grid gap-4"
      onResult={(r) => r.next === "verify-code" && setStep("code")}
    >
      <div className="grid gap-4 sm:grid-cols-[1fr_1fr_9rem]">
        <div className="grid gap-2">
          <Label htmlFor="bambu-email">Bambu email</Label>
          <Input id="bambu-email" name="email" type="email" defaultValue={email} required />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="bambu-password">Password</Label>
          <Input id="bambu-password" name="password" type="password" autoComplete="off" required />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="region">Region</Label>
          <NativeSelect id="region" name="region" defaultValue={region}>
            <option value="global">Global</option>
            <option value="china">China</option>
          </NativeSelect>
        </div>
      </div>
      <p className="text-muted-foreground text-xs">
        Your password goes straight to Bambu&apos;s servers and is never stored. Only the login token is
        kept, encrypted.
      </p>
      <div>
        <SubmitButton>Connect</SubmitButton>
      </div>
    </ActionForm>
  );
}
