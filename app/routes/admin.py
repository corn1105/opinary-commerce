import hmac
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse

from app.config import ADMIN_PASSWORD
from app.models import (
    AdminAuthRequest,
    EditBridgeRequest,
    PollCreateRequest,
    PollUpdateRequest,
    RegenerateRecsRequest,
)
from app.services import claude_service, poll_service

router = APIRouter(prefix="/admin", tags=["admin"])

STATIC_DIR = Path(__file__).parent.parent / "static"


def _verify_password(password: str) -> bool:
    return hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode())


def _check_auth(admin_token: Optional[str]) -> None:
    if not admin_token or not _verify_password(admin_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/", response_class=HTMLResponse)
async def admin_page():
    admin_html = STATIC_DIR / "admin.html"
    if admin_html.exists():
        return FileResponse(str(admin_html), headers={"Cache-Control": "no-cache"})
    return HTMLResponse("<h1>Admin panel not yet built.</h1>")


@router.post("/api/auth")
async def admin_auth(body: AdminAuthRequest, response: Response):
    if not _verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    response.set_cookie(
        key="admin_token",
        value=body.password,
        httponly=True,
        samesite="strict",
        max_age=86400,
    )
    return {"status": "ok"}


@router.get("/api/polls")
async def api_list_polls(admin_token: Optional[str] = Cookie(None)):
    _check_auth(admin_token)
    return {"polls": await poll_service.list_polls()}


@router.get("/api/polls/{poll_id}")
async def api_get_poll(poll_id: str, admin_token: Optional[str] = Cookie(None)):
    _check_auth(admin_token)
    poll = await poll_service.get_poll(poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    results = await poll_service.get_results(poll_id)
    return {"poll": poll, "results": results}


@router.post("/api/polls")
async def api_create_poll(body: PollCreateRequest, admin_token: Optional[str] = Cookie(None)):
    _check_auth(admin_token)
    poll = await poll_service.create_poll(
        question=body.question,
        options=[o.model_dump() for o in body.options],
        context_notes=body.context_notes,
        publisher_name=body.publisher_name,
        publisher_logo=body.publisher_logo,
    )
    return {"poll": poll}


@router.put("/api/polls/{poll_id}")
async def api_update_poll(
    poll_id: str,
    body: PollUpdateRequest,
    admin_token: Optional[str] = Cookie(None),
):
    _check_auth(admin_token)
    patch = body.model_dump(exclude_unset=True, exclude={"options"})
    options = [o.model_dump() for o in body.options] if body.options is not None else None
    poll = await poll_service.update_poll(poll_id, patch, options)
    return {"poll": poll}


@router.delete("/api/polls/{poll_id}")
async def api_delete_poll(poll_id: str, admin_token: Optional[str] = Cookie(None)):
    _check_auth(admin_token)
    await poll_service.delete_poll(poll_id)
    return {"status": "ok"}


@router.get("/api/polls/{poll_id}/recommendations")
async def api_list_recommendations(poll_id: str, admin_token: Optional[str] = Cookie(None)):
    _check_auth(admin_token)
    poll = await poll_service.get_poll(poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    recs = await poll_service.list_recs_for_poll(poll_id)
    return {"options": poll["options"], "recommendations": recs}


@router.post("/api/options/{option_id}/regenerate-recs")
async def api_regenerate_recs(
    option_id: str,
    body: RegenerateRecsRequest,
    admin_token: Optional[str] = Cookie(None),
):
    _check_auth(admin_token)
    # Look up the option + its poll
    from app.services.poll_service import get_db
    db = get_db()
    opt_res = db.table("poll_options").select("*").eq("id", option_id).maybe_single().execute()
    opt = opt_res.data if opt_res else None
    if not opt:
        raise HTTPException(status_code=404, detail="Option not found")
    poll = await poll_service.get_poll(opt["poll_id"])
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")

    payload = await claude_service.generate_recommendations(
        question=poll["question"],
        option_label=opt["label"],
        context_notes=poll.get("context_notes"),
        locale=body.locale,
    )
    row = await poll_service.upsert_recs(
        option_id=option_id,
        locale=body.locale,
        bridge=payload.bridge,
        products=[p.model_dump() for p in payload.products],
    )
    return {"recommendation": row}


@router.patch("/api/options/{option_id}/recommendations/bridge")
async def api_edit_bridge(
    option_id: str,
    body: EditBridgeRequest,
    admin_token: Optional[str] = Cookie(None),
):
    _check_auth(admin_token)
    row = await poll_service.update_bridge(option_id, body.locale, body.bridge)
    if row is None:
        raise HTTPException(status_code=404, detail="No cached recommendation for this option/locale")
    return {"recommendation": row}
