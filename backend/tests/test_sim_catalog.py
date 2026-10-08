import json
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.connectors.base import UserContext
from app.connectors.live import TIME_FIELDS, item_to_payload
from app.services.sim_catalog import SCENARIOS, ScenarioCtx, persona_of, scenarios_for

NOW = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
IT = UserContext("an.nguyen", "an.nguyen@bank.local", "Nguyễn Văn An", manager_email="minh.tran@bank.local")
RM = UserContext("lan.pham", "lan.pham@bank.local", "Phạm Thị Lan", manager_email="hung.le@bank.local")
ROLES = {"manager", "vip_customer", "audit", "peer", "external"}
KINDS = {"email", "meeting", "task", "ticket", "page", "chat"}


def ctx(user=IT, seed=1, rows=None):
    return ScenarioCtx(user=user, now=NOW, rng=random.Random(seed), tz=TZ, rows=rows or [])


def test_catalog_sizes_and_unique_keys():
    assert len(scenarios_for("it")) == 12 and len(scenarios_for("rm")) == 6
    assert len(SCENARIOS) == 18
    assert persona_of("an.nguyen") == "it" and persona_of("lan.pham") == "rm"


@pytest.mark.parametrize("sc", list(SCENARIOS.values()), ids=lambda s: s.key)
def test_every_scenario_builds_valid_draft_or_has_fallback(sc):
    user = RM if sc.persona == "rm" else IT
    draft = sc.build(ctx(user))
    if draft is None:  # kịch bản 'update' cần đối tượng có sẵn -> phải có fallback cùng persona và cùng nguồn
        assert sc.fallback, f"{sc.key} trả None nhưng không có fallback"
        fb = SCENARIOS[sc.fallback]
        assert fb.persona == sc.persona and fb.source == sc.source
        draft = fb.build(ctx(user))
    assert draft is not None and draft.type == "new_item" and draft.banner
    it = draft.item
    assert it.source == sc.source and it.external_id and it.title
    assert it.kind in KINDS and it.requester_role in ROLES
    assert all(getattr(it, f) is None or getattr(it, f).tzinfo for f in TIME_FIELDS)
    json.dumps(item_to_payload(it, NOW))  # payload phải serialize được


def test_external_ids_unique_within_one_ctx():
    c = ctx()
    ids = [SCENARIOS["teams_mention"].build(c).item.external_id for _ in range(20)]
    assert len(set(ids)) == 20


def test_vip_mail_contains_fake_pii_for_masker():
    d = SCENARIOS["mail_vip_customer"].build(ctx())
    assert "9704229912345678" in d.item.preview and "0987654321" in d.item.preview


def test_sla_escalation_overrides_existing_ticket_without_mutating_row(item_factory):
    row = item_factory(id=7, source="sdp", external_id="50231", kind="ticket", title="[SDP#50231] x",
                       sla_due_at=NOW + timedelta(hours=2), tags=["incident"])
    d = SCENARIOS["sdp_sla_escalation"].build(ctx(rows=[row]))
    assert d.type == "update_item" and d.item.external_id == "50231"
    assert d.item.sla_due_at == NOW + timedelta(minutes=10)
    assert "escalated" in d.item.tags and row.tags == ["incident"]
    assert row.sla_due_at == NOW + timedelta(hours=2)


def test_sla_escalation_ignores_done_or_breached(item_factory):
    done = item_factory(source="sdp", external_id="1", sla_due_at=NOW + timedelta(hours=2), done_local=True)
    breached = item_factory(source="sdp", external_id="2", sla_due_at=NOW - timedelta(minutes=5))
    assert SCENARIOS["sdp_sla_escalation"].build(ctx(rows=[done, breached])) is None


def test_meeting_conflict_overlaps_target_with_same_start(item_factory):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="Họp A",
                          start_at=NOW + timedelta(hours=2), end_at=NOW + timedelta(hours=3))
    d = SCENARIOS["meeting_conflict"].build(ctx(rows=[target]))
    assert d.item.start_at == target.start_at and d.item.end_at > d.item.start_at
    assert d.item.start_at < target.end_at and target.start_at < d.item.end_at


def test_meeting_conflict_when_target_already_started_still_overlaps(item_factory):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="Họp A",
                          start_at=NOW - timedelta(minutes=10), end_at=NOW + timedelta(minutes=50))
    d = SCENARIOS["meeting_conflict"].build(ctx(rows=[target]))
    assert target.start_at < d.item.start_at < target.end_at


@pytest.mark.parametrize("seed", range(40))
def test_meeting_moved_never_lands_in_the_past(item_factory, seed):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="Họp A",
                          start_at=NOW + timedelta(minutes=50), end_at=NOW + timedelta(minutes=110))
    d = SCENARIOS["meeting_moved"].build(ctx(seed=seed, rows=[target]))
    assert d.type == "update_item" and d.item.start_at >= NOW + timedelta(minutes=15)
    assert d.item.end_at - d.item.start_at == timedelta(minutes=60)
    assert d.item.title.count("[Dời giờ]") == 1


def test_meeting_moved_does_not_stack_prefix(item_factory):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="[Dời giờ] Họp A",
                          start_at=NOW + timedelta(hours=2), end_at=NOW + timedelta(hours=3))
    d = SCENARIOS["meeting_moved"].build(ctx(rows=[target]))
    assert d.item.title.count("[Dời giờ]") == 1


def test_jira_unblocked_only_targets_blocked(item_factory):
    ok = item_factory(source="jira", external_id="A-1", status="In Progress")
    blocked = item_factory(source="jira", external_id="A-2", status="Blocked", title="[A-2] x")
    assert SCENARIOS["jira_unblocked"].build(ctx(rows=[ok])) is None
    d = SCENARIOS["jira_unblocked"].build(ctx(rows=[ok, blocked]))
    assert d.item.external_id == "A-2" and d.item.status == "In Progress"
