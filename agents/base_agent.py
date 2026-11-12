import time
from langchain_google_genai import ChatGoogleGenerativeAI
import config

class BaseLLMAgent:
    """
    Base class providing resilient, retry-wrapped LLM invocation for all ChipGen agents.
    Handles transient 503 UNAVAILABLE, 429 rate limits, and network errors.
    """
    def __init__(self, api_key: str | None = None, model_name: str | None = None, temperature: float = 0.1):
        self.api_key = api_key or config.GOOGLE_API_KEY
        self.model_name = model_name or config.GEMINI_MODEL
        self.temperature = temperature
        self._llm = None

    def _get_llm(self) -> ChatGoogleGenerativeAI:
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not configured. Please set GOOGLE_API_KEY in your .env file or Streamlit sidebar."
            )
        if self._llm is None:
            self._llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key,
                temperature=self.temperature,
                max_retries=5,
                timeout=90
            )
        return self._llm

    def invoke_with_retry(self, messages: list, max_attempts: int = 5, initial_backoff: float = 2.0):
        """Executes LLM invoke with exponential backoff on transient errors."""
        llm = self._get_llm()
        delay = initial_backoff
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                return llm.invoke(messages)
            except Exception as e:
                err_str = str(e)
                last_exception = e
                if any(k in err_str.lower() for k in ["503", "unavailable", "429", "rate", "overloaded", "spikes in demand"]):
                    print(f"[{self.__class__.__name__}] LLM endpoint busy (attempt {attempt}/{max_attempts}). Backing off for {delay:.1f}s...")
                    time.sleep(delay)
                    delay *= 2.0
                else:
                    raise e
        raise last_exception

