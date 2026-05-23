from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_groq import ChatGroq
from agent.state import AgentState
from agent.tools import tools
from langgraph.prebuilt import ToolNode
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


def _validate_tool_schemas():
    """Groq harmony rejects tool definitions missing a function name."""
    for t in tools:
        schema = convert_to_openai_tool(t)
        name = schema.get("function", {}).get("name")
        if not name:
            raise RuntimeError(f"Tool schema missing name: {schema}")


_validate_tool_schemas()

llm = ChatGroq(temperature=0, model_name=GROQ_MODEL, groq_api_key=os.getenv("GROQ_API_KEY"))
llm_with_tools = llm.bind_tools(tools)

# Prebuilt ToolNode
tool_node = ToolNode(tools)

def sanitize_messages_for_groq(messages):
    """Drop malformed tool_calls that break Groq harmony rendering."""
    cleaned = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            valid_calls = [tc for tc in (msg.tool_calls or []) if tc.get("name")]
            extra = {k: v for k, v in msg.additional_kwargs.items() if k != "tool_calls"}
            if valid_calls != (msg.tool_calls or []) or "tool_calls" in msg.additional_kwargs:
                msg = AIMessage(
                    content=msg.content,
                    tool_calls=valid_calls,
                    additional_kwargs=extra,
                )
        cleaned.append(msg)
    return cleaned


def prune_messages(messages, max_history=10):
    """
    Ensures that we do not exceed LLM token or context limits.
    Keeps the SystemMessage at index 0 and at most the last `max_history` chat messages.
    """
    if len(messages) <= max_history + 1:
        return messages
        
    system_message = None
    if isinstance(messages[0], SystemMessage):
        system_message = messages[0]
        chat_messages = messages[1:]
    else:
        chat_messages = messages
        
    # Retain only the last max_history messages
    trimmed_chat = chat_messages[-max_history:]
    
    if system_message:
        return [system_message] + list(trimmed_chat)
    return trimmed_chat

async def agent_node(state: AgentState):
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
    
    # Prune historical messages for LLM context optimization, keeping full audit in LangGraph state
    llm_messages = sanitize_messages_for_groq(prune_messages(messages, max_history=10))

    response = await llm_with_tools.ainvoke(llm_messages)
    
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
