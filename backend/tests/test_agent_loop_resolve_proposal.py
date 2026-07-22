import json
import uuid

import pytest
from sqlalchemy import select

from app.agent.loop import resolve_confirmation
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, Project, Role, Task, User, Workspace,
)


async def _setup(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T1", created_by=ceo.id)
    db.add(task)
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    await db.commit()
    return ws, ceo, project, task, conv


async def _make_req(db, ws, conv, ceo, actions):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="bao Duy xong deadline nhe", queue_position=1.0,
                      status=ChatRequestStatus.awaiting_confirmation,
                      pending_action={"kind": "proposal", "actions": actions,
                                     "reasoning": "", "tool_use_id": "t1"})
    db.add(req)
    await db.flush()
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_approved_proposal_runs_all_actions_sequentially_skips_failures(db_session, monkeypatch):
    ws, ceo, project, task, conv = await _setup(db_session)
    req = await _make_req(db_session, ws, conv, ceo, [
        {"tool_name": "update_task", "tool_input": {"task_id": str(task.id), "percent": 80},
         "display_text": "Cap nhat task T1 len 80%"},
        {"tool_name": "update_task", "tool_input": {"task_id": str(uuid.uuid4()), "percent": 50},
         "display_text": "Cap nhat task khong ton tai"},
    ])
    invalidated = []
    from app.services import snapshot_service
    async def fake_invalidate(workspace_id):
        invalidated.append(workspace_id)
    monkeypatch.setattr(snapshot_service, "invalidate", fake_invalidate)

    await resolve_confirmation(db_session, req, approved=True)

    await db_session.refresh(task)
    assert task.percent == 80
    assert req.status == ChatRequestStatus.queued
    assert req.pending_action is None
    assert invalidated == [ws.id]

    msgs = (await db_session.execute(select(Message))).scalars().all()
    tool_result = [m for m in msgs if m.content[0]["type"] == "tool_result"][0]
    payload = json.loads(tool_result.content[0]["content"])
    results = payload["proposal_results"]
    assert len(results) == 2
    assert "error" not in results[0]["result"]
    assert results[1]["result"]["error"] == "not_found"


@pytest.mark.asyncio
async def test_denied_proposal_does_not_execute_any_action(db_session, monkeypatch):
    ws, ceo, project, task, conv = await _setup(db_session)
    req = await _make_req(db_session, ws, conv, ceo, [
        {"tool_name": "update_task", "tool_input": {"task_id": str(task.id), "percent": 80},
         "display_text": "Cap nhat task T1 len 80%"},
    ])
    from app.services import snapshot_service
    called = []
    async def fake_invalidate(workspace_id):
        called.append(workspace_id)
    monkeypatch.setattr(snapshot_service, "invalidate", fake_invalidate)

    await resolve_confirmation(db_session, req, approved=False)

    await db_session.refresh(task)
    assert task.percent == 0
    assert called == []
    assert req.status == ChatRequestStatus.queued
    msgs = (await db_session.execute(select(Message))).scalars().all()
    tool_result = [m for m in msgs if m.content[0]["type"] == "tool_result"][0]
    assert json.loads(tool_result.content[0]["content"])["error"] == "user_denied"
