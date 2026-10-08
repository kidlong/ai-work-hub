from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.alert_engine import AlertRules, generate_alerts, in_quiet_hours
from app.services.calendar_insights import analyze_day
from app.services.priority_engine import score_item

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 8, 8, 0, tzinfo=TZ).astimezone(timezone.utc)


# ---------------- Priority engine ----------------

def test_sla_breached_from_audit_is_critical(item_factory):
    it = item_factory(kind="ticket", source="sdp", sla_due_at=NOW - timedelta(minutes=30),
                      requester_role="audit", priority_raw="High", tags=["incident"])
    r = score_item(it, NOW)
    assert r.bucket == "critical"
    assert any("VI PHẠM SLA" in x for x in r.reasons)
    assert "Yêu cầu từ Kiểm toán/Tuân thủ" in r.reasons


def test_far_low_priority_task_is_low(item_factory):
    r = score_item(item_factory(due_at=NOW + timedelta(days=10), priority_raw="Low"), NOW)
    assert r.bucket == "low"


def test_ordering_overdue_beats_due_in_three_days(item_factory):
    a = score_item(item_factory(due_at=NOW - timedelta(hours=3)), NOW)
    b = score_item(item_factory(due_at=NOW + timedelta(days=2)), NOW)
    assert a.score > b.score


def test_done_status_and_finished_meeting_score_zero(item_factory):
    assert score_item(item_factory(status="Done", due_at=NOW), NOW).score == 0
    m = item_factory(kind="meeting", start_at=NOW - timedelta(hours=2), end_at=NOW - timedelta(hours=1))
    assert score_item(m, NOW).score == 0


def test_score_is_capped(item_factory):
    it = item_factory(kind="ticket", sla_due_at=NOW - timedelta(hours=1), due_at=NOW - timedelta(hours=1),
                      requester_role="audit", priority_raw="Highest", tags=["incident", "important", "flagged", "mention"],
                      status="Blocked")
    assert score_item(it, NOW).score == 100


# ---------------- Calendar insights ----------------

def _mtg(i, h1, m1, h2, m2, day=NOW.astimezone(TZ).date()):
    from tests.conftest import make_item
    s = datetime(day.year, day.month, day.day, h1, m1, tzinfo=TZ)
    e = datetime(day.year, day.month, day.day, h2, m2, tzinfo=TZ)
    return make_item(id=i, kind="meeting", title=f"M{i}", start_at=s, end_at=e)


def test_conflicts_overload_focus_and_back_to_back():
    ms = [_mtg(1, 8, 30, 9, 30), _mtg(2, 9, 0, 10, 0), _mtg(3, 10, 0, 11, 0), _mtg(4, 11, 0, 12, 0),
          _mtg(5, 13, 0, 15, 0)]
    ins = analyze_day(ms, NOW.astimezone(TZ).date(), TZ)
    assert len(ins.conflicts) == 1 and {ins.conflicts[0].a_id, ins.conflicts[0].b_id} == {1, 2}
    assert ins.meeting_minutes == 210 + 120
    assert ins.overloaded
    assert ins.back_to_back  # 1..4 liên tục
    assert [(f.start.astimezone(TZ).hour, f.minutes) for f in ins.focus_slots] == [(15, 150)]


def test_light_day_not_overloaded_with_morning_focus():
    ins = analyze_day([_mtg(1, 14, 0, 15, 0)], NOW.astimezone(TZ).date(), TZ)
    assert not ins.overloaded
    assert ins.focus_slots[0].start.astimezone(TZ).hour == 8


# ---------------- Alert engine ----------------

def test_meeting_reminder_uses_lead_time(item_factory):
    m = item_factory(id=7, kind="meeting", title="CAB", start_at=NOW + timedelta(hours=2),
                     end_at=NOW + timedelta(hours=3), requester_role="manager")
    drafts = generate_alerts([m], [], AlertRules(meeting_lead_minutes=10), NOW, TZ)
    d = [x for x in drafts if x.kind == "meeting_soon"][0]
    assert d.fire_at == m.start_at - timedelta(minutes=10)
    assert d.severity == "warning"


def test_due_reminders_24h_and_2h_and_overdue(item_factory):
    it = item_factory(id=2, due_at=NOW + timedelta(hours=30))
    kinds = [(d.kind, d.severity) for d in generate_alerts([it], [], AlertRules(), NOW, TZ)]
    assert ("due_soon", "info") in kinds and ("due_soon", "warning") in kinds
    late = item_factory(id=3, due_at=NOW - timedelta(hours=1), bucket="critical")
    od = [d for d in generate_alerts([late], [], AlertRules(), NOW, TZ) if d.kind == "overdue"][0]
    assert od.severity == "critical" and od.fire_at == NOW


def test_sla_breach_ignores_quiet_hours_but_info_is_deferred(item_factory):
    night = datetime(2026, 10, 8, 23, 0, tzinfo=TZ).astimezone(timezone.utc)
    rules = AlertRules(quiet_start="21:00", quiet_end="07:00")
    assert in_quiet_hours(night, rules, TZ)
    breach = item_factory(id=1, kind="ticket", sla_due_at=night - timedelta(minutes=5))
    mention = item_factory(id=2, kind="page", source="confluence", tags=["mention"], start_at=night)
    drafts = generate_alerts([breach, mention], [], rules, night, TZ)
    b = [d for d in drafts if d.kind == "sla_breached"][0]
    m = [d for d in drafts if d.kind == "mention"][0]
    assert b.fire_at == night
    assert m.fire_at.astimezone(TZ).hour == 7 and m.fire_at.astimezone(TZ).day == 9


def test_done_and_snoozed_items(item_factory):
    done = item_factory(id=1, due_at=NOW - timedelta(hours=1), done_local=True)
    assert generate_alerts([done], [], AlertRules(), NOW, TZ) == []
    snz = item_factory(id=2, due_at=NOW - timedelta(hours=1), snoozed_until=NOW + timedelta(hours=1))
    d = [x for x in generate_alerts([snz], [], AlertRules(), NOW, TZ) if x.kind == "overdue"][0]
    assert d.fire_at == NOW + timedelta(hours=1)


def test_digest_groups_many_info_alerts(item_factory):
    items = [item_factory(id=i, kind="page", source="confluence", title=f"P{i}", tags=["mention"],
                          start_at=NOW) for i in range(6)]
    drafts = generate_alerts(items, [], AlertRules(), NOW, TZ)
    assert len(drafts) == 1 and drafts[0].kind == "digest"
    assert "6 cập nhật" in drafts[0].title


def test_important_unread_mail_from_manager(item_factory):
    mail = item_factory(id=9, kind="email", source="exchange_mail", is_unread=True, requester_role="manager",
                        requester="sep@bank.local", start_at=NOW - timedelta(minutes=5))
    d = generate_alerts([mail], [], AlertRules(), NOW, TZ)[0]
    assert d.kind == "important_message" and d.severity == "warning"
