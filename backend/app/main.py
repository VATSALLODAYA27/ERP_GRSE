from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import auth, checks, erp, reference
from .db import migrate


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    yield


app = FastAPI(title="Drawing Compliance Checker", description="DEMO: rules, clauses and ERP data are mock data.", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(auth.users)
app.include_router(checks.router)
app.include_router(erp.router)
app.include_router(reference.router)

# In production the built web app is served from here too, so the whole tool is one process.
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"))

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(config.FRONTEND_DIST / "index.html")
