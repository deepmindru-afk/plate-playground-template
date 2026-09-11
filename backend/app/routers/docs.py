"""REST CRUD for editor documents (stored as JSON)."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import storage
from ..schemas import DocCreate, DocUpdate

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("")
async def list_docs():
    return await storage.list_docs()


@router.post("", status_code=201)
async def create_doc(body: DocCreate):
    return await storage.create_doc(body.title, body.content)


@router.get("/{doc_id}")
async def get_doc(doc_id: str):
    doc = await storage.get_doc(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/{doc_id}")
async def update_doc(doc_id: str, body: DocUpdate):
    doc = await storage.update_doc(doc_id, body.title, body.content)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_doc(doc_id: str):
    deleted = await storage.delete_doc(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return JSONResponse(status_code=204, content=None)