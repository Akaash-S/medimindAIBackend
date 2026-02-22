from abc import ABC, abstractmethod
from typing import Dict, Any

class AIProvider(ABC):
    @abstractmethod
    async def analyze_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze medical report data and return structured results.
        """
        pass
