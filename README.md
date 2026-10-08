# AI Work Hub

Trợ lý công việc thông minh trên di động cho cán bộ nhân viên ngân hàng (và doanh nghiệp nói chung).
App gom lịch họp, email, Jira, Confluence, ServiceDesk Plus và Teams về một nơi. AI sắp xếp thứ tự ưu tiên,
nhắc đúng lúc và tóm tắt công việc mỗi sáng.

| Thành phần | Công nghệ | Thư mục |
|---|---|---|
| App di động | Flutter 3.47 (Dart 3.13), Riverpod 3, go_router 18, Dio | `mobile/` |
| BFF / Integration Gateway | Python 3.12, FastAPI, SQLAlchemy 2, APScheduler | `backend/` |
| CSDL | PostgreSQL 16 (SQLite khi dev) | — |
| AI | LLM on-prem theo chuẩn OpenAI-compatible (vLLM / Ollama / TGI) | `backend/app/ai/` |

Chi tiết kiến trúc, mô hình phân quyền và quy tắc nhắc việc: [docs/architecture.md](docs/architecture.md).

---

## Tính năng

### Tính năng lõi
- **Smart Notification**: nhắc họp (trước N phút), việc sắp đến hạn (trước 24h và 2h), việc quá hạn, SLA sắp vi phạm hoặc đã vi phạm, tin nhắn chưa đọc từ quản lý / KH VIP / Kiểm toán, @mention, trùng lịch, ngày quá tải.
  - Có giờ yên lặng: chỉ mức khẩn mới được báo trong khung này.
  - Gom các nhắc nhỏ thành một bản tin để tránh spam.
  - Nhắc được lên lịch ngay trên máy, nên vẫn báo khi mất VPN.
- **Smart Summary (Morning Brief)**: mỗi sáng thứ 2–6 (giờ tuỳ chỉnh), app tạo bản tóm tắt gồm:
  - 3 việc nên làm trước, kèm lý do;
  - lịch họp trong ngày, hạn chót;
  - rủi ro (trùng lịch, quá hạn, SLA);
  - gợi ý hành động và khung giờ tập trung.

### Tính năng thông minh bổ sung (MVP, đã làm)
| Tính năng | Mô tả |
|---|---|
| **Priority Inbox / Top 3** | Chấm điểm 0–100 có giải thích ("Quá hạn 30 phút · Từ quản lý trực tiếp · Ưu tiên Highest") |
| **SLA Guard** | Theo dõi `due_by_time` của SDP, cảnh báo trước 2h, báo khẩn khi vi phạm |
| **Meeting Prep** | Trước giờ họp, gom ticket Jira được nêu trong thư mời, trang Confluence được dẫn, việc còn tồn với người dự họp. Gợi ý ý cần chuẩn bị và câu hỏi nên đặt |
| **Lịch thông minh** | Phát hiện họp trùng, chuỗi họp liền nhau, ngày quá tải (≥ 65% giờ làm), gợi ý khung giờ tập trung ≥ 90 phút |
| **Ask AI** | Hỏi bằng tiếng Việt: "Ticket SDP nào sắp vi phạm SLA?", "Chiều nay tôi họp gì?"… |
| **Quick actions** | Vuốt để hoãn hoặc đánh dấu đã xem, hoãn nhắc 1h/3h/sáng mai, đánh dấu xong, mở link gốc |

### Backlog (đề xuất, chưa làm)
1. **Follow-up tracker**: phát hiện mail đã gửi chưa có phản hồi, hoặc cam kết trong mail ("sẽ gửi trước thứ 6"), rồi nhắc.
2. **Meeting → Action items**: đọc transcript/biên bản Teams, trích việc cần làm, đề xuất tạo Jira/SDP (người dùng duyệt trước khi tạo).
3. **Tổng kết cuối ngày và báo cáo tuần tự động** từ những việc đã xong trong Jira/SDP.
4. **Ghi ngược (write-back)**: chấp nhận/từ chối họp, chặn focus time vào lịch, chuyển trạng thái ticket. Cần quyền ghi và quy trình phê duyệt riêng.
5. **Đọc Morning Brief bằng giọng nói (TTS)** khi lái xe đi làm.

