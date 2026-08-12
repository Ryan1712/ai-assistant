import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.deps import get_bundle_or_user


def _request(headers: dict) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {"type": "http", "headers": raw_headers}
    return Request(scope)


@pytest.mark.asyncio
async def test_bundle_id_matches_allowlist_returns_fixed_workspace(monkeypatch, db_session):
    from app.config import get_settings
    ws_id = uuid.uuid4()
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", str(ws_id))

    scope = await get_bundle_or_user(
        request=_request({"x-app-bundle-id": "com.9learning.app"}),
        creds=None, db=db_session)
    assert scope.workspace_id == ws_id
    assert scope.user is None


@pytest.mark.asyncio
async def test_bundle_id_not_in_allowlist_and_no_token_401(monkeypatch, db_session):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", str(uuid.uuid4()))

    with pytest.raises(HTTPException) as exc:
        await get_bundle_or_user(
            request=_request({"x-app-bundle-id": "com.other.app"}),
            creds=None, db=db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_feature_disabled_when_allowlist_empty(monkeypatch, db_session):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", "")

    with pytest.raises(HTTPException) as exc:
        await get_bundle_or_user(
            request=_request({"x-app-bundle-id": "com.9learning.app"}),
            creds=None, db=db_session)
    assert exc.value.status_code == 401


import datetime as dt

from app.models import PublicReport, PublicReportStatus


async def _make_report(db_session, workspace_id, status, *, file_bytes=b"hello",
                       content_type="text/plain"):
    from pathlib import Path
    import uuid as uuidlib
    from app.config import get_settings
    d = Path(get_settings().storage_dir) / "public_reports" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"{uuidlib.uuid4()}.txt"
    fp.write_bytes(file_bytes)
    report = PublicReport(workspace_id=workspace_id, title="R1", status=status,
                          content_type=content_type, file_path=str(fp),
                          size_bytes=len(file_bytes), created_by=uuidlib.uuid4())
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


@pytest.mark.asyncio
async def test_list_published_excludes_draft(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        await _make_report(db, ws, PublicReportStatus.published)
        await _make_report(db, ws, PublicReportStatus.draft)
        result = await public_report_service.list_published(db, ws)
        assert len(result) == 1


@pytest.mark.asyncio
async def test_list_published_excludes_other_workspace(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws1, ws2 = uuid.uuid4(), uuid.uuid4()
        await _make_report(db, ws1, PublicReportStatus.published)
        result = await public_report_service.list_published(db, ws2)
        assert result == []


@pytest.mark.asyncio
async def test_get_published_404_on_draft(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from fastapi import HTTPException
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        report = await _make_report(db, ws, PublicReportStatus.draft)
        with pytest.raises(HTTPException) as exc:
            await public_report_service.get_published(db, ws, report.id)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_content_path_returns_file(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        report = await _make_report(db, ws, PublicReportStatus.published,
                                    file_bytes=b"content-x", content_type="text/plain")
        path, content_type = await public_report_service.get_content_path(db, ws, report.id)
        assert path.read_bytes() == b"content-x"
        assert content_type == "text/plain"


from app.models import Role


def _ceo_user(workspace_id):
    from app.models import User, UserStatus
    return User(id=uuid.uuid4(), workspace_id=workspace_id, email="ceo@x.vn",
               full_name="CEO", role=Role.ceo, status=UserStatus.active,
               password_hash="x", is_root=True)


def _manager_user(workspace_id):
    from app.models import User, UserStatus
    return User(id=uuid.uuid4(), workspace_id=workspace_id, email="m@x.vn",
               full_name="M", role=Role.manager, status=UserStatus.active,
               password_hash="x")


@pytest.mark.asyncio
async def test_create_defaults_to_draft(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        ceo = _ceo_user(ws)
        out = await public_report_service.create(
            db, ceo, title="Q3 revenue", description=None, filename="q3.pdf",
            content_type="application/pdf", data=b"%PDF-x")
        assert out["status"] == "draft"


@pytest.mark.asyncio
async def test_create_rejects_non_ceo(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from fastapi import HTTPException
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        manager = _manager_user(ws)
        with pytest.raises(HTTPException) as exc:
            await public_report_service.create(
                db, manager, title="X", description=None, filename="a.pdf",
                content_type="application/pdf", data=b"x")
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_publish_then_unpublish(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    from app.models import PublicReportStatus
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        ceo = _ceo_user(ws)
        created = await public_report_service.create(
            db, ceo, title="X", description=None, filename="a.pdf",
            content_type="application/pdf", data=b"x")
        rid = uuid.UUID(created["id"])

        published = await public_report_service.set_status(
            db, ceo, rid, PublicReportStatus.published)
        assert published["status"] == "published"
        visible = await public_report_service.list_published(db, ws)
        assert len(visible) == 1

        unpublished = await public_report_service.set_status(
            db, ceo, rid, PublicReportStatus.draft)
        assert unpublished["status"] == "draft"
        visible_after = await public_report_service.list_published(db, ws)
        assert visible_after == []


@pytest.mark.asyncio
async def test_delete_removes_report(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        ceo = _ceo_user(ws)
        created = await public_report_service.create(
            db, ceo, title="X", description=None, filename="a.pdf",
            content_type="application/pdf", data=b"x")
        rid = uuid.UUID(created["id"])
        await public_report_service.delete(db, ceo, rid)
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await public_report_service.update_metadata(db, ceo, rid, title="Y",
                                                         description=None)


@pytest.mark.asyncio
async def test_cross_workspace_write_404(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws1, ws2 = uuid.uuid4(), uuid.uuid4()
        ceo1 = _ceo_user(ws1)
        ceo2 = _ceo_user(ws2)
        created = await public_report_service.create(
            db, ceo1, title="X", description=None, filename="a.pdf",
            content_type="application/pdf", data=b"x")
        rid = uuid.UUID(created["id"])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await public_report_service.update_metadata(db, ceo2, rid, title="Y",
                                                         description=None)
        assert exc.value.status_code == 404
