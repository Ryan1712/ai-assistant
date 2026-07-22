"""Phase 3: snapshot section 'Việc đã giao đang chờ xác nhận' — góc nhìn NGƯỜI GIAO
(created_by), khác các section khác vốn lọc theo visible_task_ids/visible_user_ids."""
from datetime import datetime, timezone

import pytest

from app.models import Directive, DirectiveStatus, Role, User, Workspace
from app.services.snapshot_service import build_workspace_data, get_snapshot_text, render_for_actor

NOW = datetime(2026, 7, 25, 3, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_build_workspace_data_includes_pending_directive(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee)
    db_session.add_all([ceo, duy])
    await db_session.flush()
    directive = Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=duy.id,
                          verbatim_text="lam viec X", structured_summary="Viec X")
    db_session.add(directive)
    await db_session.commit()

    data = await build_workspace_data(db_session, ws.id, now=NOW)

    assert len(data["pending_directives"]) == 1
    pd = data["pending_directives"][0]
    assert pd["directive_id"] == str(directive.id)
    assert pd["created_by"] == str(ceo.id)
    assert pd["recipient_name"] == "Duy"
    assert pd["status"] == "sent"


@pytest.mark.asyncio
async def test_build_workspace_data_excludes_acked_directive(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee)
    db_session.add_all([ceo, duy])
    await db_session.flush()
    directive = Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=duy.id,
                          verbatim_text="x", status=DirectiveStatus.acked)
    db_session.add(directive)
    await db_session.commit()

    data = await build_workspace_data(db_session, ws.id, now=NOW)

    assert data["pending_directives"] == []


def test_render_for_actor_shows_own_created_pending_directives():
    data = {
        "built_at": "2026-07-25T03:00:00+00:00", "projects": [], "users": [],
        "due_today": [], "overdue": [], "updates_24h": [],
        "pending_directives": [
            {"directive_id": "dir1", "created_by": "u-ceo", "recipient_name": "Duy",
             "task_title": "Landing page", "deadline": None, "sent_at": "2026-07-24T07:00:00+00:00",
             "status": "sent"},
        ],
    }
    text = render_for_actor(data, "u-ceo", visible_projects=set(), visible_tasks=set(),
                           visible_users=set(), own_directive_creator_ids={"u-ceo"}, now=NOW)
    assert "## Việc đã giao đang chờ xác nhận" in text
    assert "Duy" in text and "Landing page" in text and "CHƯA xác nhận" in text


def test_render_for_actor_hides_other_creators_pending_directives():
    data = {
        "built_at": "2026-07-25T03:00:00+00:00", "projects": [], "users": [],
        "due_today": [], "overdue": [], "updates_24h": [],
        "pending_directives": [
            {"directive_id": "dir1", "created_by": "u-other-manager", "recipient_name": "Nam",
             "task_title": None, "deadline": None, "sent_at": "2026-07-24T07:00:00+00:00",
             "status": "sent"},
        ],
    }
    text = render_for_actor(data, "u-mgr", visible_projects=set(), visible_tasks=set(),
                           visible_users=set(), own_directive_creator_ids={"u-mgr"}, now=NOW)
    assert "Việc đã giao đang chờ xác nhận" not in text


@pytest.mark.asyncio
async def test_get_snapshot_text_end_to_end_only_own_directives(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="Ha",
              role=Role.manager)
    db_session.add_all([ceo, mgr])
    await db_session.flush()
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee, manager_id=mgr.id)
    db_session.add(duy)
    await db_session.flush()
    d_ceo = Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=duy.id,
                      verbatim_text="tu ceo")
    db_session.add(d_ceo)
    await db_session.commit()

    mgr_text = await get_snapshot_text(db_session, mgr, now=NOW)
    assert "Việc đã giao đang chờ xác nhận" not in mgr_text

    ceo_text = await get_snapshot_text(db_session, ceo, now=NOW)
    assert "Việc đã giao đang chờ xác nhận" in ceo_text
