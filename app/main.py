"""MedSync application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.l1_data import seed
from app.l7_api import routes_api, routes_ui
from app.l7_api.common import UI_DIR, templates

log = logging.getLogger("medsync")


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed.reset()          # every start begins from the same demo data (see docs/ASSUMPTIONS.md)
    yield


app = FastAPI(title="MedSync", description=config.FOOTER, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")
app.include_router(routes_api.router)
app.include_router(routes_ui.router)


def _error(request: Request, status: int, error: str, message: str):
    """Clear JSON for API and HTMX calls, a friendly page for the browser. Never a stack trace."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and not request.headers.get("hx-request"):
        return templates.TemplateResponse(request, "error.html", {"message": message, "tab": ""}, status_code=status)
    return JSONResponse({"error": error, "message": message}, status_code=status)


@app.exception_handler(LookupError)
async def not_found(request: Request, exc: LookupError):
    return _error(request, 404, "not_found", str(exc).strip("'\""))


@app.exception_handler(ValueError)
async def bad_value(request: Request, exc: ValueError):
    return _error(request, 422, "invalid_input", str(exc))


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    return _error(request, 422, "invalid_input", "Something in the request is missing or has the wrong format.")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    message = "That page does not exist." if exc.status_code == 404 else "The request could not be handled."
    return _error(request, exc.status_code, "http_error", message)


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    log.exception("Unexpected error on %s", request.url.path)
    return _error(request, 500, "server_error", "Something went wrong on our side. Please try again.")
