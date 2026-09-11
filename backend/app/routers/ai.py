"""AI endpoints: SSE chat-command stream + JSON copilot completion."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..ai import command, copilot
from ..ai.llm import MissingApiKeyError
from ..schemas import CopilotBody

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _require_api_key(body: dict) -> None:
    from ..ai.llm import resolve_api_key

    resolve_api_key(body.get("apiKey"))


@router.post("/command")
async def command_endpoint(request: Request):
    body = await request.json()

    try:
        _require_api_key(body)
    except MissingApiKeyError:
        return JSONResponse(
            {"error": "Missing AI Gateway API key."}, status_code=401
        )

    return StreamingResponse(
        command.run_command(body),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/copilot")
async def copilot_endpoint(body: CopilotBody):
    try:
        return await copilot.run_copilot(body)
    except MissingApiKeyError:
        raise HTTPException(status_code=401, detail="Missing ai gateway API key.")