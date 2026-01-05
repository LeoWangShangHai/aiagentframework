from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from chromadb import PersistentClient

from app.db.token_usage import count_turn_usage, record_turn_usage


# Supported file types for simple demo ingestion.
_SUPPORTED_EXTS = {".txt", ".md", ".pdf"}


def _load_env() -> None:
    """Best-effort local .env loading to support local dev."""
    try:
        from dotenv import load_dotenv  # type: ignore

        project_root = Path(__file__).resolve().parents[3]
        load_dotenv(dotenv_path=project_root / "config" / "azure_openai.env", override=True)
        load_dotenv(dotenv_path=project_root / ".env", override=True)
    except Exception:
        pass


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _uploads_dir() -> Path:
    return _project_root() / "data" / "uploads"


def _chroma_dir() -> Path:
    return _project_root() / "data" / "chroma"


def _ensure_dirs() -> None:
    _uploads_dir().mkdir(parents=True, exist_ok=True)
    _chroma_dir().mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    distance: float | None


def _get_chroma_collection():
    _ensure_dirs()
    client = PersistentClient(path=str(_chroma_dir()))
    return client.get_or_create_collection(name="knowledge")


def _get_embedding_client():
    _load_env()
    endpoint = _get_required_env("AZURE_OPENAI_ENDPOINT")
    deployment = _get_required_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    tenant_id = os.getenv("AZURE_TENANT_ID", "").strip()

    try:
        from openai import AzureOpenAI  # type: ignore
    except Exception as exc:
        raise RuntimeError("Missing dependency: openai. Install with backend/requirements-agent.txt") from exc

    if api_key:
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version or "2024-06-01",
            api_key=api_key,
        )
        return client, deployment

    try:
        from azure.identity import AzureCliCredential, DefaultAzureCredential  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Entra ID auth requires azure-identity. Install with: "
            "py -m pip install -r backend\\requirements-agent.txt"
        ) from exc

    if tenant_id:
        credential = AzureCliCredential(tenant_id=tenant_id)
    else:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    def _token_provider() -> str:
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version or "2024-06-01",
        azure_ad_token_provider=_token_provider,
    )
    return client, deployment


def _usage_from_embedding(response) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None

    if not isinstance(usage, dict):
        model_dump = getattr(usage, "model_dump", None)
        if callable(model_dump):
            try:
                usage = model_dump()
            except Exception:
                usage = None
    if not isinstance(usage, dict):
        return None

    prompt = usage.get("prompt_tokens")
    total = usage.get("total_tokens")
    try:
        prompt_tokens = int(prompt) if prompt is not None else None
    except Exception:
        prompt_tokens = None
    try:
        total_tokens = int(total) if total is not None else None
    except Exception:
        total_tokens = None

    tokens = prompt_tokens if prompt_tokens is not None else total_tokens
    if tokens is None:
        return None
    return {"input_tokens": tokens, "output_tokens": 0, "total_tokens": tokens}


def _embed_texts(texts: Iterable[str]) -> list[list[float]]:
    client, deployment = _get_embedding_client()
    items = [t for t in texts if t and t.strip()]
    if not items:
        return []
    response = client.embeddings.create(model=deployment, input=items)
    return [item.embedding for item in response.data]


