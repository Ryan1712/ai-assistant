# Sprint 1: Crash Reporting & Error Resilience

**Sprint**: 1 of 1 (feature change sprint — dự án đã chạy production)
**Duration**: 1 sprint (bắt đầu 2026-07-27)
**Goal**: CEO mở Swagger là biết **app đang crash vì việc gì**; và app không còn sập trắng màn — lỗi bất kỳ (nhất là chat gọi API lỗi) hiện thông báo thân thiện + tự gửi log về server.
**Status**: PLANNED

---

## Task Details

<!--
DETAILED SECTIONS: Human-readable task breakdown
Each task has deliverables, acceptance criteria, and time tracking
-->

### Task 1.U: Wireframe màn hình lỗi + bong bóng lỗi trong chat [apple-ux-wireframer]
**Status**: [COMPLETE] · **Story Points**: 2 · **Batch**: 0

**Deliverables**:
- [ ] `.project/wireframes/screens/error-fallback.md` — fallback toàn màn (ErrorBoundary gốc) + fallback nhỏ mức màn
- [ ] `.project/wireframes/screens/chat-error-bubble.md` — bong bóng "Hệ thống đang có lỗi, vui lòng thử lại." + nút Thử lại

**Acceptance Criteria**:
- [ ] Dùng token màu/spacing từ `frontend/src/ui/theme.ts`, tuân `frontend/DESIGN.md`
- [ ] Chữ tiếng Việt có dấu, giọng điệu trấn an — không lộ stack trace cho người dùng cuối
- [ ] Nêu rõ trạng thái: đang gửi lại / gửi thất bại / đã khôi phục

---

### Task 1.S: BDD scenarios + dựng nền jest-expo [google-qa-engineer]
**Status**: [COMPLETE] · **Story Points**: 5 · **Batch**: 0

**Deliverables**:
- [ ] `.project/scenarios/sprint-1/crash-logging.feature`
- [ ] `.project/scenarios/sprint-1/error-boundary.feature`
- [ ] `.project/scenarios/sprint-1/chat-error-handling.feature`
- [ ] `frontend/jest.config.js` (preset `jest-expo`) + `frontend/jest.setup.js` (mock AsyncStorage, expo-device, expo-constants, fetch)
- [ ] `frontend/package.json` — thêm devDeps + script `"test": "jest"`
- [ ] Test skeleton (đỏ): `frontend/__tests__/*.test.ts(x)`, `backend/tests/test_crash_logs_api.py`, `backend/tests/test_crash_middleware.py`

**Acceptance Criteria**:
- [ ] `npx jest --ci` chạy được (skeleton ĐỎ là đúng — dev sẽ làm xanh ở Batch 1)
- [ ] `pytest tests/ -v` không vỡ bộ test cũ

---

### Task 1.1: Bảng `crash_logs` + migration + 3 endpoint + `crash_service` [fastapi-backend-lead #1]
**Status**: [COMPLETE] · **Story Points**: 8 · **Batch**: 1

**Deliverables**:
- [ ] `backend/app/models.py` — `CrashLog`, `CrashSource`, `CrashSeverity`
- [ ] `backend/app/schemas.py` — `CrashLogIn`, `CrashLogBatchIn`, `CrashLogOut`, `CrashLogListOut`, `CrashSummaryRow`
- [ ] `backend/app/services/crash_service.py` — `ingest_batch`, `list_crashes`, `summarize`
- [ ] `backend/app/api/crash_logs.py` — POST + GET + GET /summary
- [ ] `backend/alembic/versions/*_crash_logs_table.py`
- [ ] `backend/app/main.py` — `include_router` + `add_middleware` (**chỉ task này được sửa `main.py`**)
- [ ] `openapi.json` — chạy lại `python scripts/export_openapi.py`

