import openai
from fastapi import FastAPI
from pydantic import BaseModel
import os

# Check if the key is set (for debugging, can remove this later)
print("API key loaded:", os.getenv("OPENAI_API_KEY") is not None)

# Initialize FastAPI
app = FastAPI()

# Set API key
openai.api_key = os.getenv("OPENAI_API_KEY")

class Message(BaseModel):
    prompt: str

@app.post("/chat")
async def chat_with_ai(message: Message):
    try:
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=message.prompt,
            max_tokens=150,
            temperature=0.7,
        )
        return {"response": response.choices[0].text.strip()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Fly.io!"}
