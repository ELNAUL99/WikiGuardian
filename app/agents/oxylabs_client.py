import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(
    PROJECT_ROOT / ".env",
    override=True,
    encoding="utf-8-sig",
)

BASE_URL = "https://webapi.oxylabs.io"


class OxylabsAPIError(Exception):
    """Raised when the Oxylabs API request fails."""


class OxylabsClient:

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 120,
        max_retries: int = 2,
    ):
        self.api_key = (
            api_key or os.getenv("OXYLABS_WEB_API_KEY", "")
        ).strip()

        if not self.api_key:
            raise ValueError("Oxylabs API key is missing.")

        self.timeout = timeout
        self.max_retries = max_retries

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        url = f"{BASE_URL}{endpoint}"

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code in (
                    429, 500, 502, 503, 504
                ):
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                        continue

                if response.status_code == 401:
                    raise OxylabsAPIError(
                        "Oxylabs authentication failed (401)."
                    )

                if not response.ok:
                    raise OxylabsAPIError(
                        f"Oxylabs HTTP {response.status_code} "
                        f"at {endpoint}: {response.text[:2000]}"
                    )

                data = response.json()

                if not isinstance(data, dict):
                    raise OxylabsAPIError(
                        "Unexpected Oxylabs response format."
                    )

                return data

            except requests.Timeout as exc:
                if attempt >= self.max_retries:
                    raise OxylabsAPIError(
                        "Oxylabs request timed out."
                    ) from exc

                time.sleep(2 ** attempt)

            except requests.RequestException as exc:
                raise OxylabsAPIError(
                    f"Oxylabs network request failed: {exc}"
                ) from exc

        raise OxylabsAPIError(
            "Oxylabs request failed after retries."
        )

    def search(
        self,
        query: str,
        max_results: int = 8,
        location: str | None = None,
    ) -> list[dict[str, Any]]:

        if not query.strip():
            raise ValueError("Search query cannot be empty.")

        if not 1 <= max_results <= 20:
            raise ValueError(
                "max_results must be between 1 and 20."
            )

        payload = {
            "query": query,
            "max_results": max_results,
        }

        if location:
            payload["location"] = location

        data = self._post("/v1/search", payload)
        results = data.get("results", [])

        if not isinstance(results, list):
            raise OxylabsAPIError(
                "Search response did not contain a results list."
            )

        return results

    def scrape(self, url: str) -> dict[str, Any]:

        if not url.startswith(("https://", "http://")):
            raise ValueError(
                "A valid HTTP(S) URL is required."
            )

        payload = {
            "url": url,
            "output": ["markdown"],
        }

        data = self._post("/v1/scrape", payload)
        results = data.get("results", [])

        if not isinstance(results, list) or not results:
            raise OxylabsAPIError(
                "Scrape response did not contain page results."
            )

        return results[0]

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
