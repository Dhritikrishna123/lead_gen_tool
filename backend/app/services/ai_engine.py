"""
AI Context Engine — Uses Google Gemini to parse natural language prompts
and generate dynamic search queries for the scrapers.
"""

from typing import Any, Dict
import json
import logging
import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """You are the AI Context Engine for Lead Gen Tool.
Given a user's natural language prompt describing the leads they want to find, extract the following entities and return them strictly as a valid JSON object:
- keywords: list of strings (3 to 5 highly relevant keywords for a search query, excluding stopwords like 'find', 'companies', 'needing', 'help', etc.)
- sources: list of strings (If the user explicitly mentions 'upwork' or 'freelancer', include them here. If no sources are mentioned, return null or an empty list.)

Example Input:
"Find companies needing help deploying Docker apps on Upwork"

Example Output:
{
  "keywords": ["Docker", "deployment", "apps"],
  "sources": ["upwork"]
}
"""

# Initialize the model with the system instruction
# We use gemini-1.5-flash as it is fast and efficient for parsing JSON tasks
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_INSTRUCTION,
    generation_config={"response_mime_type": "application/json"}
)

async def parse_prompt(prompt: str) -> Dict[str, Any]:
    """Send natural language prompt to Gemini and return structured search parameters."""
    try:
        response = model.generate_content(prompt)
        result = json.loads(response.text)
        
        # Ensure 'sources' is None if empty or not provided
        if not result.get("sources"):
            result["sources"] = None
        else:
            # Normalize to lowercase just in case
            result["sources"] = [src.lower() for src in result["sources"]]
            
        return result
    except Exception as e:
        logger.error(f"Failed to parse prompt via Gemini: {e}")
        # Return fallback in case of failure to prevent breaking the flow
        return {
            "keywords": [prompt[:50]], 
            "sources": None
        }
