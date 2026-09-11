"""Port of ``src/lib/markdown-joiner-transform.ts`` to Python.

The LLM streams split markdown tokens (e.g. ``**bold**`` arrives as
``**``, ``bold``, ``**``). The editor's markdown deserializer needs the
joined token, so deltas are buffered until a candidate pattern completes.
"""

import asyncio
import re

DEFAULT_DELAY_IN_MS = 10
NEST_BLOCK_DELAY_IN_MS = 100

_BOLD_PATTERN = re.compile(r"\*\*.*?\*\*")
_CODE_LINE_PATTERN = re.compile(r"```[^\s]+")
_LINK_PATTERN = re.compile(r"^\[.*?\]\(.*?\)$")
_UNORDERED_LIST_PATTERN = re.compile(r"^[*-]\s+.+")
_TODO_LIST_PATTERN = re.compile(r"^[*-]\s+\[[ xX]\]\s+.+")
_ORDERED_LIST_PATTERN = re.compile(r"^\d+\.\s+.+")
_MDX_TAG_PATTERN = re.compile(r"<([A-Za-z][A-Za-z0-9\-_]*)>")
_DIGIT_PATTERN = re.compile(r"^[0-9]$")


class MarkdownJoiner:
    def __init__(self) -> None:
        self.delay_in_ms = DEFAULT_DELAY_IN_MS
        self.buffer = ""
        self.document_character_count = 0
        self._is_buffering = False
        self._streaming_code_block = False
        self._streaming_large_document = False
        self._streaming_table = False

    # -- predicates -------------------------------------------------------- #

    def _is_complete_bold(self) -> bool:
        return bool(_BOLD_PATTERN.search(self.buffer))

    def _is_complete_code_block_end(self) -> bool:
        return self.buffer.rstrip() == "```"

    def _is_complete_code_block_start(self) -> bool:
        return bool(_CODE_LINE_PATTERN.search(self.buffer))

    def _is_complete_link(self) -> bool:
        return bool(_LINK_PATTERN.match(self.buffer))

    def _is_complete_list(self) -> bool:
        if _UNORDERED_LIST_PATTERN.match(self.buffer) and "[" in self.buffer:
            return bool(_TODO_LIST_PATTERN.match(self.buffer))
        return bool(
            _UNORDERED_LIST_PATTERN.match(self.buffer)
            or _ORDERED_LIST_PATTERN.match(self.buffer)
            or _TODO_LIST_PATTERN.match(self.buffer)
        )

    def _is_complete_mdx_tag(self) -> bool:
        return bool(_MDX_TAG_PATTERN.search(self.buffer))

    def _is_complete_table_start(self) -> bool:
        return self.buffer.startswith("|") and self.buffer.endswith("|")

    def _is_false_positive(self, char: str) -> bool:
        if self.buffer.startswith("[") and "http" in self.buffer:
            return False
        return char == "\n" or len(self.buffer) > 30

    def _is_large_document_start(self) -> bool:
        return self.document_character_count > 2500

    def _is_list_start_char(self, char: str) -> bool:
        return char in {"-", "*"} or bool(_DIGIT_PATTERN.match(char))

    def _is_table_existed(self) -> bool:
        return len(self.buffer) > 10 and "|" not in self.buffer

    # -- public ------------------------------------------------------------ #

    def flush(self) -> str:
        remaining = self.buffer
        self._clear_buffer()
        return remaining

    def process_text(self, text: str) -> str:
        output = ""

        for char in text:
            if (
                self._streaming_code_block
                or self._streaming_table
                or self._streaming_large_document
            ):
                self.buffer += char

                if char == "\n":
                    output += self.buffer
                    self._clear_buffer()

                if self._is_complete_code_block_end() and self._streaming_code_block:
                    self._streaming_code_block = False
                    self.delay_in_ms = DEFAULT_DELAY_IN_MS
                    output += self.buffer
                    self._clear_buffer()

                if self._is_table_existed() and self._streaming_table:
                    self._streaming_table = False
                    self.delay_in_ms = DEFAULT_DELAY_IN_MS
                    output += self.buffer
                    self._clear_buffer()

            elif self._is_buffering:
                self.buffer += char

                if self._is_complete_code_block_start():
                    self.delay_in_ms = NEST_BLOCK_DELAY_IN_MS
                    self._streaming_code_block = True
                    continue

                if self._is_complete_table_start():
                    self.delay_in_ms = NEST_BLOCK_DELAY_IN_MS
                    self._streaming_table = True
                    continue

                if self._is_large_document_start():
                    self.delay_in_ms = NEST_BLOCK_DELAY_IN_MS
                    self._streaming_large_document = True
                    continue

                if (
                    self._is_complete_bold()
                    or self._is_complete_mdx_tag()
                    or self._is_complete_list()
                    or self._is_complete_link()
                ):
                    output += self.buffer
                    self._clear_buffer()
                elif self._is_false_positive(char):
                    output += self.buffer
                    self._clear_buffer()

            elif char in {"*", "<", "`", "|", "["} or self._is_list_start_char(char):
                self.buffer = char
                self._is_buffering = True
            else:
                output += char

        self.document_character_count += len(text)
        return output

    async def process_stream(self, async_iter):
        """Yield (processed_text, delay_ms) pairs for each input text chunk."""
        async for text in async_iter:
            processed = self.process_text(text)
            if processed:
                yield processed, self.delay_in_ms
                await asyncio.sleep(self.delay_in_ms / 1000)

    def _clear_buffer(self) -> None:
        self.buffer = ""
        self._is_buffering = False