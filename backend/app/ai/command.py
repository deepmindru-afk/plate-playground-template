"""Port of ``src/app/api/ai/command/route.ts`` to a Python SSE endpoint.

The original streamed a UI-message stream from the `ai` SDK. We reproduce the
same wire format the fake stream in ``use-chat.ts`` produces:

- generate / edit: ``start``, ``start-step``, ``text-start``, ``text-delta`` x N,
  ``text-end``, ``finish-step``, ``finish``, ``[DONE]``.
- comment / table: ``start``, ``start-step``, ``data-toolName``,
  ``data-comment`` / ``data-table`` x N (incl. a final ``finished`` event),
  ``[DONE]``.
"""

import asyncio
import json
import re
import uuid
from typing import Any, AsyncIterator

from livekit.agents import llm as agents_llm

from .. import config
from . import prompts
from .llm import MissingApiKeyError, create_llm, resolve_api_key, resolve_model
from .markdown_joiner import MarkdownJoiner

TOOL_NAMES = ("generate", "edit", "comment")

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _nid() -> str:
    return uuid.uuid4().hex


def _sse(obj: dict[str, Any]) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return f"data: {raw}\n\n".encode()


_DONE = b"data: [DONE]\n\n"


def _user_ctx(prompt: str) -> agents_llm.ChatContext:
    ctx = agents_llm.ChatContext()
    ctx.add_message(role="user", content=prompt)
    return ctx


async def _chat_collect(llm: Any, prompt: str) -> str:
    """Single-turn chat, returning the full response text."""
    stream = llm.chat(chat_ctx=_user_ctx(prompt))
    return (await stream.collect()).text or ""


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = min(
        [idx for idx in (text.find("["), text.find("{")) if idx != -1],
        default=-1,
    )
    if start == -1:
        raise ValueError("No JSON array/object found in model output")

    open_char, close_char = text[start], "]" if text[start] == "[" else "}"
    end = text.rfind(close_char) + 1
    if end == 0:
        raise ValueError("Unterminated JSON in model output")
    return json.loads(text[start:end])


def parse_tool_name(text: str) -> str:
    lower = (text or "").strip().lower()
    for name in TOOL_NAMES:
        if name in lower:
            return name
    return "generate"


def parse_comments(text: str) -> list[dict[str, Any]]:
    data = _extract_json(text)
    items = data if isinstance(data, list) else (data.get("comments") or data.get("comment") or [])
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        block_id = item.get("blockId") or item.get("block_id")
        content = item.get("content")
        if block_id is None or content is None:
            continue
        out.append(
            {
                "blockId": str(block_id),
                "comment": str(item.get("comment") or item.get("comments") or ""),
                "content": str(content),
            }
        )
    return out


def parse_cell_updates(text: str) -> list[dict[str, Any]]:
    data = _extract_json(text)
    items = data if isinstance(data, list) else [data]
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("id") is not None:
            out.append(
                {
                    "id": str(item["id"]),
                    "content": str(item.get("content") or ""),
                }
            )
    return out


async def _stream_text(llm: Any, prompt: str) -> AsyncIterator[bytes]:
    """Emit the text-flow SSE events for a single-turn generation."""
    msg_id = f"msg_{uuid.uuid4().hex}"
    stream = llm.chat(chat_ctx=_user_ctx(prompt))

    yield _sse(
        {
            "type": "text-start",
            "id": msg_id,
            "providerMetadata": {"openai": {"itemId": msg_id}},
        }
    )

    joiner = MarkdownJoiner()
    async for chunk in stream:
        delta = getattr(chunk, "delta", None)
        text = getattr(delta, "content", None) if delta else None
        if not text:
            continue

        processed = joiner.process_text(text)
        if processed:
            yield _sse({"type": "text-delta", "id": msg_id, "delta": processed})
            await asyncio.sleep(joiner.delay_in_ms / 1000)

    remaining = joiner.flush()
    if remaining:
        yield _sse({"type": "text-delta", "id": msg_id, "delta": remaining})

    yield _sse({"type": "text-end", "id": msg_id})
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish"})


