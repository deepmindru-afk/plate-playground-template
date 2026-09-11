'use client';

import { normalizeStaticValue, type Value } from 'platejs';
import { Plate, usePlateEditor } from 'platejs/react';
import * as React from 'react';

import { EditorKit } from '@/components/editor/editor-kit';
import { SettingsDialog } from '@/components/editor/settings-dialog';
import { Editor, EditorContainer } from '@/components/ui/editor';
import { backendUrl } from '@/lib/backend';

type DocMeta = {
  id: string;
  title: string;
  updatedAt: string;
};

type Doc = DocMeta & {
  content: Value;
};

const EMPTY_VALUE = normalizeStaticValue([
  { children: [{ text: '' }], type: 'p' },
]);

export function PlateEditor() {
  const editor = usePlateEditor({
    plugins: EditorKit,
    value: EMPTY_VALUE,
  });

  const [docs, setDocs] = React.useState<DocMeta[]>([]);
  const [docId, setDocId] = React.useState<string | null>(null);
  const [title, setTitle] = React.useState<string>('Untitled');
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [loading, setLoading] = React.useState(true);

  const serverValue = React.useRef<Value | null>(null);

  const markDirty = () => {
    setDirty(true);
  };

  const loadDoc = async (id: string | null) => {
    if (!id) return;

    const res = await fetch(backendUrl(`/api/docs/${id}`));
    if (!res.ok) return;

    const doc: Doc = await res.json();
    serverValue.current = doc.content;
    editor.tf.setValue(normalizeStaticValue(doc.content));
    setDocId(doc.id);
    setTitle(doc.title);
    setDirty(false);
  };

  // Load the list of documents and open the first one on mount.
  React.useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(backendUrl('/api/docs'));
        const list: DocMeta[] = await res.json();

        if (cancelled) return;
        setDocs(list);

        if (list.length > 0) {
          await loadDoc(list[0].id);
        }
      } catch {
        // Backend not running — keep the demo content editable.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveDoc = async () => {
    setSaving(true);

    const content = editor.children as Value;

    try {
      const payload = JSON.stringify({
        title,
        content: normalizeStaticValue(content),
      });

      const res = docId
        ? await fetch(backendUrl(`/api/docs/${docId}`), {
            body: payload,
            headers: { 'Content-Type': 'application/json' },
            method: 'PUT',
          })
        : await fetch(backendUrl('/api/docs'), {
            body: payload,
            headers: { 'Content-Type': 'application/json' },
            method: 'POST',
          });

      const saved: Doc = await res.json();

      serverValue.current = saved.content;
      setDocId(saved.id);
      setTitle(saved.title);
      setDirty(false);
      setDocs((prev) =>
        prev.some((d) => d.id === saved.id)
          ? prev.map((d) =>
              d.id === saved.id ? { ...d, title: saved.title } : d
            )
          : [...prev, saved].sort((a, b) =>
              b.updatedAt.localeCompare(a.updatedAt)
            )
      );
    } finally {
      setSaving(false);
    }
  };

  const newDoc = () => {
    serverValue.current = null;
    editor.tf.setValue(
      normalizeStaticValue([{ type: 'p', children: [{ text: '' }] }])
    );
    setDocId(null);
    setTitle('Untitled');
    setDirty(true);
  };

  const switchDoc = async (id: string) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return;
    setLoading(true);
    try {
      await loadDoc(id);
    } finally {
      setLoading(false);
    }
  };

  const handleTitleChange = (value: string) => {
    setTitle(value);
    setDirty(true);
  };

  return (
    <Plate editor={editor} onValueChange={markDirty}>
      <div className="flex h-full flex-col">
        <div className="flex flex-wrap items-center gap-2 border-border border-b px-4 py-2">
          <select
            aria-label="Documents"
            className="h-8 max-w-56 rounded-md border border-input bg-background px-2 text-sm"
            disabled={loading}
            onChange={(e) => switchDoc(e.target.value)}
            value={docId ?? ''}
          >
            <option disabled value="">
              {loading ? 'Loading…' : 'Select a document…'}
            </option>
            {docs.map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.title}
              </option>
            ))}
          </select>

          <input
            aria-label="Document title"
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            onChange={(e) => handleTitleChange(e.target.value)}
            value={title}
          />

          <button
            className="h-8 rounded-md border border-input px-3 text-sm hover:bg-muted"
            onClick={newDoc}
            type="button"
          >
            New
          </button>

          <button
            className="h-8 rounded-md bg-primary px-3 text-primary-foreground text-sm disabled:opacity-50"
            disabled={saving || !dirty}
            onClick={saveDoc}
            type="button"
          >
            {saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}
          </button>
        </div>

        <EditorContainer className="flex-1">
          <Editor variant="demo" />
        </EditorContainer>
      </div>

      <SettingsDialog />
    </Plate>
  );
}
