---
agent: vfm-agent-company:netflix-devops-engineer
task_id: 1.D
sprint: 1
title: Migration trong CD + biến môi trường Sentry
description: Xác minh pipeline chạy alembic upgrade head trước docker compose up, khai báo EXPO_PUBLIC_SENTRY_DSN trong eas.json, tài liệu vận hành crash log và Sentry DSN
status: COMPLETE
started: 2026-07-27
completed: 2026-07-27
skills_used: [vfm-agent-company:go]
---

## Progress

- [x] Read state file và điền description
- [x] Đọc deploy.yml, deploy.sh, docker-compose.prod.yml — xác minh thứ tự migration
- [x] Đọc eas.json, app.json, frontend/.env.example, backend/.env.example
- [x] Đọc sprint-1.md, architecture.md (ADR-003), README.md
- [x] Cập nhật eas.json — thêm EXPO_PUBLIC_SENTRY_DSN (empty, không commit secret)
- [x] Cập nhật frontend/.env.example — thêm EXPO_PUBLIC_SENTRY_DSN
- [x] Cập nhật README.md — thêm mục vận hành Sentry + crash log
- [x] Cập nhật sprint-1.md — Task 1.D → [COMPLETE]
- [x] Điền Completion Notes

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| frontend/eas.json | EDIT | Thêm EXPO_PUBLIC_SENTRY_DSN="" vào cả 3 profile build |
| frontend/.env.example | EDIT | Thêm EXPO_PUBLIC_SENTRY_DSN= (rỗng = Sentry tắt khi dev local) |
| README.md | EDIT | Thêm mục "Crash Reporting & Sentry" với hướng dẫn vận hành |
| .project/sprints/sprint-1.md | EDIT | Task 1.D → [COMPLETE] |

## Completion Notes

**Pipeline migration**: Không cần sửa workflow. `backend/scripts/deploy.sh` dòng 53 chạy
`docker compose --profile migration run --rm migrate` (= alembic upgrade head) ở bước [3/6],
trước `docker compose up -d` ở bước [4/6]. Bảng `crash_logs` sẽ được tạo tự động khi deploy.

**EAS / Sentry DSN**: Khai báo `EXPO_PUBLIC_SENTRY_DSN: ""` trong cả 3 profile build của
`eas.json`. Giá trị rỗng = Sentry tắt = app chạy bình thường (ADR-003). Giá trị thật được
gắn qua `eas secret:create` — không bao giờ vào repo. EAS Secret tự override giá trị rỗng
khi build preview/production.

**Secret gate**: `.gitignore` chặn `.env`. Không có DSN thật nào trong file commit được.
Các chuỗi `ingest.sentry.io` trong README là placeholder tài liệu (`<key>`, `<org>`, `<project-id>`).

**Tài liệu**: README.md có mục "Crash Reporting & Sentry" với curl example, hướng dẫn
lấy DSN, cảnh báo native module, và cách dùng EAS Secret.
