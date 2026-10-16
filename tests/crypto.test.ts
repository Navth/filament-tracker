import { randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";

import { decryptSecret, encryptSecret } from "@/lib/crypto";

const key = randomBytes(32).toString("base64");
const otherKey = randomBytes(32).toString("base64");

describe("token encryption", () => {
  it("round-trips a secret", () => {
    const enc = encryptSecret("bambu-token-123", key);
    expect(enc).not.toContain("bambu-token-123");
    expect(enc.startsWith("v1:")).toBe(true);
    expect(decryptSecret(enc, key)).toBe("bambu-token-123");
  });

  it("uses a fresh IV every time", () => {
    expect(encryptSecret("same", key)).not.toBe(encryptSecret("same", key));
  });

  it("rejects the wrong key", () => {
    const enc = encryptSecret("secret", key);
    expect(() => decryptSecret(enc, otherKey)).toThrow();
  });

  it("rejects tampered ciphertext", () => {
    const [v, iv, tag, ct] = encryptSecret("secret", key).split(":");
    const flipped = Buffer.from(ct, "base64url");
    flipped[0] ^= 0xff;
    expect(() => decryptSecret([v, iv, tag, flipped.toString("base64url")].join(":"), key)).toThrow();
  });

  it("rejects keys that aren't 32 bytes", () => {
    expect(() => encryptSecret("x", Buffer.alloc(16).toString("base64"))).toThrow(/32 bytes/);
  });
});
