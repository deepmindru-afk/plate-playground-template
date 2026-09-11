"""End-to-end test of the SSE command generator + copilot with a fake LLM.

Run:  backend/.venv/bin/python backend/tests/test_e2e.py
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import command, copilot
from app.schemas import CopilotBody


class FakeStream:
    def __init__(self, chunks: str, full_text: str):
        self._chunks = chunks
        self._full = full_text

    async def collect(self):
        return SimpleNamespace(text=self._full)

    def __aiter__(self):
        async def _gen():
            for piece in self._chunks:
                yield SimpleNamespace(delta=SimpleNamespace(content=piece))

        return _gen()


class FakeLLM:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.index = 0

    @staticmethod
    def _content_of(message) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.append(part.get("text", "") or "")
                else:
                    parts.append(getattr(part, "text", "") or "")
            return "".join(parts)
        return content or ""

    def chat(self, chat_ctx=None, **kwargs):
        prompt = "\n".join(self._content_of(m) for m in chat_ctx.messages())
        self.prompts.append(prompt)
        text = self.replies[self.index]
        self.index += 1
        return FakeStream(chunks=[text[:20], text[20:]], full_text=text)


def patch(llm):
    command.create_llm = lambda **kw: llm
    copilot.create_llm = lambda **kw: llm


async def collect_events(gen):
    return [chunk async for chunk in gen]


def test_command():
    llm = FakeLLM(["Better content here.\n\nSecond paragraph."])
    original = command.create_llm
    try:
        patch(llm)

        events = asyncio.run(
            collect_events(
                command.run_command(
                    {
                        "apiKey": "test-key",
                        "ctx": {
                            "toolName": "generate",
                            "features": {"isSelecting": True},
                            "markdown": {
                                "blockWithSelection": "This is a <Selection>test</Selection> doc."
                            },
                        },
                        "messages": [
                            {
                                "role": "user",
                                "parts": [{"type": "text", "text": "Improve this"}],
                            }
                        ],
                        "model": "openai/gpt-4o-mini",
                    }
                )
            )
        )
    finally:
        command.create_llm = original

    types = [e.decode().split(":", 1)[1].strip() for e in events]
    assert types[0] == '{"type":"start"}', types[0]
    assert types[1] == '{"type":"start-step"}', types[1]
    assert types[2] == '{"data":"generate","type":"data-toolName"}', types[2]
    deltas = [t for t in types if '"text-delta"' in t]
    assert len(deltas) == 2, deltas
    assert types[-1] == "[DONE]", types[-1]
    assert "<Selection>test</Selection>" in llm.prompts[0], llm.prompts[0]
    assert "Improve this" in llm.prompts[0], llm.prompts[0]
    # deltas forward the streamed model text (re-chunked by the markdown joiner)
    import json

    joined = "".join(json.loads(t)["delta"] for t in deltas)
    assert joined == "Better content here.\n\nSecond paragraph.", repr(joined)


def test_tool_inference():
    llm = FakeLLM(["edit", "fixed text"])
    original = command.create_llm
    try:
        patch(llm)
        events = asyncio.run(
            collect_events(
                command.run_command(
                    {
                        "apiKey": "key",
                        "ctx": {
                            "features": {"isSelecting": True, "isMultiBlocks": True},
                            "markdown": {"blockWithSelection": "# A\n\n# B"},
                        },
                        "messages": [
                            {
                                "role": "user",
                                "parts": [{"type": "text", "text": "Fix grammar"}],
                            }
                        ],
                    }
                )
            )
        )
    finally:
        command.create_llm = original

    types = [e.decode().split(":", 1)[1].strip() for e in events]
    tool_line = [t for t in types if '"data-toolName"' in t][0]
    assert '"edit"' in tool_line, tool_line
    assert "You are a strict classifier" in llm.prompts[0], llm.prompts[0]
    edit_prompt = llm.prompts[1]
    assert "# A\n\n# B" in edit_prompt, edit_prompt


def test_comment_flow():
    llm = FakeLLM(
        [
            '[{"blockId":"1","content":"AI systems are transforming modern workplaces","comments":"Clarify."}]'
        ]
    )
    original = command.create_llm
    try:
        patch(llm)
        events = asyncio.run(
            collect_events(
                command.run_command(
                    {
                        "apiKey": "key",
                        "ctx": {
                            "toolName": "comment",
                            "features": {"isSelecting": False},
                            "markdown": {
                                "blockWithBlockId": '<block id="1">AI systems are transforming modern workplaces by automating routine tasks.</block>'
                            },
                        },
                        "messages": [
                            {
                                "role": "user",
                                "parts": [{"type": "text", "text": "Review"}],
                            }
                        ],
                    }
                )
            )
        )
    finally:
        command.create_llm = original

    types = [e.decode().split(":", 1)[1].strip() for e in events]
    comments = [t for t in types if '"data-comment"' in t]
    assert len(comments) == 2, comments
    assert '"blockId":"1"' in comments[0], comments[0]
    assert '"status":"streaming"' in comments[0], comments[0]
    assert '"status":"finished"' in comments[1], comments[1]
    assert '"data":"comment"' in "\n".join(types), types
    assert types[-1] == "[DONE]", types[-1]


def test_table_flow():
    llm = FakeLLM(['[{"id":"c1","content":"New York"}]'])
    original = command.create_llm
    try:
        patch(llm)
        events = asyncio.run(
            collect_events(
                command.run_command(
                    {
                        "apiKey": "key",
                        "ctx": {
                            "toolName": "edit",
                            "features": {
                                "isSelecting": True,
                                "isSelectionInTable": True,
                                "isSingleCellSelection": False,
                            },
                            "markdown": {
                                "tableCellWithId": '| Name | City |\n| --- | --- |\n| John | <CellRef id="c1" /> |\n\n<Cell id="c1">\nNew york\n</Cell>'
                            },
                        },
                        "messages": [
                            {
                                "role": "user",
                                "parts": [{"type": "text", "text": "Fix grammar"}],
                            }
                        ],
                    }
                )
            )
        )
    finally:
        command.create_llm = original

    types = [e.decode().split(":", 1)[1].strip() for e in events]
    tables = [t for t in types if '"data-table"' in t]
    assert len(tables) == 2, tables
    assert '"data":"edit"' in "\n".join(types)
    assert '"cellUpdate":{"id":"c1","content":"New York"}' in tables[0], tables[0]
    assert '"status":"finished"' in tables[1], tables[1]
    assert "You are a table cell editor assistant" in llm.prompts[0], llm.prompts[0]


def test_copilot():
    llm = FakeLLM([" brown fox"])
    original = copilot.create_llm
    try:
        patch(llm)
        result = asyncio.run(
            copilot.run_copilot(
                CopilotBody(
                    apiKey="test-key",
                    instructions="You are a writing assistant.",
                    prompt="Continue: the quick",
                    model="gpt-4o-mini",
                )
            )
        )
    finally:
        copilot.create_llm = original

    assert result == {"text": " brown fox"}, result
    assert "You are a writing assistant." in llm.prompts[0], llm.prompts[0]
    assert llm.prompts[0].endswith("the quick"), llm.prompts[0]


def main():
    test_command()
    test_tool_inference()
    test_comment_flow()
    test_table_flow()
    test_copilot()
    print("ALL E2E TESTS PASSED")


if __name__ == "__main__":
    main()