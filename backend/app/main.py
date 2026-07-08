from fastapi import FastAPI

from app.api import auth


def create_app() -> FastAPI:
    app = FastAPI(title="AI Assistant API", version="0.1.0", docs_url="/docs")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(auth.me_router)
    return app


app = create_app()
