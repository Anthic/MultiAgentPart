import os
from langchain_mistralai import ChatMistralAI

model_map = {
    "fast": "mistral-small-2603",
    "smart": "mistral-large-2512",
}

_llm_cache : dict = {}

def get_llm(kind : str) :
    if kind not in model_map:
        raise ValueError(f"Unknown model kind: {kind!r}. Valid options: {list(model_map.keys())}")
    if kind not in _llm_cache:
        _llm_cache[kind] = ChatMistralAI(
            model= model_map[kind],
            temperature=0,
            api_key=os.getenv("MISTRALAI_API_KEY"),
        )
    return _llm_cache[kind]