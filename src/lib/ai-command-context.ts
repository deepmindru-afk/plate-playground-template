'use client';

/**
 * Client-side replacement for the Slate->markdown serialization that used to
 * happen inside the /api/ai/command route. The Python backend cannot read
 * Slate, so we serialize the author-selected context here and ship it in
 * `ctx.markdown` + `ctx.features`.
 */

import { getMarkdown } from '@platejs/ai';
import { serializeMd } from '@platejs/markdown';
import {
  createSlateEditor,
  KEYS,
  RangeApi,
  type SlateEditor,
  type TSelection,
  type Value,
} from 'platejs';

import { BaseEditorKit } from '@/components/editor/editor-base-kit';

const SELECTION_START = '<Selection>';
const SELECTION_END = '</Selection>';
const VOID_CONTENT_SEPARATOR = '】';

type CommandFeatures = {
  isSelecting: boolean;
  isMultiBlocks: boolean;
  isSelectionInTable: boolean;
  isSingleCellSelection: boolean;
};

export type CommandMarkdown = {
  blockWithBlockId?: string;
  blockWithSelection?: string;
  tableCellWithId?: string;
};

export type CommandContext = {
  children?: Value;
  selection?: TSelection;
  markdown?: CommandMarkdown;
  features?: CommandFeatures;
};

/**
 * Build a throwaway Slate editor for `getMarkdown`/`api` queries. Mirrors the
 * editor the TS route used to create server-side.
 */
export function createEditor(
  children: unknown,
  selection?: unknown
): SlateEditor {
  return createSlateEditor({
    plugins: BaseEditorKit,
    selection: selection as TSelection | undefined,
    value: children as Value,
  });
}

/** Add <Selection> markers around the current expanded selection. */
export const addSelection = (editor: SlateEditor) => {
  if (!editor.selection) return;
  if (editor.api.isExpanded()) {
    const [start, end] = RangeApi.edges(editor.selection);

    editor.tf.withoutNormalizing(() => {
      editor.tf.insertText(SELECTION_END, { at: end });
      editor.tf.insertText(SELECTION_START, { at: start });

      // If the selection ends on a void element the placeholder is dropped; fix
      // it up manually so the highlight marker survives serialization.
      const node = editor.api.block({ at: end.path });
      if (node && editor.api.isVoid(node[0])) {
        const voidString = serializeMd(editor, { value: [node[0]] });
        editor.tf.insertText(`${VOID_CONTENT_SEPARATOR}${voidString}`, {
          at: end,
        });
      }
    });
  }
};

const removeEscapeSelection = (editor: SlateEditor, text: string) => {
  let newText = text
    .replace(`\\${SELECTION_START}`, SELECTION_START)
    .replace(`\\${SELECTION_END}`, SELECTION_END);

  if (!newText.includes(SELECTION_END)) {
    const [_, end] = RangeApi.edges(editor.selection!);

    const node = editor.api.block({ at: end.path });

    if (!node) return newText;
    if (editor.api.isVoid(node[0])) {
      const voidString = serializeMd(editor, { value: [node[0]] });

      if (!voidString) return newText;

      // Replace the inserted separator + void serialization with a trailing
      // selection marker so the prompt shows where the highlight ended.
      const startIdx = newText.lastIndexOf(VOID_CONTENT_SEPARATOR);
      if (startIdx !== -1) {
        const idx = newText.lastIndexOf(voidString);
        if (idx !== -1) {
          newText =
            newText.slice(0, startIdx) +
            voidString.trimEnd() +
            SELECTION_END +
            newText.slice(idx + voidString.length);
        }
      }
    }
  }

  return newText;
};

/** Markdown of the full document with each block id embedded. */
export const getBlockWithBlockIdMarkdown = (editor: SlateEditor) =>
  getMarkdown(editor, { type: 'blockWithBlockId' });

/** Markdown with <Selection> markers around the expanded selection. */
export const getMarkdownWithSelection = (editor: SlateEditor) => {
  addSelection(editor);
  return removeEscapeSelection(editor, getMarkdown(editor, { type: 'block' }));
};

/** True when the selection covers more than one top-level block. */
export const isMultiBlocks = (editor: SlateEditor) => {
  const blocks = editor.api.blocks({ mode: 'lowest' });
  return blocks.length > 1;
};

/** True when the selection sits inside a table cell. */
export const isSelectionInTable = (editor: SlateEditor): boolean => {
  if (!editor.selection) return false;

  const tableEntry = editor.api.block({
    at: editor.selection,
    match: { type: KEYS.table },
  });

  return !!tableEntry;
};

/** True when the selection is confined to exactly one table cell. */
export const isSingleCellSelection = (editor: SlateEditor): boolean => {
  if (!editor.selection) return false;

  const cells = Array.from(
    editor.api.nodes({
      at: editor.selection,
      match: { type: KEYS.td },
    })
  );

  return cells.length === 1;
};

export function getFeatures(editor: SlateEditor): CommandFeatures {
  const isSelecting = editor.api.isExpanded();

  return {
    isSelecting,
    isMultiBlocks: isMultiBlocks(editor),
    isSelectionInTable: isSelectionInTable(editor),
    isSingleCellSelection: isSingleCellSelection(editor),
  };
}

/**
 * Serialize the author-selected context for the command request.
 * Runs against a transient clone so the real editor is never mutated.
 */
export function buildCommandContext(ctx: {
  children?: unknown;
  selection?: unknown;
}): {
  features: CommandFeatures;
  markdown: CommandMarkdown;
} {
  const editor = createEditor(ctx.children, ctx.selection);

  const features = getFeatures(editor);

  const markdown: CommandMarkdown = {
    blockWithBlockId: getBlockWithBlockIdMarkdown(editor),
  };

  if (features.isSelecting) {
    // Runs addSelection internally; do it last so blockWithBlockId stays clean.
    markdown.blockWithSelection = getMarkdownWithSelection(editor);

    if (features.isSelectionInTable && !features.isSingleCellSelection) {
      markdown.tableCellWithId = getMarkdown(editor, {
        type: 'tableCellWithId',
      });
    }
  }

  return { features, markdown };
}
