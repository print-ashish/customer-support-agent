from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import agent_node, tool_node, should_continue
from langgraph.checkpoint.memory import MemorySaver

_agent_app = None

def get_agent_app():
    global _agent_app
    if _agent_app is None:
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "escalate": "tools",
                "end": END
            }
        )

        workflow.add_edge("tools", "agent")

        _agent_app = workflow.compile(checkpointer=MemorySaver())
    return _agent_app
