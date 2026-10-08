# Bộ phát sự kiện giả lập realtime (Live Event Simulator)

Ngày: 2026-10-08 · Trạng thái: chờ duyệt spec

## 1. Mục tiêu

Ở chế độ `MOCK_CONNECTORS=true`, dữ liệu mới (mail, ticket, mention, họp, ...) xuất hiện **ngay khi người dùng đang dùng app mobile**, không cần kéo-làm-mới hay đợi chu kỳ sync 5 phút. Mỗi sự kiện đi qua đúng đường ống thật: upsert `WorkItem` → chấm điểm ưu tiên → sinh `Alert` → app làm mới và báo cho người dùng.

### Tiêu chí thành công
- Khi app đang mở và mô phỏng bật, cứ ~30–90 giây có một mục mới xuất hiện trên Today / Thông báo, kèm banner trong app, trong vòng ≤ ~10 giây kể từ lúc backend phát.
- Bấm "Phát sự kiện ngay" trong Settings tạo sự kiện trong vòng vài giây, kể cả khi không chạy worker.
- Dữ liệu giả lập **không bị xoá** bởi lần sync kế tiếp.
- Ngoài chế độ mock, toàn bộ endpoint mới trả 404 và không có UI mô phỏng.

### Ngoài phạm vi (YAGNI)
- SSE / WebSocket / FCM thật. Dùng polling.
- Các tính năng backlog trong README (Follow-up tracker, Meeting → Action items, báo cáo tuần, write-back, TTS).
- Hỗ trợ connector thật phát feed sự kiện.
- Alembic migration (dự án đang dùng `create_all`).

## 2. Hiện trạng liên quan

- [mock.py](../../../backend/app/connectors/mock.py): `MockConnector.fetch` không có trạng thái, luôn trả cùng dataset dịch theo giờ hiện tại.
- [sync_service.py](../../../backend/app/services/sync_service.py) `sync_user` xoá mọi `WorkItem` mà connector không trả về → dữ liệu bơm trực tiếp vào DB sẽ mất sau lần sync tới.
- [worker.py](../../../backend/app/worker.py): APScheduler, sync mỗi `SYNC_INTERVAL_MINUTES` (5), dispatch nhắc mỗi 1 phút.
- Mobile ([providers.dart](../../../mobile/lib/data/providers.dart)): các `FutureProvider.autoDispose`, chỉ làm mới khi app resume hoặc sau thao tác người dùng. Không có kênh realtime.

## 3. Thiết kế backend

### 3.1 Bảng `live_events` (model `LiveEvent` trong `db/models.py`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int PK autoincrement | Con trỏ cho `since` |
| `username` | FK `users.username`, index | |
| `type` | str(16) | `new_item` \| `update_item` |
| `scenario` | str(48) | Khoá kịch bản, ví dụ `mail_manager_deadline` |
| `source` | str(32) | Nguồn của item |
| `severity` | str(16) | `info` \| `warning` \| `critical` (để app chọn màu banner) |
| `title` | str(512) | Tiêu đề hiển thị trên banner |
| `external_id` | str(512) | Khoá item theo `(source, external_id)` |
| `payload` | JSON | Các trường `ItemIn`; trường thời gian lưu dạng offset phút so với `created_at` (xem 3.3) |
| `created_at` | UTCDateTime | |

Một bảng làm hai việc: **feed cho app** và **trạng thái bền của mock**.
Giữ tối đa 200 dòng gần nhất mỗi user (xoá dòng cũ khi `emit`).

### 3.2 `UserSettings.live_sim_enabled`

Cột bool, mặc định `True`. Đi qua `GET/PUT /settings` có sẵn (thêm vào schema `UserSettings` ở `schemas.py`).

`init_db()` bổ sung bước **chỉ cho dev**: nếu bảng `user_settings` chưa có cột này thì chạy `ALTER TABLE ... ADD COLUMN`. Cần vì DB SQLite hiện có sẽ không tự có cột mới.

### 3.3 `MockConnector` giữ được sự kiện

`MockConnector.fetch(ctx, now)` = dataset gốc + các `ItemIn` dựng lại từ `live_events` của user (theo thứ tự `id`). Với cùng `(source, external_id)`, dòng sau ghi đè dòng trước (cách `update_item` hoạt động). Chỉ trả các item của `self.source`.

Connector cần đọc DB: nhận một `session_factory` qua constructor (`build_connectors` truyền `SessionLocal`). Chỉ dùng ở nhánh mock.

Thời gian: `payload` lưu các trường thời gian dạng **offset phút so với `created_at`** (ví dụ `due_in_minutes`, `sla_in_minutes`, `start_in_minutes`, `end_in_minutes`). Khi dựng lại, `thời điểm tuyệt đối = created_at + offset`. Kết quả: item vừa phát và item được dựng lại sau mỗi lần sync có cùng mốc giờ, không bị trôi theo "bây giờ".

### 3.4 `services/simulator.py`

