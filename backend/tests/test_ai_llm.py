"""Kiểm tra luồng có LLM bằng LLM giả: dữ liệu gửi đi đã che PII, id bịa bị loại, PII được khôi phục."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.ai.ask_service import answer, parse_intent
from app.ai.brief_generator import generate_brief
from app.services.calendar_insights import analyze_day
from tests.conftest import make_item

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 8, 7, 30, tzinfo=TZ).astimezone(timezone.utc)


class FakeLlm:
    enabled = True

    def __init__(self, json_out=None, text_out=None):
        self.json_out, self.text_out, self.prompts = json_out, text_out, []

    def chat_json(self, system, user, **kw):
        self.prompts.append(user)
        return self.json_out

    def chat(self, system, user, **kw):
        self.prompts.append(user)
        return self.text_out


def _items():
    return [
        make_item(id=1, kind="ticket", source="sdp", title="KH TK 0123456789012 lỗi chuyển tiền", score=90,
                  sla_due_at=NOW - timedelta(minutes=10), score_reasons=["ĐÃ VI PHẠM SLA"], bucket="critical",
                  preview="SĐT 0912345678"),
        make_item(id=2, kind="task", title="[CORE-1] Fix", score=60, due_at=NOW + timedelta(hours=3),
                  score_reasons=["Đến hạn sau 3 giờ"], bucket="high"),
        make_item(id=3, kind="task", title="[CORE-2] Test", score=30, due_at=NOW + timedelta(days=2), bucket="normal"),
    ]


def test_brief_with_llm_masks_and_validates_ids():
    items = _items()
    llm = FakeLlm(json_out={
        "headline": "Ưu tiên xử lý sự cố của KH [STK_1].",
        "top_priorities": [{"item_id": 1, "why": "Đã vi phạm SLA"}, {"item_id": 999, "why": "bịa"},
                           {"item_id": 2, "why": "Hạn chiều nay"}],
        "risks": ["SLA"], "suggestions": ["Gọi lại [SĐT_1]"], "closing": "Cố lên!",
    })
    brief, by = generate_brief("Nguyễn Văn An", items, analyze_day([], NOW.astimezone(TZ).date(), TZ), NOW, TZ, llm)
    assert by == "llm"
    sent = "".join(llm.prompts)
    assert "0123456789012" not in sent and "0912345678" not in sent
    assert [t["item_id"] for t in brief["top_priorities"]] == [1, 2]
    assert "0123456789012" in brief["headline"]
    assert brief["suggestions"] == ["Gọi lại 0912345678"]


def test_brief_falls_back_when_llm_returns_nothing():
    brief, by = generate_brief("An", _items(), analyze_day([], NOW.astimezone(TZ).date(), TZ), NOW, TZ, FakeLlm())
    assert by == "fallback"
    assert brief["top_priorities"][0]["item_id"] == 1


def test_ask_intent_and_llm_answer():
    it = parse_intent("Hôm nay tôi có ticket SDP nào quá hạn SLA không?", NOW, TZ)
    assert it.sources == {"sdp"} and it.overdue and it.sla and it.start is not None
    # "hợp đồng" không bị hiểu nhầm là "họp"
    assert "exchange_calendar" not in parse_intent("hợp đồng tín dụng Sao Việt", NOW, TZ).sources
    assert "exchange_calendar" in parse_intent("chiều nay tôi họp gì?", NOW, TZ).sources

    llm = FakeLlm(text_out="Có 1 ticket vi phạm SLA: KH [STK_1] [#1].")
    res = answer("ticket nào đã quá hạn?", _items(), NOW, TZ, llm)
    assert res["items"] == [1] and res["generated_by"] == "llm"
    assert "0123456789012" in res["answer"]
    assert "0123456789012" not in "".join(llm.prompts)


def test_ask_sla_soon_excludes_breached_and_sorts_by_deadline():
    items = _items() + [
        make_item(id=4, kind="ticket", source="sdp", title="B", sla_due_at=NOW + timedelta(hours=5), score=20),
        make_item(id=5, kind="ticket", source="sdp", title="A", sla_due_at=NOW + timedelta(hours=1), score=10),
        make_item(id=6, kind="ticket", source="sdp", title="C", sla_due_at=NOW + timedelta(days=3), score=50),
    ]
    res = answer("Ticket SDP nào sắp vi phạm SLA?", items, NOW, TZ, FakeLlm())
    assert res["items"] == [5, 4]
    res2 = answer("Ticket nào đã vi phạm SLA?", items, NOW, TZ, FakeLlm())
    assert res2["items"] == [1]
