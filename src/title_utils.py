import re
import logging
from src.nodes import get_llm, invoke_llm

logger = logging.getLogger(__name__)

_GREETINGS = {"hi", "hello", "hey", "good morning", "good evening", "how are you", "ok", "ohk", "okay", "thanks", "thank you", "test", "?", "testing"}

def _is_greeting(message: str) -> bool:
    clean_msg = message.strip().lower()
    if clean_msg in _GREETINGS:
        return True
    words = clean_msg.split()
    # Check if it's very short and consists only of greeting words
    if len(words) < 3 and all(re.sub(r"[^\w]", "", w) in _GREETINGS for w in words):
        return True
    # If the message is a single character or just symbols
    if len(re.sub(r"[^\w]", "", clean_msg)) == 0:
        return True
    return False

def generate_title(message: str) -> str:
    """Return a concise title (2-6 words) for the conversation.
    If the message is a greeting or too short, return 'New Conversation'.
    """
    if _is_greeting(message):
        return "New Conversation"
    
    try:
        llm = get_llm()
        prompt = (
            "You are a helpful AI. Given the user message below, produce a concise title (2-6 words) that captures its intent. "
            "Return ONLY the title without quotes or extra text. "
            "If the message is a simple greeting or gibberish, return exactly 'New Conversation'.\n\nMessage:\n" + message
        )
        
        response = invoke_llm(llm, prompt).strip()
        
        # Clean up quotes if the LLM added them
        response = response.strip('"').strip("'")
        
        if response.lower() == "new conversation":
            return "New Conversation"
            
        # Keep only alphanumeric, spaces, and hyphens
        clean = re.sub(r"[^\w\s-]", "", response)
        words = clean.split()
        if not words:
            return "New Conversation"
        # Truncate to 6 words
        return " ".join(words[:6])
    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        return "New Conversation"
