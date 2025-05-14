from openai import OpenAI
from fastapi import FastAPI
from pydantic import BaseModel
import os

# Debug
print("API key loaded:", os.getenv("OPENAI_API_KEY") is not None)

# Set up OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Init FastAPI
app = FastAPI()

class Message(BaseModel):
    prompt: str

@app.post("/chat")
async def chat_with_ai(message: Message):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Or "gpt-4" if your key has access
            messages=[{"role": "user", "content": message.prompt}],
            temperature=0.7,
            max_tokens=150,
        )
        return {"response": response.choices[0].message.content.strip()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Fly.io!"}
