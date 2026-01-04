from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(title="testpython")

    app.include_router(api_router, prefix="/api")

    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(frontend_dir / "index.html"))

    return app


app = create_app()
