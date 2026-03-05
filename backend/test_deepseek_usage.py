import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from loguru import logger

# Mocking the dependencies
import sys
from types import ModuleType

# Create mock modules to avoid importing real ones and hitting DB/API
mock_storage = ModuleType('storage.sql')
sys.modules['storage.sql'] = mock_storage
mock_storage.ConversationManager = MagicMock()
mock_storage.UserManager = MagicMock()
mock_storage.ToolUsageManager = MagicMock()
mock_storage.PreferenceManager = MagicMock()

mock_tools = ModuleType('tools.registry_tools')
sys.modules['tools.registry_tools'] = mock_tools
mock_tools.tool_registry = MagicMock()
mock_tools.tool_registry.get_cached_tools.return_value = []

mock_factory = ModuleType('service.llm_factory')
sys.modules['service.llm_factory'] = mock_factory
mock_factory.LLMFactory = MagicMock()

# Now we can import ChatAgent
from service.agent import ChatAgent
from service.llm_service import ChatCompletionResponse, ChatMessage

class MockUsage:
    def model_dump(self):
        return {"completion_tokens": 10, "prompt_tokens": 20, "total_tokens": 30}

class MockDelta:
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls

class MockChoice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason

class MockChunk:
    def __init__(self, choices, usage=None):
        self.choices = choices
        self.usage = usage
        self.model = "test-model"
        self.created = 123456789

async def test_streaming_usage():
    # 1. Setup mock service
    mock_llm_service = MagicMock()
    mock_llm_service.model = "test-model"
    mock_llm_service.message = []
    
    # 2. Setup mock client and stream
    mock_client = AsyncMock()
    mock_llm_service.client = mock_client
    
    chunks = [
        MockChunk([MockChoice(MockDelta(content="Hello"))]),
        MockChunk([MockChoice(MockDelta(content=" world"))], usage=MockUsage())
    ]
    
    async def mock_stream():
        for chunk in chunks:
            yield chunk
            
    mock_client.chat.completions.create.return_value = mock_stream()
    
    # 3. Setup Agent
    agent = ChatAgent(user_id="test_user", session_id="test_session")
    agent.llm_service = mock_llm_service
    
    # 4. Run stream_chat
    print("Starting stream_chat...")
    full_content = ""
    async for event in agent.stream_chat("hi"):
        if event["type"] == "token":
            full_content += event["content"]
        elif event["type"] == "done":
            print(f"Done event: {event}")
    
    print(f"Full content: {full_content}")
    
    # 5. Verify ConversationManager.save_message was called with correct usage
    save_message_calls = mock_storage.ConversationManager.save_message.call_args_list
    
    # Find the assistant's save_message call
    assistant_calls = [c for c in save_message_calls if c.kwargs.get('role') == 'assistant']
    
    if assistant_calls:
        actual_usage = assistant_calls[0].kwargs.get('usage')
        print(f"Saved usage: {actual_usage}")
        expected_usage = {"completion_tokens": 10, "prompt_tokens": 20, "total_tokens": 30}
        assert actual_usage == expected_usage, f"Usage mismatch: {actual_usage} != {expected_usage}"
        print("✅ SUCCESS: Usage recorded correctly!")
    else:
        print("❌ FAILURE: Assistant message not saved!")

if __name__ == "__main__":
    asyncio.run(test_streaming_usage())
