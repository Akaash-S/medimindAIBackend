from app.core.config import settings
from app.ai.groq_provider import GroqProvider
from app.ai.base import AIProvider

def get_ai_provider() -> AIProvider:
    if settings.AI_PROVIDER == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set")
        return GroqProvider(api_key=settings.GROQ_API_KEY)
    elif settings.AI_PROVIDER == "internal":
        # Placeholder for InternalProvider
        # return InternalProvider(url=settings.INTERNAL_AI_URL)
        raise NotImplementedError("Internal provider not implemented yet")
    else:
        raise ValueError(f"Unknown AI provider: {settings.AI_PROVIDER}")
