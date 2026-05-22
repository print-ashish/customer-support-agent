from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from agent.state import AgentState
from agent.tools import tools
from langgraph.prebuilt import ToolNode
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq LLM
llm = ChatGroq(temperature=0, model_name="openai/gpt-oss-120b", groq_api_key=os.getenv("GROQ_API_KEY"))
llm_with_tools = llm.bind_tools(tools)

# Prebuilt ToolNode
tool_node = ToolNode(tools)

def agent_node(state: AgentState):
    messages = state["messages"]
    
    # Inject RAG context or memory if available and not already in messages (simplification: we prepend system message)
    system_content = "You are a helpful customer support agent for an e-commerce company. "
    if state.get("context"):
        system_content += f"\nRelevant Information:\n{state['context']}\n"
    
    system_msg = SystemMessage(content=system_content)
    
    # Always include the system message at the beginning
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [system_msg] + list(messages)
    else:
        messages[0] = system_msg
    
    response = llm_with_tools.invoke(messages)
    
    # Update retry count (basic logic, could be refined)
    retry_count = state.get("retry_count", 0) + 1
    
    return {"messages": [response], "retry_count": retry_count}

def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    
    # Force end or escalate if retry count is too high
    if state.get("retry_count", 0) > 3:
        return "escalate"
    
    # If the LLM made a tool call, then we route to the "tools" node
    print("checking the tool call ")
    if last_message.tool_calls:
        # Check if the tool is escalate
        print("tool calls == ", last_message.tool_calls)
        if any(call["name"] == "escalate_to_human" for call in last_message.tool_calls):
            return "escalate"
        return "tools"
    
    # Otherwise, we end and reply to the user
    return "end"
