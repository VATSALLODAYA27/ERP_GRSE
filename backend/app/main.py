from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import auth, checks, erp, finance, intel, reference, scm
from .core.ledger import LedgerError
from .db import migrate


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    yield


app = FastAPI(title="PRAVAH: shipyard ERP intelligence", lifespan=lifespan,
              description="DEMO: rules, clauses, vendors and all ERP data are mock data. Sentinel is the engineering release module.")
app.include_router(auth.router)
app.include_router(auth.users)
app.include_router(checks.router)
app.include_router(erp.router)
app.include_router(reference.router)
app.include_router(scm.router)
app.include_router(finance.router)
app.include_router(intel.router)


@app.exception_handler(LedgerError)
async def refused_by_the_books(request: Request, error: LedgerError):
    """A posting the books refuse (stock below zero, an unbalanced entry, a wrong state) comes back with its reason."""
    return JSONResponse({"detail": str(error)}, status_code=error.status)


# In production the built web app is served from here too, so the whole tool is one process.
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"))

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(config.FRONTEND_DIST / "index.html")
