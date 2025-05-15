import os
import hashlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import httpx
from supabase import create_client, Client
from bs4 import BeautifulSoup
from datetime import datetime
import re

# ---------- ENVIRONMENT VARIABLES ----------
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = "setup-bot"

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

# ---------- SCRAPER: REDDIT SETUPS ----------
@app.get("/scrape/reddit")
def scrape_reddit():
    headers = {"User-Agent": REDDIT_USER_AGENT}
    auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_SECRET)
    data = {"grant_type": "client_credentials"}
    try:
        # Token
        token_res = requests.post("https://www.reddit.com/api/v1/access_token", auth=auth, data=data, headers=headers)
        token_res.raise_for_status()
        token = token_res.json()["access_token"]
        headers["Authorization"] = f"bearer {token}"

        search_url = "https://oauth.reddit.com/r/simracing/search"
        params = {"q": "setup", "limit": 10, "sort": "new", "restrict_sr": True}
        res = requests.get(search_url, headers=headers, params=params)
        res.raise_for_status()
        posts = res.json()["data"]["children"]

        saved = []
        for post in posts:
            p = post["data"]
            title = p["title"]
            match = re.match(r"(.*?) Setup for (.*?)", title)
            if not match:
                continue
            car, track = match.groups()
            entry = {
                "car": car.strip(),
                "track": track.strip(),
                "url": f"https://reddit.com{p['permalink']}",
                "source": "reddit",
                "notes": p.get("selftext", "")[:250],
                "created_at": datetime.utcnow().isoformat(),
            }
            entry["hash"] = dedup_hash(entry["car"], entry["track"], entry["notes"])
            if save_to_supabase(entry):
                saved.append(entry)

        return {"saved": len(saved), "entries": saved}
    except Exception as e:
        return {"error": str(e)}
