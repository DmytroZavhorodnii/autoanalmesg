"""AdminList sink — equivalent of Step 6 (Create item in Admin List)."""

from __future__ import annotations
import logging
import requests
from msal import ConfidentialClientApplication
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import Config
from ..models import AdminListItem

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class AdminListWriter:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._app = ConfidentialClientApplication(
            client_id=config.sp_client_id,
            client_credential=config.sp_client_secret,
            authority=f"https://login.microsoftonline.com/{config.sp_tenant_id}",
        )
        self._site_id: str | None = None
        self._list_id: str | None = None

    def _token(self) -> str:
        r = self._app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in r:
            raise RuntimeError(f"MSAL auth failed: {r.get('error_description')}")
        return r["access_token"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _resolve_ids(self) -> tuple[str, str]:
        if self._site_id and self._list_id:
            return self._site_id, self._list_id

        host_path = self._config.sp_target_site_url.replace("https://", "")
        host, path = host_path.split("/", 1) if "/" in host_path else (host_path, "")
        site = requests.get(f"{GRAPH_BASE}/sites/{host}:/{path}", headers=self._headers(), timeout=20)
        site.raise_for_status()
        self._site_id = site.json()["id"]

        lists = requests.get(f"{GRAPH_BASE}/sites/{self._site_id}/lists", headers=self._headers(), timeout=20)
        lists.raise_for_status()
        for lst in lists.json().get("value", []):
            if lst.get("displayName") == self._config.sp_target_list_name:
                self._list_id = lst["id"]
                return self._site_id, self._list_id
        raise RuntimeError(f"Target list '{self._config.sp_target_list_name}' not found")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def create_item(self, row: AdminListItem) -> None:
        site_id, list_id = self._resolve_ids()
        fields = {
            "Title": row.title,
            "SourceID": str(row.source_id),
            "Category": row.category.value,
            "Priority": row.priority.value,
            "Impact": row.impact.value,
            "Summary": row.summary,
            "ActionsTaken": row.actions_taken,
            "Status": row.status.value,
        }
        if row.created_on_src:
            fields["CreatedOn_Src"] = row.created_on_src.isoformat()
        if row.modified_on_src:
            fields["ModifiedOn_Src"] = row.modified_on_src.isoformat()

        resp = requests.post(
            f"{GRAPH_BASE}/sites/{site_id}/lists/{list_id}/items",
            headers=self._headers(),
            json={"fields": fields},
            timeout=20,
        )
        resp.raise_for_status()
