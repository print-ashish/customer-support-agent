import os
import sys
from sentence_transformers import SentenceTransformer

# Add the backend dir to sys.path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import async_session_maker
from db.models import Document
from sqlalchemy import select

# Initialize embedding model (768 dimensions) - must match ingest.py
embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')

async def search_faq(query: str, top_k: int = 3):
    """
    Search the documents table for the most relevant FAQ chunks.
    """
    async with async_session_maker() as db:
        query_embedding = embedder.encode(query).tolist()
        
        # pgvector cosine distance: <->
        result = await db.execute(
            select(Document).order_by(
                Document.embedding.cosine_distance(query_embedding)
            ).limit(top_k)
        )
        results = result.scalars().all()
        
        if not results:
            return "No relevant FAQ found."
            
        context = []
        for doc in results:
            context.append(f"Source: {doc.source}\nContent: {doc.content}")
            
        return "\n\n---\n\n".join(context)

# ans = search_faq("refund policy")
# print(ans)
