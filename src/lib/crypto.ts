import "server-only";

import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

import { env } from "@/lib/env";

/**
 * AES-256-GCM encryption for secrets stored in the database (the Bambu
 * Cloud token). Format: "v1:<iv>:<auth tag>:<ciphertext>", base64url parts.
 * The key never leaves the server; a leaked database row is useless
 * without it.
 */
const VERSION = "v1";

function key(raw = env.tokenEncKey): Buffer {
  const buf = Buffer.from(raw, "base64");
  if (buf.length !== 32) {
    throw new Error("TOKEN_ENC_KEY must be 32 bytes, base64-encoded");
  }
  return buf;
}

export function encryptSecret(plaintext: string, rawKey?: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(rawKey), iv);
  const ct = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [VERSION, iv, tag, ct].map((p) => (typeof p === "string" ? p : p.toString("base64url"))).join(":");
}

export function decryptSecret(payload: string, rawKey?: string): string {
  const [version, iv, tag, ct] = payload.split(":");
  if (version !== VERSION || !iv || !tag || !ct) {
    throw new Error("Unrecognised encrypted secret format");
  }
  const decipher = createDecipheriv("aes-256-gcm", key(rawKey), Buffer.from(iv, "base64url"));
  decipher.setAuthTag(Buffer.from(tag, "base64url"));
  return Buffer.concat([
    decipher.update(Buffer.from(ct, "base64url")),
    decipher.final(),
  ]).toString("utf8");
}
