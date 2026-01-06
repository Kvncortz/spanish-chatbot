import os
import json
import base64
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import asyncio
from dotenv import load_dotenv
from datetime import datetime
import uuid

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NARAKEET_API_KEY = os.getenv("NARAKEET_API_KEY")  # Optional: for best Spanish voices
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # Optional: for better Spanish voices
TTS_SERVICE = os.getenv("TTS_SERVICE", "openai")  # Options: "openai", "elevenlabs", "narakeet"

# Debug environment variables
print(f"=== TTS Configuration ===")
print(f"OPENAI_API_KEY present: {bool(OPENAI_API_KEY)}")
print(f"ELEVENLABS_API_KEY present: {bool(ELEVENLABS_API_KEY)}")
print(f"TTS_SERVICE: {TTS_SERVICE}")
print(f"========================")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard(request: Request):
    return templates.TemplateResponse("teacher.html", {"request": request})

@app.get("/student", response_class=HTMLResponse)
async def student_assignment(request: Request):
    return templates.TemplateResponse("student.html", {"request": request})

@app.get("/practice", response_class=HTMLResponse)
async def practice_mode(request: Request):
    return templates.TemplateResponse("simple.html", {"request": request})

# API endpoints for assignments and logs
@app.post("/api/assignments")
async def create_assignment(request: Request):
    """Create a new assignment"""
    try:
        data = await request.json()
        assignment = {
            "id": str(uuid.uuid4()),
            "title": data.get("title"),
            "level": data.get("level"),
            "duration": data.get("duration"),
            "prompt": data.get("prompt", ""),
            "description": data.get("description"),
            "instructions": data.get("instructions"),
            "createdAt": datetime.now().isoformat(),
            "studentCount": 0,
            "completionCount": 0
        }
        
        # In production, save to database
        # For now, return the assignment
        return {"assignment": assignment}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/assignments")
async def get_assignments():
    """Get all assignments"""
    # In production, fetch from database
    # For now, return empty list (frontend uses localStorage)
    return {"assignments": []}

