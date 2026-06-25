"""SharePoint source adapter — equivalent of Step 1 (trigger) + Step 8 (update).

Uses the Microsoft Graph API to read and update items on the `MessageCenters`
SharePoint list. Auth via client credentials (the same model the Power Platform
solution uses through its Connection Reference + service account).

Two responsibilities:
- `poll_changes()`  — return items where Processed != true (the equivalent of
                      the SharePoint trigger firing for new/modified items)
- `mark_processed(id)` — set Processed = true on the row (Step 8)
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List
import requests
from msal import ConfidentialClientApplication
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import Config
from ..models import MCItem

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointSource:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._app = ConfidentialClientApplication(
            client_id=config.sp_client_id,
            client_credential=config.sp_client_secret,
            authority=f"https://login.microsoftonline.com/{config.sp_tenant_id}",
        )
        self._site_id: str | None = None
        self._list_id: str | None = None

    # ----- auth -----

    def _token(self) -> str:
        result = self._app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(f"MSAL auth failed: {result.get('error_description')}")
        return result["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}

    # ----- site/list resolution (lazy, cached) -----

    def _resolve_ids(self) -> tuple[str, str]:
        if self._site_id and self._list_id:
            return self._site_id, self._list_id

        host_path = self._config.sp_source_site_url.replace("https://", "")
        host, path = host_path.split("/", 1) if "/" in host_path else (host_path, "")
        site_resp = requests.get(
            f"{GRAPH_BASE}/sites/{host}:/{path}",
            headers=self._headers(),
            timeout=20,
        )
        site_resp.raise_for_status()
        self._site_id = site_resp.json()["id"]

        list_resp = requests.get(
            f"{GRAPH_BASE}/sites/{self._site_id}/lists",
            headers=self._headers(),
            timeout=20,
        )
        list_resp.raise_for_status()
        for lst in list_resp.json().get("value", []):
            if lst.get("displayName") == self._config.sp_source_list_name:
                self._list_id = lst["id"]
                return self._site_id, self._list_id

        raise RuntimeError(
            f"Source list '{self._config.sp_source_list_name}' not found on site"
        )

    # ----- public API -----

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def poll_changes(self, batch_size: int = 50) -> List[MCItem]:
        """Return up to `batch_size` items where Processed != true.

        Equivalent to the SharePoint trigger fan-in — we pull a batch rather
        than wait for individual events because the Python edition is meant
        to be run as a scheduled job, not a webhook receiver.
        """
        site_id, list_id = self._resolve_ids()
        params = {
            "$expand": "fields",
            "$filter": "fields/Processed ne true",
            "$top": str(batch_size),
            "$orderby": "fields/Modified desc",
        }
        resp = requests.get(
            f"{GRAPH_BASE}/sites/{site_id}/lists/{list_id}/items",
            headers={**self._headers(), "Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        items = []
        for row in resp.json().get("value", []):
            fields = row.get("fields", {})
            try:
                items.append(MCItem(
                    id=int(fields["ID"]),
                    created=datetime.fromisoformat(fields["Created"].replace("Z", "+00:00")),
                    modified=datetime.fromisoformat(fields["Modified"].replace("Z", "+00:00")),
                    full_message_html=fields.get("FullMessage", ""),
                    processed=bool(fields.get("Processed", False)),
                ))
            except (KeyError, ValueError) as exc:
                log.warning("Skipping malformed source row %s: %s", row.get("id"), exc)
        log.info("Pulled %d unprocessed items from %s", len(items), self._config.sp_source_list_name)
        return items

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def mark_processed(self, item_id: int) -> None:
        site_id, list_id = self._resolve_ids()
        resp = requests.patch(
            f"{GRAPH_BASE}/sites/{site_id}/lists/{list_id}/items/{item_id}/fields",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"Processed": True},
            timeout=20,
        )
        resp.raise_for_status()
