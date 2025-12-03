import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, RemoveMessage
from tradingagents.agents.utils.agent_utils import create_msg_delete


class TestCreateMsgDelete:
    """Test suite for create_msg_delete function."""

    def test_create_msg_delete_returns_callable(self):
        """Test that create_msg_delete returns a callable function."""
        delete_func = create_msg_delete()
        assert callable(delete_func)

    def test_delete_messages_removes_all_messages(self):
        """Test that delete_messages removes all existing messages."""
        # Create mock messages with IDs
        mock_msg1 = Mock(spec=HumanMessage)
        mock_msg1.id = "msg_1"
        mock_msg2 = Mock(spec=HumanMessage)
        mock_msg2.id = "msg_2"
        mock_msg3 = Mock(spec=HumanMessage)
        mock_msg3.id = "msg_3"
        
        state = {"messages": [mock_msg1, mock_msg2, mock_msg3]}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        # Should return removal operations for all messages plus a placeholder
        assert "messages" in result
        messages = result["messages"]
        
        # First 3 should be RemoveMessage operations
        removal_count = sum(1 for msg in messages if isinstance(msg, RemoveMessage))
        assert removal_count == 3
        
        # Last message should be the placeholder HumanMessage
        assert isinstance(messages[-1], HumanMessage)
        assert messages[-1].content == "Continue"

    def test_delete_messages_empty_state(self):
        """Test delete_messages with an empty message list."""
        state = {"messages": []}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        # Should only contain the placeholder message
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], HumanMessage)
        assert result["messages"][0].content == "Continue"

    def test_delete_messages_single_message(self):
        """Test delete_messages with a single message."""
        mock_msg = Mock(spec=HumanMessage)
        mock_msg.id = "single_msg"
        
        state = {"messages": [mock_msg]}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        assert len(result["messages"]) == 2  # 1 removal + 1 placeholder
        assert isinstance(result["messages"][0], RemoveMessage)
        assert isinstance(result["messages"][1], HumanMessage)

    def test_delete_messages_preserves_message_ids(self):
        """Test that RemoveMessage operations use correct message IDs."""
        msg_ids = ["id_1", "id_2", "id_3", "id_4"]
        mock_messages = []
        
        for msg_id in msg_ids:
            mock_msg = Mock(spec=HumanMessage)
            mock_msg.id = msg_id
            mock_messages.append(mock_msg)
        
        state = {"messages": mock_messages}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        # Extract RemoveMessage operations
        removal_operations = [msg for msg in result["messages"] if isinstance(msg, RemoveMessage)]
        removal_ids = [op.id for op in removal_operations]
        
        # All original message IDs should be in removal operations
        for original_id in msg_ids:
            assert original_id in removal_ids

    def test_delete_messages_anthropic_compatibility(self):
        """Test that the placeholder message ensures Anthropic API compatibility."""
        # Anthropic requires at least one message in the conversation
        mock_msg = Mock(spec=HumanMessage)
        mock_msg.id = "test_msg"
        
        state = {"messages": [mock_msg]}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        # Verify placeholder is a HumanMessage (required by Anthropic)
        placeholder = result["messages"][-1]
        assert isinstance(placeholder, HumanMessage)
        assert placeholder.content == "Continue"

    def test_delete_messages_large_message_list(self):
        """Test delete_messages with a large number of messages."""
        # Create 100 mock messages
        mock_messages = []
        for i in range(100):
            mock_msg = Mock(spec=HumanMessage)
            mock_msg.id = f"msg_{i}"
            mock_messages.append(mock_msg)
        
        state = {"messages": mock_messages}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        # Should have 100 removal operations + 1 placeholder
        assert len(result["messages"]) == 101
        
        # Count removal operations
        removal_count = sum(1 for msg in result["messages"] if isinstance(msg, RemoveMessage))
        assert removal_count == 100

    def test_delete_messages_multiple_calls(self):
        """Test that create_msg_delete can be called multiple times."""
        mock_msg1 = Mock(spec=HumanMessage)
        mock_msg1.id = "msg_1"
        mock_msg2 = Mock(spec=HumanMessage)
        mock_msg2.id = "msg_2"
        
        state1 = {"messages": [mock_msg1]}
        state2 = {"messages": [mock_msg1, mock_msg2]}
        
        delete_func1 = create_msg_delete()
        delete_func2 = create_msg_delete()
        
        result1 = delete_func1(state1)
        result2 = delete_func2(state2)
        
        # Each call should work independently
        assert len(result1["messages"]) == 2  # 1 removal + placeholder
        assert len(result2["messages"]) == 3  # 2 removals + placeholder

    def test_delete_messages_state_immutability(self):
        """Test that delete_messages doesn't modify the original state."""
        mock_msg = Mock(spec=HumanMessage)
        mock_msg.id = "test_id"
        
        original_state = {"messages": [mock_msg]}
        original_msg_count = len(original_state["messages"])
        
        delete_func = create_msg_delete()
        result = delete_func(original_state)
        
        # Original state should remain unchanged
        assert len(original_state["messages"]) == original_msg_count
        assert original_state["messages"][0] is mock_msg

    def test_delete_messages_return_structure(self):
        """Test that delete_messages returns the correct structure."""
        mock_msg = Mock(spec=HumanMessage)
        mock_msg.id = "test_msg"
        
        state = {"messages": [mock_msg]}
        
        delete_func = create_msg_delete()
        result = delete_func(state)
        
        # Result should be a dict with 'messages' key
        assert isinstance(result, dict)
        assert "messages" in result
        assert isinstance(result["messages"], list)