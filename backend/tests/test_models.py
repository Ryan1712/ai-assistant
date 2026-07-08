import pytest
from sqlalchemy import select

from app.models import Workspace, User, Role, UserStatus


@pytest.mark.asyncio
async def test_create_workspace_and_root_ceo(db_session):
    ws = Workspace(name="Cong ty A")
    db_session.add(ws)
    await db_session.flush()

    user = User(
        workspace_id=ws.id, email="ceo@a.vn", password_hash="x",
        full_name="Sep", role=Role.ceo, is_root=True,
    )
    db_session.add(user)
    await db_session.commit()

    found = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    assert found.workspace_id == ws.id
    assert found.status == UserStatus.active
    assert found.is_root is True
