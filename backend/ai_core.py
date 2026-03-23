import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

URL = "https://api.groq.com/openai/v1/chat/completions"
MEMORY_FILE = Path(__file__).resolve().parent / "memory.json"


def get_headers():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY in .env")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def read_store():
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "chats" in data:
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"active": None, "chats": {}}


def write_store(store):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def call_model(messages):
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": messages,
        "temperature": 0.8,
    }
    resp = requests.post(URL, headers=get_headers(), json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