---

## Chạy nhanh (chế độ MOCK, không cần hệ thống thật)

### 1. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env              # mặc định MOCK_CONNECTORS=true, AUTH_MODE=mock
uvicorn app.main:app --reload     # API: http://localhost:8000/docs
python -m app.worker              # (cửa sổ khác) đồng bộ định kỳ, gửi nhắc, Morning Brief
pytest                            # 35 test
```
Hoặc chạy bằng Docker: `docker compose up --build` (API + worker + PostgreSQL).

Tài khoản demo: `an.nguyen / demo` (chuyên viên CNTT Core Banking) hoặc `lan.pham / demo` (RM khách hàng doanh nghiệp).
Dữ liệu mẫu được sinh theo giờ hiện tại, nên lúc nào mở app cũng có họp sắp tới, việc quá hạn và ticket vi phạm SLA.

### 2. App Flutter
```bash
cd mobile
flutter pub get
flutter test                                                     # 11 test
flutter run                                                      # Android emulator -> http://10.0.2.2:8000
flutter run --dart-define=API_BASE_URL=http://<ip-may-dev>:8000/api/v1   # máy thật
flutter build apk --dart-define=API_BASE_URL=https://aiworkhub.bank.local/api/v1
```
Bản release bắt buộc HTTPS. Bản debug Android cho phép HTTP để gọi backend dev.

---

## Kết nối hệ thống thật

Đặt `MOCK_CONNECTORS=false` và `AUTH_MODE=ldap` trong `backend/.env`, rồi cấu hình:

| Hệ thống | Cách kết nối | Biến cấu hình | Việc phía quản trị |
|---|---|---|---|
| Active Directory | LDAPS bind bằng UPN | `LDAP_URL`, `LDAP_DOMAIN`, `LDAP_BASE_DN` | Mở cổng 636 từ BFF tới DC |
| Exchange on-prem (mail + lịch) | EWS + service account **ApplicationImpersonation**, NTLM/Kerberos | `EXCHANGE_*` | Tạo Management Scope giới hạn theo group (lệnh mẫu trong `connectors/exchange_ews.py`) |
| Jira Data Center | REST v2 + PAT | `JIRA_BASE_URL`, `JIRA_TOKEN` | Service account chỉ có quyền Browse |
| Confluence Data Center | REST + CQL (`mention`, `watcher`) | `CONFLUENCE_*` | Service account chỉ đọc |
| ServiceDesk Plus on-prem | REST API v3, header `authtoken` | `SDP_*` | Technician key chỉ đọc |
| Microsoft Teams (cloud) | Microsoft Graph, client credentials | `TEAMS_ENABLED`, `GRAPH_*` | App registration + `Chat.Read.All` + egress proxy. **Mặc định tắt** |
| LLM on-prem | `POST /v1/chat/completions` | `LLM_*` | Endpoint nội bộ (vLLM/Ollama). Không có LLM thì dùng bản tóm tắt theo quy tắc |
| Push | FCM HTTP v1 (`pip install .[fcm]`) | `PUSH_*`, `FCM_*` | Egress tới `fcm.googleapis.com`. Push không chứa nội dung nghiệp vụ |

CA nội bộ: đặt `INTERNAL_CA_BUNDLE` (Jira/Confluence/SDP/LLM) và `EXCHANGE_CA_CERT_FILE` (EWS).
Proxy: `HTTPS_PROXY` cho Graph/FCM. Các hệ thống on-prem phải nằm trong `NO_PROXY`.

---

## API (tóm tắt, chi tiết tại `/docs`)

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/v1/auth/login`, `/auth/refresh` | Đăng nhập AD → JWT (access 30', refresh 8h) |
| GET | `/api/v1/today` | Dashboard: Top 3, thống kê, họp tiếp theo, hạn chót, phân tích lịch |
| GET | `/api/v1/work-items?source=&kind=&bucket=&q=` | Hộp việc ưu tiên |
| POST | `/api/v1/work-items/{id}/done` · `/undone` · `/snooze` | Thao tác cục bộ, không ghi về hệ thống gốc |
| GET | `/api/v1/alerts?scope=active\|upcoming\|all` | Nhắc việc |
| POST | `/api/v1/alerts/{id}/ack` · `/snooze` · `/alerts/ack-all` | Xử lý nhắc |
| GET/POST | `/api/v1/brief/today` · `/brief/regenerate` | Morning Brief |
| GET | `/api/v1/meetings/{id}/prep` | Meeting Prep |
| POST | `/api/v1/ask` | Ask AI |
| GET | `/api/v1/insights/calendar?day=` | Phân tích lịch theo ngày |
| GET/PUT | `/api/v1/settings` · GET `/sources` | Cài đặt cá nhân |
| POST/DELETE | `/api/v1/devices` | Đăng ký push token |
| POST | `/api/v1/sync` | Đồng bộ ngay |

---

## Bảo mật (tóm tắt)
- Mobile **không** giữ bất kỳ thông tin đăng nhập hệ thống nguồn nào. Token JWT nằm trong Keychain/Keystore. Có khoá sinh trắc học, tự khoá sau 5 phút ở nền.
- PII (số TK, số thẻ (Luhn), CCCD/CMND, SĐT, email) được **che trước khi gửi LLM** và khôi phục ở backend. Bảng ánh xạ không rời backend.
- `item_id` do LLM trả về được kiểm tra để chống bịa. Mọi lần gọi AI và truy cập đều ghi audit log, nhưng không ghi nội dung câu hỏi.
- Push và thông báo trên màn hình khoá mặc định **không chứa nội dung nghiệp vụ**.
- Connector chỉ **đọc**. "Đã xong" / "Hoãn" chỉ là trạng thái trên AI Work Hub.

## Cấu trúc thư mục
```
ai_work_hub/
├── backend/
│   ├── app/
│   │   ├── api/          # router REST: auth, work, alerts, ai, settings
│   │   ├── connectors/   # exchange_ews, jira_dc, confluence_dc, sdp, teams_graph, mock, registry
│   │   ├── services/     # priority_engine, alert_engine, calendar_insights, sync, push, brief
│   │   ├── ai/           # llm_client, pii_masker, prompts, brief_generator, ask_service, meeting_prep
│   │   ├── core/         # config, JWT, LDAP, audit
│   │   ├── db/           # SQLAlchemy models
│   │   ├── main.py       # FastAPI app
│   │   └── worker.py     # APScheduler worker
│   └── tests/
├── mobile/
│   ├── lib/
│   │   ├── app/          # app, router, theme
│   │   ├── core/         # api client, secure store, local notifications, format
│   │   ├── data/         # repository, providers
│   │   ├── domain/       # models
│   │   ├── features/     # today, notifications, brief, meeting_prep, assistant, settings, login, items
│   │   └── widgets/
│   └── test/             # contract test với fixture thật từ backend, planner, widget
├── docs/architecture.md
└── docker-compose.yml
```

## Việc cần làm trước khi lên production
- [ ] Chuyển Jira/Confluence sang OAuth 2.0 hoặc PAT cho từng người, để quyền xem dữ liệu khớp đúng quyền cá nhân (hiện dùng service account + lọc theo username).
- [ ] Tích hợp `firebase_messaging` trên app (cần `google-services.json` / `GoogleService-Info.plist`), gọi `POST /devices`.
- [ ] Alembic migration thay cho `create_all`. Retention policy cho `work_items` và `audit_logs`.
- [ ] Mã hoá cột `preview` (pgcrypto / TDE). Rate limit ở API gateway thay cho bộ đếm trong bộ nhớ.
- [ ] Distributed lock nếu chạy nhiều worker. Đăng ký app vào MDM, bật certificate pinning.
- [ ] Đánh giá bảo mật (pentest) và đánh giá tác động xử lý dữ liệu cá nhân theo quy định hiện hành về bảo vệ dữ liệu cá nhân (Luật Bảo vệ dữ liệu cá nhân và văn bản hướng dẫn), cùng chính sách ATTT nội bộ của ngân hàng.