def _embed_texts_with_usage(texts: Iterable[str]) -> tuple[list[list[float]], dict[str, int] | None]:
    client, deployment = _get_embedding_client()
    items = [t for t in texts if t and t.strip()]
    if not items:
        return [], None
    response = client.embeddings.create(model=deployment, input=items)
    embeddings = [item.embedding for item in response.data]
    return embeddings, _usage_from_embedding(response)


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, *, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Lightweight chunker for short docs."""
    text = _clean_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + max_chars)
        if end < length:
            last_space = text.rfind(" ", start, end)
            if last_space > start + 200:
                end = last_space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(0, end - overlap)
    return chunks


def _read_text_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise RuntimeError("Missing dependency: pypdf. Install with backend/requirements-agent.txt") from exc

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def read_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_text_from_pdf(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise RuntimeError(f"Unsupported file type: {suffix}")


def save_upload(filename: str, content: bytes) -> Path:
    _ensure_dirs()
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name) or "upload"
    target = _uploads_dir() / f"{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(content)
    return target


def _metadata_path(path: Path) -> Path:
    return Path(str(path) + ".meta.json")


def write_upload_metadata(
    path: Path,
    *,
    original_name: str,
    size_bytes: int,
    chunks_indexed: int,
    chunk_lengths: list[int] | None = None,
) -> Path:
    meta = {
        "original_name": original_name,
        "stored_name": path.name,
        "stored_path": str(path),
        "size_bytes": int(size_bytes),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "chunks_indexed": int(chunks_indexed),
        "chunk_lengths": [int(x) for x in (chunk_lengths or [])],
    }
    meta_path = _metadata_path(path)
    meta_path.write_text(json.dumps(meta, ensure_ascii=True), encoding="utf-8")
    return meta_path


def list_uploads() -> list[dict]:
    _ensure_dirs()
    items: list[dict] = []
    for path in _uploads_dir().iterdir():
        if path.is_dir():
            continue
        if path.name.endswith(".meta.json"):
            continue
        if path.suffix.lower() not in _SUPPORTED_EXTS:
            continue

        meta_path = _metadata_path(path)
        meta: dict | None = None
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = None

        size_bytes = int(path.stat().st_size)
        if meta and isinstance(meta.get("uploaded_at"), str):
            uploaded_at = meta.get("uploaded_at")
        else:
            uploaded_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()

        chunk_lengths = list((meta or {}).get("chunk_lengths") or [])
        chunks_indexed = int((meta or {}).get("chunks_indexed") or 0)
        if not chunk_lengths:
            try:
                text = read_text_from_file(path)
                chunks = chunk_text(text)
                chunk_lengths = [len(c) for c in chunks]
                if chunks_indexed == 0:
                    chunks_indexed = len(chunks)
            except Exception:
                pass

        items.append(
            {
                "original_name": (meta or {}).get("original_name") or path.name,
                "stored_name": path.name,
                "size_bytes": size_bytes,
                "uploaded_at": uploaded_at,
                "chunks_indexed": chunks_indexed,
                "chunk_lengths": chunk_lengths,
            }
        )

    items.sort(key=lambda x: x.get("uploaded_at") or "", reverse=True)
    return items


def index_file(path: Path, *, source_name: str | None = None) -> dict:
    collection = _get_chroma_collection()
    text = read_text_from_file(path)
    chunks = chunk_text(text)
    if not chunks:
        return {"chunks": 0}

    chunk_lengths = [len(c) for c in chunks]
    embeddings, usage = _embed_texts_with_usage(chunks)
    ids = [uuid.uuid4().hex for _ in chunks]
    source = source_name or path.name
    metadatas = [{"source": source} for _ in chunks]

    collection.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    if usage:
        conversation_id = f"knowledge:upload:{source}"
        try:
            turn_index = count_turn_usage(conversation_id) + 1
            model_name = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "").strip() or None
            record_turn_usage(conversation_id, turn_index, usage, model_name)
        except Exception:
            # Best-effort; do not break ingestion if stats write fails.
            pass
    return {"chunks": len(chunks), "chunk_lengths": chunk_lengths}


def query_knowledge(query: str, *, top_k: int = 4) -> list[RetrievedChunk]:
    collection = _get_chroma_collection()
    embeddings, usage = _embed_texts_with_usage([query])
    if not embeddings:
        return []
    if usage:
        conversation_id = "knowledge:query"
        try:
            turn_index = count_turn_usage(conversation_id) + 1
            model_name = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "").strip() or None
            record_turn_usage(conversation_id, turn_index, usage, model_name)
        except Exception:
            # Best-effort; do not break query if stats write fails.
            pass
    results = collection.query(
        query_embeddings=embeddings,
        n_results=int(top_k),
        include=["documents", "metadatas", "distances"],
    )
    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or []
    distances = results.get("distances") or []

    chunks: list[RetrievedChunk] = []
    for idx, doc in enumerate(documents[0] if documents else []):
        meta = (metadatas[0][idx] if metadatas and metadatas[0] else {}) or {}
        dist = None
        if distances and distances[0] and idx < len(distances[0]):
            dist = float(distances[0][idx])
        chunks.append(
            RetrievedChunk(
                text=str(doc),
                source=str(meta.get("source") or "unknown"),
                distance=dist,
            )
        )
    return chunks


def knowledge_stats() -> dict:
    collection = _get_chroma_collection()
    count = collection.count()
    return {"chunks": int(count)}


def supported_exts() -> set[str]:
    return set(_SUPPORTED_EXTS)
