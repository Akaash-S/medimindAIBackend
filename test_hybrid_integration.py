import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import json

# Import the module we want to test
import sys
import os
sys.path.append(os.getcwd())

# Mock Firebase before importing ai_chat to avoid connection issues
with patch('app.core.firebase.db'), patch('app.core.firebase.firestore'):
    from app.api.ai_chat import _get_medical_knowledge, SYSTEM_GUIDE, ChatRequest, ChatMessage

async def test_medical_knowledge_call():
    print("\nTesting RAG service call...")
    # Mock httpx.AsyncClient.post
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"answer": "This is medical knowledge about CRT."}
        
        knowledge = await _get_medical_knowledge("What is CRT?")
        print(f"Knowledge received: {knowledge}")
        assert knowledge == "This is medical knowledge about CRT."
        print("RAG service call test passed!")

async def test_system_guide_presence():
    print("\nTesting System Guide content...")
    assert "MediMindAI System Information" in SYSTEM_GUIDE
    assert "AI Medical Analysis" in SYSTEM_GUIDE
    assert "Appointments" in SYSTEM_GUIDE
    print("System Guide test passed!")

if __name__ == "__main__":
    asyncio.run(test_medical_knowledge_call())
    asyncio.run(test_system_guide_presence())
    print("\nAll integration unit tests passed!")
