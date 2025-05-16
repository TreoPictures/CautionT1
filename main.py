    import os
    import uuid
    from datetime import datetime
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import requests
    import httpx
    from supabase import create_client, Client

    # Environment Variables
    TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    SERPAPI_KEY = os.getenv("SERPAPI_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # Initialize FastAPI
    app = FastAPI()

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Adjust for Carrd domain in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Supabase client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Request model
    class Message(BaseModel):
        prompt: str

    # Save chat history to Supabase
    def save_chat_history(prompt: str, response: str):
        supabase.table("chat_history").insert({
            "id": str(uuid.uuid4()),
            "prompt": prompt,
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()

    # Save setup to Supabase (if structured as JSON setup output)
    def save_setup_to_supabase(prompt: str, setup_json: dict):
        import json

        # Minimal extraction - assumes prompt has car and track names
        car = track = "Unknown"
        if "for" in prompt:
            try:
                parts = prompt.split("for", 1)[1].strip()
                car, track = parts.split("at") if "at" in parts else (parts, "Unknown")
                car, track = car.strip(), track.strip()
            except:
                pass

        supabase.table("setups").insert({
            "id": str(uuid.uuid4()),
            "car": car,
            "track": track,
            "url": "N/A",
            "source": "AI",
            "notes": json.dumps(setup_json),
            "created_at": datetime.utcnow().isoformat()
        }).execute()

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

    # SerpAPI fallback
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

    # Main chat endpoint
    @app.post("/chat")
    async def chat_with_ai(message: Message):
        search_results = await brave_search(message.prompt)
        if "failed" in search_results.lower() or "No relevant search results" in search_results:
            search_results = await serpapi_search(message.prompt)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert sim racing setup engineer. "
                    "Given search results that may include setup guides or forum posts, extract detailed setup parameters for the car and track in question. "
                    "These parameters include (but are not limited to): tire pressures, suspension stiffness, camber, toe, wing angles, gear ratios, brake bias, and any other relevant tuning values. "
                    "If the search results do NOT contain any setup parameters, then provide a complete realistic setup for the specified car, track, and conditions based on your own expertise. "
                    "Always output the setup parameters clearly and numerically if possible. "
                    "Please output the setup parameters as a JSON object with keys such as:\n"
                    "{\n"
                    "  \"tire_pressure_front\": value,\n"
                    "  \"tire_pressure_rear\": value,\n"
                    "  \"front_wing_angle\": value,\n"
                    "  \"rear_wing_angle\": value,\n"
                    "  \"suspension_front_stiffness\": value,\n"
                    "  \"suspension_rear_stiffness\": value,\n"
                    "  \"camber_front\": value,\n"
                    "  \"camber_rear\": value,\n"
                    "  \"toe_front\": value,\n"
                    "  \"toe_rear\": value,\n"
                    "  \"gear_ratios\": [...],\n"
                    "  \"brake_bias\": value\n"
                    "}\n"
                    "If any value is unknown, estimate it realistically."
                )
            },
            {
                "role": "user",
                "content": (
                    f"User request: {message.prompt}\n\n"
                    f"Search results:\n{search_results}\n\n"
                    "Please provide the detailed setup parameters or a full expert setup."
                )
            }
        ]

        headers = {
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 700
        }

        try:
            response = requests.post(
                "https://api.together.xyz/v1/chat/completions",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()

            # Save to Supabase: chat_history
            save_chat_history(message.prompt, content)

            # Optional: Try parsing JSON setup and saving to setups
            import json
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "tire_pressure_front" in parsed:
                    save_setup_to_supabase(message.prompt, parsed)
            except:
                pass

            return {"response": content}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/")
    def read_root():
        return {"message": "Together AI + Brave Search + SerpAPI + Supabase live"}
