"""Configuration loader.

Mirrors Power Platform Environment Variables 1:1. Every value the original
solution reads from an Environment Variable comes from os.environ here.
No hard-coded secrets — the same rule that applies in the Power Platform
solution applies here.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Required env variable {key!r} is not set")
    return value


def _get(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Config:
    # SharePoint - source list
    sp_source_site_url: str
    sp_source_list_name: str

    # SharePoint - target Admin List
    sp_target_site_url: str
    sp_target_list_name: str

    # Auth
    sp_tenant_id: str
    sp_client_id: str
    sp_client_secret: str

    # AI model
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    ai_prompt_name: str

    # Notifications
    admin_email_dl: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str

    # Runtime
    poll_interval_seconds: int
    log_level: str

    @classmethod
    def load(cls) -> "Config":
        return cls(
            sp_source_site_url=_require("SP_SOURCE_SITE_URL"),
            sp_source_list_name=_get("SP_SOURCE_LIST_NAME", "MessageCenters"),
            sp_target_site_url=_require("SP_TARGET_SITE_URL"),
            sp_target_list_name=_get("SP_TARGET_LIST_NAME", "AdminList"),
            sp_tenant_id=_require("SP_TENANT_ID"),
            sp_client_id=_require("SP_CLIENT_ID"),
            sp_client_secret=_require("SP_CLIENT_SECRET"),
            openai_api_key=_require("OPENAI_API_KEY"),
            openai_model=_get("OPENAI_MODEL", "gpt-5-reasoning"),
            openai_base_url=_get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            ai_prompt_name=_get("AI_PROMPT_NAME", "MC_ClassificationPrompt"),
            admin_email_dl=_require("ADMIN_EMAIL_DL"),
            smtp_host=_get("SMTP_HOST", "smtp.office365.com"),
            smtp_port=int(_get("SMTP_PORT", "587")),
            smtp_username=_require("SMTP_USERNAME"),
            smtp_password=_require("SMTP_PASSWORD"),
            poll_interval_seconds=int(_get("POLL_INTERVAL_SECONDS", "60")),
            log_level=_get("LOG_LEVEL", "INFO"),
        )