**Acceptance Criteria**:
- [ ] `workspace_id`/`user_id` lấy **từ JWT**, không từ body — kể cả khi client cố gửi
- [ ] GET list + summary gọi `require_ceo` **ở service layer**; user thường → 403
- [ ] Workspace A không bao giờ thấy log của workspace B
- [ ] Gửi lại cùng `client_event_id` → không tạo bản ghi trùng (ràng buộc UNIQUE ở DB)
- [ ] `message` > 2 000 ký tự / `stack` > 20 000 → server **cắt**, không 500, không lưu nguyên
- [ ] Quá 60 bản ghi/user/5 phút → 429
- [ ] `/summary` trả về nhóm theo `fingerprint`: số lần, số user bị ảnh hưởng, lần đầu, lần cuối, message mẫu

---

### Task 1.2: `CrashCaptureMiddleware` bắt unhandled exception BE [fastapi-backend-lead #2]
**Status**: [COMPLETE] · **Story Points**: 3 · **Batch**: 1

**Deliverables**:
- [ ] `backend/app/middleware/crash_capture.py` (+ `backend/app/middleware/__init__.py`)

**Acceptance Criteria**:
- [ ] Endpoint ném exception → có bản ghi `source=be_unhandled` kèm traceback, path, method
- [ ] Ghi log dùng **session DB riêng** (session của request đã hỏng sau exception)
- [ ] Việc ghi log thất bại KHÔNG được nuốt hay đổi lỗi gốc — client vẫn nhận 500
- [ ] `HTTPException` bình thường (401/403/404/422) **không** bị ghi log — chỉ lỗi thật sự chưa xử lý
- [ ] **KHÔNG sửa `main.py`** (Task 1.1 sở hữu file đó)

---

### Task 1.3: Hạ tầng `src/errors` + ErrorBoundary toàn app + Sentry [expo-mobile-lead #1]
**Status**: [NOT STARTED] · **Story Points**: 8 · **Batch**: 1 · **Wireframe**: `error-fallback.md`

**Deliverables**:
- [ ] `frontend/src/errors/`: `types.ts`, `fingerprint.ts`, `redact.ts`, `deviceInfo.ts`, `breadcrumbs.ts`, `crashReporter.ts`, `globalHandlers.ts`, `sessionSentinel.ts`, `sentry.ts`, `ErrorBoundary.tsx`, `ScreenErrorBoundary.tsx`, `index.ts`
- [ ] `frontend/App.tsx` — bọc `<ErrorBoundary>` ngoài cùng + `initSentry()` + `initGlobalHandlers()`
- [ ] `frontend/src/navigation/MainNavigator.tsx` + `AuthNavigator.tsx` — bọc `<ScreenErrorBoundary>`
- [ ] `frontend/src/auth/AuthContext.tsx` — đăng nhập xong → `crashReporter.flush()`
- [ ] `frontend/app.json` — config plugin Sentry
- [ ] `npx expo install @sentry/react-native`

**Acceptance Criteria**:
- [ ] Component con ném lỗi khi render → hiện fallback, **app không sập**, có gọi report
- [ ] Lỗi ở 1 màn chỉ giết màn đó; bấm "Thử lại" là màn đó sống lại
- [ ] Crash lúc **chưa đăng nhập** → nằm trong hàng đợi, đăng nhập xong tự gửi lên
- [ ] `crashReporter` KHÔNG BAO GIỜ ném lỗi ra ngoài (có test chứng minh, kể cả khi AsyncStorage lỗi)
- [ ] Hàng đợi tối đa 50 bản ghi (FIFO, cũ nhất bị bỏ) — không phình bộ nhớ khi mất mạng dài
- [ ] Thiếu `EXPO_PUBLIC_SENTRY_DSN` → Sentry im lặng không khởi tạo, app chạy bình thường
- [ ] `redact()` xóa `Authorization`, `refresh_token`, `password` khỏi context trước khi gửi

---

### Task 1.4: Chat báo lỗi thân thiện + `apiFetch` báo cáo lỗi API [expo-mobile-lead #2]
**Status**: [NOT STARTED] · **Story Points**: 5 · **Batch**: 1 · **Wireframe**: `chat-error-bubble.md`

