import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# CORS for Carrd site (currently open to all origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For Carrd, use e.g. ["https://your-site.carrd.co"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    prompt: str

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

def fetch_recent_setups(limit=3) -> str:
    try:
        result = supabase.table("setups").select("*").order("id", desc=True).limit(limit).execute()
        if not result.data:
            return "No real setups found."
        return "\n".join([
            f"- {s['car']} at {s['track']} → {s['url']}" for s in result.data
        ])
    except Exception as e:
        return f"Could not load setups: {str(e)}"

@app.post("/chat")
async def chat_with_ai(message: Message):
    search_results = await brave_search(message.prompt)
    if "failed" in search_results.lower():
        search_results = await serpapi_search(message.prompt)

    real_setups = fetch_recent_setups()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a sim racing setup expert. Use the provided search results "
                "and real setup data to help the user."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User prompt: {message.prompt}\n\n"
                f"Search results:\n{search_results}\n\n"
                f"Real setups:\n{real_setups}"
            ),
        },
    ]

    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 400,
    }

    try:
        response = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers=headers,
            json=data,
        )
        response.raise_for_status()
        return {
            "response": response.json()["choices"][0]["message"]["content"].strip()
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Together AI + Brave + SerpAPI + Supabase SetupBot is live!"}
