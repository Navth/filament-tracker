"""Minimal Bambu Lab Cloud API client (unofficial).

Login flow (2FA via email code):
  1. POST /v1/user-service/user/login  {account, password}
     -> {"success": true, "accessToken": "..."}            (rare, no 2FA)
     -> {"success": false, "loginType": "verifyCode"}      (needs email code)
  2. POST /v1/user-service/user/sendemail/code {email, type: "codeLogin"}
  3. POST /v1/user-service/user/login  {account, code}
     -> {"success": true, "accessToken": "..."}

Print history: GET /v1/user-service/my/tasks?limit=N
Each task includes `weight` (estimated grams) and `amsDetailMapping`
(per-AMS-slot filament info) among other fields.
"""

import requests

BASE_URLS = {
    "global": "https://api.bambulab.com",
    "china": "https://api.bambulab.cn",
}

UA_HEADERS = {
    "User-Agent": "bambu_network_agent/01.09.05.01",
    "X-BBL-Client-Name": "OrcaSlicer",
    "X-BBL-Client-Type": "slicer",
    "X-BBL-Client-Version": "01.09.05.51",
    "Content-Type": "application/json",
}


class BambuCloudError(Exception):
    pass


class NeedsVerifyCode(Exception):
    """Raised when Bambu wants an email verification code."""


class BambuCloud:
    def __init__(self, region="global", token=None):
        self.base = BASE_URLS.get(region, BASE_URLS["global"])
        self.token = token

    # ---------- auth ----------

    def _post(self, path, payload):
        r = requests.post(self.base + path, json=payload, headers=UA_HEADERS, timeout=20)
        try:
            data = r.json()
        except ValueError:
            data = {}
        return r, data

    def login(self, email, password):
        """Start login. Returns token, or raises NeedsVerifyCode."""
        r, data = self._post("/v1/user-service/user/login",
                             {"account": email, "password": password, "apiError": ""})
        token = data.get("accessToken")
        if token:
            self.token = token
            return token
        if data.get("loginType") == "verifyCode":
            self.request_code(email)
            raise NeedsVerifyCode()
        if data.get("loginType") == "tfa":
            raise BambuCloudError(
                "This account has app-based MFA enabled, which this tool doesn't "
                "support. Disable MFA or use email-code login.")
        raise BambuCloudError(f"Login failed (HTTP {r.status_code}): {data.get('error') or r.text[:200]}")

    def request_code(self, email):
        r, data = self._post("/v1/user-service/user/sendemail/code",
                             {"email": email, "type": "codeLogin"})
        if r.status_code >= 400:
            raise BambuCloudError(f"Could not send verification code (HTTP {r.status_code}): {r.text[:200]}")

    def login_with_code(self, email, code):
        r, data = self._post("/v1/user-service/user/login",
                             {"account": email, "code": code})
        token = data.get("accessToken")
        if not token:
            raise BambuCloudError(f"Code verification failed (HTTP {r.status_code}): {r.text[:200]}")
        self.token = token
        return token

    # ---------- authenticated requests ----------

    def _get(self, path, params=None):
        if not self.token:
            raise BambuCloudError("Not logged in")
        headers = dict(UA_HEADERS)
        headers["Authorization"] = f"Bearer {self.token}"
        r = requests.get(self.base + path, params=params, headers=headers, timeout=20)
        if r.status_code == 401:
            raise BambuCloudError("Token expired or invalid — please log in again (401)")
        r.raise_for_status()
        return r.json()

    def verify_token(self):
        try:
            self._get("/v1/user-service/my/profile")
            return True
        except Exception:
            return False

    def get_devices(self):
        data = self._get("/v1/iot-service/api/user/bind")
        return data.get("devices", [])

    def get_tasks(self, device_id=None, limit=100):
        """Return list of print tasks, newest first.

        Task fields of interest: id, title, deviceId, status,
        startTime, endTime, weight (grams), costTime, amsDetailMapping.
        """
        params = {"limit": limit}
        if device_id:
            params["deviceId"] = device_id
        data = self._get("/v1/user-service/my/tasks", params=params)
        return data.get("hits", [])
