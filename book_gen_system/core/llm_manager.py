import os
import time
import google.generativeai as genai
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class LLMManager:
    """Wrapper for LLM calls using Gemini or DeepSeek."""
    def __init__(self, api_key: str = None):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        if self.provider == "deepseek":
            self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
            self.model_name = os.getenv("LLM_MODEL", "deepseek-chat")
            self.api_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/")
            if self.api_key and OpenAI:
                self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
            else:
                self.client = None
                print("Warning: DEEPSEEK_API_KEY missing or openai library not installed.")
        else:
            self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
            if self.api_key:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.0-flash')
            else:
                self.model = None
                print("Warning: GOOGLE_API_KEY not found. Using MOCK mode for demo.")

    def _mock_generate(self, prompt: str) -> str:
        if "outline" in prompt.lower():
            return '{"chapters": ["The Beginning", "The Middle", "The End"]}'
        elif "summarize" in prompt.lower():
            return "This is a mock summary of the chapter content."
        else:
            return "This is mock chapter content generated for demonstration purposes."

    async def generate_content(self, prompt: str) -> str:
        if self.provider == "deepseek":
            if not self.client:
                return self._mock_generate(prompt)
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant and creative writer. Provide output strictly addressing the prompt."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    if "429" in str(e).lower() or "limit" in str(e).lower():
                        if attempt < max_retries - 1:
                            time.sleep(5 * (2 ** attempt))
                        else:
                            return f"Error during generation: Max retries exceeded. ({e})"
                    else:
                        return f"Error during generation: {str(e)}"
        else:
            if not self.api_key:
                return self._mock_generate(prompt)
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                return f"Error during generation: {str(e)}"

    def get_summary_prompt(self, chapter_content: str) -> str:
        return f"Summarize the following book chapter in 3-5 concise sentences:\n\n{chapter_content}"

    def get_outline_prompt(self, title: str, notes: str) -> str:
        return f"Generate a detailed book outline for a book titled '{title}'. Context: {notes}. Output in JSON format with chapter titles."

    def get_chapter_prompt(self, title: str, chapter_title: str, prev_summaries: list, extra_notes: str = "") -> str:
        summaries_text = "\n".join([f"Chapter {i+1}: {s}" for i, s in enumerate(prev_summaries)])
        return f"""
        Book Title: {title}
        Current Chapter: {chapter_title}
        
        Previous Chapter Summaries:
        {summaries_text}
        
        Editor's Notes: {extra_notes}
        
        Write a full, engaging chapter for this book.
        """