```
emit(db, user, scenario: str | None = None, now=None) -> LiveEvent
```
1. Chọn kịch bản: `scenario` nếu được truyền (sai tên → `ValueError`, API trả 422), ngược lại chọn ngẫu nhiên có trọng số trong danh mục của persona (`lan.pham` → bộ RM, còn lại → bộ IT).
2. Dựng `ItemIn` từ template (điền tên, số ticket tăng dần theo user, mốc giờ).
3. Ghi `LiveEvent`, cắt về 200 dòng.
4. Upsert `WorkItem` ngay bằng các trường trong `UPDATABLE_FIELDS` (không đợi sync).
5. Gọi `recompute(db, user, now)` để chấm điểm và sinh `Alert`.
6. Trả `LiveEvent`.

Dữ liệu đều hư cấu. Một số template cố ý chứa số tài khoản / SĐT giả để thử PII masker.

### 3.5 Danh mục kịch bản

| Khoá | Nguồn | Loại event | Hiệu ứng |
|---|---|---|---|
| `mail_manager_deadline` | exchange_mail | new | Mail từ quản lý, hạn trong 1–3 giờ |
| `mail_audit_request` | exchange_mail | new | Mail từ KTNB, hạn ngày mai |
| `mail_vip_customer` | exchange_mail | new | Mail KH VIP có số TK/SĐT giả, hạn trong ngày |
| `sdp_new_incident` | sdp | new | Ticket mới, SLA còn 60–90 phút |
| `sdp_sla_escalation` | sdp | update | Ticket hiện có bị kéo SLA về còn ~10 phút |
| `teams_mention` | teams | new | @mention từ quản lý |
| `meeting_new` | exchange_calendar | new | Họp mới trong ngày |
| `meeting_conflict` | exchange_calendar | new | Họp mới cố ý trùng một họp có sẵn → alert trùng lịch |
| `meeting_moved` | exchange_calendar | update | Dời giờ một họp sắp tới |
| `jira_assigned_highest` | jira | new | Ticket Highest gán cho user |
| `jira_unblocked` | jira | update | Ticket Blocked chuyển sang In Progress |
| `confluence_mention` | confluence | new | @mention trong trang wiki |

Kịch bản `update` chọn đối tượng từ item đang có của user (dataset gốc hoặc item đã phát). Nếu không có đối tượng phù hợp thì rơi về một kịch bản `new` cùng nguồn.

Persona RM (`lan.pham`) dùng cùng cơ chế với danh mục riêng gồm 6 kịch bản: `rm_mail_customer_disbursement` (mail KH VIP đề nghị giải ngân, có số TK giả), `rm_mail_manager_deadline`, `rm_sdp_los_incident`, `rm_meeting_new`, `rm_meeting_moved`, `rm_confluence_policy_mention`.

### 3.6 Kích hoạt tự động (worker)

Job `job_sim_tick` trong [worker.py](../../../backend/app/worker.py), interval 10 giây, `max_instances=1`, `coalesce=True`, **chỉ đăng ký khi `mock_connectors`**.

Mỗi tick: với mỗi user hoạt động (`last_login_at` trong `ACTIVE_USER_DAYS`) và `live_sim_enabled=True`, nếu `now >= next_due[username]` thì `emit` rồi đặt `next_due = now + uniform(30, 90)s`. `next_due` giữ trong bộ nhớ worker (mất khi khởi động lại là chấp nhận được; lần đầu `next_due` = now + 10–30s). Lỗi của một user được log và không chặn user khác.

### 3.7 Kích hoạt thủ công và endpoint

Router mới `api/sim.py`, mount cùng prefix `/api/v1`. Mọi endpoint dùng dependency chung `require_mock` trả **404** khi `mock_connectors=false`.

| Method | Path | Mô tả |
|---|---|---|
| GET | `/events?since=<id>&limit=50` | Sự kiện của user có `id > since`, tăng dần. Thiếu `since` → chỉ trả `{"events": [], "latest_id": N}` để app lấy con trỏ. Luôn kèm `latest_id`. |
| POST | `/sim/emit` | Body tuỳ chọn `{"scenario": "..."}`. Phát một sự kiện ngay, trả sự kiện đó. |
| GET | `/sim/scenarios` | Danh sách khoá + nhãn tiếng Việt cho persona của user (cho picker trong Settings). |
| POST | `/sim/reset` | Xoá `live_events` của user và các `WorkItem` do sim tạo, rồi `recompute`. |

`POST /sim/emit` chạy `emit` trong tiến trình API và dùng chung DB với worker nên không cần IPC. Ghi `audit` cho `sim_emit` và `sim_reset`, **không** ghi nội dung item.

Response `LiveEventOut`: `id, type, scenario, source, severity, title, work_item_id, created_at`. **Không** trả `payload`.

### 3.8 Xử lý lỗi và an toàn
- Kịch bản không tồn tại → 422. Chế độ không mock → 404.
- `emit` chạy trong một transaction. Lỗi → rollback, không để lại `live_events` mồ côi so với `work_items`.
- Dữ liệu giả lập chỉ nằm trong DB dev/mock. `sim` không bao giờ được đăng ký ngoài mock nên không thể rò sang môi trường thật.

## 4. Thiết kế mobile

