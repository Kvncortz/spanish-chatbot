import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("voice.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection established")
    
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not set")
        await websocket.send_text("Error: OPENAI_API_KEY not set")
        return
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Start with an icebreaker question
        icebreakers = [
            "¡Hola! ¿Cómo estás hoy?",
            "¿Qué tal tu día hasta ahora?",
            "¿Qué te gustaría hacer hoy?",
            "¿Has practicado español antes?",
            "¿Qué tiempo hace donde estás?"
        ]
        
        import random
        icebreaker = random.choice(icebreakers)
        print(f"Sending icebreaker: {icebreaker}")
        
        # Send icebreaker as text for now
        await websocket.send_text(json.dumps({
            "type": "message",
            "content": icebreaker,
            "sender": "bot"
        }))
        
        # Handle messages
        while True:
            try:
                # Wait for user message
                data = await websocket.receive_text()
                print(f"Received message: {data}")
                
                message_data = json.loads(data)
                
                if message_data.get("type") == "message":
                    user_message = message_data.get("content", "")
                    
                    # Get response from OpenAI
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "Eres un compañero de conversación amigable para practicar español. Responde SIEMPRE en español neutro. Mantén tus respuestas naturales, cortas y conversacionales. Haz preguntas de seguimiento para mantener la conversación fluida. Sé paciente y educativo."},
                            {"role": "user", "content": user_message}
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )
                    
                    bot_response = response.choices[0].message.content
                    print(f"Sending response: {bot_response}")
                    
                    # Send response
                    await websocket.send_text(json.dumps({
                        "type": "message",
                        "content": bot_response,
                        "sender": "bot"
                    }))
                    
            except WebSocketDisconnect:
                print("Client disconnected")
                break
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(error_msg)
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": f"Lo siento, ha ocurrido un error: {str(e)}",
                    "sender": "bot"
                }))
                break
                
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error", 
            "content": f"Error: {str(e)}",
            "sender": "bot"
        }))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
