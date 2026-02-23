
import os
from typing import List

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

class ResearchManager:
    """Handles web research to inject context into book generation."""
    def __init__(self, mode: str = "agentic"):
        self.mode = mode

    def get_research_context(self, topic: str) -> str:
        """
        Retrieves real search context using duckduckgo-search API.
        """
        if not DDGS:
            return "DuckDuckGo search library not installed. Using fallback knowledge."
            
        print(f"Researching topic: {topic}")
        snippets = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(topic, max_results=3))
                for res in results:
                    snippets.append(res.get('body', ''))
        except Exception as e:
            print(f"Search failed: {e}")
            return "Search temporarily unavailable."
            
        if not snippets:
            return "No specific research context found."
            
        return "\n".join([f"- {s}" for s in snippets])
