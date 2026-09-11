"""Port of ``src/app/api/ai/copilot/route.ts`` (single-shot completion)."""

from typing import Any

from livekit.agents import llm as agents_llm

from .. import config
from ..schemas import CopilotBody
from .llm import create_llm, resolve_api_key, resolve_model


async def run_copilot(body: CopilotBody) -> dict[str, Any]:
    api_key = resolve_api_key(body.apiKey)
    model = resolve_model(body.model, fallback=config.AI_COPILOT_MODEL)
    llm = create_llm(model=model, api_key=api_key, temperature=0.7)

    ctx = agents_llm.ChatContext()
    instructions = body.instructions or body.system
    if instructions:
        ctx.add_message(role="system", content=instructions)
    ctx.add_message(role="user", content=body.prompt or "")

    response = await llm.chat(
        chat_ctx=ctx,
        extra_kwargs={"max_tokens": 50},
    ).collect()

    return {"text": response.text or ""}