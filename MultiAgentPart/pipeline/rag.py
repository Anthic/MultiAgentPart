"""
pipeline/rag.py
────────────────────────────────────────────────────────────
Production RAG: Qdrant Cloud + Mistral Embeddings API

Changes from dev:
  • Chroma (local)     → Qdrant Cloud (persistent, serverless-safe)
  • HuggingFace model  → Mistral Embeddings API (no cold-start, no download)
"""

import hashlib
import logging
import os
from typing import Dict, List

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_mistralai import MistralAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

load_dotenv()

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

QDRANT_URL      = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY  = os.getenv("QDRANT_API_KEY", "")
EMBEDDING_MODEL = "mistral-embed"   # Mistral's embedding model (1024-dim)
VECTOR_SIZE     = 1024              # mistral-embed output dimension
COLLECTION_PREFIX = "research_"


# ── Singletons ─────────────────────────────────────────────────────────────────

_qdrant_client: QdrantClient | None = None
_embeddings: MistralAIEmbeddings | None = None


def _get_client() -> QdrantClient:
    """Lazy-init Qdrant Cloud client (reused across requests)."""
    global _qdrant_client
    if _qdrant_client is None:
        if not QDRANT_URL or not QDRANT_API_KEY:
            raise EnvironmentError(
                "QDRANT_URL and QDRANT_API_KEY must be set in .env"
            )
        _qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        log.info("RAG: Qdrant client connected to %s", QDRANT_URL)
    return _qdrant_client


def _get_embeddings() -> MistralAIEmbeddings:
    """Lazy-init Mistral Embeddings (API-based, no local model download)."""
    global _embeddings
    if _embeddings is None:
        _embeddings = MistralAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=os.getenv("MISTRALAI_API_KEY"),
        )
        log.info("RAG: Mistral Embeddings initialised (model=%s)", EMBEDDING_MODEL)
    return _embeddings


# ── Helpers ────────────────────────────────────────────────────────────────────

def _topic_collection(topic: str) -> str:
    """Generate a stable, URL-safe collection name from a topic string."""
    h = hashlib.md5(topic.lower().strip().encode()).hexdigest()[:10]
    return f"{COLLECTION_PREFIX}{h}"


def _ensure_collection(client: QdrantClient, name: str) -> bool:
    """
    Create the Qdrant collection if it doesn't exist yet.
    Returns True if newly created, False if already existed.
    """
    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        return False
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    log.info("RAG: Created Qdrant collection '%s'", name)
    return True


def _chunk_text(raw_text: str) -> List[Document]:
    """Split raw scraped text into overlapping chunks for embedding."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=60)
    return splitter.create_documents([raw_text])


# ── Main Node ──────────────────────────────────────────────────────────────────

def run_rag_node(state: Dict) -> Dict:
    """
    LangGraph node — embeds scraped content into Qdrant and retrieves
    the most relevant chunks for the current topic.

    Uses summarized_content if available (better signal), falls back to
    raw scraped_content.
    """
    topic = state.get("topic", "").strip()

    # Prefer summarized content (less noise)
    raw_text = (
        state.get("summarized_content", "").strip()
        or state.get("scraped_content", "").strip()
    )

    if not raw_text:
        return {
            **state,
            "rag_context": "",
            "error": state.get("error", "No content available for RAG."),
        }

    try:
        client     = _get_client()
        embeddings = _get_embeddings()
        collection = _topic_collection(topic)

        # Create collection + ingest only on first visit for this topic
        is_new = _ensure_collection(client, collection)
        vectorstore = QdrantVectorStore(
            client=client,
            collection_name=collection,
            embedding=embeddings,
        )

        if is_new:
            chunks = _chunk_text(raw_text)
            if not chunks:
                return {
                    **state,
                    "rag_context": "",
                    "error": "RAG: no chunks generated from content.",
                }
            vectorstore.add_documents(chunks)
            log.info("RAG: ingested %d chunks into '%s'", len(chunks), collection)
        else:
            log.info("RAG: collection '%s' already has data, skipping ingest", collection)

        # Similarity search — top-4 most relevant chunks
        docs = vectorstore.similarity_search(topic, k=4)
        rag_context = "\n\n".join(
            f"[Chunk {i+1}]: {doc.page_content}"
            for i, doc in enumerate(docs)
        )

        log.info(
            "RAG: retrieved %d chunks (%d chars) for topic=%r",
            len(docs), len(rag_context), topic,
        )
        return {**state, "rag_context": rag_context}

    except Exception as exc:
        log.exception("RAG node failed")
        return {**state, "rag_context": "", "error": f"RAG failed: {exc}"}