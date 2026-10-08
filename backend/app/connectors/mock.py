"""Dữ liệu mẫu theo ngữ cảnh ngân hàng, sinh tương đối theo thời điểm hiện tại.

Dùng khi MOCK_CONNECTORS=true để chạy end-to-end mà không cần Exchange/Jira/SDP thật.
Tên công ty, khách hàng, số tài khoản đều là hư cấu.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.connectors.base import Connector, ItemIn, UserContext


def _clock(now: datetime, tz):  # noqa: ANN001
    local = now.astimezone(tz)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)

    def at(day: int, h: int, m: int = 0) -> datetime:
        return midnight + timedelta(days=day, hours=h, minutes=m)

    return at, local.strftime("%Y%m%d")


def _it_dataset(ctx: UserContext, now: datetime, tz) -> list[ItemIn]:  # noqa: ANN001
    at, day = _clock(now, tz)
    mgr = ctx.manager_email or "minh.tran@bank.local"
    team = ["minh.tran@bank.local", "hoa.do@bank.local", "tuan.vu@bank.local", ctx.email]
    return [
        # ---------- Lịch họp ----------
        ItemIn("exchange_calendar", f"cal-standup-{day}", "meeting", "Daily stand-up Core Banking",
               "Cập nhật tiến độ sprint 21. Link họp Microsoft Teams.", "https://mail.bank.local/owa/",
               start_at=at(0, 8, 30), end_at=at(0, 8, 45), requester=mgr, requester_role="manager",
               participants=team, location="Microsoft Teams", tags=["teams"]),
        ItemIn("exchange_calendar", f"cal-cab-{day}", "meeting", "Họp CAB - phê duyệt Release T24 R2026.10",
               "Rà soát change request cho đợt release cuối tháng. Tài liệu: trang Confluence 'Kế hoạch Release "
               "T24 R2026.10'. Các thay đổi liên quan CORE-2481, CORE-2455. Yêu cầu mỗi nhóm trình bày rủi ro "
               "và phương án rollback.", "https://mail.bank.local/owa/",
               start_at=at(0, 9, 30), end_at=at(0, 11, 0), requester=mgr, requester_role="manager",
               participants=team + ["cab@bank.local", "ops.lead@bank.local"], location="P.1203 - Hội sở"),
        ItemIn("exchange_calendar", f"cal-interview-{day}", "meeting", "Phỏng vấn ứng viên Backend Developer",
               "Vòng kỹ thuật. CV đính kèm trong mail của Phòng Nhân sự.", "https://mail.bank.local/owa/",
               start_at=at(0, 10, 30), end_at=at(0, 11, 30), requester="tuyendung@bank.local",
               participants=["tuyendung@bank.local", ctx.email], location="P.805"),
        ItemIn("exchange_calendar", f"cal-audit-{day}", "meeting", "Làm việc với Kiểm toán nội bộ về phân quyền hệ thống T24",
               "KTNB đề nghị giải trình danh sách user đặc quyền và log truy cập quý III.",
               "https://mail.bank.local/owa/", start_at=at(0, 14, 0), end_at=at(0, 15, 0),
               requester="ksnb@bank.local", requester_role="audit",
               participants=["ksnb@bank.local", mgr, ctx.email], location="P.1501"),
        ItemIn("exchange_calendar", f"cal-demo-{day}", "meeting", "Demo API Open Banking cho Khối Bán lẻ",
               "Demo luồng liên kết tài khoản và truy vấn số dư. Liên quan OPB-118.", "https://mail.bank.local/owa/",
               start_at=at(0, 15, 0), end_at=at(0, 16, 0), requester=ctx.email, is_organizer=True,
               participants=[ctx.email, "retail.pm@bank.local", mgr], location="Microsoft Teams", tags=["teams"]),
        ItemIn("exchange_calendar", f"cal-11-{day}", "meeting", "1:1 với anh Minh",
               "Trao đổi mục tiêu Q4.", "https://mail.bank.local/owa/",
               start_at=at(0, 16, 0), end_at=at(0, 16, 30), requester=mgr, requester_role="manager",
               participants=[mgr, ctx.email], location="P.1201"),
        ItemIn("exchange_calendar", f"cal-uat-{day}", "meeting", "Họp UAT tính năng chuyển tiền nhanh 24/7",
               "Nghiệm thu kịch bản UAT đợt 2.", "https://mail.bank.local/owa/",
               start_at=at(1, 9, 0), end_at=at(1, 10, 30), requester="qa.lead@bank.local",
               participants=team + ["qa.lead@bank.local"], location="P.1203"),
        ItemIn("exchange_calendar", f"cal-sec-{day}", "meeting", "Đào tạo bắt buộc: An toàn thông tin Q4",
               "", "https://mail.bank.local/owa/", start_at=at(1, 14, 0), end_at=at(1, 15, 0),
               requester="attt@bank.local", location="Hội trường tầng 3"),
        # ---------- Email ----------
        ItemIn("exchange_mail", f"mail-mgr-{day}", "email", "Cần số liệu sự cố tháng 9 trước 15h hôm nay",
               "An ơi, em tổng hợp giúp anh số liệu sự cố tháng 9 (số lượng, MTTR, nguyên nhân chính) để anh báo "
               "cáo Ban điều hành. Hạn 15h hôm nay nhé.", "https://mail.bank.local/owa/",
               start_at=now - timedelta(minutes=50), due_at=at(0, 15, 0), requester=mgr, requester_role="manager",
               is_unread=True, tags=["important", "flagged"]),
        ItemIn("exchange_mail", f"mail-ktnb-{day}", "email", "Yêu cầu cung cấp log truy cập hệ thống T24 quý III",
               "Đề nghị phòng Core Banking cung cấp log truy cập của các user đặc quyền trước 17h ngày mai.",
               "https://mail.bank.local/owa/", start_at=now - timedelta(hours=3), due_at=at(1, 17, 0),
               requester="ksnb@bank.local", requester_role="audit", is_unread=True, tags=["flagged"]),
        ItemIn("exchange_mail", f"mail-vendor-{day}", "email", "Temenos Support: hotfix cho lỗi đối soát batch",
               "Hotfix HF-2026-0931 đã sẵn sàng, đề nghị ngân hàng cài trên môi trường UAT để xác nhận.",
               "https://mail.bank.local/owa/", start_at=now - timedelta(hours=5),
               requester="support@temenos-partner.example", requester_role="external", is_unread=True),
        ItemIn("exchange_mail", f"mail-peer-{day}", "email", "Góp ý tài liệu thiết kế API tài khoản",
               "Mình đã comment một số điểm trong tài liệu, An xem giúp nhé.", "https://mail.bank.local/owa/",
               start_at=now - timedelta(hours=20), requester="hoa.do@bank.local", is_unread=True),
        # ---------- Jira ----------
        ItemIn("jira", "CORE-2481", "task", "[CORE-2481] Fix lỗi timeout khi đối soát giao dịch chuyển tiền nhanh",
               "Batch đối soát cuối ngày bị timeout khi số giao dịch > 2 triệu. Cần tối ưu truy vấn.",
               "https://jira.bank.local/browse/CORE-2481", due_at=at(0, 17, 30), status="In Progress",
               priority_raw="Highest", requester="Trần Minh", requester_role="manager", tags=["bug"],
               source_updated_at=now - timedelta(hours=2)),
        ItemIn("jira", "CORE-2455", "task", "[CORE-2455] Nâng cấp thư viện logging trên batch server",
               "Đang chờ hạ tầng cấp quyền deploy lên server batch.", "https://jira.bank.local/browse/CORE-2455",
               due_at=at(-1, 17, 30), status="Blocked", priority_raw="High", requester="Đỗ Hoa",
               tags=["security"]),
        ItemIn("jira", "OPB-118", "task", "[OPB-118] Chuẩn bị tài liệu API cho buổi demo Open Banking",
               "Bổ sung sequence diagram và Postman collection.", "https://jira.bank.local/browse/OPB-118",
               due_at=at(0, 14, 30), status="To Do", priority_raw="High", requester="Trần Minh",
               requester_role="manager", tags=["story"]),
        ItemIn("jira", "CORE-2502", "task", "[CORE-2502] Viết unit test cho module tính lãi tiền gửi",
               "", "https://jira.bank.local/browse/CORE-2502", due_at=at(3, 17, 30), status="To Do",
               priority_raw="Medium", requester="Vũ Tuấn", tags=["task"]),
        # ---------- Confluence ----------
        ItemIn("confluence", "880011", "page", "Kế hoạch Release T24 R2026.10",
               "Không gian: Core Banking. Cập nhật bởi Trần Minh — có @mention bạn ở mục rollback.",
               "https://wiki.bank.local/pages/viewpage.action?pageId=880011", requester="Trần Minh",
               tags=["mention"], start_at=now - timedelta(hours=1), source_updated_at=now - timedelta(hours=1)),
        ItemIn("confluence", "880042", "page", "Quy trình xử lý sự cố mức 1 (v3.2)",
               "Không gian: Vận hành CNTT. Cập nhật bởi Lê Ops.",
               "https://wiki.bank.local/pages/viewpage.action?pageId=880042", requester="Lê Ops",
               tags=["watching"], start_at=now - timedelta(hours=18), source_updated_at=now - timedelta(hours=18)),
        # ---------- SDP ----------
        ItemIn("sdp", "50231", "ticket", "[SDP#50231] KH không chuyển được tiền liên ngân hàng từ app",
               "Chi nhánh Hoàn Kiếm báo: KH chủ TK 0123456789012, SĐT 0912345678 chuyển tiền bị lỗi E-504 "
               "từ 8h sáng.", "https://sdp.bank.local/WorkOrder.do?woMode=viewWO&woID=50231",
               sla_due_at=now + timedelta(minutes=95), status="In Progress", priority_raw="High",
               requester="CN Hoàn Kiếm", tags=["incident"], start_at=now - timedelta(hours=2)),
        ItemIn("sdp", "50198", "ticket", "[SDP#50198] Lỗi hiển thị sao kê PDF trên Mobile Banking",
               "Một số KH không xem được sao kê tháng 9.", "https://sdp.bank.local/WorkOrder.do?woMode=viewWO&woID=50198",
               sla_due_at=now - timedelta(minutes=30), status="Open", priority_raw="Medium",
               requester="Trung tâm Dịch vụ KH", tags=["incident", "overdue"], start_at=now - timedelta(days=1)),
        ItemIn("sdp", "50240", "ticket", "[SDP#50240] Cấp quyền truy cập môi trường UAT cho nhân sự mới",
               "", "https://sdp.bank.local/WorkOrder.do?woMode=viewWO&woID=50240",
               sla_due_at=at(2, 17, 0), status="Open", priority_raw="Low", requester="Vũ Tuấn",
               tags=["request"], start_at=now - timedelta(hours=4)),
        # ---------- Teams ----------
        ItemIn("teams", f"chat-demo-{day}", "chat", "Trần Minh: @An chiều nay demo nhớ chuẩn bị môi trường nhé",
               "@An chiều nay demo Open Banking nhớ chuẩn bị môi trường sandbox và dữ liệu test nhé.",
               "https://teams.microsoft.com/", start_at=now - timedelta(minutes=20), requester="Trần Minh",
               requester_role="manager", is_unread=True, tags=["mention"]),
    ]


def _rm_dataset(ctx: UserContext, now: datetime, tz) -> list[ItemIn]:  # noqa: ANN001
    at, day = _clock(now, tz)
    mgr = ctx.manager_email or "hung.le@bank.local"
    return [
        ItemIn("exchange_calendar", f"rm-kh-{day}", "meeting", "Gặp KH Công ty TNHH Dệt may Sao Việt - gia hạn hạn mức",
               "Trao đổi nhu cầu gia hạn hạn mức tín dụng 50 tỷ và tài trợ xuất khẩu Q4.",
               "https://mail.bank.local/owa/", start_at=at(0, 9, 0), end_at=at(0, 10, 0),
               requester=ctx.email, is_organizer=True,
               participants=[ctx.email, "ketoan@saoviet.example"], location="Văn phòng KH - Q.Cầu Giấy"),
        ItemIn("exchange_calendar", f"rm-giaoban-{day}", "meeting", "Giao ban Khối KHDN", "",
               "https://mail.bank.local/owa/", start_at=at(0, 11, 0), end_at=at(0, 11, 30),
               requester=mgr, requester_role="manager", participants=[mgr, ctx.email], location="P.902"),
        ItemIn("exchange_calendar", f"rm-hdtd-{day}", "meeting", "Hội đồng tín dụng - hồ sơ Dệt may Sao Việt",
               "Trình hồ sơ gia hạn hạn mức. Cần tờ trình bản cuối.", "https://mail.bank.local/owa/",
               start_at=at(0, 14, 0), end_at=at(0, 15, 30), requester=mgr, requester_role="manager",
               participants=[mgr, ctx.email, "qltd@bank.local"], location="P.1501"),
        ItemIn("exchange_mail", f"rm-mail-kh-{day}", "email", "Đề nghị giải ngân lô hàng xuất khẩu tháng 10",
               "Kính gửi Quý Ngân hàng, công ty đề nghị giải ngân vào TK 9704229912345678 trước 16h hôm nay. "
               "Liên hệ kế toán trưởng: 0987654321.", "https://mail.bank.local/owa/",
               start_at=now - timedelta(minutes=35), due_at=at(0, 16, 0), requester="ketoan@saoviet.example",
               requester_role="vip_customer", is_unread=True, tags=["important"]),
        ItemIn("exchange_mail", f"rm-mail-mgr-{day}", "email", "Bổ sung tờ trình trước 11h",
               "Lan bổ sung phần phân tích dòng tiền vào tờ trình Sao Việt trước 11h nhé.",
               "https://mail.bank.local/owa/", start_at=now - timedelta(hours=1), due_at=at(0, 11, 0),
               requester=mgr, requester_role="manager", is_unread=True, tags=["flagged"]),
        ItemIn("jira", "KHDN-77", "task", "[KHDN-77] Cập nhật hồ sơ KYC định kỳ cho 5 KH doanh nghiệp",
               "", "https://jira.bank.local/browse/KHDN-77", due_at=at(2, 17, 30), status="In Progress",
               priority_raw="Medium", requester="Lê Hùng", requester_role="manager"),
        ItemIn("confluence", "770120", "page", "Chính sách tín dụng KHDN 2026 (bản cập nhật tháng 10)",
               "Không gian: Quản lý tín dụng. Có @mention bạn.", "https://wiki.bank.local/pages/viewpage.action?pageId=770120",
               requester="Phòng QLTD", tags=["mention"], start_at=now - timedelta(hours=6)),
        ItemIn("sdp", "50277", "ticket", "[SDP#50277] Không đăng nhập được hệ thống LOS",
               "Lỗi tài khoản bị khoá sau khi đổi mật khẩu.", "https://sdp.bank.local/WorkOrder.do?woMode=viewWO&woID=50277",
               sla_due_at=now + timedelta(hours=3), status="Assigned", priority_raw="High",
               requester=ctx.display_name, tags=["incident"], start_at=now - timedelta(hours=1)),
    ]


def mock_dataset(ctx: UserContext, now: datetime, tz) -> list[ItemIn]:  # noqa: ANN001
    if ctx.username == "lan.pham":
        return _rm_dataset(ctx, now, tz)
    return _it_dataset(ctx, now, tz)


class MockConnector(Connector):
    def __init__(self, source: str, tz):  # noqa: ANN001
        self.source = source
        self.tz = tz

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        return [i for i in mock_dataset(ctx, now, self.tz) if i.source == self.source]
