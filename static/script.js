// Spanish Voice Bot (WebRTC + OpenAI Realtime)
// One click Start -> connects, bot speaks first (ice breaker), then server VAD handles turns.

const toggleBtn = document.getElementById("toggleBtn");
const stopBtn   = document.getElementById("stopBtn");
const statusEl  = document.getElementById("status");
const logEl     = document.getElementById("log");
const remoteAudio = document.getElementById("remoteAudio");
const dot = document.getElementById("dot");

let pc = null;
let dc = null;
let localStream = null;
let started = false;

function ts() {
  const d = new Date();
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function log(msg) {
  const line = `[${ts()}] ${msg}\n`;
  logEl.textContent += line;
  logEl.scrollTop = logEl.scrollHeight;
  console.log(line.trim());
}
function setStatus(s, color = null) {
  statusEl.textContent = `Status: ${s}`;
  if (color === "green") dot.style.background = "rgba(34,197,94,0.9)";
  else if (color === "red") dot.style.background = "rgba(239,68,68,0.9)";
  else if (color === "purple") dot.style.background = "rgba(124,92,255,0.9)";
  else dot.style.background = "rgba(255,255,255,0.35)";
}

async function unlockAudio() {
  // Helps satisfy autoplay policies - simplified version
  log("🔓 Starting audio unlock...");
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') {
      await ctx.resume();
      log("🔓 AudioContext resumed");
    }
    ctx.close();
    log("🔓 Audio unlock complete");
  } catch (e) {
    log("⚠️ AudioContext unlock failed (may still work): " + e);
  }
}

function randomIcebreaker() {
  const qs = [
    "¡Hola! ¿Cómo estás hoy?",
    "¿Qué tal tu día hasta ahora?",
    "¿Qué te gustaría hacer hoy?",
    "¿Has practicado español antes?",
    "¿Qué tiempo hace donde estás?",
    "¿Cuál es tu comida favorita?",
    "¿Qué te gusta hacer en tu tiempo libre?",
    "¿Cómo te llamas?",
    "¿De dónde eres?",
    "¿Qué planes tienes para el fin de semana?"
  ];
  return qs[Math.floor(Math.random() * qs.length)];
}

function sendEvent(obj) {
  if (!dc || dc.readyState !== "open") {
    log("⚠️ DataChannel not open; cannot send event.");
    return;
  }
  dc.send(JSON.stringify(obj));
}