**Deliverables**:
- [ ] `frontend/src/api/crashLogs.ts` — `postCrashLogs()` dùng `fetch` **trần** (không qua `apiFetch`)
- [ ] `frontend/src/api/client.ts` — `apiFetch` ghi breadcrumb + báo lỗi 5xx/timeout/mất mạng vào reporter
- [ ] `frontend/app/main/chat.tsx` — mọi đường lỗi hiện bong bóng hệ thống

**Acceptance Criteria**:
- [ ] Gửi tin nhắn mà API trả 500 → hiện **"Hệ thống đang có lỗi, vui lòng thử lại."** trong khung chat, app KHÔNG sập, KHÔNG văng ra màn login
- [ ] Mất mạng → cùng thông báo đó, có nút thử lại
- [ ] 401 → vẫn giữ nguyên luồng refresh token cũ (KHÔNG được biến thành thông báo lỗi hệ thống)
- [ ] Chỉ 5xx / timeout / lỗi mạng mới ghi log; 401/403/404/422 **không** ghi (tránh nhiễu)
- [ ] Gửi crash log thất bại KHÔNG sinh thêm crash log (không đệ quy)

---

### Task 1.D: Migration trong CD + biến môi trường Sentry [netflix-devops-engineer]
**Status**: [COMPLETE] · **Story Points**: 2 · **Batch**: 1

**Deliverables**:
- [ ] Xác nhận `.github/workflows/*` chạy `alembic upgrade head` trước khi `up` (bảng mới phải có trên VPS)
- [ ] Ghi tài liệu biến `EXPO_PUBLIC_SENTRY_DSN` cho EAS build + `eas.json`
- [ ] `.env.example` / README: biến mới + cách xem crash log

**Acceptance Criteria**:
- [ ] Deploy lên VPS không hỏng vì thiếu migration
- [ ] Không commit DSN/secret vào repo

---

## Sprint Backlog (Machine-Parseable)

<!--
IMPORTANT: This table is parsed by scripts (generate-progress-dashboard.sh)
- ID format: {sprint}.{task} (e.g., 1.1, 1.2)
- Status: empty | [IN PROGRESS] | [COMPLETE] | [BLOCKED]
- Points: 1-8 (story points)
- Assignee: Frontend | Backend | QA | DevOps | UX
- Wireframe: filename.md or -

DO NOT change column order! Scripts depend on exact format.
-->

| ID | Task | Points | Status | Assignee | Wireframe |
|----|------|--------|--------|----------|-----------|
| 1.U | Wireframe man hinh loi + bong bong loi trong chat | 2 | [COMPLETE] | UX | - |
| 1.S | BDD scenarios + dung nen jest-expo | 5 | [COMPLETE] | QA | - |
| 1.1 | Bang crash_logs + migration + 3 endpoint + crash_service | 8 | [COMPLETE] | Backend | - |
| 1.2 | CrashCaptureMiddleware bat unhandled exception BE | 3 | [COMPLETE] | Backend | - |
| 1.3 | Ha tang src/errors + ErrorBoundary toan app + Sentry | 8 | [COMPLETE] | Frontend | error-fallback.md |
| 1.4 | Chat bao loi than thien + apiFetch bao cao loi API | 5 | | Frontend | chat-error-bubble.md |
| 1.D | Migration trong CD + bien moi truong Sentry | 2 | [COMPLETE] | DevOps | - |
| 1.R | Code review toan sprint | 3 | | QA | - |
| 1.Q | QA verification: regression + coverage | 5 | | QA | - |

---

## Sprint Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 9 |
| Story Points | 41 |
| Estimated Hours | 30h |
| Actual Hours | -h |
| Velocity | -% |

| Role | Tasks | Points | Hours |
|------|-------|--------|-------|
| Frontend | 2 | 13 | 10h |
| Backend | 2 | 11 | 8h |
| QA | 3 | 13 | 10h |
| DevOps | 1 | 2 | 1h |
| UX | 1 | 2 | 1h |

---

## Definition of Done

<!--
SPRINT-SPECIFIC DoD: What THIS sprint must achieve
NOT generic checkboxes - actual testable outcomes
-->

