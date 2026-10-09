"""One place to choose the model. Defaults to Groq so it matches PaperTrail."""
from testbed import config


def get_llm(temperature: float = 0.0, model: str | None = None):
    provider = config.LLM_PROVIDER.lower()
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model or config.LLM_MODEL or "qwen/qwen3.8-27b", temperature=temperature)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model or config.LLM_MODEL or "claude-haiku-4-5-20251001", temperature=temperature)
    raise ValueError(f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER}")