async function start() {
  if (started) return;
  started = true;

  toggleBtn.disabled = true;
  stopBtn.disabled = false;
  toggleBtn.textContent = "Iniciando…";
  setStatus("requesting microphone…", "purple");

  log("🚀 start()");
  await unlockAudio();
  log("🚀 Audio unlock finished - moving to microphone...");

  // 1) Mic
  log("🎤 getUserMedia() - requesting microphone access...");
  setStatus("requesting microphone…", "purple");
  try {
    log("🎤 Calling navigator.mediaDevices.getUserMedia...");
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const track = localStream.getAudioTracks()[0];
    log(`🎤 Mic OK: ${track.label || "audio track"}`);
    setStatus("microphone connected", "green");
  } catch (e) {
    log("❌ Mic access failed: " + e.message);
    log("❌ Full error: " + JSON.stringify(e, null, 2));
    setStatus("mic access denied: " + e.message, "red");
    throw e;
  }

  // 2) PeerConnection
  pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
  });

  pc.oniceconnectionstatechange = () => log(`ICE state: ${pc.iceConnectionState}`);
  pc.onconnectionstatechange = () => log(`PC state: ${pc.connectionState}`);

  pc.ontrack = async (e) => {
    log(`🎧 ontrack fired (kind=${e.track.kind})`);
    remoteAudio.srcObject = e.streams[0];
    try {
      await remoteAudio.play();
      log("🔊 remoteAudio.play() OK");
    } catch (err) {
      log("⚠️ remoteAudio.play() failed: " + err);
    }
  };

  // Add mic track
  localStream.getTracks().forEach(t => pc.addTrack(t, localStream));

  // DataChannel for Realtime events
  dc = pc.createDataChannel("oai-events");
  dc.onopen = () => {
    log("📡 DataChannel open");
    setStatus("connected — bot starting…", "green");

    // 3) Bot speaks first (ice breaker) in AUDIO
    const q = randomIcebreaker();
    log(`🧊 Ice breaker: ${q}`);

    sendEvent({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: q }]
      }
    });

    sendEvent({
      type: "response.create",
      response: {
        output_modalities: ["audio"],
        instructions: "Responde en español neutro con una respuesta natural y amistosa a la pregunta del usuario. Mantén tu respuesta corta y conversacional."
      }
    });

    // After this, server VAD will auto-create responses to speech
    setStatus("your turn — speak", "green");
    toggleBtn.textContent = "Iniciar";
    toggleBtn.disabled = false;
  };

  dc.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "response.created") {
        log("⬅️ response.created - Bot está pensando...");
        setStatus("bot speaking...", "purple");
      }
      if (msg.type === "response.done") {
        log("⬅️ response.done - Bot terminó de hablar");
        setStatus("your turn — speak", "green");
      }
      if (msg.type === "input_audio_buffer.speech_started") {
        log("⬅️ input_audio_buffer.speech_started - Te escucho...");
        setStatus("listening…", "purple");
      }
      if (msg.type === "input_audio_buffer.speech_stopped") {
        log("⬅️ input_audio_buffer.speech_stopped - Procesando tu respuesta...");
        setStatus("thinking…", "purple");
      }
      if (msg.type === "error") {
        log("⬅️ error: " + JSON.stringify(msg.error));
        setStatus("error (see logs)", "red");
      }
    } catch {
      // ignore non-JSON
    }
  };

  // 2) PeerConnection
  pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
  });

  pc.oniceconnectionstatechange = () => log(`ICE state: ${pc.iceConnectionState}`);
  pc.onconnectionstatechange = () => log(`PC state: ${pc.connectionState}`);

  pc.ontrack = async (e) => {
    log(`🎧 ontrack fired (kind=${e.track.kind})`);
    remoteAudio.srcObject = e.streams[0];
    try {
      await remoteAudio.play();
      log("🔊 remoteAudio.play() OK");
    } catch (err) {
      log("⚠️ remoteAudio.play() failed: " + err);
    }
  };

  // Add mic track
  localStream.getTracks().forEach(t => pc.addTrack(t, localStream));

  // 4) Create SDP offer and send to your server
  setStatus("creating offer…", "purple");
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  setStatus("creating session…", "purple");
  log("➡️ POST /session (sending SDP offer)");

  const res = await fetch("/session", {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: offer.sdp
  });

  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Session init failed: ${res.status} ${t}`);
  }

  const answerSdp = await res.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
  log("✅ setRemoteDescription(answer) done");

  setStatus("connected — waiting for bot…", "green");

  // DataChannel for Realtime events
  dc = pc.createDataChannel("oai-events");
  dc.onopen = () => {
    log("📡 DataChannel open");
    setStatus("connected — bot starting…", "green");

    // Bot speaks first (ice breaker) in AUDIO
    const q = randomIcebreaker();
    log(`🧊 Ice breaker: ${q}`);

    sendEvent({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: q }]
      }
    });

    sendEvent({
      type: "response.create",
      response: {
        output_modalities: ["audio"],
        instructions: "Responde en español neutro con una respuesta natural y amistosa a la pregunta del usuario. Mantén tu respuesta corta y conversacional."
      }
    });

    // After this, server VAD will auto-create responses to speech
    setStatus("your turn — speak", "green");
    toggleBtn.textContent = "Iniciar";
    toggleBtn.disabled = false;
  };
}

async function stop() {
  if (!started) return;
  started = false;

  log("🛑 stop()");
  setStatus("idle", null);

  stopBtn.disabled = true;
  toggleBtn.disabled = false;
  toggleBtn.textContent = "Iniciar";

  try { if (dc && dc.readyState === "open") dc.close(); } catch {}
  try { if (pc) pc.close(); } catch {}

  dc = null;
  pc = null;

  try {
    if (localStream) localStream.getTracks().forEach(t => t.stop());
  } catch {}
  localStream = null;

  try {
    remoteAudio.pause();
    remoteAudio.srcObject = null;
  } catch {}
}

toggleBtn.addEventListener("click", async () => {
  // Start/stop toggle behavior (single button feel)
  if (!started) {
    try {
      await start();
    } catch (e) {
      log("❌ start error: " + e.message);
      setStatus("error: " + e.message, "red");
      await stop();
    }
  } else {
    await stop();
  }
});

stopBtn.addEventListener("click", stop);

log("✅ script.js loaded");
setStatus("idle");