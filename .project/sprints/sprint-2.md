# Sprint 2: New Chat Entry + Global FAB

**Sprint**: 2 of 2
**Duration**: 2026-08-02 (single-day feature-change sprint)
**Goal**: Người dùng luôn có lối vào "Cuộc trò chuyện mới": một entry rõ ràng trong drawer + một Floating Action Button ở góc phải-dưới trên MỌI màn không phải Chat; bấm vào mở một cuộc chat mới trống.
**Status**: COMPLETE
**Type**: Feature Change (BDD required)

---

## Task Details

<!--
DETAILED SECTIONS: Human-readable task breakdown
Each task has deliverables, acceptance criteria, and time tracking
-->

### Task 2.S: BDD Scenarios — New Chat entry + Global FAB [QA]
**Status**: [COMPLETE] (user approved 2026-08-02)
**Story Points**: 1
**Wireframe**: -

**Deliverables**:
- [ ] `.project/scenarios/sprint-2/new-chat-fab.feature`

**Acceptance Criteria**:
- [ ] Scenario mô tả entry "Cuộc trò chuyện mới" trong drawer
- [ ] Scenario mô tả FAB hiện trên mọi màn KHÔNG phải Chat, ẩn trên Chat
- [ ] Scenario mô tả bấm FAB/entry → mở Chat mới trống
- [ ] **User đã duyệt** scenarios

---

### Task 2.1: New Chat drawer entry + Global New-Chat FAB [Frontend]
**Status**: [COMPLETE]
**Estimated**: 3 hours | **Actual**: 2 hours
**Story Points**: 3
**Wireframe**: -

**Deliverables**:
- [ ] `frontend/src/ui/NewChatFab.tsx` — component FAB dùng chung (tokens từ theme.ts)
- [ ] `frontend/src/navigation/DrawerContent.tsx` — thêm entry "Cuộc trò chuyện mới" ở đầu drawer
- [ ] Wiring FAB global: render 1 lần trong `MainNavigator`/`RootNavigator`, tự ẩn khi route đang active là `Chat`, dựa trên navigation state (không nhét FAB vào từng screen)
- [ ] Unit test cho NewChatFab (visibility theo route + onPress điều hướng)

**Acceptance Criteria**:
- [ ] Drawer có nút "Cuộc trò chuyện mới" nổi bật; bấm → navigate `Chat` không kèm `id` + đóng drawer
- [ ] FAB hiển thị góc phải-dưới trên MỌI màn khác Chat (Dashboard, Công việc, Cài đặt + các màn push: Team, Notes, Conversations, ...)
- [ ] FAB KHÔNG hiển thị khi đang ở màn Chat
- [ ] Bấm FAB → mở Chat với cuộc trò chuyện mới trống (navigate `Chat`, không `id`)
- [ ] Không inline hex/spacing lệch grid — dùng tokens `src/ui/theme.ts`; tôn trọng safe-area insets
- [ ] `npx tsc --noEmit` sạch; jest GREEN

**Notes**: FAB dùng chung được đặt ở tầng navigator để "global". Đọc `DESIGN.md` + `theme.ts` trước khi code. Điều hướng từ màn push (stack) về Chat: `navigation.navigate("Drawer", { screen: "Chat" })`; từ màn drawer: `navigation.navigate("Chat")`.

---

### Task 2.R: Code Review [Code Review]
**Status**: [COMPLETE]
**Story Points**: 1
**Wireframe**: -

**Acceptance Criteria**:
- [ ] LGTM từ google-code-reviewer (đúng tokens, không regress UX, đúng RN/Expo patterns)

---

### Task 2.Q: QA Verification [QA]
**Status**: [COMPLETE]
**Story Points**: 1
**Wireframe**: -

**Acceptance Criteria**:
- [ ] tsc + jest GREEN, không regress
- [ ] Scenarios 2.S thỏa mãn (verify hành vi hiển thị/ẩn FAB + điều hướng)

---

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
| 2.S | BDD Scenarios: New chat entry + FAB | 1 | [COMPLETE] | QA | - |
| 2.1 | New chat drawer entry + global FAB | 3 | [COMPLETE] | Frontend | - |
| 2.R | Code Review | 1 | [COMPLETE] | QA | - |
| 2.Q | QA Verification | 1 | [COMPLETE] | QA | - |

---

## Sprint Summary

| Metric | Value |
|--------|-------|
| Total Tasks | {count} |
| Story Points | {total} |
| Estimated Hours | {total_hours}h |
| Actual Hours | {actual_hours}h |
| Velocity | {percent}% |

| Role | Tasks | Points | Hours |
|------|-------|--------|-------|
| Frontend | {count} | {pts} | {hours}h |
| Backend | {count} | {pts} | {hours}h |
| QA | {count} | {pts} | {hours}h |
| DevOps | {count} | {pts} | {hours}h |

---

## Definition of Done

<!--
SPRINT-SPECIFIC DoD: What THIS sprint must achieve
NOT generic checkboxes - actual testable outcomes
-->

### Functional Criteria
- [x] Drawer có entry "Cuộc trò chuyện mới" → mở Chat mới trống + đóng drawer
- [x] FAB góc phải-dưới hiển thị trên MỌI màn khác Chat, ẩn trên Chat
- [x] Bấm FAB → mở Chat mới trống (navigate `Chat`, không `id`); tôn trọng safe-area

### Technical Criteria
- [ ] All tasks marked [COMPLETE] in Sprint Backlog
- [ ] Code reviewed (LGTM from google-code-reviewer)
- [ ] No TypeScript errors (`npm run build` passes)
- [ ] No ESLint errors (`npm run lint` passes)
- [ ] Unit tests written for new code

### Quality Criteria
- [ ] {Sprint-specific quality: e.g., "Tree renders in <1 second"}
- [ ] {Another quality: e.g., "No console errors in browser"}

---

## Dependencies

<!--
NOTE: Use "Task X.Y" format (not bare "X.Y") to avoid false parsing by progress scripts
-->

| Dependency | Reason | Status |
|------------|--------|--------|
| Task 2.X → {M}.Y | {Why dependency exists} | Resolved / Pending |

---

## Risks & Blockers

| # | Type | Description | Impact | Mitigation | Owner | Status |
|---|------|-------------|--------|------------|-------|--------|
| 1 | Risk | {Potential issue} | {H/M/L} | {Plan} | {Name} | Open |
| - | - | None identified | - | - | - | - |

---

## Notes

- {Important context for this sprint}
- {Technical decisions made}
- {Coordination needed between specialists}

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
| Frontend | meta-react-architect | React, Next.js, TailwindCSS |
| Backend | netflix-backend-architect | Node.js, Prisma, APIs |
| QA | google-qa-engineer | Jest, Playwright, E2E |
| DevOps | netflix-devops-engineer | Vercel, CI/CD, Docker |
| UX | apple-ux-wireframer | Wireframes, Figma |

### Story Points Guide
| Points | Complexity | Time Estimate |
|--------|------------|---------------|
| 1 | Trivial | < 1 hour |
| 2 | Simple | 1-2 hours |
| 3 | Medium | 2-4 hours |
| 5 | Complex | 4-8 hours |
| 8 | Very Complex | 8-16 hours |
