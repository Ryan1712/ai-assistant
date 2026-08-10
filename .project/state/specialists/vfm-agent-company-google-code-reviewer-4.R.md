---
agent: vfm-agent-company:google-code-reviewer
task_id: 4.R
sprint: 4
title: Code Review — Project-Scoped Chat Phase A (BE) + ChatGPT-style + ProjectCard (FE)
description: Review toàn bộ thay đổi sprint 4/bug-fix: khóa cứng project scope ở tool layer BE, migration, FE banner + ProjectCard + chatUtils refactor
status: COMPLETE
started: 2026-08-08
completed: 2026-08-08
skills_used: []
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Read CLAUDE.md + frontend/AGENTS.md
- [x] Read backend: models.py, schemas.py, api/chat.py, agent/tools.py, agent/loop.py, agent/worker.py
- [x] Read migration a1b2c3d4e5f6
- [x] Read backend tests test_project_scoped_chat.py (22 tests)
- [x] Read frontend: chat.ts, ProjectScopeBanner.tsx, chat.tsx, chatUtils.ts, ProjectCard.tsx, projects.tsx
- [x] Read frontend tests: chatUtils.test.ts, ProjectChat.test.tsx
- [x] Read design system (theme.ts type scale)
- [x] Write review report

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| (read-only review — no files modified) | READ | N/A |

## Completion Notes

Verdict: NEEDS MAJOR. Core enforcement logic solid, but 7 tools bypass scope (search, semantic_search, resolve_task, generate_report, get_today_dashboard, get_progress_stats, create_directive), plus a DB-level race condition in find-or-create. FE has minor static inline style violations. Tests don't cover the enforcement gaps.
