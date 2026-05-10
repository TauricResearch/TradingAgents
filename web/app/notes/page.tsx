"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Notes } from "@/lib/api";
import { Markdown } from "@/components/Markdown";

export default function NotesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [tickerFilter, setTickerFilter] = useState("");

  const q = useQuery({
    queryKey: ["notes", search, tickerFilter],
    queryFn: () =>
      Notes.list({
        q: search || undefined,
        ticker: tickerFilter || undefined,
      }),
  });

  const [showNew, setShowNew] = useState(false);

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Notes</h1>
          <p className="text-muted text-sm">
            Markdown notes pinned to a ticker, run, or standalone.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowNew((s) => !s)}>
          {showNew ? "Cancel" : "+ New note"}
        </button>
      </header>

      {showNew && <NewNoteForm onDone={() => { setShowNew(false); qc.invalidateQueries({ queryKey: ["notes"] }); }} />}

      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <label className="label">Search</label>
          <input
            className="input w-full"
            placeholder="title / body / tags…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Ticker</label>
          <input
            className="input"
            placeholder="(any)"
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
          />
        </div>
      </div>

      <div className="space-y-3">
        {q.isLoading && <div className="text-muted text-sm">Loading…</div>}
        {!q.isLoading && (q.data?.length ?? 0) === 0 && (
          <div className="card text-sm text-muted">No notes match.</div>
        )}
        {(q.data ?? []).map((n) => (
          <NoteCard
            key={n.id}
            note={n}
            onChanged={() => qc.invalidateQueries({ queryKey: ["notes"] })}
          />
        ))}
      </div>
    </div>
  );
}

function NewNoteForm({ onDone }: { onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [ticker, setTicker] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");

  const create = useMutation({
    mutationFn: () => Notes.create({
      title: title.trim(),
      body,
      ticker: ticker.trim().toUpperCase() || undefined,
      tags: tags.trim() || undefined,
    }),
    onSuccess: onDone,
  });

  return (
    <form
      className="card grid grid-cols-1 md:grid-cols-3 gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim() || !body.trim()) return;
        create.mutate();
      }}
    >
      <div className="md:col-span-2">
        <label className="label">Title</label>
        <input className="input w-full" value={title} onChange={(e) => setTitle(e.target.value)} required />
      </div>
      <div>
        <label className="label">Ticker (optional)</label>
        <input className="input w-full" value={ticker} onChange={(e) => setTicker(e.target.value)} />
      </div>
      <div className="md:col-span-3">
        <label className="label">Body (markdown)</label>
        <textarea className="input w-full h-40" value={body} onChange={(e) => setBody(e.target.value)} required />
      </div>
      <div className="md:col-span-2">
        <label className="label">Tags (comma-separated)</label>
        <input className="input w-full" value={tags} onChange={(e) => setTags(e.target.value)} />
      </div>
      <div className="md:col-span-3 flex justify-end">
        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function NoteCard({
  note,
  onChanged,
}: {
  note: { id: number; title: string; body: string; ticker?: string | null; tags?: string | null; updated_at: string };
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [body, setBody] = useState(note.body);
  const [tags, setTags] = useState(note.tags ?? "");

  const save = useMutation({
    mutationFn: () => Notes.update(note.id, { title, body, tags: tags || undefined }),
    onSuccess: () => { setEditing(false); onChanged(); },
  });
  const del = useMutation({
    mutationFn: () => Notes.delete(note.id),
    onSuccess: onChanged,
  });

  if (editing) {
    return (
      <form
        className="card space-y-2"
        onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
      >
        <input className="input w-full" value={title} onChange={(e) => setTitle(e.target.value)} />
        <textarea className="input w-full h-40" value={body} onChange={(e) => setBody(e.target.value)} />
        <input className="input w-full" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tags" />
        <div className="flex gap-2 justify-end">
          <button type="button" className="btn" onClick={() => setEditing(false)}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>Save</button>
        </div>
      </form>
    );
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{note.title}</h3>
          <div className="text-xs text-muted">
            {note.ticker && <span className="mr-2">`{note.ticker}`</span>}
            {note.tags && <span className="mr-2 italic">{note.tags}</span>}
            <span>{note.updated_at}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn text-xs" onClick={() => setEditing(true)}>Edit</button>
          <button className="btn btn-danger text-xs" onClick={() => {
            if (confirm("Delete this note?")) del.mutate();
          }}>Delete</button>
        </div>
      </div>
      <div className="mt-3">
        <Markdown>{note.body}</Markdown>
      </div>
    </div>
  );
}
