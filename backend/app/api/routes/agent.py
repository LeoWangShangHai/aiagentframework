import asyncio
import inspect
import json
import os
import uuid
from typing import Any
import re
from urllib.parse import urlparse
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.af_client import create_azure_responses_agent
from app.db.token_usage import record_turn_usage, list_turn_usage_page, count_turn_usage, list_conversations_page, count_conversations

router = APIRouter()

_conversation_lock = asyncio.Lock()
_conversation_threads: dict[str, dict[str, Any]] = {}


class AgentRunRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class AgentRunResponse(BaseModel):
    output: str
    conversation_id: str
    stats: dict | None = None


@router.get("/agent/info")
def agent_info() -> dict:
    # Load local env files (dev convenience), matching agent client behavior.
    # Priority:
    # 1) config/azure_openai.env
    # 2) .env
    try:
        from dotenv import load_dotenv  # type: ignore

        project_root = Path(__file__).resolve().parents[4]
        load_dotenv(dotenv_path=project_root / "config" / "azure_openai.env", override=True)
        load_dotenv(dotenv_path=project_root / ".env", override=True)
    except Exception:
        pass

    endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    deployment_name = (os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME") or "").strip()
    embedding_deployment = (os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or "").strip()
    api_version = (os.getenv("AZURE_OPENAI_API_VERSION") or "").strip()
    tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip()

    api_key_present = bool((os.getenv("AZURE_OPENAI_API_KEY") or "").strip())
    auth_mode = "api_key" if api_key_present else "entra_id"

    endpoint_host = ""
    if endpoint:
        try:
            parsed = urlparse(endpoint)
            endpoint_host = parsed.netloc or parsed.path
        except Exception:
            endpoint_host = endpoint

    return {
        "deployment_name": deployment_name or None,
        "embedding_deployment_name": embedding_deployment or None,
        "api_version": api_version or None,
        "endpoint": endpoint or None,
        "endpoint_host": endpoint_host or None,
        "auth_mode": auth_mode,
        "tenant_id": tenant_id or None,
    }



@router.get("/agent/usage")
def agent_usage(
    conversation_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    conv_id = (conversation_id or "").strip()
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 200")

    total = count_turn_usage(conv_id)
    offset = (page - 1) * page_size
    rows = list_turn_usage_page(conv_id, limit=page_size, offset=offset)

    items = [
        {
            "turn_index": r.turn_index,
            "model_name": r.model_name,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens": r.total_tokens,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    return {
        "conversation_id": conv_id,
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }



@router.get("/agent/conversations")
def agent_conversations(
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 200")

    total = count_conversations()
    offset = (page - 1) * page_size
    rows = list_conversations_page(limit=page_size, offset=offset)

    items = [
        {
            "conversation_id": r.conversation_id,
            "turns": r.turns,
            "total_tokens": r.total_tokens,
            "last_created_at": r.last_created_at,
        }
        for r in rows
    ]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }



def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _as_int(value) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        return int(value)
    except Exception:
        return None


def _extract_usage(obj) -> dict[str, int] | None:
    """Best-effort extraction of token usage from agent results/updates."""

    if obj is None:
        return None

    usage = getattr(obj, "usage", None)
    if usage is None and isinstance(obj, dict):
        usage = obj.get("usage")

    if usage is None:
        inner = getattr(obj, "response", None)
        if inner is None and isinstance(obj, dict):
            inner = obj.get("response")
        if inner is not None:
            usage = getattr(inner, "usage", None)
            if usage is None and isinstance(inner, dict):
                usage = inner.get("usage")

    if usage is None:
        return None

    if not isinstance(usage, dict):
        model_dump = getattr(usage, "model_dump", None)
        if callable(model_dump):
            try:
                usage = model_dump()
            except Exception:
                usage = None
        if usage is not None and not isinstance(usage, dict):
            dict_fn = getattr(usage, "dict", None)
            if callable(dict_fn):
                try:
                    usage = dict_fn()
                except Exception:
                    usage = None

    if not isinstance(usage, dict):
        return None

    input_tokens = _as_int(usage.get("input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    total_tokens = _as_int(usage.get("total_tokens"))

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    result: dict[str, int] = {}
    if input_tokens is not None:
        result["input_tokens"] = input_tokens
    if output_tokens is not None:
        result["output_tokens"] = output_tokens
    if total_tokens is not None:
        result["total_tokens"] = total_tokens
    return result


def _extract_model_name(obj) -> str | None:
    if obj is None:
        return None

    for attr in ("model", "model_name", "deployment", "deployment_name"):
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if isinstance(obj, dict):
        for key in ("model", "model_name", "deployment", "deployment_name"):
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    inner = getattr(obj, "response", None)
    if inner is None and isinstance(obj, dict):
        inner = obj.get("response")
    if inner is not None:
        return _extract_model_name(inner)

    return None


def _fallback_model_name() -> str | None:
    return (os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME") or "").strip() or None


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _token_count_fallback(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return 0

    # Rough but stable: count CJK chars + word-ish chunks + remaining punctuation.
    cjk = len(_CJK_RE.findall(text))
    words = len(_WORD_RE.findall(text))
    # Remaining non-space chars excluding counted word chars.
    stripped = re.sub(_WORD_RE, "", text)
    rest = sum(1 for ch in stripped if not ch.isspace())
    return max(1, cjk + words + rest)


def _token_count(text: str) -> int:
    text = text or ""
    if not text.strip():
        return 0

    # Prefer tiktoken if available (more accurate), otherwise fallback.
    try:
        import tiktoken  # type: ignore

        try:
            enc = tiktoken.get_encoding("o200k_base")
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return _token_count_fallback(text)


def _compute_usage_from_texts(input_text: str, output_text: str) -> dict[str, int]:
    input_tokens = _token_count(input_text)
    output_tokens = _token_count(output_text)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _get_stats(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {
            "turns": 0,
            "total": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "last": None,
        }
    stats = record.get("stats")
    if isinstance(stats, dict):
        return stats
    return {
        "turns": 0,
        "total": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "last": None,
    }


def _apply_usage(stats: dict[str, Any], usage: dict[str, int] | None) -> dict[str, Any]:
    if not usage:
        stats["last"] = None
        return stats

    total = stats.get("total")
    if not isinstance(total, dict):
        total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if key in usage:
            total[key] = int(total.get(key, 0)) + int(usage[key])

    stats["total"] = total
    stats["last"] = usage
    stats["turns"] = int(stats.get("turns", 0)) + 1
    return stats


def _extract_text(result) -> str:
    if result is None:
        return ""

    # Common patterns across SDKs
    for attr in ("output_text", "text", "content"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value

    # Some results expose a dict-like payload
    if isinstance(result, dict):
        for key in ("output_text", "text", "content", "message", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return str(result)


def _extract_delta(update) -> str:
    if update is None:
        return ""

    preferred_keys = ("delta", "text", "output_text", "content")

    # 1) Direct common attributes
    for attr in preferred_keys:
        value = getattr(update, attr, None)
        if isinstance(value, str) and value:
            return value

    def to_obj(value):
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, dict):
            return value

        # Pydantic v2
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                return model_dump()
            except Exception:
                pass

        # Pydantic v1
        dict_fn = getattr(value, "dict", None)
        if callable(dict_fn):
            try:
                return dict_fn()
            except Exception:
                pass

        # Best-effort object dict
        try:
            d = getattr(value, "__dict__", None)
            if isinstance(d, dict):
                return d
        except Exception:
            pass

        return None

    def find_text(node, depth: int = 0) -> str:
        if depth > 6:
            return ""
        if node is None:
            return ""
        if isinstance(node, str):
            return ""
        if isinstance(node, dict):
            for key in preferred_keys:
                v = node.get(key)
                if isinstance(v, str) and v:
                    return v
            # Search nested values
            for v in node.values():
                found = find_text(v, depth + 1)
                if found:
                    return found
        if isinstance(node, list):
            for item in node:
                found = find_text(item, depth + 1)
                if found:
                    return found
        return ""

    obj = to_obj(update)
    return find_text(obj)


@router.post("/agent/run", response_model=AgentRunResponse)
async def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
    try:
        agent = create_azure_responses_agent()

        conversation_id = (payload.conversation_id or "").strip() or str(uuid.uuid4())

        async with _conversation_lock:
            record = _conversation_threads.get(conversation_id)

        serialized_thread = None
        stats = _get_stats(record if isinstance(record, dict) else None)
        if isinstance(record, dict):
            serialized_thread = record.get("thread")
            # Back-compat: older values stored the thread dict directly
            if serialized_thread is None and "thread" not in record:
                serialized_thread = record

        if isinstance(serialized_thread, dict):
            thread = agent.deserialize_thread(serialized_thread)
            if inspect.isawaitable(thread):
                thread = await thread
        else:
            thread = agent.get_new_thread()
            if inspect.isawaitable(thread):
                thread = await thread

        result = await agent.run(payload.message, thread=thread)

        output_text = _extract_text(result)
        usage = _extract_usage(result) or _compute_usage_from_texts(payload.message, output_text)
        model_name = _extract_model_name(result) or _fallback_model_name()
        stats = _apply_usage(stats, usage)

        try:
            await asyncio.to_thread(
                record_turn_usage,
                conversation_id,
                int(stats.get("turns", 0)),
                usage,
                model_name,
            )
        except Exception:
            # Best-effort persistence; do not fail the request if DB is unavailable.
            pass

        serialized = thread.serialize()
        if inspect.isawaitable(serialized):
            serialized = await serialized

        async with _conversation_lock:
            _conversation_threads[conversation_id] = {"thread": serialized, "stats": stats}

        return AgentRunResponse(output=output_text, conversation_id=conversation_id, stats=stats)
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "agent-framework is not installed. Install with: "
                "py -m pip install -r backend\\requirements-agent.txt"
            ),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc


@router.post("/agent/stream")
async def stream_agent(payload: AgentRunRequest):
    """Stream assistant output as Server-Sent Events (SSE).

    Event types:
      - meta: { conversation_id }
      - delta: { delta }
      - done: { conversation_id }
      - error: { message }
    """

    try:
        agent = create_azure_responses_agent()

        conversation_id = (payload.conversation_id or "").strip() or str(uuid.uuid4())

        async with _conversation_lock:
            record = _conversation_threads.get(conversation_id)

        serialized_thread = None
        stats = _get_stats(record if isinstance(record, dict) else None)
        if isinstance(record, dict):
            serialized_thread = record.get("thread")
            if serialized_thread is None and "thread" not in record:
                serialized_thread = record

        if isinstance(serialized_thread, dict):
            thread = agent.deserialize_thread(serialized_thread)
            if inspect.isawaitable(thread):
                thread = await thread
        else:
            thread = agent.get_new_thread()
            if inspect.isawaitable(thread):
                thread = await thread

        async def event_generator():
            yield _sse("meta", {"conversation_id": conversation_id, "stats": stats})

            try:
                last_usage: dict[str, int] | None = None
                last_model_name: str | None = None
                output_acc = ""
                if hasattr(agent, "run_stream"):
                    async for update in agent.run_stream(payload.message, thread=thread):
                        delta = _extract_delta(update)
                        if delta:
                            output_acc += delta
                            yield _sse("delta", {"delta": delta})

                        update_usage = _extract_usage(update)
                        if update_usage:
                            last_usage = update_usage
                        update_model = _extract_model_name(update)
                        if update_model:
                            last_model_name = update_model
                else:
                    result = await agent.run(payload.message, thread=thread)
                    output = _extract_text(result)
                    if output:
                        output_acc += output
                        yield _sse("delta", {"delta": output})

                    last_usage = _extract_usage(result)
                    last_model_name = _extract_model_name(result)

                usage = last_usage or _compute_usage_from_texts(payload.message, output_acc)
                model_name = last_model_name or _fallback_model_name()
                stats_updated = _apply_usage(stats, usage)

                try:
                    await asyncio.to_thread(
                        record_turn_usage,
                        conversation_id,
                        int(stats_updated.get("turns", 0)),
                        usage,
                        model_name,
                    )
                except Exception:
                    # Best-effort persistence; do not break streaming if DB is unavailable.
                    pass

                serialized = thread.serialize()
                if inspect.isawaitable(serialized):
                    serialized = await serialized

                async with _conversation_lock:
                    _conversation_threads[conversation_id] = {"thread": serialized, "stats": stats_updated}

                yield _sse("stats", stats_updated)

                yield _sse("done", {"conversation_id": conversation_id})
            except Exception as exc:
                yield _sse("error", {"message": f"Agent error: {exc}"})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "agent-framework is not installed. Install with: "
                "py -m pip install -r backend\\requirements-agent.txt"
            ),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc
