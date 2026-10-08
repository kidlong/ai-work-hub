from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    timezone: str = "Asia/Ho_Chi_Minh"
    jwt_secret: str = "dev-only-secret-change-me-please-0123456789"
    access_token_minutes: int = 30
    refresh_token_hours: int = 8
    database_url: str = "sqlite:///./aiworkhub.db"
    cors_origins: str = "*"

    mock_connectors: bool = True
    auth_mode: str = "mock"  # mock | ldap

    ldap_url: str = ""
    ldap_domain: str = ""
    ldap_base_dn: str = ""
    ldap_ca_cert_file: str = ""

    exchange_enabled: bool = True
    exchange_ews_url: str = ""
    exchange_service_user: str = ""
    exchange_service_password: str = ""
    exchange_auth_type: str = "NTLM"
    exchange_ca_cert_file: str = ""

    jira_enabled: bool = True
    jira_base_url: str = ""
    jira_token: str = ""

    confluence_enabled: bool = True
    confluence_base_url: str = ""
    confluence_token: str = ""

    sdp_enabled: bool = True
    sdp_base_url: str = ""
    sdp_authtoken: str = ""

    teams_enabled: bool = False
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""

    internal_ca_bundle: str = ""

    llm_enabled: bool = False
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen2.5-14b-instruct"
    llm_timeout_seconds: float = 45.0

    push_provider: str = "log"
    fcm_project_id: str = ""
    fcm_service_account_file: str = ""
    push_include_content: bool = False

    sync_interval_minutes: int = Field(default=5, ge=1)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def tls_verify(self) -> bool | str:
        """Đường dẫn CA nội bộ nếu có, ngược lại dùng CA hệ thống."""
        return self.internal_ca_bundle or True


@lru_cache
def get_settings() -> Settings:
    return Settings()
