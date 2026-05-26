import os
import sys
import json
import asyncio

from dotenv import load_dotenv

from langfuse import observe, get_client
from langchain_groq import ChatGroq
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
)

# =============================================================================
# PATH SETUP
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_DIR = os.path.join(BASE_DIR, "backend")

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

sys.path.append(BACKEND_DIR)

# =============================================================================
# IMPORT AGENT
# =============================================================================

from agent.graph import get_agent_app

# =============================================================================
# LOAD TEST CASES
# =============================================================================

TEST_CASES_PATH = os.path.join(
    os.path.dirname(__file__),
    "test_cases.json"
)

with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
    test_cases = json.load(f)

# =============================================================================
# LANGFUSE CLIENT
# =============================================================================

langfuse = get_client()

# =============================================================================
# EVALUATION LLM
# =============================================================================

eval_llm = ChatGroq(
    temperature=0,
    model_name="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY"),
)

# =============================================================================
# HELPER FUNCTION
# =============================================================================

def extract_final_response(messages) -> str:
    """
    Extract final AI response from LangGraph messages.
    """

    for msg in reversed(messages):

        if not isinstance(msg, AIMessage):
            continue

        # Ignore tool call messages
        if getattr(msg, "tool_calls", None):
            continue

        if isinstance(msg.content, str) and msg.content.strip():
            return msg.content

    return "No response generated."


# =============================================================================
# EVALUATION FUNCTION
# =============================================================================

@observe(name="customer-support-eval")
async def evaluate_case(
    case: dict,
    index: int,
    total: int,
    agent_app,
):

    user_input = case["input"]

    expected_topic = case["expected_topic"]

    ground_truth = case.get(
        "ground_truth",
        "N/A"
    )

    expected_tool = case.get(
        "expected_tool",
        "N/A"
    )

    print("\n" + "=" * 80)
    print(f"[{index}/{total}]")
    print(f"USER QUERY      : {user_input}")
    print(f"EXPECTED TOPIC  : {expected_topic}")
    print(f"EXPECTED TOOL   : {expected_tool}")

    # =========================================================================
    # RUN AGENT
    # =========================================================================

    input_state = {
        "messages": [
            HumanMessage(content=user_input)
        ],
        "user_id": 9999,
    }

    config = {
        "configurable": {
            "thread_id": f"eval-thread-{index}",
            "user_id": 9999,
        }
    }

    try:

        final_state = await agent_app.ainvoke(
            input_state,
            config=config,
        )

        agent_response = extract_final_response(
            final_state.get("messages", [])
        )

        print(f"AGENT RESPONSE  : {agent_response}")

    except Exception as e:

        print(f"AGENT ERROR     : {e}")

        return

    # =========================================================================
    # UPDATE LANGFUSE SPAN
    # =========================================================================

    langfuse.update_current_span(
        input=user_input,
        output=agent_response,
        metadata={
            "expected_topic": expected_topic,
            "expected_tool": expected_tool,
            "ground_truth": ground_truth,
        }
    )

    # =========================================================================
    # JUDGE PROMPT
    # =========================================================================

    judge_prompt = f"""
You are an expert AI QA evaluator.

Evaluate the following customer support response.

USER QUERY:
{user_input}

EXPECTED TOPIC:
{expected_topic}

GROUND TRUTH:
{ground_truth}

AGENT RESPONSE:
{agent_response}

Evaluate on:

1. Relevance (1-5)
2. Factual Accuracy (1-5)
3. Professionalism (1-5)

Return ONLY valid JSON.

Example:

{{
    "relevance_score": 5,
    "factual_accuracy_score": 5,
    "professionalism_score": 5,
    "explanation": "The response is accurate, relevant, and professional."
}}
"""

    # =========================================================================
    # RUN JUDGE
    # =========================================================================

    try:

        result = eval_llm.invoke([
            SystemMessage(
                content="You are a strict evaluator."
            ),
            HumanMessage(content=judge_prompt),
        ])

        raw_response = result.content.strip()

        # Remove accidental markdown formatting
        if raw_response.startswith("```"):
            raw_response = raw_response.replace(
                "```json",
                ""
            )
            raw_response = raw_response.replace(
                "```",
                ""
            ).strip()

        eval_data = json.loads(raw_response)

    except Exception as e:

        print(f"JUDGE ERROR     : {e}")

        eval_data = {
            "relevance_score": 3,
            "factual_accuracy_score": 3,
            "professionalism_score": 3,
            "explanation": "Fallback due to parsing failure."
        }

    # =========================================================================
    # PRINT SCORES
    # =========================================================================

    print(f"RELEVANCE       : {eval_data['relevance_score']}/5")

    print(
        f"FACTUAL         : "
        f"{eval_data['factual_accuracy_score']}/5"
    )

    print(
        f"PROFESSIONALISM : "
        f"{eval_data['professionalism_score']}/5"
    )

    print(f"EXPLANATION     : {eval_data['explanation']}")

    langfuse.score_current_trace(
        name="relevance",
        value=float(eval_data["relevance_score"]),
        data_type="NUMERIC",
        comment=eval_data["explanation"],
    )

    langfuse.score_current_trace(
        name="factual_accuracy",
        value=float(eval_data["factual_accuracy_score"]),
        data_type="NUMERIC",
        comment=eval_data["explanation"],
    )

    langfuse.score_current_trace(
        name="professionalism",
        value=float(eval_data["professionalism_score"]),
        data_type="NUMERIC",
        comment=eval_data["explanation"],
    )


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_evaluation():

    print("\nStarting Customer Support Agent Evaluations...\n")

    agent_app = get_agent_app()

    total = len(test_cases)

    for index, case in enumerate(
        test_cases,
        start=1
    ):

        await evaluate_case(
            case=case,
            index=index,
            total=total,
            agent_app=agent_app,
        )

    langfuse.flush()

    print("\nEvaluations completed successfully.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    asyncio.run(run_evaluation())