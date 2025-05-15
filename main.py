import os
from fastapi import FastAPI
from pydantic import BaseModel
import requests

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

app = FastAPI()

class Message(BaseModel):
    prompt: str

@app.post("/chat")
async def chat_with_ai(message: Message):
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",  # Or try meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
        "messages": [{"role": "user", "content": message.prompt}],
        "temperature": 0.7,
        "max_tokens": 300
    }

    try:
        response = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        return {
            "response": response.json()["choices"][0]["message"]["content"].strip()
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Together AI + FastAPI is live"}
