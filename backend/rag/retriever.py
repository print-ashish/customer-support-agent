import os
import sys

# Add the backend dir to sys.path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import async_session_maker
from db.models import Document
from sqlalchemy import select

EMBEDDER_MODEL = "sentence-transformers/all-mpnet-base-v2"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_embedder = None
_reranker = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBEDDER_MODEL)
    return _embedder


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


async def search_faq(query: str, top_k: int = 3):
    embedder = _get_embedder()
    reranker = _get_reranker()

    async with async_session_maker() as db:
        query_embedding = embedder.encode(query).tolist()

        result = await db.execute(
            select(Document).order_by(
                Document.embedding.cosine_distance(query_embedding)
            ).limit(20)
        )
        candidates = result.scalars().all()

        print("retrived docs ==", candidates)

        if not candidates:
            print("nothing found ")
            return "No relevant FAQ found."

        pairs = [[query, doc.content] for doc in candidates]
        scores = reranker.predict(pairs)

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        results = [doc for _, doc in ranked[:top_k]]

        context = []
        for doc in results:
            context.append(f"Source: {doc.source}\nContent: {doc.content}")

        print("context from the rag == ", context)

        return "\n\n---\n\n".join(context)


def search_faq_sync(query: str, top_k: int = 3) -> str:
    from db.session import SessionLocal

    embedder = _get_embedder()
    reranker = _get_reranker()

    with SessionLocal() as db:
        query_embedding = embedder.encode(query).tolist()
        result = db.execute(
            select(Document).order_by(
                Document.embedding.cosine_distance(query_embedding)
            ).limit(20)
        )
        candidates = result.scalars().all()
        if not candidates:
            return "No relevant FAQ found."

        pairs = [[query, doc.content] for doc in candidates]
        scores = reranker.predict(pairs)
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        results = [doc for _, doc in ranked[:top_k]]

        return "\n\n---\n\n".join(
            f"Source: {doc.source}\nContent: {doc.content}" for doc in results
        )
