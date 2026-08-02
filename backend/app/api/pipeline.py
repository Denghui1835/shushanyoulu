"""全链路生成 API（SSE 进度流）."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.pipeline import run_pipeline

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/{document_id}/run")
async def run(document_id: str, db: AsyncSession = Depends(get_db)):
    async def event_stream():
        async for evt in run_pipeline(db, document_id):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
