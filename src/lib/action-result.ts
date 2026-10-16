export type ActionResult = {
  ok: boolean;
  message?: string;
  /** Extra step the UI should show (e.g. Bambu's email-code prompt). */
  next?: "verify-code";
  /** Increments on every submit so the UI can react to repeated results. */
  at?: number;
};

export const idle: ActionResult = { ok: true };

export function ok(message?: string, extra?: Partial<ActionResult>): ActionResult {
  return { ok: true, message, at: Date.now(), ...extra };
}

export function fail(message: string): ActionResult {
  return { ok: false, message, at: Date.now() };
}
