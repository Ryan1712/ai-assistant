# Team Composition — AI Assistant / Sprint CR-1 (Crash Reporting & Error Resilience)

**Complexity**: Standard (1 sprint, sửa repo đang chạy production)
**Duration**: 1 sprint
**Team Size**: 6 specialists (trong đó **2 vị trí tuyển mới**)

---

## Core Roles (Not Spawned)

These roles are handled by the main agent reading role instructions:

| Role | Phase | File | Responsibility |
|------|-------|------|----------------|
| CEO | 1, 7 | `core/ceo.md` | Approval, sign-off |
| CTO | 2a | `core/cto.md` | Tech stack, architecture |
| HR | 2a | `core/hr.md` | Team composition |
| BA | 1 | `core/ba.md` | Requirements gathering |
| PM | All | `core/pm.md` | Sprint planning, coordination |

---

## Specialists (Spawned)

These are actual agents spawned for parallel execution:

| Specialist | Role | Phases | Primary Skills | Nguồn |
|------------|------|--------|----------------|-------|
| `fastapi-backend-lead` | Backend | 3 | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, pytest | 🆕 **Tuyển mới** |
| `expo-mobile-lead` | Mobile FE | 3 | Expo SDK 57, RN 0.86, React 19, TS, jest-expo, Sentry RN | 🆕 **Tuyển mới** |
| `google-qa-engineer` | QA | 4 | BDD scenarios, Jest, pytest, regression, coverage | Có sẵn |
| `google-code-reviewer` | Code Review | 3 | Security, correctness, TypeScript/Python review | Có sẵn |
| `netflix-devops-engineer` | DevOps | 5-6 | GitHub Actions, Docker, migration khi deploy | Có sẵn |
| `apple-ux-wireframer` | UX | 2b | Wireframe màn fallback lỗi + bong bóng lỗi trong chat | Có sẵn |

### 🆕 Dynamic Hiring — hồ sơ 2 vị trí tuyển mới

| Vị trí | Khoảng trống đã bịt | File |
|---|---|---|
| `fastapi-backend-lead` (Tomás Herrera) | Không specialist nào biết Python/FastAPI/SQLAlchemy. `netflix-backend-architect` là Node.js+Prisma — 0 dòng Python. | `.claude/agents/fastapi-backend-lead.md` |
| `expo-mobile-lead` (Priya Raman) | `meta-react-architect` ghi rõ *"Native iOS/Android (use mobile specialists)"* — là React **web**, không phải React **Native**. | `.claude/agents/expo-mobile-lead.md` |

Mỗi hồ sơ nhúng sẵn cạm bẫy cụ thể của stack này: RN không có DOM/`className`/`localStorage`;
bắt buộc đọc doc Expo **versioned v57**; SQLAlchemy 2.0 async (không `.query()`); middleware
bắt exception phải mở **session DB riêng**; quy ước `workspace_id` + quyền ở service layer của repo.

> ⚠️ **Lưu ý vận hành**: 2 agent này vừa được tạo trong phiên hiện tại. Nếu registry agent chưa
> nạp lại, PM spawn bằng `general-purpose` kèm chỉ thị đọc file hồ sơ và nhập vai đúng specialist —
> chuyên môn giữ nguyên, chỉ khác đường vào.

---

## SDLC Phase Coverage

