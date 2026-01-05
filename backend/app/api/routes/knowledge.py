from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.af_client import create_azure_responses_agent
from app.knowledge.store import (
    index_file,
    knowledge_stats,
    list_uploads,
    query_knowledge,
    save_upload,
    supported_exts,
    write_upload_metadata,
)


router = APIRouter()


class KnowledgeQuery(BaseModel):
    question: str
    top_k: int | None = 4
    use_llm: bool | None = True


class KnowledgeAnswer(BaseModel):
    answer: str
    sources: list[dict[str, Any]]


@router.post("/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix and f".{suffix}" not in supported_exts():
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{suffix}")

    content = await file.read()
    path = save_upload(file.filename, content)
    info = index_file(path, source_name=file.filename)
    write_upload_metadata(
        path,
        original_name=file.filename,
        size_bytes=len(content),
        chunks_indexed=int(info.get("chunks", 0)),
        chunk_lengths=list(info.get("chunk_lengths") or []),
    )

    return {
        "file": file.filename,
        "stored_path": str(path),
        "chunks_indexed": info.get("chunks", 0),
        "supported_exts": sorted(supported_exts()),
        "stats": knowledge_stats(),
    }


def _build_prompt(question: str, contexts: list[dict[str, str]]) -> str:
    lines = ["你是一个基于知识库回答的助手。请只使用提供的上下文回答用户问题。"]
    for idx, ctx in enumerate(contexts, 1):
        source = ctx.get("source", "unknown")
        text = ctx.get("text", "")
        lines.append(f"[{idx}] 来源:{source}\n{text}")
    lines.append(f"\n用户问题: {question}\n请用中文简洁回答，并引用相关来源编号。")
    return "\n\n".join(lines)


@router.post("/knowledge/query", response_model=KnowledgeAnswer)
async def knowledge_query(payload: KnowledgeQuery) -> KnowledgeAnswer:
    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")

    try:
        chunks = query_knowledge(q, top_k=payload.top_k or 4)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"query failed: {exc}") from exc

    if not chunks:
        return KnowledgeAnswer(answer="知识库中没有可用内容。", sources=[])

    sources = [{"text": c.text, "source": c.source, "distance": c.distance} for c in chunks]
    if payload.use_llm is False:
        return KnowledgeAnswer(answer="(仅检索结果，未调用模型)", sources=sources)
    prompt = _build_prompt(q, sources)

    try:
        agent = create_azure_responses_agent()
        thread = agent.get_new_thread()
        if inspect.isawaitable(thread):
            thread = await thread
        result = await agent.run(prompt, thread=thread)
        answer = getattr(result, "output_text", None) or getattr(result, "text", None) or str(result)
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "agent-framework is not installed. Install with: "
                "py -m pip install -r backend\\requirements-agent.txt"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"agent error: {exc}") from exc

    return KnowledgeAnswer(answer=answer, sources=sources)


@router.get("/knowledge/stats")
def knowledge_stats_endpoint() -> dict:
    return knowledge_stats()


@router.get("/knowledge/uploads")
def knowledge_uploads() -> dict:
    return {"items": list_uploads()}
