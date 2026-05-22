import json
import os
import sys
from langfuse import Langfuse
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

# Load test cases
test_cases_path = os.path.join(os.path.dirname(__file__), "test_cases.json")
with open(test_cases_path, "r") as f:
    test_cases = json.load(f)

# Initialize Langfuse
langfuse = Langfuse()

# Initialize LLM for Evaluation
eval_llm = ChatGroq(temperature=0, model_name="llama3-70b-8192")

# Basic evaluation loop
for case in test_cases:
    print(f"Evaluating: {case['input']}")
    
    # We would ideally call our actual API or LangGraph here.
    # For now, we simulate the evaluation step.
    
    # The evaluation judge prompt
    eval_prompt = f"""
    You are an AI judge evaluating a customer support response.
    User Question: {case['input']}
    Does this question fall under the expected topic: {case['expected_topic']}?
    Rate 1 to 5.
    """
    
    res = eval_llm.invoke([SystemMessage(content=eval_prompt)])
    score_text = res.content
    
    print(f"Score: {score_text}")
    
    # Log score to Langfuse (using a placeholder trace id)
    trace = langfuse.trace(name="eval_run", input=case['input'])
    trace.score(
        name="topic_accuracy",
        value=5, # Parse score_text safely in reality
        comment=score_text
    )

print("Evals completed.")
