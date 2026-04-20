import os
from langchain_mistralai import ChatMistralAI

def get_llm(kind: str):
    """
    Model routing in one place.
    kind: 'fast' or 'smart'
    """
    model_map = {
        "fast": "mistral-small-2603",
        "smart": "mistral-large-2512",
    }

    if kind not in model_map:
        raise ValueError(f"Unknown model kind: {kind}")

    return ChatMistralAI(
        model=model_map[kind],
        temperature=0,
        api_key=os.getenv("MISTRALAI_API_KEY"),
    )