- **Model** `LiveEvent` trong [models.dart](../../../mobile/lib/domain/models.dart): `id, type, scenario, source, severity, title, workItemId, createdAt`. Cộng `SimScenario(key, label)`.
- **Repository** ([repository.dart](../../../mobile/lib/data/repository.dart)): `liveEvents({int? since})` trả `(events, latestId)`; `simEmit({String? scenario})`; `simScenarios()`; `simReset()`. Gặp 404 thì `liveEvents` ném `SimUnavailable` để UI ẩn tính năng.
- **`LiveEventsController`** (Riverpod `Notifier`, trong `providers.dart` hoặc file riêng `data/live_events.dart`):
  - Chỉ chạy khi `AuthStatus.signedIn` **và** app ở foreground. Dừng ở `paused`, tiếp tục ở `resumed` (nối vào `didChangeAppLifecycleState` trong [app.dart](../../../mobile/lib/app/app.dart)).
  - Lần đầu: gọi `/events` không `since` để lấy `latest_id` làm con trỏ (không phát lại lịch sử).
  - Sau đó poll mỗi **8 giây** với `since=con trỏ`. Lỗi mạng → bỏ qua nhịp đó, tăng giãn cách tối đa 30 giây, về 8 giây khi thành công. 404 → tự dừng.
  - Có sự kiện mới → `refreshWorkData(ref)` (invalidate Today / Alerts / Brief và `resync()` lịch nhắc cục bộ), cập nhật con trỏ, đẩy sự kiện vào luồng cho banner.
- **Banner trong app:** dùng `ScaffoldMessenger` toàn cục (`GlobalKey` gắn vào `MaterialApp.router`). Hiển thị tiêu đề sự kiện, màu theo `severity`; chạm để mở item sheet của `workItemId`. Gom nhiều sự kiện đến cùng lúc thành một banner ("3 mục mới").
- **Settings** ([settings_screen.dart](../../../mobile/lib/features/settings/settings_screen.dart)): mục "Dữ liệu giả lập" gồm công tắc `live_sim_enabled`, nút **"Phát sự kiện ngay"**, picker kịch bản (tuỳ chọn), nút "Đặt lại dữ liệu giả lập". Mục chỉ hiện khi `liveEvents` không ném `SimUnavailable`.
- Các màn hình hiện có không đổi, chúng tự cập nhật nhờ invalidate provider.

## 5. Kiểm thử

### Backend (pytest)
- `emit` tạo `LiveEvent`, `WorkItem` và sinh `Alert` khi kịch bản đủ điều kiện (ví dụ `sdp_sla_escalation`, `meeting_conflict`).
- Item do sim tạo **còn nguyên sau `sync_user`**. Kiểm thử trực tiếp lỗi xoá ở [sync_service.py:118](../../../backend/app/services/sync_service.py#L118).
- `update_item` ghi đè đúng item, không tạo bản sao.
- `GET /events`: `since` cắt đúng; thiếu `since` trả `latest_id` mà không trả lịch sử; cô lập giữa hai user.
- Giữ tối đa 200 dòng / user.
- Kịch bản sai tên → 422. `mock_connectors=false` → 404 cho cả 4 endpoint.
- `POST /sim/reset` đưa dữ liệu về dataset gốc.
- `init_db` thêm cột `live_sim_enabled` vào DB cũ chưa có cột.
- Test tick của worker: user tắt `live_sim_enabled` không nhận sự kiện (tách phần chọn user ra hàm thuần để test).

### Mobile
- Fixture `test/fixtures/events.json` sinh từ backend thật (cùng cách các fixture hiện có), thêm vào `models_test.dart`.
- Test `LiveEventsController` với repository giả: lấy con trỏ lần đầu mà không phát sự kiện cũ; có sự kiện → invalidate provider và đẩy lên luồng banner; 404 → dừng; tạm dừng khi `paused`.

### Xác minh thủ công
Chạy backend + worker + app, quan sát sự kiện tự đến, bấm "Phát sự kiện ngay", tắt công tắc để xác nhận dừng, kiểm tra banner và mở item.

## 6. Rủi ro và quyết định đã chốt

- **Không dùng SSE/WebSocket:** polling 8 giây đủ cảm giác realtime cho mock và bền hơn khi mất mạng / refresh token.
- **Cột mới không có Alembic:** xử lý bằng `ALTER TABLE` lúc khởi động, chỉ cho dev. Production không dùng mock nên không bị ảnh hưởng.
- **Mô phỏng tự động cần worker:** thiếu worker thì chỉ còn nút thủ công. Ghi rõ trong README.
- **Nhiều worker:** `next_due` trong bộ nhớ sẽ nhân đôi sự kiện. Chấp nhận được vì README đã quy định chỉ chạy 1 worker.
- **Dữ liệu cũ trôi theo thời gian:** xử lý bằng mốc thời gian lưu dạng offset so với `created_at` (mục 3.3).

## 7. Tài liệu cần cập nhật
- README: mục "Chạy nhanh" thêm giải thích mô phỏng realtime, cách bật/tắt, endpoint `/events` và `/sim/*`.
- `docs/architecture.md`: thêm luồng sự kiện giả lập.
