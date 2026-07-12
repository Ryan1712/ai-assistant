from fastapi import FastAPI

from app.api import (
    auth, chat, dashboard, instructions, invites, notes, projects, reports, skills,
    subscription, tasks, users, workspace, ws,
)
from app.config import assert_safe_config, get_settings


def create_app() -> FastAPI:
    assert_safe_config(get_settings())
    app = FastAPI(title="AI Assistant API", version="0.1.0", docs_url="/docs")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.on_event("startup")
    async def _startup_arq_pool():
        from arq import create_pool
        from arq.connections import RedisSettings
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))

    @app.on_event("shutdown")
    async def _shutdown_arq_pool():
        if getattr(app.state, "arq_pool", None) is not None:
            await app.state.arq_pool.close()

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(invites.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(skills.router)
    app.include_router(instructions.router)
    app.include_router(notes.router)
    app.include_router(dashboard.router)
    app.include_router(subscription.router)
    app.include_router(workspace.router)
    app.include_router(reports.router)
    app.include_router(chat.router)
    app.include_router(chat.chat_requests_router)
    app.include_router(ws.router)
    return app


app = create_app()
