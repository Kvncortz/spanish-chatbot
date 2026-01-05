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
    return templates.TemplateResponse("simple.html", {"request": request})

@app.websocket("/ws/{level}")
async def websocket_endpoint(websocket: WebSocket, level: str = "intermediate"):
    await websocket.accept()
    connection_id = id(websocket)  # Unique ID for this connection
    print(f"WebSocket connection {connection_id} established with level: {level}")
    
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not set")
        await websocket.send_text("Error: OPENAI_API_KEY not set")
        return
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Define level-specific prompts and icebreakers
        level_configs = {
            "beginner": {
                "system_prompt": "Eres un profesor de español amigable para principiantes. Usa vocabulario simple y frases cortas. Habla despacio y repite cosas importantes. Usa solo presente tense. Responde SIEMPRE en español neutro. Sé muy paciente y anima al estudiante. NO saludes repetidamente, solo saluda una vez al inicio.",
                "icebreakers": [
                    "¡Hola! ¿Cómo te llamas?",
                    "¿De dónde eres?",
                    "¿Qué te gusta hacer?",
                    "¿Tienes hermanos?",
                    "¿Cuál es tu color favorito?",
                    "¿Qué comida te gusta?",
                    "¿Tienes mascotas?",
                    "¿Cuál es tu número favorito?",
                    "¿Qué música te gusta?",
                    "¿Cuál es tu estación del año favorita?",
                    "¿Qué bebida te gusta?",
                    "¿Tienes celular?",
                    "¿Qué deportes te gustan?",
                    "¿Cuántos años tienes?",
                    "¿Dónde vives?"
                ]
            },
            "intermediate": {
                "system_prompt": "Eres un compañero de conversación amigable para practicar español. Usa vocabulario moderado y frases naturales. Puedes usar pretérito y futuro. Responde SIEMPRE en español neutro. Mantén tus respuestas naturales, cortas y conversacionales. Haz preguntas de seguimiento para mantener la conversación fluida. Sé paciente y educativo. NO saludes repetidamente, solo saluda una vez al inicio.",
                "icebreakers": [
                    "¡Hola! ¿Cómo estás hoy?",
                    "¿Qué tal tu día hasta ahora?",
                    "¿Qué te gustaría hacer hoy?",
                    "¿Has practicado español antes?",
                    "¿Qué tiempo hace donde estás?",
                    "¿Qué has visto en Netflix últimamente?",
                    "¿Cuál es tu canción favorita ahora?",
                    "¿Has visto alguna película buena recientemente?",
                    "¿Qué planes tienes para el fin de semana?",
                    "¿Qué opinas sobre la nueva serie de Disney+?",
                    "¿Has escuchado el nuevo álbum de Bad Bunny?",
                    "¿Qué tipo de videos ves en TikTok?",
                    "¿Cuál es tu meme favorito este mes?",
                    "¿Has viajado a algún lugar interesante?",
                    "¿Qué libro estás leyendo?",
                    "¿Cuál es tu videojuego favorito?",
                    "¿Qué piensas sobre el último estreno de Marvel?",
                    "¿Has probado algún restaurante nuevo?",
                    "¿Qué celebridad sigues en Instagram?"
                ]
            },
            "advanced": {
                "system_prompt": "Eres un conversador nativo español educado. Usa vocabulario rico, expresiones idiomáticas, y estructuras complejas. Puedes discutir temas abstractos y usar subjuntivo. Responde SIEMPRE en español neutro. Mantén la conversación interesante y desafiante. Corrige sutilmente errores gramaticales si es apropiado. NO saludes repetidamente, solo saluda una vez al inicio.",
                "icebreakers": [
                    "¡Hola! ¿Qué opinas sobre la situación actual en tu país?",
                    "¿Has leído algo interesante últimamente?",
                    "¿Cuál es tu perspectiva sobre el aprendizaje de idiomas?",
                    "¿Qué te motivó a aprender español específicamente?",
                    "¿Cómo ha influido la tecnología en tu vida diaria?",
                    "¿Qué piensas sobre el impacto de las redes sociales en la sociedad?",
                    "¿Cuál es tu análisis sobre la última película de Nolan?",
                    "¿Cómo has percibido la evolución de la música latina globalmente?",
                    "¿Qué opinas sobre los cambios en la industria del streaming?",
                    "¿Cómo te sientes acerca de la inteligencia artificial en el arte?",
                    "¿Qué perspectiva tienes sobre el futuro del trabajo remoto?",
                    "¿Cómo influye la cultura pop en tu identidad personal?",
                    "¿Qué piensas sobre la representación en las películas recientes?",
                    "¿Cómo has adaptado tus hábitos con el cambio climático?",
                    "¿Qué rol juega el arte en tiempos de crisis?",
                    "¿Cómo percibes la globalización cultural a través de Netflix?",
                    "¿Qué opinas sobre la fusión de géneros musicales actuales?",
                    "¿Cómo ha cambiado tu forma de consumir noticias?",
                    "¿Qué piensas sobre la sostenibilidad en la moda?",
                    "¿Cómo afectan los algoritmos a tus decisiones diarias?"
                ]
            }
        }
        
        # Get config for selected level, default to intermediate
        config = level_configs.get(level, level_configs["intermediate"])
        print(f"Using {level} level configuration")
        
        import random
        icebreaker = random.choice(config["icebreakers"])
        print(f"Sending icebreaker: {icebreaker}")
        
        # Send icebreaker
        await websocket.send_text(f"bot:{icebreaker}")
        
        # Maintain conversation history with level-specific system prompt
        conversation_history = [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "assistant", "content": icebreaker}
        ]
        
        # Handle messages
        while True:
            try:
                # Wait for user message
                data = await websocket.receive_text()
                print(f"Connection {connection_id} received message: {data}")
                
                # Validate this is still the active connection
                if websocket.client_state.name != "CONNECTED":
                    print(f"Connection {connection_id} no longer active, stopping")
                    break
                
                if data.startswith("user:"):
                    user_message = data[5:]  # Remove "user:" prefix
                    
                    # Add user message to history
                    conversation_history.append({"role": "user", "content": user_message})
                    
                    # Get response from OpenAI
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=conversation_history,
                        max_tokens=150,
                        temperature=0.7
                    )
                    
                    bot_response = response.choices[0].message.content
                    print(f"Sending response: {bot_response}")
                    
                    # Add bot response to history
                    conversation_history.append({"role": "assistant", "content": bot_response})
                    
                    # Keep history manageable (last 10 exchanges)
                    if len(conversation_history) > 21:  # system + 10 pairs
                        conversation_history = [conversation_history[0]] + conversation_history[-20:]
                    
                    await websocket.send_text(f"bot:{bot_response}")
                    
            except WebSocketDisconnect:
                print("Client disconnected")  # Debug log
                break
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(error_msg)  # Debug log
                await websocket.send_text(f"bot:Lo siento, ha ocurrido un error: {str(e)}")
                break
                
    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
