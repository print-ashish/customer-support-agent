"""
Multi-turn agent eval — same idea as run_evals.py but sends several user messages
on one thread_id, then scores the final answer + full conversation trace.

  1. For each case: send turn 1, turn 2, ... (same thread)
  2. Read answer / tools / RAG contexts from final messages
  3. Score with Ragas
  4. Print results

Uses test@example.com user (run backend/db/seed.py first).
"""

import os
import sys
import json
import asyncio
from statistics import mean
from types import ModuleType

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from sqlalchemy import select

# --- paths -------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
load_dotenv(os.path.join(BACKEND, ".env"))

from agent.graph import get_agent_app  # noqa: E402
from db.models import User  # noqa: E402
from db.session import async_session_maker  # noqa: E402

# --- ragas import fix --------------------------------------------------------

for mod_name, cls_name in [
    ("langchain_community.chat_models.vertexai", "ChatVertexAI"),
    ("langchain_community.llms", "VertexAI"),
]:
    if mod_name not in sys.modules:
        mod = ModuleType(mod_name)
        setattr(mod, cls_name, type(cls_name, (), {}))
        sys.modules[mod_name] = mod

from datasets import Dataset  # noqa: E402
from langchain_community.embeddings import HuggingFaceEmbeddings  # noqa: E402
from langchain_groq import ChatGroq  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    answer_correctness,
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

# --- config ------------------------------------------------------------------

CASES_PATH = os.path.join(os.path.dirname(__file__), "multiturn_cases.json")
with open(CASES_PATH, encoding="utf-8") as f:
    CASES = json.load(f)

langfuse = get_client()
RAG_METRICS = [faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness]
TOOL_METRICS = [answer_relevancy, answer_correctness]


async def get_seed_user_id() -> int:
    """Orders in seed.py belong to test@example.com."""
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == "test@example.com"))
        user = result.scalar_one_or_none()
    if not user:
        raise RuntimeError("test@example.com not found — run: python backend/db/seed.py")
    return user.id


# --- read trace from messages ------------------------------------------------

def get_answer(messages) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            return msg.content
    return ""


def get_tool_calls(messages) -> list[str]:
    names = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls or []:
                names.append(call["name"])
    return names


def get_rag_contexts(messages) -> list[str]:
    contexts = []
    for msg in messages:
        if not isinstance(msg, ToolMessage) or msg.name != "search_faq":
            continue
        if not msg.content or msg.content == "No relevant FAQ found.":
            continue
        for chunk in msg.content.split("\n\n---\n\n"):
            text = chunk.strip()
            if text.lower().startswith("content:"):
                text = text.split(":", 1)[1].strip()
            if text:
                contexts.append(text)
    return contexts


def tools_passed(called: list[str], expected: list[str]) -> bool:
    if not expected:
        return True
    return all(t in called for t in expected)


# --- ragas -------------------------------------------------------------------

def score_with_ragas(records: list[dict]) -> list[dict]:
    llm = LangchainLLMWrapper(ChatGroq(
        temperature=0, model_name="llama-3.3-70b-versatile", groq_api_key=os.getenv("GROQ_API_KEY"),
    ))
    emb = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2"))

    rag_rows = [r for r in records if r["contexts"]]
    tool_rows = [r for r in records if not r["contexts"]]

    def run_batch(rows, metrics):
        if not rows:
            return {}
        ds = Dataset.from_dict({
            "question": [r["question"] for r in rows],
            "answer": [r["answer"] for r in rows],
            "contexts": [r["contexts"] for r in rows],
            "ground_truth": [r["ground_truth"] for r in rows],
        })
        try:
            df = evaluate(dataset=ds, metrics=metrics, llm=llm, embeddings=emb).to_pandas()
        except Exception as e:
            print(f"  Ragas error: {e}")
            return {}
        return {
            id(row): {m.name: float(df.iloc[i][m.name]) for m in metrics if m.name in df.columns}
            for i, row in enumerate(rows)
        }

    rag_scores = run_batch(rag_rows, RAG_METRICS)
    tool_scores = run_batch(tool_rows, TOOL_METRICS)

    for r in records:
        r["scores"] = {**(rag_scores.get(id(r)) or tool_scores.get(id(r)) or {})}
        r["scores"]["tool_routing_accuracy"] = 1.0 if tools_passed(r["tool_calls"], r["expected_tools"]) else 0.0

    return records


# --- main --------------------------------------------------------------------

async def main():
    user_id = await get_seed_user_id()
    print(f"\nMulti-turn eval — {len(CASES)} cases (user_id={user_id})\n")

    agent = get_agent_app()
    records = []

    for i, case in enumerate(CASES, 1):
        name = case.get("name", f"case-{i}")
        turns = case["turns"]
        thread_id = f"multiturn-eval-{i}"

        print(f"[{i}/{len(CASES)}] {name}")
        print(f"  scenario : {case.get('scenario', '')}")

        messages = []
        error = None

        try:
            for n, user_msg in enumerate(turns, 1):
                print(f"  turn {n}  : {user_msg}")
                state = await agent.ainvoke(
                    {"messages": [HumanMessage(content=user_msg)], "user_id": user_id},
                    config={
                        "configurable": {"thread_id": thread_id, "user_id": user_id},
                        "callbacks": [CallbackHandler()],
                    },
                )
                await asyncio.sleep(0.5)
            messages = state["messages"]
        except Exception as e:
            error = str(e)
            print(f"  ERROR: {e}\n")

        answer = get_answer(messages)
        contexts = get_rag_contexts(messages)
        tools = get_tool_calls(messages)

        print(f"  tools    : {tools or 'none'}")
        print(f"  expected : {case.get('expected_tools', [])}")
        print(f"  contexts : {len(contexts)} chunk(s)")
        print(f"  answer   : {answer[:120]}{'...' if len(answer) > 120 else ''}\n")

        records.append({
            "name": name,
            "turns": turns,
            "question": case.get("scenario") or " | ".join(turns),
            "answer": answer,
            "contexts": contexts,
            "ground_truth": case.get("ground_truth", ""),
            "expected_tools": case.get("expected_tools", []),
            "tool_calls": tools,
            "error": error,
        })

    print("Scoring with Ragas...\n")
    records = score_with_ragas(records)

    metric_names = [m.name for m in RAG_METRICS] + ["tool_routing_accuracy"]
    totals = {m: [] for m in metric_names}

    for r in records:
        print(f"--- {r['name']}")
        print(f"  turns: {len(r['turns'])}")
        for m in metric_names:
            val = r["scores"].get(m)
            if val is not None:
                print(f"  {m}: {val:.3f}")
                totals[m].append(val)

    print("\n=== AVERAGES ===")
    for m, vals in totals.items():
        if vals:
            print(f"  {m}: {mean(vals):.3f}")
    print(f"  tool routing pass: {sum(r['scores'].get('tool_routing_accuracy', 0) for r in records)}/{len(records)}")

    langfuse.flush()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