```
PHASE COVERAGE VERIFICATION:
├── Phase 1 (Requirements).... CEO + PM (yêu cầu client đã rõ, 3 câu hỏi đã chốt)  ✅
├── Phase 2a (Architecture)... CTO → architecture.md (blueprint + schema + 4 ADR)  ✅
├── Phase 2b (UX Design)...... apple-ux-wireframer (fallback lỗi + bong bóng chat) ✅
├── Phase 3 (Development)..... fastapi-backend-lead ×2, expo-mobile-lead ×2        ✅
├── Phase 4 (Testing)......... google-qa-engineer (BDD + regression)               ✅
├── Phase 5 (Packaging)....... netflix-devops-engineer (migration trong CD)        ✅
├── Phase 6 (Deployment)...... netflix-devops-engineer (GHCR → VPS, alembic)       ✅
└── Phase 7 (Release)......... PM + CEO sign-off                                   ✅

MANDATORY SPECIALISTS CHECK:
├── apple-ux-wireframer ...... ✅ có
├── google-code-reviewer ..... ✅ có (Batch 2)
├── google-qa-engineer ....... ✅ có (Batch 0 + Batch 3)
└── netflix-devops-engineer .. ✅ có

SKILL GAP CHECK:
├── React Native / Expo ...... ❌ GAP → 🆕 đã tuyển expo-mobile-lead     → ✅ bịt
├── Python / FastAPI ......... ❌ GAP → 🆕 đã tuyển fastapi-backend-lead → ✅ bịt
├── SQLAlchemy / Alembic ..... ❌ GAP → gộp vào fastapi-backend-lead     → ✅ bịt
├── PostgreSQL ............... ✅ có sẵn
├── Sentry RN ................ ❌ GAP → gộp vào expo-mobile-lead        → ✅ bịt
└── Jest / testing ........... ✅ google-qa-engineer

STATUS: ✅ ALL CHECKS PASSED — không vị trí nào bị gán bừa sang công nghệ khác
```

---

## Specialist Responsibilities

### `fastapi-backend-lead` #1 — API & dữ liệu
- Model `CrashLog` + enum, Pydantic schema, migration Alembic
- 3 endpoint: POST batch / GET list / GET summary + `crash_service` (fingerprint, dedupe, cắt payload, rate-limit, `require_ceo`)
- **Deliverables**: `backend/app/models.py`, `schemas.py`, `api/crash_logs.py`, `services/crash_service.py`, `alembic/versions/*`, `main.py`

### `fastapi-backend-lead` #2 — Middleware
- `CrashCaptureMiddleware`: bắt unhandled exception, ghi bằng **session DB riêng**, không nuốt lỗi gốc
- **Deliverables**: `backend/app/middleware/crash_capture.py` (KHÔNG chạm `main.py` — BE #1 sở hữu)

### `expo-mobile-lead` #1 — Hạ tầng lỗi FE
- `src/errors/**` đầy đủ + bọc `ErrorBoundary` ở `App.tsx` + `ScreenErrorBoundary` mỗi màn + flush sau login + Sentry
- **Deliverables**: `frontend/src/errors/*`, `App.tsx`, `src/navigation/*`, `src/auth/AuthContext.tsx`, `app.json`

### `expo-mobile-lead` #2 — Chat & tầng API
- Chat gặp lỗi API → bong bóng *"Hệ thống đang có lỗi, vui lòng thử lại."* thay vì sập
- `apiFetch` báo 5xx/timeout/mất mạng vào reporter (bỏ qua 401/403/404/422)
- **Deliverables**: `frontend/app/main/chat.tsx`, `src/api/client.ts`, `src/api/crashLogs.ts`

### `google-qa-engineer` — Batch 0 + Batch 3
- Batch 0: `.feature` scenarios + dựng nền `jest-expo` + test skeleton
- Batch 3: chạy `pytest` + `jest` toàn bộ, regression, coverage
- **Deliverables**: `.project/scenarios/sprint-cr1/*.feature`, `frontend/jest.config.js`, `jest.setup.js`, `frontend/__tests__/*`, `backend/tests/*`

---

## Team Size Guidelines

| Complexity | Team Size | Duration |
|------------|-----------|----------|
| Simple | 3-4 specialists | 1-2 weeks |
| Standard | 5-6 specialists | 1-2 months |
| Complex | 6-8 specialists | 2-4 months |
| Enterprise | 8-12 specialists | 4-12 months |

---

## Communication Matrix

| From → To | Channel | Frequency |
|-----------|---------|-----------|
| PM → Specialists | Task assignments | Per sprint |
| Specialists → PM | Progress updates | Daily |
| PM → CEO | Milestone reports | Per sprint |
| Frontend ↔ Backend | API contracts | As needed |
| QA → All | Bug reports | As found |

---

## Code Review

After each task completion:
- `google-code-reviewer` reviews code
- Must get LGTM before task marked complete
- Focus: TypeScript, security, performance

---

**Created**: [DATE]
**Last Updated**: [DATE]
