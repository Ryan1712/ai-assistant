import pytest

from app.config import Settings
from app.models import Report, Role, User, Workspace


def test_storage_dir_setting_default():
    assert Settings().storage_dir == "./storage/reports"


@pytest.mark.asyncio
async def test_report_model_roundtrip(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    report = Report(workspace_id=ws.id, requested_by=ceo.id,
                    filters={"status": "done"}, summary={"total": 0},
                    file_path=f"{ws.id}/x.xlsx")
    db_session.add(report)
    await db_session.commit()

    fetched = await db_session.get(Report, report.id)
    assert fetched.kind == "task_summary"
    assert fetched.filters == {"status": "done"}
    assert fetched.summary == {"total": 0}
    assert fetched.created_at is not None
