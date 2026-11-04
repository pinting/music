import time
from typing import Optional

import requests

from src.config import Config

class APIClient:
    def __init__(self, config: Config, delay: float):
        self.config = config
        self.delay = delay
        self.session = requests.Session()

    def _headers(self) -> dict:
        return {}

    def _on_unauthorized(self) -> None:
        pass

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        response = self._send("GET", url, params=params)

        return {} if response.status_code == 404 else response.json()

    def _post(self, url: str, body: dict, headers: dict) -> dict:
        response = self._send("POST", url, json=body, headers=headers)

        response.raise_for_status()

        return response.json() if response.content else {}

    def _send(self, method: str, url: str, headers: Optional[dict] = None, **kwargs) -> requests.Response:
        """Returns a successful or 404 response, retrying what is worth retrying."""

        retries = self.config.retries

        for attempt in range(1, retries + 1):
            time.sleep(self.delay)

            try:
                response = self.session.request(
                    method, url, headers={**self._headers(), **(headers or {})}, timeout=self.config.timeout, **kwargs
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == retries:
                    raise

                print(f"Request failed: {e}. Retrying ({attempt}/{retries})...")
                self._backoff(attempt)

                continue

            if response.ok or response.status_code == 404:
                return response

            if attempt == retries:
                response.raise_for_status()

            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", self.config.retry_after))

                print(f"Rate limited, waiting {wait}s ({attempt}/{retries})...")
                time.sleep(wait)
            elif response.status_code == 401:
                self._on_unauthorized()
            elif response.status_code >= 500:
                self._backoff(attempt)
            else:
                response.raise_for_status()

    def _backoff(self, attempt: int) -> None:
        time.sleep(self.config.retry_backoff * attempt)

class OAuthClient(APIClient):
    """Client Credentials flow, failing authentication is fatal instead of a failed request."""

    def __init__(self, config: Config, delay: float, auth_url: str, client_id: str, client_secret: str):
        super().__init__(config, delay)
        self.auth_url = auth_url
        self.credentials = (client_id, client_secret)
        self.token = None
        self.token_expires_at = 0

    def _headers(self) -> dict:
        if self.token is None or time.time() >= self.token_expires_at:
            self._authenticate()

        return {"Authorization": f"Bearer {self.token}"}

    def _on_unauthorized(self) -> None:
        self.token = None

    def _authenticate(self) -> None:
        retries = self.config.retries

        for attempt in range(1, retries + 1):
            try:
                response = self.session.post(
                    self.auth_url,
                    data={"grant_type": "client_credentials"},
                    auth=self.credentials,
                    timeout=self.config.timeout
                )
                response.raise_for_status()
                data = response.json()

                self.token = data["access_token"]
                self.token_expires_at = time.time() + data.get("expires_in", 3600) - self.config.token_margin

                return
            except requests.exceptions.RequestException as e:
                if attempt == retries:
                    raise RuntimeError(f"Authentication failed at {self.auth_url}: {e}")

                self._backoff(attempt)
