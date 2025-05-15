import os
import hashlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

import requests
import httpx
import praw
from supabase import create_client, Client
from bs4 import BeautifulSoup

# ---------- ENVIRONMENT VARIABLES ----------
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "setup-bot")

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

# ---------- UTILS ----------
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

# ---------- SCRAPER: REDDIT ----------
@app.get("/scrape/reddit")
def scrape_reddit(car: str = "Mazda MX-5", track: str = "Okayama"):
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )

        query = f"{car} {track} setup"
        subreddit = reddit.subreddit("simracing+iracing")
        posts = subreddit.search(query, limit=10, sort="new")

        saved = []
        for post in posts:
            url = f"https://www.reddit.com{post.permalink}"
            title = post.title.strip()
            body = post.selftext.strip()

            entry = {
                "car": car,
                "track": track,
                "url": url,
                "source": "reddit",
                "notes": f"{title}\n\n{body}" if body else title,
                "created_at": datetime.utcnow().isoformat()
            }
            entry["hash"] = dedup_hash(entry["car"], entry["track"], entry["notes"])
            if save_to_supabase(entry):
                saved.append(entry)

        return {"saved": len(saved), "entries": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Brave API connection error: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Brave API error: {e.response.text}")

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
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"SerpAPI error: {str(e)}")

@app.post("/chat")
def chat(msg: Message):
    prompt = msg.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    return {"response": f"You said: {prompt}"}
