from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from tradingagents.agents.utils.agent_utils import create_msg_delete


def test_create_msg_delete_uses_context_aware_placeholder():
    delete_messages = create_msg_delete()

    result = delete_messages(
        {
            "messages": [
                HumanMessage(content="old user message", id="human-1"),
                AIMessage(content="old ai message", id="ai-1"),
            ],
            "company_of_interest": "EC",
            "trade_date": "2026-05-13",
            "asset_type": "stock",
        }
    )

    messages = result["messages"]
    placeholder = messages[-1]

    assert len(messages) == 3
    assert all(isinstance(message, RemoveMessage) for message in messages[:-1])
    assert isinstance(placeholder, HumanMessage)

    assert placeholder.content != "Continue"
    assert "`EC`" in placeholder.content
    assert "stock" in placeholder.content
    assert "2026-05-13" in placeholder.content
    assert "assigned analysis" in placeholder.content
    assert "standalone user request" in placeholder.content


def test_create_msg_delete_placeholder_has_safe_defaults():
    delete_messages = create_msg_delete()

    result = delete_messages(
        {
            "messages": [
                HumanMessage(content="old user message", id="human-1"),
            ],
        }
    )

    placeholder = result["messages"][-1]

    assert isinstance(placeholder, HumanMessage)
    assert placeholder.content != "Continue"
    assert "the requested instrument" in placeholder.content
    assert "the requested date" in placeholder.content
    assert "stock" in placeholder.content