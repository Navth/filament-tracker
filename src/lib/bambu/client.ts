import "server-only";

/**
 * Minimal Bambu Lab Cloud API client (unofficial, undocumented API).
 *
 * Login flow (2FA via email code):
 *   1. POST /v1/user-service/user/login {account, password}
 *      -> {accessToken}                       (rare, no 2FA)
 *      -> {loginType: "verifyCode"}            (needs email code)
 *   2. POST /v1/user-service/user/sendemail/code {email, type: "codeLogin"}
 *   3. POST /v1/user-service/user/login {account, code} -> {accessToken}
 *
 * Print history: GET /v1/user-service/my/tasks?limit=N
 */

export type BambuRegion = "global" | "china";

const BASE_URLS: Record<BambuRegion, string> = {
  global: "https://api.bambulab.com",
  china: "https://api.bambulab.cn",
};

const HEADERS = {
  "User-Agent": "bambu_network_agent/01.09.05.01",
  "X-BBL-Client-Name": "OrcaSlicer",
  "X-BBL-Client-Type": "slicer",
  "X-BBL-Client-Version": "01.09.05.51",
  "Content-Type": "application/json",
};

const TIMEOUT_MS = 20_000;

export class BambuCloudError extends Error {}

/** Thrown when Bambu has emailed a verification code to finish login. */
export class NeedsVerifyCode extends Error {}

export type BambuDevice = { dev_id: string; name?: string; dev_product_name?: string };

export type BambuTask = {
  id: number | string;
  title?: string;
  deviceId?: string;
  status?: number;
  startTime?: string;
  endTime?: string;
  weight?: number;
  amsDetailMapping?: { ams?: number; weight?: number }[];
};

export class BambuCloud {
  private base: string;

  constructor(
    region: BambuRegion = "global",
    public token?: string,
  ) {
    this.base = BASE_URLS[region] ?? BASE_URLS.global;
  }

  private async post(path: string, body: unknown) {
    const res = await fetch(this.base + path, {
      method: "POST",
      headers: HEADERS,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    return { res, data };
  }

  async login(email: string, password: string): Promise<string> {
    const { res, data } = await this.post("/v1/user-service/user/login", {
      account: email,
      password,
      apiError: "",
    });
    const token = data.accessToken;
    if (typeof token === "string" && token) {
      this.token = token;
      return token;
    }
    if (data.loginType === "verifyCode") {
      await this.requestCode(email);
      throw new NeedsVerifyCode();
    }
    if (data.loginType === "tfa") {
      throw new BambuCloudError(
        "This account uses app-based MFA, which isn't supported. Use email-code login instead.",
      );
    }
    throw new BambuCloudError(
      `Login failed (HTTP ${res.status})${typeof data.error === "string" ? `: ${data.error}` : ""}`,
    );
  }

  async requestCode(email: string) {
    const { res } = await this.post("/v1/user-service/user/sendemail/code", {
      email,
      type: "codeLogin",
    });
    if (res.status >= 400) {
      throw new BambuCloudError(`Could not send verification code (HTTP ${res.status})`);
    }
  }

  async loginWithCode(email: string, code: string): Promise<string> {
    const { res, data } = await this.post("/v1/user-service/user/login", {
      account: email,
      code,
    });
    const token = data.accessToken;
    if (typeof token !== "string" || !token) {
      throw new BambuCloudError(`Code verification failed (HTTP ${res.status})`);
    }
    this.token = token;
    return token;
  }

  private async get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
    if (!this.token) throw new BambuCloudError("Not connected to Bambu Cloud");
    const url = new URL(this.base + path);
    for (const [k, v] of Object.entries(params ?? {})) url.searchParams.set(k, String(v));
    const res = await fetch(url, {
      headers: { ...HEADERS, Authorization: `Bearer ${this.token}` },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    if (res.status === 401) {
      throw new BambuCloudError("Bambu token expired. Reconnect in Settings.");
    }
    if (!res.ok) throw new BambuCloudError(`Bambu Cloud error (HTTP ${res.status})`);
    return (await res.json()) as T;
  }

  async getDevices(): Promise<BambuDevice[]> {
    const data = await this.get<{ devices?: BambuDevice[] }>("/v1/iot-service/api/user/bind");
    return data.devices ?? [];
  }

  async getTasks(deviceId?: string, limit = 100): Promise<BambuTask[]> {
    const params: Record<string, string | number> = { limit };
    if (deviceId) params.deviceId = deviceId;
    const data = await this.get<{ hits?: BambuTask[] }>("/v1/user-service/my/tasks", params);
    return data.hits ?? [];
  }
}
