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
        
        ### Risk Level Definitions:
        - **Low**: All values within normal range, or minor deviations with no clinical significance.
        - **Medium**: Significant deviations from normal (e.g., high cholesterol, borderline blood pressure) requiring lifestyle changes or non-urgent followup.
        - **High**: Critical values (e.g., extremely high glucose, severe anemia, markers indicating acute heart/liver issues) requiring immediate medical attention.

        ### Instructions:
        1. Perform a step-by-step clinical reasoning based on the lab values provided.
        2. Identify specific tests, their values, units, and status.
        3. Determine the overall health score (0-100) and risk level.
        
        Return a JSON object with strictly these fields:
        1. "summary": Concise technical summary of findings.
        2. "risk_level": EXACTLY one of ["Low", "Medium", "High"].
        3. "health_score": Integer 0-100.
        4. "reasoning": A brief explanation of why the risk level was chosen.
        5. "lab_values": Array of { "name", "value", "unit", "status" }.
           - status must be one of ["Normal", "Abnormal", "Critical"].
        6. "recommendations": Array of actionable steps.

        Be precise, medicaly accurate, and prioritize patient safety.
        """
        
        user_prompt = f"Analyze this medical report text:\n\n{text}"
        
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama-3.3-70b-versatile", # Latest model for superior reasoning
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(chat_completion.choices[0].message.content)
            
            # --- POST-PROCESSING & NORMALIZATION ---
            # Sanitize risk_level
            raw_risk = str(result.get("risk_level", "Medium")).strip().capitalize()
            if raw_risk not in ["Low", "Medium", "High"]:
                # Fallback logic based on health score or reasoning
                score = result.get("health_score", 70)
                if score < 50: raw_risk = "High"
                elif score < 75: raw_risk = "Medium"
                else: raw_risk = "Low"
            
            result["risk_level"] = raw_risk
            
            # Ensure other fields exist
            result.setdefault("summary", "Analysis completed based on available data.")
            result.setdefault("health_score", 70)
            result.setdefault("lab_values", [])
            result.setdefault("recommendations", ["Please consult with your assigned doctor for a full clinical review."])
            
            return result
        except Exception as e:
            print(f"Groq Analysis Error: {e}")
            return {
                "summary": "AI extraction failed. Please review the report manually.",
                "risk_level": "Medium", # Safe fallback
                "health_score": 0,
                "reasoning": f"Technical error: {str(e)}",
                "lab_values": [],
                "error": str(e)
            }
