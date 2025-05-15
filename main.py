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

# ---------- HELPER: setup hash & insert with deduplication ----------
def compute_setup_hash(car: str, track: str, notes: str) -> str:
    normalized = (car.strip().lower() + "|" + track.strip().lower() + "|" + (notes or "").strip().lower()).encode('utf-8')
    return hashlib.sha256(normalized).hexdigest()

def insert_setup_if_new(car, track, url, source, notes):
    setup_hash = compute_setup_hash(car, track, notes)
    # Check if setup_hash exists
    existing = supabase.table("setups").select("id").eq("setup_hash", setup_hash).limit(1).execute()
    if existing.data:
        return False  # duplicate
    entry = {
        "car": car,
        "track": track,
        "url": url,
        "source": source,
        "notes": notes,
        "setup_hash": setup_hash,
        "created_at": datetime.utcnow().isoformat()
    }
    supabase.table("setups").insert(entry).execute()
    return True

# ---------- SCRAPER: simracingsetup.com ----------
@app.get("/scrape/simracingsetup")
def scrape_simracingsetup():
    base_url = "https://www.simracingsetup.com"
    setups_saved = 0
    try:
        # Example: scrape main page setups or paginated setup listings
        resp = requests.get(f"{base_url}/setups", timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find setup listings - adapt selector to actual page structure
        setup_items = soup.select(".setup-listing")  # <- hypothetical
        if not setup_items:
            return {"message": "No setups found or site structure changed."}

        for item in setup_items:
            car = item.select_one(".car-name")
            track = item.select_one(".track-name")
            link = item.select_one("a.details-link")
            notes = None

            if car and track and link:
                detail_url = base_url + link["href"]
                # Fetch detail page to extract notes/details
                detail_resp = requests.get(detail_url, timeout=10)
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                notes_tag = detail_soup.select_one(".setup-notes")
                notes = notes_tag.text.strip() if notes_tag else None

                inserted = insert_setup_if_new(
                    car=car.text.strip(),
                    track=track.text.strip(),
                    url=detail_url,
                    source="SimRacingSetup.com",
                    notes=notes,
                )
                if inserted:
                    setups_saved += 1

        return {"message": f"Saved {setups_saved} new setups from SimRacingSetup.com"}

    except Exception as e:
        return {"error": str(e)}

# ---------- SCRAPER: racingsetups.shop ----------
@app.get("/scrape/racingsetups")
def scrape_racingsetups():
    base_url = "https://racingsetups.shop"
    setups_saved = 0
    try:
        # Example: scrape latest setups or by car/track filters
        resp = requests.get(f"{base_url}/setups", timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        setup_items = soup.select(".setup-card")  # hypothetical selector
        if not setup_items:
            return {"message": "No setups found or site structure changed."}

        for item in setup_items:
            car = item.select_one(".car")
            track = item.select_one(".track")
            link = item.select_one("a")
            notes = None

            if car and track and link:
                detail_url = base_url + link["href"]
                detail_resp = requests.get(detail_url, timeout=10)
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                notes_tag = detail_soup.select_one(".setup-details")
                notes = notes_tag.text.strip() if notes_tag else None

                inserted = insert_setup_if_new(
                    car=car.text.strip(),
                    track=track.text.strip(),
                    url=detail_url,
                    source="RacingSetups.shop",
                    notes=notes,
                )
                if inserted:
                    setups_saved += 1

        return {"message": f"Saved {setups_saved} new setups from RacingSetups.shop"}

    except Exception as e:
        return {"error": str(e)}

# ---------- SCRAPER: Reddit via Pushshift API ----------
@app.get("/scrape/reddit")
def scrape_reddit(car: str = "", track: str = ""):
    if not car:
        return {"error": "Please provide a 'car' query parameter"}
    query = f"setup {car} {track}".strip()
    setups_saved = 0
    try:
        url = f"https://api.pushshift.io/reddit/search/submission/?q={query}&subreddit=simracing,iracing&size=10&sort=desc"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", [])

        for post in posts:
            title = post.get("title", "")
            url = post.get("url", "")
            selftext = post.get("selftext", "")
            # Simple heuristic: use post text as notes
            notes = selftext if selftext else title

            inserted = insert_setup_if_new(
                car=car,
                track=track if track else "Unknown",
                url=url,
                source="Reddit",
                notes=notes,
            )
            if inserted:
                setups_saved += 1

        return {"message": f"Saved {setups_saved} new setups from Reddit"}

    except Exception as e:
        return {"error": str(e)}

# ---------- FETCH RECENT SETUPS ----------
def fetch_recent_setups(limit=3) -> str:
    try:
        result = supabase.table("setups").select("*").order("created_at", desc=True).limit(limit).execute()
        if not result.data:
            return "No real setups found."
        return "\n".join([
            f"- {s['car']} at {s['track']} → {s['url']}" for s in result.data
        ])
    except Exception as e:
        return f"Could not load setups: {str(e)}"

# ---------- CHAT WITH AI ----------
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

# ---------- SEARCH UTILS ----------
async def brave_search(query: str) -> str:
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    params = {"q": query, "count": 3}
    try:
        async with httpx.AsyncClient() as client:
            res
