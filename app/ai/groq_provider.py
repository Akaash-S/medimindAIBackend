from groq import AsyncGroq
from app.ai.base import AIProvider
from app.core.config import settings
from typing import Dict, Any

class GroqProvider(AIProvider):
    def __init__(self, api_key: str):
        self.client = AsyncGroq(api_key=api_key)

    async def analyze_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        text = data.get("text", "")
        
        system_prompt = """
        You are a highly skilled Medical AI Assistant. Your task is to analyze medical report text and extract structured clinical insights.
        
        Return a JSON object with the following fields:
        1. "summary": A concise (2-3 sentences) clinical summary of the findings.
        2. "risk_level": One of ["Low", "Medium", "High"] based on the severity of the findings.
        3. "health_score": An integer from 0-100 (100 being perfect health) based on the results.
        4. "lab_values": A list of objects, each containing:
           - "name": The name of the test (e.g., "Glucose", "LDL Cholesterol")
           - "value": The numerical value
           - "unit": The measurement unit (e.g., "mg/dL", "mmol/L")
           - "status": One of ["Normal", "Abnormal", "Critical"]
        5. "recommendations": A list of short actionable steps for the patient.

        Be precise, conservative with risk assessments, and prioritize patient safety.
        """
        
        user_prompt = f"Analyze this medical report text:\n\n{text}"
        
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama3-70b-8192",  # More reliable for complex reasoning
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(chat_completion.choices[0].message.content)
            
            # Ensure required fields exist even if AI missed them
            result.setdefault("risk_level", "Unknown")
            result.setdefault("summary", "Analysis completed.")
            result.setdefault("health_score", 70)
            result.setdefault("lab_values", [])
            
            return result
        except Exception as e:
            print(f"Groq Analysis Error: {e}")
            return {
                "summary": "AI analysis failed due to a technical error.",
                "risk_level": "Unknown",
                "health_score": 0,
                "lab_values": [],
                "error": str(e)
            }