@app.post("/api/logs")
async def submit_log(request: Request):
    """Submit student activity log"""
    try:
        log_data = await request.json()
        log = {
            "id": str(uuid.uuid4()),
            "assignmentId": log_data.get("assignmentId"),
            "studentName": log_data.get("studentName"),
            "startTime": log_data.get("startTime"),
            "endTime": log_data.get("endTime"),
            "level": log_data.get("level"),
            "messageCount": log_data.get("messageCount"),
            "voiceUsed": log_data.get("voiceUsed", False),
            "transcriptUsed": log_data.get("transcriptUsed", False),
            "completed": log_data.get("completed", False),
            "isNewStudent": log_data.get("isNewStudent", False),
            "submittedAt": datetime.now().isoformat()
        }
        
        # In production, save to database
        # For now, return success
        return {"success": True, "logId": log["id"]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/logs")
async def get_logs(assignment_id: str = None):
    """Get activity logs, optionally filtered by assignment"""
    # In production, fetch from database
    # For now, return empty list (frontend uses localStorage)
    return {"logs": []}

@app.get("/api/analytics")
async def get_analytics():
    """Get analytics data"""
    # In production, calculate from database
    # For now, return empty stats
    return {
        "totalAssignments": 0,
        "totalStudents": 0,
        "avgCompletion": 0,
        "voiceUsage": 0
    }

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
            print(f"Generating speech for text: '{text[:50]}...' with level: {level}")
            print(f"TTS_SERVICE: {TTS_SERVICE}, ELEVENLABS_API_KEY present: {bool(ELEVENLABS_API_KEY)}")
            
            # Prioritize ElevenLabs when API key is available for best Spanish voices
            if ELEVENLABS_API_KEY:
                try:
                    # Different voices for each level
                    voice_map = {
                        "beginner": "21m00Tcm4TlvDq8ikWAM",  # Rachel - clear, friendly female voice
                        "intermediate": "29vD33N1CtxCmqQRPOHJ",  # Spanish male voice
                        "advanced": "AZnzlk1XvdvUeBnXmlld"   # Drew - natural male voice
                    }
                    
                    voice_id = voice_map.get(level, "29vD33N1CtxCmqQRPOHJ")
                    print(f"Using ElevenLabs voice: {voice_id}")
                    
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
                        print("ElevenLabs TTS successful")
                        return response.content
                    else:
                        print(f"ElevenLabs error: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"ElevenLabs TTS failed: {e}")
            
            # Fallback to OpenAI (but will have Spanish issues)
            print("Falling back to OpenAI TTS with shimmer voice")
            speech_response = client.audio.speech.create(
                model="tts-1",
                voice="shimmer",
                input=text,
                speed=1.1
            )
            print("OpenAI TTS successful")
            return speech_response.content
        
        # Define level-specific prompts and icebreakers
        level_configs = {
            "beginner": {
                "system_prompt": "Eres un amigo español amigable para estudiantes de secundaria. Habla de forma natural sobre temas apropiados para menores de edad. Usa vocabulario simple y presente indicativo. Mantén las frases cortas y naturales. Sé breve y amigable. NO saludes repetidamente ni des lecciones. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado. Si un estudiante pregunta sobre bebidas alcoholicas, responde 'Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos o refrescos'. Si un estudiante pregunta sobre temas inapropiados, redirige educativamente a temas apropiados. Solo sugiere bebidas sin alcohol (agua, jugos, refrescos).",
                "icebreakers": [
                    "¡Hola! ¿Qué tal tu día?",
                    "¿Has hecho algo divertido últimamente?",
                    "¿Qué te gusta hacer en tu tiempo libre?",
                    "¿Tienes alguna mascota? Me encantan los animales.",
                    "¿Cuál es tu comida favorita? A mí me gusta la pizza.",
                    "¿Qué música escuchas estos días?",
                    "¿Has visto alguna película buena recientemente?",
                    "¿Prefieres el verano o el invierno?",
                    "¿Qué bebida te gusta? Yo soy de agua.",
                    "¿Practicas algún deporte?",
                    "¿Dónde te gustaría viajar?",
                    "¿Tienes hermanos? A veces discuto con los míños.",
                    "¿Cuál es tu color favorito? El mío es azul.",
                    "Qué tal el clima donde vives?",
                    "¿Qué haces normalmente los fines de semana?"
                ]
            },
            "intermediate": {
                "system_prompt": "Eres un amigo español conversacional para estudiantes de secundaria. Habla sobre temas apropiados para menores de edad de forma espontánea. Usa presente, pretérito y futuro simple. Mantén una conversación fluida y amigable. Usa lenguaje informal pero educado (tú/tú). Sé breve y natural. NO saludos repetidos ni correcciones. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado. Si un estudiante pregunta sobre bebidas alcoholicas, responde 'Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café'. Si un estudiante pregunta sobre temas inapropiados, redirige educativamente a temas apropiados. Solo sugiere bebidas sin alcohol (jugos, refrescos, té, agua).",
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
                    "¿Qué opinas sobre las nuevas series de streaming?",
                    "¿Has escuchado música buena últimamente?",
                    "¿Qué tipo de videos ves en internet?",
                    "¿Cuál es tu meme favorito este mes?",
                    "¿Has viajado a algún lugar interesante?",
                    "¿Qué libro estás leyendo?",
                    "¿Cuál es tu videojuego favorito?",
                    "¿Qué piensas sobre los estrenos recientes?",
                    "¿Has probado algún restaurante nuevo?",
                    "¿Qué celebridad sigues en redes sociales?"
                ]
            },
            "advanced": {
                "system_prompt": "Eres un profesional nativo de un país hispanohablante con experiencia en atención al cliente. Habla de forma sofisticada y natural, usando un vocabulario rico y variado. Usa 'usted' para el contexto formal de hotel/restaurant, pero hazlo de manera fluida y natural, no rígida. Incorpora expresiones idiomáticas, modismos cultos, y frases más elaboradas. Usa todos los tiempos verbales incluyendo subjuntivo y condicional de forma espontánea. Mantén un tono profesional pero cálido y auténtico, como lo haría un profesional bien educado en España, México o Argentina. Usa conectores complejos y frases bien estructuradas. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado para menores de edad. Si un estudiante pregunta sobre bebidas alcoholicas, responde con elegancia 'Le sugiero opciones sin alcohol como té infusiones o agua mineral'. Si un estudiante pregunta sobre temas inapropiados, redirige con diplomacia y naturalidad.",
                "icebreakers": [
                    "¡Buenas tardes! Encantado de ayudarle con su registro.",
                    "¡Hola! Bienvenido a nuestro establecimiento. ¿En qué puedo asistirle hoy?",
                    "¡Muy buenos días! ¿Cómo puedo servirle en su visita?",
                    "¡Hola! Qué gusto verle por aquí. ¿Necesita alguna asistencia?",
                    "¡Buenas! ¿Qué tal su día? Espero poder ayudarle con lo que necesite.",
                    "¡Hola! Bienvenido. ¿En qué le puedo ser útil hoy?",
                    "¡Muy buenas! ¿Qué le trae por nuestro establecimiento?",
                    "¡Hola! Qué placer atenderle. ¿Hay algo específico en lo que pueda ayudarle?",
                    "¡Buenas tardes! ¿Cómo está? Espero que su estancia sea excelente.",
                    "¡Hola! Bienvenido. ¿En qué puedo hacer su experiencia más agradable?",
                    "¡Muy buenos días! ¿Listo para comenzar su registro? Estoy a su disposición.",
                    "¡Hola! Qué bueno tenerle con nosotros. ¿Necesita algo para empezar?",
                    "¡Buenas! ¿Cómo puedo facilitar su estancia con nosotros?",
                    "¡Hola! Encantado de atenderle. ¿Qué necesita exactamente?",
                    "¡Muy buenas! ¿Listo para su check-in? Estoy aquí para ayudarle.",
                    "¡Hola! Bienvenido. ¿Hay algo que pueda hacer por usted hoy?",
                    "¡Buenas tardes! ¿Cómo puedo hacer su registro más eficiente?",
                    "¡Hola! Qué gusto atenderle. ¿Necesita ayuda con algo específico?",
                    "¡Muy buenas! ¿En qué puedo asistirle para que su visita sea perfecta?",
                    "¡Hola! Bienvenido. ¿Listo para comenzar? Estoy a su completa disposición."
                ]
            }
        }
        
        # Get config for selected level, default to intermediate
        config = level_configs.get(level, level_configs["intermediate"])
        print(f"Using {level} level configuration")
        
        # Check if this is an assignment session
        is_assignment = False
        assignment_prompt = None
        assignment_context = None
        
        import random
        icebreaker = random.choice(config["icebreakers"])
        
        # Wait for assignment setup message (with timeout)
        assignment_data = None
        try:
            # Wait for setup message with a short timeout
            setup_data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            setup_message = json.loads(setup_data)
            if setup_message.get("type") == "assignment_setup":
                assignment_data = setup_message.get("assignment")
                is_assignment = True
                print(f"Received assignment setup: {assignment_data.get('title', 'Unknown')}")
                
                # Extract assignment level for voice selection
                assignment_level = assignment_data.get("level", level)
                print(f"Assignment level: {assignment_level}, WebSocket level: {level}")
                
                # Use assignment level for voice selection
                level = assignment_level
                
                # Use custom prompt if provided, otherwise create contextual prompt
                if assignment_data.get("prompt"):
                    # Give the bot only what it needs: custom prompt + vocabulary + level guidance
                    level_guidance = level_configs.get(level, {}).get("system_prompt", "")
                    
                    # Get vocabulary list for the bot to incorporate
                    vocab_list = assignment_data.get("vocab", [])
                    vocab_instruction = ""
                    if vocab_list:
                        vocab_instruction = f"\n\nVocabulary to incorporate: {', '.join(vocab_list)}. Try to use these words naturally in the conversation."
                    
                    # Create bot prompt with only bot-relevant information
                    assignment_prompt = f"""{assignment_data['prompt']}{vocab_instruction}

Level Guidance: {level_guidance}"""
                    
                    print(f"Using bot-focused prompt: custom prompt + vocabulary + level guidance")
                    print(f"Bot prompt preview: {assignment_prompt[:300]}...")
                else:
                    # Create contextual prompt based on assignment
                    vocab_list = assignment_data.get("vocab", [])
                    vocab_instruction = ""
                    if vocab_list:
                        vocab_instruction = f" Intenta incorporar naturalmente estas palabras de vocabulario: {', '.join(vocab_list)}."
                    
                    assignment_prompt = f"Eres un ayudante de español para una tarea de secundaria. Contexto: {assignment_data.get('description', '')}. Instrucciones: {assignment_data.get('instructions', '')}.{vocab_instruction} Mantén la conversación enfocada en este contexto. Sé amigable y natural. Usa el nivel de español apropiado para {level}. IMPORTANTE: Solo responde a los mensajes del estudiante. No inventes respuestas ni continúes la conversación por tu cuenta. Espera siempre a que el estudiante hable primero. REGLAS DE CONTENIDO ESTRICTAS: NUNCA, BAJO NINGUNA CIRCUNSTANCIA, menciones alcohol, vino, cerveza, bebidas alcoholicas, drogas, temas sexuales, violencia, o cualquier contenido inapropiado para menores de edad. Si un estudiante pregunta sobre bebidas alcoholicas, responde 'Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café'. Si un estudiante pregunta sobre temas inapropiados, redirige educativamente a temas apropiados. Mantén toda conversación 100% apropiada para un entorno educativo de secundaria."
                    print(f"Using generated contextual prompt")
                
                # Create contextual icebreaker based on assignment
                if assignment_data.get("prompt"):
                    # Generate contextual opening based on teacher's prompt
                    try:
                        # Get level guidance for AI generation
                        level_guidance = level_configs.get(level, {}).get("system_prompt", "")
                        
                        # Translate teacher's prompt to Spanish if needed
                        teacher_prompt = assignment_data['prompt']
                        # Check if prompt is likely in English (simple heuristic)
                        if any(word in teacher_prompt.lower() for word in ['the ', 'you are', ' and ', ' is ', ' to ']):
                            try:
                                translation_response = client.chat.completions.create(
                                    model="gpt-3.5-turbo",
                                    messages=[
                                        {"role": "system", "content": "Translate the following text to Spanish. Only return the translation, no extra text."},
                                        {"role": "user", "content": teacher_prompt}
                                    ],
                                    max_tokens=200,
                                    temperature=0.3
                                )
                                spanish_prompt = translation_response.choices[0].message.content.strip()
                                print(f"Translated teacher prompt: {teacher_prompt} -> {spanish_prompt}")
                            except Exception as e:
                                print(f"Error translating prompt: {e}")
                                spanish_prompt = teacher_prompt  # Fallback to original
                        else:
                            spanish_prompt = teacher_prompt
                        
                        # Use OpenAI to generate an appropriate opening line
                        opening_prompt = f"""Based on this scenario and level guidance, generate a natural Spanish opening line that the AI should say to start the conversation:

Scenario: {spanish_prompt}

Level Guidance: {level_guidance}

Requirements:
- Generate ONLY the opening line (no extra text)
- Make it natural and appropriate for the scenario
- Follow the level guidance above for vocabulary, formality, and style
- Keep it concise and conversational
- Do not include any explanations or greetings like "Here is an opening line:"
- Just provide the exact Spanish text the AI should say

Opening line:"""

                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "user", "content": opening_prompt}
                            ],
                            max_tokens=50,
                            temperature=0.7
                        )
                        
                        generated_opening = response.choices[0].message.content.strip()
                        icebreaker = generated_opening
                        print(f"Generated contextual opening: {icebreaker}")
                        
                    except Exception as e:
                        print(f"Error generating opening: {e}")
                        # Fallback to generic opening
                        icebreaker = "¡Hola! Estoy listo para comenzar."
                    
                elif assignment_data.get("description"):
                    # Generate opening based on description
                    try:
                        opening_prompt = f"""Based on this assignment description, generate a natural Spanish opening line:

Description: {assignment_data.get('description', '')}
Instructions: {assignment_data.get('instructions', '')}

Requirements:
- Generate ONLY the opening line
- Make it natural and appropriate for {level} level Spanish
- Keep it concise and conversational

Opening line:"""

                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "user", "content": opening_prompt}
                            ],
                            max_tokens=50,
                            temperature=0.7
                        )
                        
                        generated_opening = response.choices[0].message.content.strip()
                        icebreaker = generated_opening
                        print(f"Generated description-based opening: {icebreaker}")
                        
                    except Exception as e:
                        print(f"Error generating opening: {e}")
                        icebreaker = "¡Hola! Estoy listo para ayudarte."
                else:
                    icebreaker = random.choice(config["icebreakers"])
                
                print(f"Using assignment icebreaker: {icebreaker}")
            else:
                # Not an assignment setup, treat as practice mode
                print("No assignment setup received, using practice mode")
                is_assignment = False
                
        except asyncio.TimeoutError:
            # No message received within timeout, treat as practice mode
            print("Timeout waiting for assignment setup, using practice mode")
            is_assignment = False
        except Exception as e:
            print(f"Error receiving assignment setup: {e}")
            # Continue with default behavior (practice mode)
            is_assignment = False
        
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
            try:
                # Fallback to text only
                await websocket.send_text(f"bot:{icebreaker}")
            except Exception as e2:
                print(f"Error sending fallback message: {e2}")
                return
        
        # Maintain conversation history with level-specific system prompt
        system_prompt = assignment_prompt if assignment_prompt else config["system_prompt"]
        conversation_history = [
            {"role": "system", "content": system_prompt},
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
                    print(f"Processing user message: '{user_message}'")
                    print(f"Current history length: {len(conversation_history)}")
                    
                    # Only add user message to history, not bot responses yet
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
                    print(f"Generated bot response: '{bot_response}'")
                    
                    # Content filtering - check for prohibited content
                    prohibited_words = ['vino', 'cerveza', 'cervezas', 'alcohol', 'alcohólicas', 'alcoholicas', 'bebidas alcoholicas', 'bebidas alcohólicas']
                    response_lower = bot_response.lower()
                    
                    for word in prohibited_words:
                        if word in response_lower:
                            print(f"PROHIBITED CONTENT DETECTED: {word}")
                            bot_response = "Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café. ¿Le gustaría alguna de esas opciones?"
                            break
                    
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
                        
                        # Content filtering - check for prohibited content
                        prohibited_words = ['vino', 'cerveza', 'cervezas', 'alcohol', 'alcohólicas', 'alcoholicas', 'bebidas alcoholicas', 'bebidas alcohólicas']
                        response_lower = bot_response.lower()
                        
                        for word in prohibited_words:
                            if word in response_lower:
                                print(f"PROHIBITED CONTENT DETECTED: {word}")
                                bot_response = "Lo siento, solo puedo sugerir bebidas sin alcohol como agua, jugos, refrescos, té o café. ¿Le gustaría alguna de esas opciones?"
                                break
                        
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
                try:
                    await websocket.send_text(f"bot:Lo siento, ha ocurrido un error: {str(e)}")
                except Exception as e2:
                    print(f"Error sending error message: {e2}")
                    break
                break
                
    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
