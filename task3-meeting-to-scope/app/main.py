"""FastAPI entry point for Meeting-to-Scope."""
import hmac

from fastapi import FastAPI, Header, HTTPException

from app.config import get_settings
from app.pipeline import build_scope
from app.schemas import ApprovalInput, HealthResponse, ScopeResult, TranscriptInput
from app.store import get_scope, list_scopes, put_scope, review_scope

settings = get_settings()
app = FastAPI(title="AI Tech Consultant — Meeting to Scope", version="0.2.0")


@app.get("/health", response_model=HealthResponse, tags=["operations"])
async def health() -> HealthResponse:
    return HealthResponse(service=settings.service_name, mode="demo" if settings.demo_mode else "live")


@app.post("/scopes", response_model=ScopeResult)
async def create_scope(data: TranscriptInput) -> ScopeResult:
    try:
        return put_scope(await build_scope(data))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Keep provider failures safe and do not return secrets/provider payloads.
        raise HTTPException(status_code=503, detail="Scope generation failed; check model and Knowledge Brain configuration") from exc


@app.get("/scopes", response_model=list[ScopeResult])
async def scopes() -> list[ScopeResult]:
    return list_scopes()


@app.get("/scopes/{scope_id}", response_model=ScopeResult)
async def scope(scope_id: str) -> ScopeResult:
    result = get_scope(scope_id)
    if not result: raise HTTPException(status_code=404, detail="Scope not found")
    return result


@app.post("/scopes/{scope_id}/review", response_model=ScopeResult)
async def review(scope_id: str, data: ApprovalInput, x_admin_token: str = Header(default="")) -> ScopeResult:
    if settings.app_env.lower() == "production" and not settings.admin_api_token:
        raise HTTPException(status_code=503, detail="Scope approval authentication is not configured")
    if settings.admin_api_token and not hmac.compare_digest(settings.admin_api_token, x_admin_token):
        raise HTTPException(status_code=401, detail="Valid X-Admin-Token header required")
    result = review_scope(scope_id, data.action == "approve", data.reviewer)
    if not result: raise HTTPException(status_code=404, detail="Scope not found")
    return result
