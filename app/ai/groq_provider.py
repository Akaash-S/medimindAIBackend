from groq import AsyncGroq
from app.ai.base import AIProvider
from app.core.config import settings
from typing import Dict, Any

class GroqProvider(AIProvider):
    def __init__(self, api_key: str):
        self.client = AsyncGroq(api_key=api_key)

    async def analyze_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        content = f"Analyze the following medical report data: {data}. Return a JSON with summary, risk level (Low, Medium, High), and recommendations."
        
        chat_completion = await self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional medical AI assistant."
                },
                {
                    "role": "user",
                    "content": content,
                }
            ],
            model="mixtral-8x7b-32768",
            response_format={"type": "json_object"}
        )
        
        import json
        return json.loads(chat_completion.choices[0].message.content)
