"""Notes CRUD."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException

from gui import storage
from service.schemas import Note, NoteCreateRequest, NoteUpdateRequest

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=List[Note])
def list_notes(
    ticker: Optional[str] = None,
    run_id: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Note]:
    rows = storage.list_notes(ticker=ticker, run_id=run_id, query=q)
    return [Note(**r) for r in rows]


@router.post("", response_model=Note)
def create_note(req: NoteCreateRequest) -> Note:
    note_id = storage.add_note(
        title=req.title.strip(),
        body=req.body,
        ticker=req.ticker,
        run_id=req.run_id,
        tags=req.tags,
    )
    row = storage.get_note(note_id)
    if not row:
        raise HTTPException(status_code=500, detail="note created but not retrievable")
    return Note(**row)


@router.put("/{note_id}", response_model=Note)
def update_note(note_id: int, req: NoteUpdateRequest) -> Note:
    if not storage.get_note(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    storage.update_note(note_id, title=req.title, body=req.body, tags=req.tags)
    row = storage.get_note(note_id)
    if row is None:
        raise HTTPException(status_code=500, detail="note not retrievable")
    return Note(**row)


@router.delete("/{note_id}")
def delete_note(note_id: int) -> dict:
    storage.delete_note(note_id)
    return {"deleted": True}
