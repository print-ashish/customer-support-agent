import os
import sys
from sentence_transformers import SentenceTransformer , CrossEncoder


# Add the backend dir to sys.path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import async_session_maker
from db.models import Document
from sqlalchemy import select

# Initialize embedding model (768 dimensions) - must match ingest.py
embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')        # ADD THIS



async def search_faq(query: str, top_k: int = 3):
    async with async_session_maker() as db:
        query_embedding = embedder.encode(query).tolist()
        
        # CHANGE 1 — fetch 20 instead of top_k
        result = await db.execute(
            select(Document).order_by(
                Document.embedding.cosine_distance(query_embedding)
            ).limit(20)                                                  # was top_k
        )
        candidates = result.scalars().all()

        print("retrived docs ==" , candidates)
        
        if not candidates:
            print("nothing found ")
            return "No relevant FAQ found."
        
        # ADD THIS BLOCK — reranker scores all 20 candidates
        pairs = [[query, doc.content] for doc in candidates]
        scores = reranker.predict(pairs)
        
        # sort by score, keep top_k
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        results = [doc for _, doc in ranked[:top_k]]                    # was result.scalars().all()
        
        context = []
        for doc in results:
            context.append(f"Source: {doc.source}\nContent: {doc.content}")

        print("context from the rag == " , context)
            
        return "\n\n---\n\n".join(context)


def search_faq_sync(query: str, top_k: int = 3) -> str:
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

