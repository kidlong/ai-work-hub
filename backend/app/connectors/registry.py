from __future__ import annotations

from functools import lru_cache

from app.connectors.base import Connector
from app.core.config import Settings, get_settings

ALL_SOURCES = ["exchange_calendar", "exchange_mail", "jira", "confluence", "sdp", "teams"]


def build_connectors(settings: Settings) -> dict[str, Connector]:
    if settings.mock_connectors:
        from app.connectors.mock import MockConnector
        from app.db.session import SessionLocal

        return {src: MockConnector(src, settings.tz, SessionLocal) for src in ALL_SOURCES}

    conns: dict[str, Connector] = {}
    if settings.exchange_enabled:
        from app.connectors.exchange_ews import (
            ExchangeCalendarConnector,
            ExchangeEwsConnector,
            ExchangeMailConnector,
        )

        ews = ExchangeEwsConnector(settings)
        conns["exchange_calendar"] = ExchangeCalendarConnector(ews)
        conns["exchange_mail"] = ExchangeMailConnector(ews)
    if settings.jira_enabled:
        from app.connectors.jira_dc import JiraDcConnector

        conns["jira"] = JiraDcConnector(settings)
    if settings.confluence_enabled:
        from app.connectors.confluence_dc import ConfluenceDcConnector

        conns["confluence"] = ConfluenceDcConnector(settings)
    if settings.sdp_enabled:
        from app.connectors.sdp import SdpConnector

        conns["sdp"] = SdpConnector(settings)
    if settings.teams_enabled:
        from app.connectors.teams_graph import TeamsGraphConnector

        conns["teams"] = TeamsGraphConnector(settings)
    return conns


@lru_cache
def get_connectors() -> dict[str, Connector]:
    return build_connectors(get_settings())
