"""RAG indexing/retrieval: embeds a repo's code into Qdrant so review
prompts can be augmented with context beyond the raw diff.

Deliberately skips LangChain — chunk/embed/upsert/query is simple enough
that the extra framework would add indirection without real benefit here.
"""

import logging

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.services.github_api import get_default_branch, get_file_content, list_repo_files

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # matches OpenAI's text-embedding-3-small default
CHUNK_LINES = 60
CHUNK_OVERLAP = 10
MAX_FILES = 300
MAX_FILE_BYTES = 100_000
INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rs", ".kt", ".swift", ".md",
}

_qdrant: QdrantClient | None = None
_openai: OpenAI | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=settings.qdrant_url)
    return _qdrant


def _get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.openai_api_key)
    return _openai


def _collection_name(repository_id: int) -> str:
    return f"repo_{repository_id}"


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = _get_openai().embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def _chunk_file(path: str, content: str) -> list[tuple[int, str]]:
    lines = content.splitlines()
    if not lines:
        return []
    step = max(CHUNK_LINES - CHUNK_OVERLAP, 1)
    chunks = []
    for start in range(0, len(lines), step):
        chunk_lines = lines[start : start + CHUNK_LINES]
        if not chunk_lines:
            continue
        text = f"# file: {path} (lines {start + 1}-{start + len(chunk_lines)})\n" + "\n".join(
            chunk_lines
        )
        chunks.append((start + 1, text))
        if start + CHUNK_LINES >= len(lines):
            break
    return chunks


def index_repository(repository_id: int, token: str, owner: str, repo_name: str) -> int:
    """(Re)index a repo's default branch into its Qdrant collection.

    Returns the number of chunks indexed. Recreates the collection each
    time — simplest way to avoid stale points, at the cost of not being
    incremental.
    """
    ref = get_default_branch(token, owner, repo_name)
    entries = list_repo_files(token, owner, repo_name, ref)

    candidates = [
        e
        for e in entries
        if any(e["path"].endswith(ext) for ext in INDEXABLE_EXTENSIONS)
        and 0 < e["size"] <= MAX_FILE_BYTES
    ]
    if len(candidates) > MAX_FILES:
        logger.info(
            "Repo %s/%s has %d indexable files, capping at %d",
            owner,
            repo_name,
            len(candidates),
            MAX_FILES,
        )
        candidates = candidates[:MAX_FILES]

    chunk_texts: list[str] = []
    chunk_payloads: list[dict] = []
    for entry in candidates:
        content = get_file_content(token, owner, repo_name, entry["path"], ref)
        if content is None:
            continue
        for start_line, text in _chunk_file(entry["path"], content):
            chunk_texts.append(text)
            chunk_payloads.append({"file": entry["path"], "start_line": start_line, "text": text})

    collection = _collection_name(repository_id)
    client = _get_qdrant()
    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )

    if not chunk_texts:
        return 0

    BATCH = 100
    point_id = 0
    for batch_start in range(0, len(chunk_texts), BATCH):
        batch_texts = chunk_texts[batch_start : batch_start + BATCH]
        batch_payloads = chunk_payloads[batch_start : batch_start + BATCH]
        vectors = _embed(batch_texts)
        points = [
            PointStruct(id=point_id + i, vector=vector, payload=payload)
            for i, (vector, payload) in enumerate(zip(vectors, batch_payloads))
        ]
        client.upsert(collection_name=collection, points=points)
        point_id += len(points)

    return len(chunk_texts)


def query_context(repository_id: int, query_text: str, top_k: int | None = None) -> list[dict]:
    """Return up to top_k relevant chunks, or [] if unavailable for any reason."""
    collection = _collection_name(repository_id)
    try:
        client = _get_qdrant()
        if not client.collection_exists(collection):
            return []
        [vector] = _embed([query_text])
        result = client.query_points(
            collection_name=collection, query=vector, limit=top_k or settings.rag_top_k
        )
        return [point.payload for point in result.points]
    except Exception:
        logger.exception("RAG context lookup failed for repository %s", repository_id)
        return []
