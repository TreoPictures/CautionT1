# main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import httpx
from supabase import create_client, Client
from bs4 import BeautifulSoup
from datetime import datetime

# API Keys
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase init
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# ---------- SCRAPER ----------
@app.get("/scrape/garage61")
def scrape_garage61():
    url = "https://garage61.gg/setups"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        setup_cards = soup.select(".setup-card")
        saved = []

        for card in setup_cards:
            car = card.select_one(".car-name")
            track = card.select_one(".track-name")
            link = card.select_one("a")["href"]

            if car and track and link:
                entry = {
                    "car": car.text.strip(),
                    "track": track.text.strip(),
                    "url": f"https://garage61.gg{link}",
                    "source": "Garage61",
                    "notes": None,
                    "created_at": datetime.utcnow().isoformat()
                }
                supabase.table("setups").insert(entry).execute()
                saved.append(entry)

        return {"message": f"Saved {len(saved)} setups from Garage61", "data": saved}
    except Exception as e:
        return {"error": str(e)}

# ---------- LEGAL STUBS ----------
@app.get("/scrape/simracingsetups")
def stub_simracingsetups():
    return {
        "note": "SimRacingSetups.com disallows bots in robots.txt. Please visit manually.",
        "url": "https://www.simracingsetup.com/"
    }

@app.get("/scrape/racedepartment")
def stub_racedepartment():
    return {
        "note": "RaceDepartment requires login and uses JavaScript. Scraping not allowed or feasible.",
        "url": "https://www.racedepartment.com/downloads/categories/assetto-corsa.1/"
    }

@app.get("/scrape/coachdave")
def stub_coachdave():
    return {
        "note": "Coach Dave Academy content is paid. Scraping is against TOS.",
        "url": "https://coachdaveacademy.com/setups/"
    }

# ---------- SETUPS FETCH ----------
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

# ---------- CHAT ----------
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
