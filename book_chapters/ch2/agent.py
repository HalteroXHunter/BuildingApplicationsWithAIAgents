from langchain.tools import tool
from langchain_openai.chat_models import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph


# Define our business tool
@tool
def cancel_order(order_id: str) -> str:
    """Cancel an order that hasn't been shipped"""
    # Here we would would call our API
    return f"Order {order_id} has been successfully canceled."


# The agent brain: invoke LLM, run tool, then invoke LLM again
def call_model(state):
    msgs = state["messages"]
    order = state.get("order_id", {"order_id": "UNKNOWN"})  # Example order ID

    # system propmpt tells the model what to do
    prompt = f""" You are an ecommerce support agent.
        Order ID: {order['order_id']}
        if the customer asks to cancel, call cancel_order(order_id)
        and then send a simple confimation.
        Otherwise, just respond normally.
        """
    full = [SystemMessage(content=prompt)] + msgs

    # 1st LLM pass: decides whether to call our tool
    AIMessage = ChatOpenAI(model="gpt-5-nano", temperature=0)(full)
    out = [*msgs, AIMessage]

    # ... not well in code
