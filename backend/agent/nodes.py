import os

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_litellm import ChatLiteLLM
from langgraph.prebuilt import ToolNode

from agent.state import AgentState
from agent.tools import tools
from agent.system_prompt import SYSTEM_PROMPT

load_dotenv()

model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
if not model.startswith("groq/"):
    model = f"groq/{model}"

fallbacks = [m.strip() for m in os.getenv("LLM_FALLBACKS", "groq/llama-3.3-70b-versatile").split(",") if m.strip()]

llm = ChatLiteLLM(model=model, temperature=0, model_kwargs={"fallbacks": fallbacks})
llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)


async def agent_node(state: AgentState):
    messages = list(state["messages"])

    system_content = SYSTEM_PROMPT
    if state.get("context"):
        system_content += f"\nRelevant Information from RAG/FAQ Knowledge Base:\n{state['context']}\n"

    system_msg = SystemMessage(content=system_content)
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [system_msg] + messages
    else:
        messages[0] = system_msg

    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "end"
