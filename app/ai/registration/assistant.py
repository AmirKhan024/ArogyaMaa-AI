"""
AI Assistant for Registration

Groq LLM wrapper used by the RegistrationEngine for data extraction
and empathetic question generation.
"""

from groq import Groq


class AIAssistant:
    def __init__(self, groq_api_key: str):
        self.client = Groq(api_key=groq_api_key)

    def _call_groq(self, prompt: str, system_prompt: str, model="llama-3.3-70b-versatile") -> str:
        """Call Groq API with specific model and system prompt."""
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model=model,
                temperature=0.7,
                max_tokens=1024
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Groq API Error: {e}")
            return "AI feature disabled due to missing GROQ Key."
