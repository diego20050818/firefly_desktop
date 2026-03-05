import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

# This script simulates the logic in _stream_llm_call to verify it captures usage
# as defined in our proposed change.

class MockChunk:
    def __init__(self, content=None, usage=None, finish_reason=None):
        self.choices = [MagicMock()]
        self.choices[0].delta = MagicMock()
        self.choices[0].delta.content = content
        self.choices[0].delta.reasoning_content = None
        self.choices[0].delta.tool_calls = None
        self.choices[0].finish_reason = finish_reason
        self.usage = usage
        self.model = "test-model"
        self.created = 123456789

async def simulate_agent_logic():
    # Simulate the result_container and queue from _stream_llm_call
    result_container = {
        "tool_calls": [],
        "full_content": "",
        "reasoning_content": None,
        "finish_reason": None,
        "usage": {}
    }
    
    # Simulate chunks received from the API (including usage in the last chunk)
    chunks = [
        MockChunk(content="Hello"),
        MockChunk(content=" world", finish_reason="stop", usage=MagicMock(model_dump=lambda: {"total_tokens": 100}))
    ]
    
    # The logic we implemented for the producer:
    for chunk in chunks:
        choice = chunk.choices[0]
        delta = choice.delta
        
        if delta.content:
            result_container["full_content"] += delta.content
        
        if choice.finish_reason:
            result_container["finish_reason"] = choice.finish_reason
            
        if hasattr(chunk, 'usage') and chunk.usage:
            result_container["usage"] = chunk.usage.model_dump()
            
    print(f"Final full_content: {result_container['full_content']}")
    print(f"Final usage: {result_container['usage']}")
    
    # Assert usage was captured
    expected_usage = {"total_tokens": 100}
    assert result_container["usage"] == expected_usage, f"Usage capture failed: {result_container['usage']}"
    print("✅ Logic verification successful: Usage correctly captured from chunks.")

if __name__ == "__main__":
    asyncio.run(simulate_agent_logic())
