# ShopEase Intelligent Customer Support Agent

An enterprise-grade, autonomous customer support agent powered by **LangGraph**, **LangChain**, and **PostgreSQL (with `pgvector`)**. The system integrates semantic document lookup (RAG), transactional order lifecycles with strict state-machine guardrails, defensive tool execution, and detailed observability.

---
##Demo Video 
https://youtu.be/Kb6mnA9MS0Y

## 🏗️ System Architecture

The following diagram illustrates the end-to-end data flow, illustrating the interface between the web frontend, FastAPI server, LangGraph agentic loop, vector store, and transactional database:

```mermaid
graph TD
    User([Customer / Frontend]) <-->|HTTPS / JSON / JWT| API[FastAPI Web Gateway]
    API <-->|State & Thread ID| Graph[LangGraph Agentic Loop]
    
    subgraph Agentic Reasoning Loop
        Graph -->|System Manual + Thread Context| LLM{Llama-3 Reasoning Engine}
        LLM -->|Decision: Direct Reply| Graph
        LLM -->|Decision: Tool Call| Router[Tool Execution Router]
    end

    Router -->|1. Semantic Query| RAG[RAG Vector Retriever]
    Router -->|2. Cancel / Refund / Status| DB[(PostgreSQL Database)]
    Router -->|3. Escalate Request| Escalation[Escalations Queue]
    
    RAG -->|Semantic Cosine Similarity| VecDB[(pgvector Embeddings)]
    
    API -.->|Traces & Scores| Langfuse[Langfuse Observability Dashboard]
```

---

## 🌟 Key Features

### 1. LangGraph Multi-Agent Architecture
- Built on **LangGraph StateGraphs**, allowing the agent to dynamically loop between reasoning, tool execution, and feedback iterations.
- Full session persistence aligned with persistent threads, allowing seamless conversation tracking.

### 2. Transactional Order Lifecycle Engine
Enforces a strict, deterministic state machine directly at the database layer. Every order moves securely through specific transitions:

```
[processing] ──► [shipped] ──► [delivered] ──► [refunded]
      │              │
      └──► [cancelled] └──► [cancelled]
```

* **Business Rules Enforced**:
  * **Cancellation**: Allowed only in `processing` or `shipped` status. If shipped, the agent issues a proactive warning about package refusal at the door. Cancel is strictly blocked for `delivered` or `refunded` orders.
  * **Refunds**: Allowed only for `delivered` orders within a strict **30-day window** based on `delivered_at` timestamps.
  * **Category Constraints**: Perishable (e.g. food/juices) and personalized/custom goods are automatically blocked from refunds.

### 3. Defensive Tool Signature Pattern (Production Failsafe)
- Solves a common LLM production pitfall where the agent triggers empty tool calls (e.g., `cancel_order` with missing fields) resulting in upstream `400 BadRequestError` schema validation failures at the provider gateway (Groq/OpenAI).
- Uses **optional parameters with python defaults** (`order_id: int = None`) coupled with **inner defensive validations**. If required fields are omitted, the tool catches them gracefully and returns self-correcting prompt advice to the LLM instead of crashing the server.

### 4. Dynamic Semantic Knowledge Base (RAG)
- Uses `sentence-transformers/all-mpnet-base-v2` to vectorize corporate policy guidelines and FAQs.
- Leverages `pgvector` for native cosine similarity lookup inside PostgreSQL.
- Includes a duplicate-safe ingestion workflow that clears vector segments before re-indexing to ensure pristine retriever search quality.

### 6. Full-Stack Langfuse Observability & Tracing
- Integrates **Langfuse** natively via LangChain Callback Handlers to trace every single LLM call, token usage, tool invocation, and latency span.
- Propagates custom frontend metadata such as session IDs (`session_id`) and authenticated user IDs (`user_id`) using contextual tracing attributes.
- Features LLM-as-a-Judge evaluations inside the evaluation pipeline (`evals/run_evals.py`), feeding metrics for *Relevance*, *Factual Accuracy*, and *Professionalism* directly back into the Langfuse dashboard.

### 7. Security & Infrastructure
- **JWT Authentication**: Secure user endpoints with token lifetimes.
- **Sliding Rate Limiter**: Implemented using Redis to protect public `/chat` and `/auth` routes against brute-force vector generation requests.

---

## 📁 Repository Structure

```filepath
├── backend/
│   ├── agent/               # LangGraph state machine, nodes, and tool definitions
│   │   ├── system_prompt.py # Support Policy Manual constant
│   │   ├── tools.py         # Defensive tools (refund, cancel, search_faq)
│   │   └── nodes.py         # Agent reasoning context-merger
│   ├── auth/                # JWT hashing and bearer credentials verification
│   ├── db/                  # SQL Schemas (User, Order, Escalation) and db seeder
│   ├── memory/              # Conversation stores and message history recorders
│   ├── rag/                 # SentenceTransformers encoders and pgvector query handlers
│   └── main.py              # FastAPI endpoints, CORS middlewares, & DB migrations
├── frontend/                # React + Vite Client
│   ├── src/
│   │   ├── components/      # Sleek Chat Bubble UIs and Session Badges
│   │   └── api.js           # Fetch-client wrappers supporting multi-tab session IDs
├── docs/                    # Plaintext knowledge source documents
└── evals/                   # Evaluation suite asserting agent alignment
```

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have Python 3.10+, Node.js 18+, and a running PostgreSQL instance with the `vector` extension installed.

### 2. Backend Setup
1. Navigate to the backend, create a virtual environment, and activate it:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   source .venv/bin/activate # macOS/Linux
   ```
2. Install dependencies and set up your `.env`:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the database migrations & populate the 8 test lifecycle orders:
   ```bash
   python db/seed.py
   ```
4. Run document embedding ingestion:
   ```bash
   python rag/ingest.py
   ```
5. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```

### 3. Frontend Setup
1. In a separate terminal, navigate to the frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
2. Open `http://localhost:5173` in your browser. Use `test@example.com` / `password` to log in and interact with your orders!
