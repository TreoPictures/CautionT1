# Import necessary libraries
import openai
from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Set your OpenAI API key from the environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

# Define a class for the incoming request
class Message(BaseModel):
    prompt: str

# Create an endpoint to interact with the AI
@app.post("/chat")
async def chat_with_ai(message: Message):
    try:
        # OpenAI API call to generate a response based on the user's message
        response = openai.Completion.create(
            engine="text-davinci-003",  # You can also try other engines
            prompt=message.prompt,
            max_tokens=150,
            temperature=0.7,
        )

        # Return the AI's response
        return {"response": response.choices[0].text.strip()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Fly.io!"}