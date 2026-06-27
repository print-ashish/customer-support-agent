# ShopEase Intelligent Customer Support Agent

An enterprise-grade, autonomous customer support agent powered by **LangGraph**, **LangChain**, and **PostgreSQL (with `pgvector`)**. The system integrates semantic document lookup (RAG), transactional order lifecycles with strict state-machine guardrails, defensive tool execution, and detailed observability.

---

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

### 6. Langfuse Observability & Ragas Evaluation
- Integrates **Langfuse** via LangChain `CallbackHandler` to trace LLM calls, tool invocations, token usage, and latency.
- Propagates `session_id` and `user_id` into traces for production debugging.
- **Ragas-based eval suite** (`evals/`) measures agent quality end-to-end:
  - **Answer quality**: `answer_correctness`, `answer_relevancy`
  - **RAG quality**: `faithfulness`, `context_precision`, `context_recall` (from `search_faq` tool outputs in the trace)
  - **Tool routing**: whether expected tools were called during the conversation
- Supports **single-turn** and **multi-turn** scenarios with separate test case JSON files.

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
├── docs/                    # Plaintext knowledge source documents (faq, refund policy)
└── evals/
    ├── test_cases.json          # Single-turn eval cases
    ├── multiturn_cases.json     # Multi-turn eval cases
    ├── run_evals.py             # Single-turn Ragas runner
    └── run_multiturn_evals.py   # Multi-turn Ragas runner
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.12** (recommended; 3.14 has issues with `sentence-transformers`)
- Node.js 18+ (frontend)
- Docker & Docker Compose (PostgreSQL + pgvector, Redis, Langfuse stack)

> **Port conflicts:** If ports `5432` or `6379` are already in use on your machine, stop the conflicting services before running `docker compose up`.

### 2. Infrastructure (Docker)

From the project root:

```bash
docker compose up -d
```

This starts the app database (`customer_support` on port `5432`), Redis, and Langfuse.

### 3. Backend Setup

1. Create and activate a virtual environment at the project root:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # macOS/Linux
   ```

2. Install dependencies:

   ```bash
   pip install -r backend/requirements.txt
   pip install ragas==0.2.15 datasets langchain-community langchain
   ```

3. Configure environment variables in `backend/.env`:

   ```env
   GROQ_API_KEY=your_key
   DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/customer_support
   LANGFUSE_PUBLIC_KEY=...
   LANGFUSE_SECRET_KEY=...
   LANGFUSE_BASE_URL=http://localhost:3000
   ```

4. Seed the database and ingest documents:

   ```bash
   python backend/db/seed.py
   python backend/rag/ingest.py
   ```

5. Start the API server:

   ```bash
   cd backend
   uvicorn main:app --reload
   ```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Log in with `test@example.com` / `password` to interact with seeded orders.

---

## 📊 Evaluation

The eval suite runs the **full LangGraph agent** against fixed test cases, extracts the conversation trace from `final_state["messages"]`, and scores with **Ragas**.

### Flow

```
test_cases.json  →  agent.ainvoke()  →  parse messages trace  →  Ragas metrics  →  console report
```

From each run we extract:

| Field | Source in trace |
|-------|-----------------|
| **answer** | Last text-only `AIMessage` |
| **contexts** | Chunks from `search_faq` `ToolMessage` content |
| **tool_calls** | All `AIMessage.tool_calls` names |
| **ground_truth** | Expected answer from JSON test case |

### Metrics

| Metric | What it checks |
|--------|----------------|
| `faithfulness` | Is the answer grounded in retrieved contexts? |
| `answer_relevancy` | Does the answer address the question? |
| `context_precision` | Are retrieved chunks relevant (low noise)? |
| `context_recall` | Do retrieved chunks cover the ground truth facts? |
| `answer_correctness` | Semantic match to `ground_truth` |
| `tool_routing_accuracy` | Were expected tools called? (name presence, not order) |

RAG metrics run only when `search_faq` returned contexts. Tool-only cases use `answer_relevancy` + `answer_correctness`.

### Single-turn eval

```bash
python evals/run_evals.py
```

Uses `evals/test_cases.json` — one user message per case (FAQ, refund policy, order status).

### Multi-turn eval

```bash
python evals/run_multiturn_evals.py
```

Uses `evals/multiturn_cases.json` — several user turns on the **same `thread_id`**, then scores the final answer and **full** tool/RAG history. Requires `test@example.com` from `seed.py` (order/refund flows use real seeded data).

### Example test case (multi-turn)

```json
{
  "name": "refund_flow",
  "turns": [
    "I want a refund",
    "It's for order 3",
    "Am I eligible?"
  ],
  "scenario": "User wants a refund, identifies order 3, asks about eligibility.",
  "ground_truth": "Agent should confirm order 3 (Laptop) is eligible for a refund.",
  "expected_tools": ["check_refund_eligibility"]
}
```

### Interpreting results

- **Low `tool_routing_accuracy`** does not always mean a bad agent — equivalent tools (e.g. `list_my_orders` vs `get_order_status`) may both be valid. Tune `expected_tools` to match acceptable paths.
- **Low `answer_correctness`** with a good-looking answer — Ragas LLM judge can be strict; spot-check printed answers.
- **Empty contexts** on a RAG case — agent never called `search_faq`; RAG metrics are skipped.

### Prerequisites for evals

1. Docker stack running (PostgreSQL + ingested docs)
2. `python backend/db/seed.py` and `python backend/rag/ingest.py` completed
3. `GROQ_API_KEY` set in `backend/.env`

---

## 🧪 Pre-deploy checklist (recommended)

1. Run `python evals/run_evals.py` — FAQ, refund policy, tool routing
2. Run `python evals/run_multiturn_evals.py` — follow-up and order flows
3. Confirm tool routing pass on critical cases and no major regressions in Ragas averages
4. Spot-check failed or low-scoring cases in the console output
5. Verify Langfuse traces at `http://localhost:3000` during eval runs