async def _comment_flow(
    *,
    api_key: str,
    client_model: str,
    messages: list[dict[str, Any]],
    block_markdown: str | None,
) -> AsyncIterator[bytes]:
    llm_model = resolve_model(client_model, fallback=config.AI_COMMAND_MODEL)
    llm = create_llm(model=llm_model, api_key=api_key)
    prompt = prompts.get_comment_prompt(messages, block_markdown)
    text = await _chat_collect(llm, prompt)
    items = parse_comments(text)

    for item in items:
        yield _sse(
            {
                "id": _nid(),
                "data": {"comment": item, "status": "streaming"},
                "type": "data-comment",
            }
        )
    yield _sse(
        {
            "id": _nid(),
            "data": {"comment": None, "status": "finished"},
            "type": "data-comment",
        }
    )


async def _table_flow(
    *,
    api_key: str,
    client_model: str,
    messages: list[dict[str, Any]],
    table_cell_markdown: str | None,
) -> AsyncIterator[bytes]:
    llm_model = resolve_model(client_model, fallback=config.AI_COMMAND_MODEL)
    llm = create_llm(model=llm_model, api_key=api_key)
    prompt = prompts.build_edit_table_prompt(messages, table_cell_markdown)
    text = await _chat_collect(llm, prompt)
    items = parse_cell_updates(text)

    for item in items:
        yield _sse(
            {
                "id": _nid(),
                "data": {"cellUpdate": item, "status": "streaming"},
                "type": "data-table",
            }
        )
    yield _sse(
        {
            "id": _nid(),
            "data": {"cellUpdate": None, "status": "finished"},
            "type": "data-table",
        }
    )


async def run_command(body: dict[str, Any]) -> AsyncIterator[bytes]:
    """Validate the body and yield the SSE response byte stream."""
    api_key = resolve_api_key(body.get("apiKey"))

    ctx = body.get("ctx") or {}
    messages = body.get("messages") or []
    client_model = body.get("model") or ""
    features = ctx.get("features") or {}
    markdown = ctx.get("markdown") or {}

    is_selecting = bool(features.get("isSelecting"))
    in_table = bool(features.get("isSelectionInTable"))
    single_cell = bool(features.get("isSingleCellSelection"))
    tool_name = ctx.get("toolName") or None

    yield _sse({"type": "start"})
    yield _sse({"type": "start-step"})

    if not tool_name or tool_name not in TOOL_NAMES:
        choose_model = resolve_model(client_model, fallback=config.AI_CHOOSE_MODEL)
        llm = create_llm(model=choose_model, api_key=api_key)
        prompt = prompts.get_choose_tool_prompt(
            is_selecting=is_selecting,
            messages=messages,
        )
        tool_name = parse_tool_name(await _chat_collect(llm, prompt))

    yield _sse({"data": tool_name, "type": "data-toolName"})

    if tool_name == "comment":
        async for event in _comment_flow(
            api_key=api_key,
            client_model=client_model,
            messages=messages,
            block_markdown=markdown.get("blockWithBlockId"),
        ):
            yield event
    elif tool_name == "edit" and in_table and not single_cell:
        async for event in _table_flow(
            api_key=api_key,
            client_model=client_model,
            messages=messages,
            table_cell_markdown=markdown.get("tableCellWithId"),
        ):
            yield event
    elif tool_name == "edit":
        edit_prompt, edit_type = prompts.get_edit_prompt(
            is_selecting=True,
            messages=messages,
            features=features,
            with_selection=markdown.get("blockWithSelection"),
            table_cell_markdown=markdown.get("tableCellWithId"),
        )
        fallback_model = (
            config.AI_EDIT_SELECTION_MODEL
            if edit_type == "selection"
            else config.AI_EDIT_MODEL
        )
        llm_model = resolve_model(client_model, fallback=fallback_model)
        llm = create_llm(model=llm_model, api_key=api_key)
        async for event in _stream_text(llm, edit_prompt):
            yield event
    else:
        generate_prompt = prompts.get_generate_prompt(
            is_selecting=is_selecting,
            messages=messages,
            with_selection=markdown.get("blockWithSelection"),
        )
        llm_model = resolve_model(client_model, fallback=config.AI_COMMAND_MODEL)
        llm = create_llm(model=llm_model, api_key=api_key)
        async for event in _stream_text(llm, generate_prompt):
            yield event

    yield _DONE