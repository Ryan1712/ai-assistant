from fastapi import FastAPI

from app.api import auth, invites, projects, tasks, users
from app.config import assert_safe_config, get_settings


def create_app() -> FastAPI:
    assert_safe_config(get_settings())
    app = FastAPI(title="AI Assistant API", version="0.1.0", docs_url="/docs")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(invites.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    return app


app = create_app()
