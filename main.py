import os
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Message(BaseModel):
    prompt: str

@app.post("/chat")
async def chat_with_ai(message: Message):
    headers = {
        "Authorization": f"Bearer {os.getenv('TOGETHER_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "togethercomputer/Mixtral-8x7B-Instruct-v0.1",
        "prompt": f"<s>[INST] {message.prompt} [/INST]",
        "max_tokens": 200,
        "temperature": 0.7,
        "top_p": 0.7,
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.together.xyz/v1/completions", headers=headers, json=payload)
            res.raise_for_status()
            output = res.json()
            return {"response": output["choices"][0]["text"].strip()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Hello from your ethical sim-racing AI!"}
