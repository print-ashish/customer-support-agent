import os
import sys
from sentence_transformers import SentenceTransformer
from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Add the backend dir to sys.path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import SessionLocal
from db.models import Document

# Initialize embedding model (768 dimensions)
embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')

def ingest_docs(docs_dir: str):
    db = SessionLocal()
    try:
        # Delete existing documents to prevent duplication on re-run
        db.query(Document).delete()
        db.commit()

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        
        for filename in os.listdir(docs_dir):
            if filename.endswith(".txt"):
                filepath = os.path.join(docs_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                chunks = text_splitter.split_text(content)
                embeddings = embedder.encode(chunks)
                
                for chunk, embedding in zip(chunks, embeddings):
                    doc = Document(
                        content=chunk,
                        embedding=embedding.tolist(),
                        metadata_={"source": filename},
                        source=filename
                    )
                    db.add(doc)
                
                print(f"Ingested {len(chunks)} chunks from {filename}")
        
        db.commit()
        print("Ingestion complete.")
    finally:
        db.close()

if __name__ == "__main__":
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")
    if os.path.exists(docs_dir):
        ingest_docs(docs_dir)
    else:
        print(f"Docs directory not found at {docs_dir}")
