"""Shared helpers for the routes: templates, content negotiation, live-update counter."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import config
from app.l3_resolve.pipeline import fmt_date

UI_DIR = Path(__file__).resolve().parent.parent / "l8_ui"
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
templates.env.globals.update(footer=config.FOOTER, fmt_date=fmt_date)


def wants_html(request: Request) -> bool:
    """HTMX and browsers get HTML; API clients get JSON."""
    if request.headers.get("hx-request"):
        return True
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept.split(",")[0]


async def payload(request: Request) -> dict:
    """Read a form or a JSON body into one dict."""
    if "application/json" in request.headers.get("content-type", ""):
        try:
            body = await request.json()
            return body if isinstance(body, dict) else {}
        except ValueError:
            return {}
    form = await request.form()
    return dict(form)


def truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class Live:
    """A tiny in-memory change counter so open pages can refresh within a second."""
    version = 1
    message = ""

    @classmethod
    def bump(cls, message: str = "") -> None:
        cls.version += 1
        cls.message = message