### Functional Criteria (đúng 3 điều client yêu cầu)
- [ ] **API lưu crash log**: gọi `GET /api/v1/crash-logs/summary` bằng tài khoản CEO → thấy danh sách nhóm lỗi kèm số lần, trả lời được câu "app đang crash về việc gì"
- [ ] **ErrorBoundary bọc hết app**: lỗi render ở bất kỳ màn nào → hiện fallback, app KHÔNG sập trắng
- [ ] **Chat gọi API lỗi**: hiện "Hệ thống đang có lỗi, vui lòng thử lại." trong khung chat — KHÔNG crash, KHÔNG văng ra login
- [ ] Crash lúc chưa đăng nhập được xếp hàng và tự gửi lên sau khi đăng nhập
- [ ] Unhandled exception phía backend cũng vào chung bảng `crash_logs`
- [ ] Native crash được Sentry ghi nhận (khi đã cấu hình DSN)

### Technical Criteria
- [ ] Mọi task `[COMPLETE]` trong Sprint Backlog
- [ ] Code review LGTM từ `google-code-reviewer`
- [ ] `cd frontend && npx tsc --noEmit` — 0 lỗi
- [ ] `cd frontend && npx jest --ci` — toàn bộ XANH
- [ ] `cd backend && pytest tests/ -v` — toàn bộ XANH (gồm cả bộ test cũ, không regression)
- [ ] `openapi.json` đã export lại

### Quality Criteria
- [ ] Không có đường nào để chính lớp chống-crash gây crash (test chứng minh `crashReporter` nuốt mọi lỗi)
- [ ] Không ghi log 401/403/404/422 → bảng không bị nhiễu
- [ ] Không có token/mật khẩu trong `context` của bất kỳ bản ghi nào
- [ ] Chạy app thật trên simulator: client tự tay thấy 3 kịch bản ở trên

---

## Dependencies

<!--
NOTE: Use "Task X.Y" format (not bare "X.Y") to avoid false parsing by progress scripts
-->

| Dependency | Reason | Status |
|------------|--------|--------|
| Task 1.S → Task 1.1/1.2/1.3/1.4 | Dev phải có `.feature` + nền jest trước khi code (BDD) | Pending |
| Task 1.U → Task 1.3/1.4 | FE cần wireframe fallback trước khi dựng UI lỗi | Pending |
| Task 1.1 → Task 1.4 | FE cần biết hình dạng payload thật của endpoint | Pending |
| Task 1.1 → Task 1.2 | Task 1.1 sở hữu `main.py`; Task 1.2 chỉ thêm file middleware | Pending |
| Task 1.1+1.2+1.3+1.4 → Task 1.R | Review sau khi dev xong | Pending |
| Task 1.R → Task 1.Q | QA verify sau khi review pass | Pending |

---

## Risks & Blockers

| # | Type | Description | Impact | Mitigation | Owner | Status |
|---|------|-------------|--------|------------|-------|--------|
| 1 | Risk | Lớp chống-crash tự gây crash (reporter ném lỗi, đệ quy log) | **H** | ADR-004: mọi hàm public nuốt lỗi; gửi bằng `fetch` trần; test bắt buộc | expo-mobile-lead #1 | Open |
| 2 | Risk | Sentry cần build native lại — không chạy trên Expo Go | M | Gate bằng `EXPO_PUBLIC_SENTRY_DSN`; thiếu DSN thì no-op, sprint không bị chặn | expo-mobile-lead #1 | Open |
| 3 | Risk | Client chưa có tài khoản Sentry / chưa có DSN | M | Phần còn lại vẫn chạy đủ; DSN gắn sau, không cần sửa code | netflix-devops-engineer | Open |
| 4 | Risk | Bão log lúc sự cố diện rộng làm phình DB | M | Rate-limit 60/user/5 phút + hàng đợi client tối đa 50 + cắt payload phía server | fastapi-backend-lead #1 | Open |
| 5 | Risk | `main.py` bị 2 agent BE sửa cùng lúc → xung đột | M | Task 1.1 độc quyền `main.py`; Task 1.2 chỉ tạo file mới | PM | Open |
| 6 | Risk | Repo FE chưa từng có test → dựng jest-expo có thể vướng transform RN 0.86 | M | Task 1.S làm riêng ở Batch 0, có `transformIgnorePatterns` sẵn trong hồ sơ agent | google-qa-engineer | Open |
| 7 | Gap | **Chưa biết nguyên nhân crash hiện tại** — sprint này xây công cụ ĐO, chưa sửa lỗi gốc | **H** | Sau khi deploy, đọc `/summary` vài ngày → mở sprint sửa lỗi theo dữ liệu thật | CEO | Open |

