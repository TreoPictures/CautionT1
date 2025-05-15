import os
import hashlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from supabase import create_client, Client
from bs4 import BeautifulSoup
from datetime import datetime
import re
import praw
import httpx

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

# ---------- SCRAPER: SIMRACINGSETUP.COM ----------
@app.get("/scrape/simracingsetup")
def scrape_simracingsetup():
    url = "https://simracingsetup.com/assetto-corsa-setups/"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select("a[href*='/assetto-corsa-setups/']")

        saved = []

        for a in links:
            href = a.get("href", "")
            text = a.text.strip()
            match = re.match(r"(.*?) Setup – (.*?)$", text)
            if not match:
                continue
            car, track = match.groups()
            entry = {
                "car": car,
                "track": track,
                "url": href,
                "source": "simracingsetup.com",
                "notes": None,
                "created_at": datetime.utcnow().isoformat(),
            }
            entry["hash"] = dedup_hash(entry["car"], entry["track"], entry["notes"])
            if save_to_supabase(entry):
                saved.append(entry)

        return {"saved": len(saved), "entries": saved}
    except Exception as e:
        return {"error": str(e)}

# ---------- SCRAPER: RACINGSSETUPS.SHOP ----------
@app.get("/scrape/racingsetups")
def scrape_racingsetups():
    base_url = "https://racingsetups.shop"
    try:
        res = requests.get(base_url, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select("a[href*='/products/']")

        saved = []
        for a in links:
            href = a.get("href", "")
            title = a.get("title", "") or a.text.strip()
            match = re.match(r"(.*?) Setup for (.*?)$", title)
            if not match:
                continue
            car, track = match.groups()
            entry = {
                "car": car.strip(),
                "track": track.strip(),
                "url": f"{base_url}{href}",
                "source": "racingsetups.shop",
                "notes": None,
                "created_at": datetime.utcnow().isoformat(),
            }
            entry["hash"] = dedup_hash(entry["car"], entry["track"], entry["notes"])
            if save_to_supabase(entry):
                saved.append(entry)

        return {"saved": len(saved), "entries": saved}
    except Exception as e:
        return {"error": str(e)}

# ---------- SCRAPER: REDDIT (USING PRAW) ----------
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
        return {"error": str(e)}

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
