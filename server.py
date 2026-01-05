import os
import json
import requests
import ssl
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ✅ Official Realtime Calls endpoint (multipart form fields: sdp + session)
OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico")
def favicon():
    # Avoid noisy 404 in console
    return Response(status_code=204)


@app.post("/session")
async def create_session(request: Request):
    """
    Go back to the original SDP approach but fix the multipart encoding
    """
    if not OPENAI_API_KEY:
        return PlainTextResponse("Missing OPENAI_API_KEY env var", status_code=500)

    offer_sdp_bytes = await request.body()
    offer_sdp = offer_sdp_bytes.decode("utf-8", errors="ignore").strip()

    print("===== /session called =====")
    print("Incoming content-type:", request.headers.get("content-type"))
    print("Incoming SDP chars:", len(offer_sdp))
    print("Incoming SDP first line:", offer_sdp.splitlines()[0] if offer_sdp else "(empty)")

    # Session config: Spanish voice bot, server VAD, audio out
    session_obj = {
        "model": "gpt-realtime-mini-2025-12-15",
        "instructions": (
            "Eres un compañero de conversación amigable para practicar español. "
            "Responde SIEMPRE en español neutro. Mantén tus respuestas naturales, "
            "cortas y conversacionales. Haz preguntas de seguimiento para mantener "
            "la conversación fluida. Sé paciente y educativo."
        ),
        "output_modalities": ["audio"],
        "audio": {
            "output": {"voice": "marin"},
            "input": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 800,
                    "create_response": True,
                    "interrupt_response": True
                }
            }
        }
    }

    # Use the correct OpenAI Realtime API endpoint
    OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime"
    
    # Try the exact format from OpenAI documentation
    files = {
        'sdp': (None, offer_sdp, 'application/sdp'),
        'session': (None, json.dumps(session_obj), 'application/json')
    }
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    
    print("Sending to OpenAI Realtime API with exact format")
    print("SDP length:", len(offer_sdp))
    print("Session JSON length:", len(json.dumps(session_obj)))
    print("SDP preview:", offer_sdp[:100] + "..." if len(offer_sdp) > 100 else offer_sdp)

    try:
        r = requests.post(
            OPENAI_REALTIME_URL,
            headers=headers,
            files=files,
            timeout=60,
        )
    except Exception as e:
        print("OpenAI call failed:", repr(e))
        return PlainTextResponse(f"OpenAI call failed: {e}", status_code=502)

    print("OpenAI status:", r.status_code)
    print("OpenAI content-type:", r.headers.get("content-type"))
    print("OpenAI body preview:", (r.text[:300] + ("..." if len(r.text) > 300 else "")))

    if r.status_code != 201:
        return PlainTextResponse(f"Session init failed: {r.status_code}\n{r.text}", status_code=400)

    # The response body is the SDP answer (text)
    answer_sdp = r.text
    return PlainTextResponse(answer_sdp, status_code=200)