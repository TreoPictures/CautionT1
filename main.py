import os
from fastapi import FastAPI
from pydantic import BaseModel
import requests
import httpx
from supabase import create_client, Client

# API Keys
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

class Message(BaseModel):
    prompt: str

# Brave Search
async def brave_search(query: str) -> str:
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    params = {"q": query, "count": 3}

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()
            results = data.get("web", {}).get("results", [])
            if not results:
                return "No relevant search results found."
            return "\n".join([f"- {item['title']}: {item['url']}" for item in results])
    except Exception as e:
        return f"Brave Search failed: {str(e)}"

# SerpAPI Fallback
async def serpapi_search(query: str) -> str:
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "num": 3
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
            results = data.get("organic_results", [])
            if not results:
                return "No results found from SerpAPI."
            return "\n".join([f"- {r['title']}: {r['link']}" for r in results])
    except Exception as e:
        return f"SerpAPI failed: {str(e)}"

# Chat Endpoint
@app.post("/chat")
async def chat_with_ai(message: Message):
    # Search first
    search_results = await brave_search(message.prompt)
    if "failed" in search_results.lower():
        search_results = await serpapi_search(message.prompt)

    # Construct prompt
    messages = [
        {"role": "system", "content": "You are a sim racing setup expert. Use the provided search results to help answer questions."},
        {"role": "user", "content": f"User prompt: {message.prompt}\n\nSearch results:\n{search_results}"}
    ]

    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 400
    }

    try:
        response = requests.post("https://api.together.xyz/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"].strip()

        # Save to Supabase
        supabase.table("chat_history").insert({
            "prompt": message.prompt,
            "response": reply
        }).execute()

        return {"response": reply}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Together AI + Brave Search + SerpAPI + Supabase live"}