---

## Notes

- **Đây là repo production đang chạy thật**, không phải dự án mới. Mọi thay đổi phải cộng thêm, không được phá luồng cũ (đặc biệt luồng refresh token ở `client.ts` và luồng gửi tin ở `chat.tsx` — đã có 5 commit sửa lỗi gần đây quanh khu vực này).
- Quyết định của client: endpoint **bắt buộc đăng nhập** (ADR-002), **Sentry** cho native crash (ADR-003), **dựng jest-expo** cho test FE.
- 4 ADR đầy đủ ở `.project/documentation/architecture.md`.
- Sprint này **xây công cụ đo**, không phải sửa lỗi crash cụ thể — vì hiện chưa có dữ liệu nào cho biết app crash vì cái gì. Sprint tiếp theo mới sửa theo dữ liệu thật.
- BAT (Browser Acceptance Test) của template **không áp dụng**: đây là app mobile, không phải web. Thay bằng chạy trên **iOS Simulator** qua MCP để client xem trực tiếp.

---

## Sprint Retrospective

<!--
Fill this out AFTER sprint completes
-->

### What Went Well
- {Positive outcome 1}
- {Positive outcome 2}

### What Needs Improvement
- {Issue 1 and how to fix}
- {Issue 2 and how to fix}

### Carry Over to Next Sprint
- {Incomplete task or scope change}

### Time Analysis
| Metric | Estimated | Actual | Variance |
|--------|-----------|--------|----------|
| Total Hours | TBDh | TBDh | {+/-Z}h |
| Velocity | 100% | {actual}% | - |

---

## Reference

### Task ID Format
**Format**: `{sprint}.{task}` (e.g., 1.1, 1.2, 2.1)

### Status Values
| Status | Task Details | Sprint Backlog Table |
|--------|--------------|----------------------|
| Not started | `[NOT STARTED]` | (empty) |
| In progress | `[IN PROGRESS]` | `[IN PROGRESS]` |
| Complete | `[COMPLETE]` | `[COMPLETE]` |
| Blocked | `[BLOCKED]` | `[BLOCKED]` |
| Deferred | - | `→ Sprint N` |

### Assignee Values
| Assignee | Specialist | Skills |
|----------|------------|--------|
| Frontend | **expo-mobile-lead** 🆕 | Expo SDK 57, RN 0.86, React 19, TS, jest-expo, Sentry RN |
| Backend | **fastapi-backend-lead** 🆕 | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, pytest |
| QA | google-qa-engineer | BDD, Jest, pytest, regression, coverage |
| DevOps | netflix-devops-engineer | GitHub Actions, Docker, Alembic trong CD |
| UX | apple-ux-wireframer | Wireframes |

> ⚠️ `meta-react-architect` và `netflix-backend-architect` **KHÔNG** dùng trong sprint này —
> chúng là React **web** và Node.js, không khớp stack React Native + Python. Xem Skill Gap
> Check trong `.project/documentation/team.md`.

### Story Points Guide
| Points | Complexity | Time Estimate |
|--------|------------|---------------|
| 1 | Trivial | < 1 hour |
| 2 | Simple | 1-2 hours |
| 3 | Medium | 2-4 hours |
| 5 | Complex | 4-8 hours |
| 8 | Very Complex | 8-16 hours |
