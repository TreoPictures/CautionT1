import os
import hashlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import httpx
from supabase import create_client, Client
from datetime import datetime

# ---------- ENVIRONMENT VARIABLES ----------
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ---------- SUPABASE CLIENT ----------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- FASTAPI SETUP ----------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    prompt: str

def dedup_hash(car: str, track: str, notes: str | None) -> str:
    content = f"{car.lower()}|{track.lower()}|{notes or ''}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def is_duplicate(hash_value: str) -> bool:
    result = supabase.table("setups").select("id").eq("hash", hash_value).execute()
    return bool(result.data)

def save_to_supabase(entry: dict) -> bool:
    if is_duplicate(entry["hash"]):
        return False
    supabase.table("setups").insert(entry).execute()
    return True

# ---------- HEALTH CHECK ----------
@app.get("/")
def health():
    return {"status": "ok"}

# ---------- SEARCH: BRAVE API ----------
@app.get("/search/brave")
def search_brave(car: str, track: str):
    query = f"{car} {track} setup site:reddit.com OR site:simracingsetup.com OR site:racingsetups.shop"
    try:
        res = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
            params={"q": query, "count": 10},
            timeout=10
        )
        res.raise_for_status()
        data = res.json()
        urls = [item["url"] for item in data.get("web", {}).get("results", [])]
        return {"query": query, "results": urls}
    except Exception as e:
        return {"error": f"Brave API error: {str(e)}"}

# ---------- SEARCH: SERPAPI ----------
@app.get("/search/serpapi")
def search_serpapi(car: str, track: str):
    query = f"{car} {track} setup site:reddit.com OR site:simracingsetup.com OR site:racingsetups.shop"
    try:
        res = requests.get("https://serpapi.com/search", params={
            "q": query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": 10
        }, timeout=10)
        res.raise_for_status()
        data = res.json()
        urls = [r.get("link") for r in data.get("organic_results", []) if r.get("link")]
        return {"query": query, "results": urls}
    except Exception as e:
        return {"error": f"SerpAPI error: {str(e)}"}

# ---------- CHAT: TOGETHER.AI ----------
class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not TOGETHER_API_KEY:
        raise HTTPException(status_code=500, detail="TOGETHER_API_KEY not set")

    url = "https://api.together.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json",
    }
    json_data = {
        "model": "together-mosaicml/mpt-7b-chat",
        "messages": [
            {"role": "user", "content": request.prompt}
        ],
        "max_tokens": 512,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, headers=headers, json=json_data)
            response.raise_for_status()
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            return ChatResponse(reply=reply)

    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Together.ai API error: {str(e)}")
