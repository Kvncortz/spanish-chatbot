import os
import json
import base64
import requests
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
NARAKEET_API_KEY = os.getenv("NARAKEET_API_KEY")  # Optional: for best Spanish voices
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # Optional: for better Spanish voices
TTS_SERVICE = os.getenv("TTS_SERVICE", "openai")  # Options: "openai", "elevenlabs", "narakeet"

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
        
        # TTS function using ElevenLabs for best Spanish voices
        async def generate_speech(text: str, level: str = "intermediate") -> bytes:
            # Use ElevenLabs for much better Spanish pronunciation
            if TTS_SERVICE == "elevenlabs" and ELEVENLABS_API_KEY:
                try:
                    # Different voices for each level
                    voice_map = {
                        "beginner": "21m00Tcm4TlvDq8ikWAM",  # Rachel - clear, friendly female voice
                        "intermediate": "29vD33N1CtxCmqQRPOHJ",  # Spanish male voice
                        "advanced": "AZnzlk1XvdvUeBnXmlld"   # Drew - natural male voice
                    }
                    
                    voice_id = voice_map.get(level, "29vD33N1CtxCmqQRPOHJ")
                    
                    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                    headers = {
                        "Accept": "audio/mpeg",
                        "Content-Type": "application/json",
                        "xi-api-key": ELEVENLABS_API_KEY
                    }
                    data = {
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.75,
                            "similarity_boost": 0.75,
                            "style": 0.0,
                            "use_speaker_boost": True
                        }
                    }
                    
                    response = requests.post(url, json=data, headers=headers)
                    if response.status_code == 200:
                        return response.content
                    else:
                        print(f"ElevenLabs error: {response.status_code}")
                except Exception as e:
                    print(f"ElevenLabs TTS failed: {e}")
            
            # Fallback to OpenAI (but will have Spanish issues)
            speech_response = client.audio.speech.create(
                model="tts-1",
                voice="shimmer",
                input=text,
                speed=1.1
            )
            return speech_response.content
        
        # Define level-specific prompts and icebreakers
        level_configs = {
            "beginner": {
                "system_prompt": "Eres un amigo español amigable y conversacional. Habla de forma natural sobre temas cotidianos. Usa vocabulario simple y presente indicativo. Mantén las frases cortas y naturales. Sé breve y amigable. NO saludes repetidamente ni des lecciones.",
                "icebreakers": [
                    "¡Hola! ¿Qué tal tu día?",
                    "¿Has hecho algo divertido últimamente?",
                    "¿Qué te gusta hacer en tu tiempo libre?",
                    "¿Tienes alguna mascota? Me encantan los animales.",
                    "¿Cuál es tu comida favorita? A mí me gusta la pizza.",
                    "¿Qué música escuchas estos días?",
                    "¿Has visto alguna película buena recientemente?",
                    "¿Prefieres el verano o el invierno?",
                    "¿Qué bebida te gusta? Yo soy de café.",
                    "¿Practicas algún deporte?",
                    "¿Dónde te gustaría viajar?",
                    "¿Tienes hermanos? A veces discuto con los míños.",
                    "¿Cuál es tu color favorito? El mío es azul.",
                    "Qué tal el clima donde vives?",
                    "¿Qué haces normalmente los fines de semana?"
                ]
            },
            "intermediate": {
                "system_prompt": "Eres un amigo español conversacional y natural. Habla sobre temas interesantes de forma espontánea. Usa presente, pretérito y futuro simple. Mantén una conversación fluida y amigable. Sé breve y natural. NO saludos repetidos ni correcciones.",
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
                "system_prompt": "Eres un amigo español culto y conversacional. Habla sobre temas profundos de forma natural e intelectual. Usa todo los tiempos verbales y expresiones coloquiales. Mantén conversación interesante pero amigable. Sé conciso pero profundo. NO saludos repetidos ni correcciones gramaticales.",
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
        
        # Generate speech for icebreaker
        try:
            audio_bytes = await generate_speech(icebreaker, level)
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Send icebreaker with audio
            await websocket.send_text(json.dumps({
                "type": "voice_response",
                "text": icebreaker,
                "audio": audio_base64,
                "transcription": None
            }))
        except Exception as e:
            print(f"Error generating icebreaker audio: {e}")
            # Fallback to text only
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
                
                # Parse JSON message
                try:
                    message_data = json.loads(data)
                except json.JSONDecodeError:
                    # Handle legacy text format
                    if data.startswith("user:"):
                        message_data = {"type": "text", "content": data[5:]}
                    else:
                        continue
                
                # Validate this is still the active connection
                if websocket.client_state.name != "CONNECTED":
                    print(f"Connection {connection_id} no longer active, stopping")
                    break
                
                if message_data.get("type") == "text":
                    user_message = message_data.get("content", "")
                    
                    # Get response from OpenAI with level-specific parameters
                    # Advanced level needs more tokens for complex responses
                    if level == "advanced":
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=conversation_history,
                            max_tokens=250,  # More tokens for advanced discussions
                            temperature=0.7,  # Slightly lower for more coherent long responses
                            presence_penalty=0.4,  # Lower to avoid repetition in long texts
                            frequency_penalty=0.2
                        )
                    else:
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=conversation_history,
                            max_tokens=120,
                            temperature=0.8,
                            presence_penalty=0.6,
                            frequency_penalty=0.3
                        )
                    
                    bot_response = response.choices[0].message.content
                    print(f"Sending response: {bot_response}")
                    
                    # Add bot response to history
                    conversation_history.append({"role": "assistant", "content": bot_response})
                    
                    # Keep history manageable (last 10 exchanges)
                    if len(conversation_history) > 21:  # system + 10 pairs
                        conversation_history = [conversation_history[0]] + conversation_history[-20:]
                    
                    await websocket.send_text(f"bot:{bot_response}")
                    
                elif message_data.get("type") == "voice":
                    # Handle voice input - speech to text
                    audio_data = message_data.get("audio", "")
                    
                    try:
                        # Transcribe audio using OpenAI Whisper
                        transcription = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=("audio.webm", base64.b64decode(audio_data), "audio/webm")
                        )
                        
                        user_message = transcription.text
                        print(f"Transcribed: {user_message}")
                        
                        # Add transcribed message to history
                        conversation_history.append({"role": "user", "content": user_message})
                        
                        # Get response from OpenAI with level-specific parameters
                        # Advanced level needs more tokens for complex responses
                        if level == "advanced":
                            response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=conversation_history,
                                max_tokens=250,  # More tokens for advanced discussions
                                temperature=0.7,  # Slightly lower for more coherent long responses
                                presence_penalty=0.4,  # Lower to avoid repetition in long texts
                                frequency_penalty=0.2
                            )
                        else:
                            response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=conversation_history,
                                max_tokens=120,
                                temperature=0.8,
                                presence_penalty=0.6,
                                frequency_penalty=0.3
                            )
                        
                        bot_response = response.choices[0].message.content
                        print(f"Sending response: {bot_response}")
                        
                        # Add bot response to history
                        conversation_history.append({"role": "assistant", "content": bot_response})
                        
                        # Keep history manageable
                        if len(conversation_history) > 21:
                            conversation_history = [conversation_history[0]] + conversation_history[-20:]
                        
                        # Generate speech from response using the new TTS function
                        audio_bytes = await generate_speech(bot_response, level)
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        
                        # Send both text and audio
                        await websocket.send_text(json.dumps({
                            "type": "voice_response",
                            "text": bot_response,
                            "audio": audio_base64,
                            "transcription": user_message
                        }))
                        
                    except Exception as e:
                        print(f"Voice processing error: {e}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "content": f"Error procesando voz: {str(e)}"
                        }))
                    
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
