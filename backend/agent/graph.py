from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import agent_node, tool_node, should_continue
from langgraph.checkpoint.memory import MemorySaver

def create_graph():
    workflow = StateGraph(AgentState)
    
    # Define the nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    
    # Define the edges
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "escalate": END, # In a real scenario, this might route to a human node or pause
            "end": END
        }
    )
    
    workflow.add_edge("tools", "agent")
    
    # Compile
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    return app

agent_app = create_graph()
