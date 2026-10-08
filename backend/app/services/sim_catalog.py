"""Danh mục kịch bản sự kiện giả lập. Dữ liệu hoàn toàn hư cấu, bối cảnh ngân hàng.

Mỗi kịch bản có hàm build(ctx) -> Draft | None. Kịch bản 'update_item' cần đối tượng có sẵn
(ctx.rows); nếu không có thì trả None và simulator rơi về kịch bản `fallback` (cùng nguồn).
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from app.connectors.base import ItemIn, UserContext
from app.connectors.live import item_from_row

OWA = "https://mail.bank.local/owa/"
JIRA = "https://jira.bank.local/browse/"
WIKI = "https://wiki.bank.local/pages/viewpage.action?pageId="
SDP = "https://sdp.bank.local/WorkOrder.do?woMode=viewWO&woID="
TEAMS = "https://teams.microsoft.com/"
MOVED_PREFIX = "[Dời giờ] "


def persona_of(username: str) -> str:
    return "rm" if username == "lan.pham" else "it"


@dataclass
class ScenarioCtx:
    user: UserContext
    now: datetime
    rng: random.Random
    tz: ZoneInfo
    rows: list[Any] = field(default_factory=list)  # WorkItem hiện có của user (đối tượng cho kịch bản update)
    taken_ids: set[str] = field(default_factory=set)

    def hm(self, dt: datetime) -> str:
        return dt.astimezone(self.tz).strftime("%H:%M")

    def later(self, minutes: int) -> datetime:
        return self.now + timedelta(minutes=minutes)

    def claim(self, ext_id: str) -> str:
        while ext_id in self.taken_ids:
            ext_id += "x"
        self.taken_ids.add(ext_id)
        return ext_id

    def new_id(self, key: str) -> str:
        return self.claim(f"sim-{key}-{int(self.now.timestamp() * 1000)}-{self.rng.randrange(1000, 10000)}")

    @property
    def manager(self) -> str:
        default = "hung.le@bank.local" if persona_of(self.user.username) == "rm" else "minh.tran@bank.local"
        return self.user.manager_email or default


@dataclass
class Draft:
    type: str  # new_item | update_item
    banner: str
    item: ItemIn


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    persona: str  # it | rm
    source: str
    weight: int
    severity: str  # info | warning | critical (màu banner trong app)
    build: Callable[[ScenarioCtx], Draft | None]
    fallback: str | None = None


# ---------------------------------------------------------------- Trình dựng dùng chung (kịch bản "new")


def _mail(ctx: ScenarioCtx, *, key: str, pool: list[tuple[str, str]], due_minutes: list[int], requester: str | None = None,
          role: str = "manager", tags: tuple[str, ...] = ("important", "flagged"),
          banner: str = "Mail mới từ quản lý: {subject}") -> Draft:
    subject, body = ctx.rng.choice(pool)
    due = ctx.later(ctx.rng.choice(due_minutes))
    subject, body = subject.format(hm=ctx.hm(due)), body.format(hm=ctx.hm(due))
    item = ItemIn(
        "exchange_mail", ctx.new_id(key), "email", subject, body, OWA, start_at=ctx.now, due_at=due,
        requester=requester or ctx.manager, requester_role=role, is_unread=True, tags=list(tags),
    )
    return Draft("new_item", banner.format(subject=subject), item)


def _ticket(ctx: ScenarioCtx, *, pool: list[tuple[str, str]], sla_minutes: list[int], requesters: list[str]) -> Draft:
    title, body = ctx.rng.choice(pool)
    ext = ctx.claim(str(ctx.rng.randint(50300, 50999)))
    item = ItemIn(
        "sdp", ext, "ticket", f"[SDP#{ext}] {title}", body, SDP + ext, start_at=ctx.now,
        sla_due_at=ctx.later(ctx.rng.choice(sla_minutes)), status="Open", priority_raw="High",
        requester=ctx.rng.choice(requesters), tags=["incident"],
    )
    return Draft("new_item", f"Ticket SDP mới: {title}", item)


def _chat(ctx: ScenarioCtx, *, key: str, pool: list[str], who: str) -> Draft:
    text = ctx.rng.choice(pool)
    item = ItemIn(
        "teams", ctx.new_id(key), "chat", f"{who}: {text}", text, TEAMS, start_at=ctx.now,
        requester=who, requester_role="manager", is_unread=True, tags=["mention"],
    )
    return Draft("new_item", f"Teams · {who}: {text}", item)


def _meeting_new(ctx: ScenarioCtx, *, key: str, pool: list[tuple[str, str]], locations: list[str]) -> Draft:
    title, body = ctx.rng.choice(pool)
    start = ctx.later(ctx.rng.choice([60, 90, 120, 180]))
    end = start + timedelta(minutes=ctx.rng.choice([30, 45, 60]))
    item = ItemIn(
        "exchange_calendar", ctx.new_id(key), "meeting", title, body, OWA, start_at=start, end_at=end,
        requester=ctx.manager, requester_role="manager", participants=[ctx.manager, ctx.user.email],
        location=ctx.rng.choice(locations),
    )
    return Draft("new_item", f"Lời mời họp {ctx.hm(start)}: {title}", item)


def _jira_new(ctx: ScenarioCtx, *, project: str, pool: list[tuple[str, str]], who: str) -> Draft:
    summary, body = ctx.rng.choice(pool)
    issue = ctx.claim(f"{project}-{ctx.rng.randint(2600, 2999)}")
    item = ItemIn(
        "jira", issue, "task", f"[{issue}] {summary}", body, JIRA + issue,
        due_at=ctx.later(ctx.rng.choice([240, 360, 480])), status="To Do", priority_raw="Highest",
        requester=who, requester_role="manager", tags=["bug"], source_updated_at=ctx.now,
    )
    return Draft("new_item", f"Jira mới (Highest): {summary}", item)


def _wiki(ctx: ScenarioCtx, *, pool: list[tuple[str, str]], who: str) -> Draft:
    title, space = ctx.rng.choice(pool)
    page_id = ctx.claim(str(ctx.rng.randint(880100, 889999)))
    item = ItemIn(
        "confluence", page_id, "page", title, f"Không gian: {space}. Cập nhật bởi {who}, có @mention bạn.",
        WIKI + page_id, start_at=ctx.now, requester=who, tags=["mention"], source_updated_at=ctx.now,
    )
    return Draft("new_item", f"Wiki · bạn được nhắc tên: {title}", item)


# ---------------------------------------------------------------- Kịch bản "update" (cần đối tượng có sẵn)


def _sla_escalation(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.source == "sdp" and not r.done_local and r.sla_due_at
             and r.sla_due_at > ctx.now + timedelta(minutes=15)]
    if not cands:
        return None
    item = item_from_row(ctx.rng.choice(cands))
    item.sla_due_at = ctx.later(10)
    item.priority_raw = "Urgent"
    if "escalated" not in item.tags:
        item.tags = [*item.tags, "escalated"]
    return Draft("update_item", f"SLA còn 10 phút: {item.title}", item)


def _meeting_conflict(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.kind == "meeting" and not r.done_local and r.start_at and r.end_at
             and r.end_at > ctx.now + timedelta(minutes=20)]
    if not cands:
        return None
    target = ctx.rng.choice(cands)
    start = max(target.start_at, ctx.later(10))  # bắt đầu cùng lúc (hoặc giữa) họp mục tiêu -> luôn cùng ngày
    item = ItemIn(
        "exchange_calendar", ctx.new_id("meeting_conflict"), "meeting", "Họp khẩn: rà soát sự cố giao dịch",
        "Họp đột xuất về sự cố giao dịch chuyển tiền nhanh.", OWA, start_at=start, end_at=start + timedelta(minutes=30),
        requester=ctx.manager, requester_role="manager", participants=[ctx.manager, ctx.user.email],
        location="Microsoft Teams", tags=["teams"],
    )
    return Draft("new_item", f"Họp mới trùng lịch với \"{target.title}\"", item)


def _meeting_moved(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.kind == "meeting" and not r.done_local and r.start_at and r.end_at
             and r.start_at > ctx.now + timedelta(minutes=45)]
    if not cands:
        return None
    row = ctx.rng.choice(cands)
    shift = timedelta(minutes=ctx.rng.choice([30, 60, -30]))
    if row.start_at + shift < ctx.later(15):
        shift = timedelta(minutes=30)
    item = item_from_row(row)
    item.start_at, item.end_at = row.start_at + shift, row.end_at + shift
    if not item.title.startswith(MOVED_PREFIX):
        item.title = MOVED_PREFIX + item.title
    return Draft("update_item", f"Họp bị dời sang {ctx.hm(item.start_at)}: {row.title}", item)


def _jira_unblocked(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.source == "jira" and not r.done_local and (r.status or "").lower() == "blocked"]
    if not cands:
        return None
    item = item_from_row(ctx.rng.choice(cands))
    item.status = "In Progress"
    return Draft("update_item", f"Hết bị chặn, có thể làm tiếp: {item.title}", item)


# ---------------------------------------------------------------- Nội dung mẫu (hư cấu)

IT_MGR_MAIL = [
    ("Cần báo cáo tiến độ sprint 21 trước {hm}",
     "An ơi, em gửi anh burndown và các rủi ro của sprint 21 để anh báo cáo giao ban. Hạn {hm} nhé."),
    ("Rà soát giúp anh checklist release T24 trước {hm}",
     "Em rà lại checklist release R2026.10, đặc biệt phần rollback, và phản hồi anh trước {hm}."),
    ("Tổng hợp giao dịch lỗi 3 ngày gần nhất, hạn {hm}",
     "Anh cần số lượng giao dịch lỗi theo nguyên nhân trong 3 ngày qua. Gửi anh trước {hm}."),
]
IT_AUDIT_MAIL = [
    ("Đề nghị cung cấp danh sách user đặc quyền T24 trước {hm}",
     "KTNB đề nghị phòng Core Banking cung cấp danh sách user đặc quyền kèm người phê duyệt trước {hm} ngày mai."),
    ("Yêu cầu giải trình ngoại lệ phân quyền quý III, hạn {hm}",
     "Đề nghị giải trình các trường hợp cấp quyền ngoài quy trình trong quý III. Hạn {hm}."),
]
IT_VIP_MAIL = [
    ("Đối tác cần xác nhận kết quả đối soát trước {hm}",
     "Kính gửi Quý Ngân hàng, đề nghị xác nhận kết quả đối soát cho TK 9704229912345678 trước {hm}. "
     "Liên hệ kế toán trưởng: 0987654321."),
]
IT_INCIDENTS = [
    ("KH không xem được số dư trên Mobile Banking",
     "Chi nhánh Đống Đa báo: KH chủ TK 0123456789012, SĐT 0912345678 không xem được số dư từ sáng."),
    ("Lỗi timeout khi tra cứu lịch sử giao dịch",
     "Nhiều KH báo tra cứu lịch sử giao dịch quá 30 giây. Liên hệ: 0934567890."),
    ("Không in được sao kê tại quầy",
     "Chi nhánh Cầu Giấy không in được sao kê TK 0987654321098 từ 9h."),
]
BRANCHES = ["CN Đống Đa", "CN Cầu Giấy", "CN Hoàn Kiếm", "Trung tâm Dịch vụ KH"]
IT_CHAT = [
    "@An chiều nay anh cần số liệu sự cố sớm hơn dự kiến nhé",
    "@An em xem giúp anh ticket vừa lên, khách đang chờ",
    "@An nhớ cập nhật tiến độ CORE-2481 trước giờ họp CAB",
]
IT_MEETINGS = [
    ("Họp nhanh về lỗi đối soát batch", "Trao đổi phương án xử lý lỗi timeout đối soát."),
    ("Review thiết kế API tài khoản", "Rà soát tài liệu thiết kế trước khi chốt."),
    ("Đồng bộ kế hoạch release T24", "Cập nhật tiến độ và rủi ro trước CAB."),
]
IT_JIRA = [
    ("Fix lỗi sai lệch số dư sau đối soát", "Phát hiện sai lệch số dư với một số tài khoản sau batch đối soát."),
    ("Khắc phục lỗi mất kết nối cổng thanh toán", "Cổng thanh toán ngắt kết nối ngắt quãng trên môi trường UAT."),
]
IT_WIKI = [
    ("Kế hoạch Release T24 R2026.10 (cập nhật)", "Core Banking"),
    ("Hướng dẫn rollback batch đối soát", "Vận hành CNTT"),
]

RM_CUSTOMER_MAIL = [
    ("Đề nghị giải ngân đợt bổ sung trước {hm}",
     "Kính gửi Quý Ngân hàng, công ty đề nghị giải ngân vào TK 9704229912345678 trước {hm}. "
     "Liên hệ kế toán trưởng: 0987654321."),
    ("Đề nghị xác nhận số dư hạn mức trước {hm}",
     "Công ty cần Ngân hàng xác nhận số dư hạn mức còn lại trước {hm} để làm hồ sơ thầu. Liên hệ: 0987654321."),
]
RM_MGR_MAIL = [
    ("Bổ sung phụ lục tờ trình trước {hm}", "Lan bổ sung phụ lục tài sản bảo đảm vào tờ trình trước {hm} nhé."),
    ("Cập nhật số liệu dư nợ KHDN trước {hm}", "Em cập nhật dư nợ các KH trong danh mục để anh báo cáo trước {hm}."),
]
RM_INCIDENTS = [
    ("Không tải được hồ sơ tín dụng trên LOS", "Lỗi tải tệp đính kèm khi mở hồ sơ tín dụng trên LOS."),
    ("LOS báo lỗi khi in tờ trình", "Hệ thống LOS báo lỗi 500 khi in tờ trình thẩm định."),
]
RM_MEETINGS = [
    ("Gặp KH Công ty CP Thép Hoà Việt - trao đổi hạn mức", "Trao đổi nhu cầu hạn mức tín dụng Q4."),
    ("Gặp KH Công ty TNHH Nông sản Đại Phát - tài trợ xuất khẩu", "Giới thiệu gói tài trợ xuất khẩu."),
]
RM_WIKI = [
    ("Hướng dẫn thẩm định KHDN (bản cập nhật tháng 10)", "Quản lý tín dụng"),
    ("Chính sách lãi suất cho vay KHDN Q4", "Quản lý tín dụng"),
]


def _s(key: str, label: str, persona: str, source: str, weight: int, severity: str,
       build: Callable[[ScenarioCtx], Draft | None], fallback: str | None = None) -> Scenario:
    return Scenario(key, label, persona, source, weight, severity, build, fallback)


_ALL: list[Scenario] = [
    # ----- Persona IT (an.nguyen)
    _s("mail_manager_deadline", "Mail từ quản lý cần xử lý gấp", "it", "exchange_mail", 3, "warning",
       partial(_mail, key="mail_manager_deadline", pool=IT_MGR_MAIL, due_minutes=[60, 90, 120, 180])),
    _s("mail_audit_request", "Mail yêu cầu từ Kiểm toán nội bộ", "it", "exchange_mail", 1, "warning",
       partial(_mail, key="mail_audit_request", pool=IT_AUDIT_MAIL, due_minutes=[1200, 1500, 1800],
               requester="ksnb@bank.local", role="audit", tags=("flagged",),
               banner="Mail từ Kiểm toán: {subject}")),
    _s("mail_vip_customer", "Mail từ khách hàng/đối tác VIP", "it", "exchange_mail", 1, "critical",
       partial(_mail, key="mail_vip_customer", pool=IT_VIP_MAIL, due_minutes=[60, 90, 120],
               requester="ketoan@saoviet.example", role="vip_customer", tags=("important",),
               banner="Mail từ KH VIP: {subject}")),
    _s("sdp_new_incident", "Ticket SDP mới (sắp hết SLA)", "it", "sdp", 3, "critical",
       partial(_ticket, pool=IT_INCIDENTS, sla_minutes=[60, 75, 90], requesters=BRANCHES)),
    _s("sdp_sla_escalation", "Ticket SDP sắp vi phạm SLA", "it", "sdp", 1, "critical",
       _sla_escalation, fallback="sdp_new_incident"),
    _s("teams_mention", "@mention trên Teams", "it", "teams", 2, "info",
       partial(_chat, key="teams_mention", pool=IT_CHAT, who="Trần Minh")),
    _s("meeting_new", "Lời mời họp mới", "it", "exchange_calendar", 2, "info",
       partial(_meeting_new, key="meeting_new", pool=IT_MEETINGS, locations=["Microsoft Teams", "P.1203", "P.805"])),
    _s("meeting_conflict", "Họp mới trùng lịch", "it", "exchange_calendar", 1, "warning",
       _meeting_conflict, fallback="meeting_new"),
    _s("meeting_moved", "Họp bị dời giờ", "it", "exchange_calendar", 1, "warning",
       _meeting_moved, fallback="meeting_new"),
    _s("jira_assigned_highest", "Jira mới mức Highest gán cho bạn", "it", "jira", 2, "warning",
       partial(_jira_new, project="CORE", pool=IT_JIRA, who="Trần Minh")),
    _s("jira_unblocked", "Jira hết bị chặn", "it", "jira", 1, "info",
       _jira_unblocked, fallback="jira_assigned_highest"),
    _s("confluence_mention", "@mention trong trang wiki", "it", "confluence", 1, "info",
       partial(_wiki, pool=IT_WIKI, who="Trần Minh")),
    # ----- Persona RM (lan.pham)
    _s("rm_mail_customer_disbursement", "Mail KH đề nghị giải ngân", "rm", "exchange_mail", 3, "critical",
       partial(_mail, key="rm_mail_customer_disbursement", pool=RM_CUSTOMER_MAIL, due_minutes=[60, 90, 120],
               requester="ketoan@saoviet.example", role="vip_customer", tags=("important",),
               banner="Mail từ KH VIP: {subject}")),
    _s("rm_mail_manager_deadline", "Mail từ quản lý cần xử lý gấp", "rm", "exchange_mail", 2, "warning",
       partial(_mail, key="rm_mail_manager_deadline", pool=RM_MGR_MAIL, due_minutes=[60, 120, 180])),
    _s("rm_sdp_los_incident", "Ticket LOS mới", "rm", "sdp", 2, "warning",
       partial(_ticket, pool=RM_INCIDENTS, sla_minutes=[90, 120, 180], requesters=["Phạm Thị Lan"])),
    _s("rm_meeting_new", "Lời mời gặp khách hàng", "rm", "exchange_calendar", 2, "info",
       partial(_meeting_new, key="rm_meeting_new", pool=RM_MEETINGS, locations=["Văn phòng KH", "P.902"])),
    _s("rm_meeting_moved", "Cuộc họp bị dời giờ", "rm", "exchange_calendar", 1, "warning",
       _meeting_moved, fallback="rm_meeting_new"),
    _s("rm_confluence_policy_mention", "@mention trong chính sách tín dụng", "rm", "confluence", 1, "info",
       partial(_wiki, pool=RM_WIKI, who="Phòng QLTD")),
]

SCENARIOS: dict[str, Scenario] = {s.key: s for s in _ALL}


def scenarios_for(persona: str) -> list[Scenario]:
    return [s for s in _ALL if s.persona == persona]
