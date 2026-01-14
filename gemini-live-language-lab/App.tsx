import React, { useState, useEffect, useRef, useCallback } from 'react';
import { GoogleGenAI, LiveServerMessage, Modality, Blob } from '@google/genai';
import { VoiceName, TranscriptionEntry, ConnectionStatus, CEFRLevel, ScenarioPARTS, AppStage, Language } from './types';
import { LANGUAGES, getLanguageByCode } from './languages';
import { encode, decode, decodeAudioData } from './utils/audioUtils';
import { AudioVisualizer } from './components/AudioVisualizer';

const MODEL_NAME = 'gemini-2.5-flash-native-audio-preview-12-2025';

const PERSONA = {
  name: "Elli",
  role: "Language Coach",
  images: {
    photorealistic: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&q=80&w=1200&h=1600"
  }
};

const App: React.FC = () => {
  // --- Stage & Settings ---
  const [stage, setStage] = useState<AppStage>('setup');
  const [level, setLevel] = useState<CEFRLevel>('A2');
  const [voice, setVoice] = useState<VoiceName>(VoiceName.ZEPHYR);
  const [language, setLanguage] = useState<Language>(Language.SPANISH_SPAIN);
  const [scaffoldingEnabled, setScaffoldingEnabled] = useState(false);
  const [scenario, setScenario] = useState<ScenarioPARTS>({
    persona: "",
    act: "Ordering breakfast and asking for directions",
    recipient: "A hungry traveler (the student)",
    theme: "",
    structure: "Start by greeting the student warmly. If they make a mistake, gently correct them after their full sentence."
  });

  // --- Session State ---
  const [status, setStatus] = useState<ConnectionStatus>({ isConnected: false, isConnecting: false, error: null });
  const [history, setHistory] = useState<TranscriptionEntry[]>([]);
  const [currentInputText, setCurrentInputText] = useState('');
  const [currentOutputText, setCurrentOutputText] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const [isGeminiSpeaking, setIsGeminiSpeaking] = useState(false);

  // --- Audio Refs ---
  const sessionRef = useRef<any>(null);
  const inputAudioCtxRef = useRef<AudioContext | null>(null);
  const outputAudioCtxRef = useRef<AudioContext | null>(null);
  const nextStartTimeRef = useRef(0);
  const audioSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const inputAnalyzerRef = useRef<AnalyserNode | null>(null);
  const outputAnalyzerRef = useRef<AnalyserNode | null>(null);
  const historyEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, currentInputText, currentOutputText]);

  const createAudioContexts = () => {
    if (!inputAudioCtxRef.current) {
      inputAudioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      inputAnalyzerRef.current = inputAudioCtxRef.current.createAnalyser();
      inputAnalyzerRef.current.fftSize = 256;
    }
    if (!outputAudioCtxRef.current) {
      outputAudioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 });
      outputAnalyzerRef.current = outputAudioCtxRef.current.createAnalyser();
      outputAnalyzerRef.current.fftSize = 256;
    }
  };

  const stopAllAudio = () => {
    audioSourcesRef.current.forEach(source => source.stop());
    audioSourcesRef.current.clear();
    nextStartTimeRef.current = 0;
    setIsGeminiSpeaking(false);
  };

  const disconnect = useCallback(() => {
    if (sessionRef.current) {
      sessionRef.current.close();
      sessionRef.current = null;
    }
    stopAllAudio();
    setStatus({ isConnected: false, isConnecting: false, error: null });
    setStage('summary');
  }, []);

  const startSession = async () => {
    setStage('calling');
    setStatus({ isConnected: false, isConnecting: true, error: null });
    // Clear all transcription state for a fresh session
    setHistory([]);
    setCurrentInputText('');
    setCurrentOutputText('');

    try {
      createAudioContexts();
      const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const systemInstruction = `
        You are Elli, a professional Language Coach.
        PEDAGOGICAL LEVEL: ${level} (CEFR). Speak at a speed and vocabulary complexity appropriate for this level.
        LANGUAGE: Respond in ${getLanguageByCode(language)?.name || 'Spanish'}. Use authentic, natural ${getLanguageByCode(language)?.nativeName || 'Español'} expressions and cultural context.
        
        SESSION SCENARIO (PARTS):
        - PERSONA: ${scenario.persona}
        - ACTING AS: ${scenario.act}
        - RECIPIENT: ${scenario.recipient}
        - THEME: ${scenario.theme}
        - STRUCTURE: ${scenario.structure}

        GENERAL RULES:
        1. Keep responses concise (under 30 words) to mimic a real conversation.
        2. ${scaffoldingEnabled ? 'Correct the user\'s grammar GENTLY but only after they finish their thought.' : 'Do NOT correct the user\'s grammar - focus on natural conversation flow.'}
        3. Use your voice naturally, expressing warmth and encouragement.
      `;
      
      const sessionPromise = ai.live.connect({
        model: MODEL_NAME,
        callbacks: {
          onopen: () => {
            setStatus({ isConnected: true, isConnecting: false, error: null });
            setStage('active');
            const source = inputAudioCtxRef.current!.createMediaStreamSource(micStream);
            const scriptProcessor = inputAudioCtxRef.current!.createScriptProcessor(4096, 1, 1);
            
            scriptProcessor.onaudioprocess = (e) => {
              if (isMuted) return;
              const inputData = e.inputBuffer.getChannelData(0);
              const l = inputData.length;
              const int16 = new Int16Array(l);
              for (let i = 0; i < l; i++) { int16[i] = inputData[i] * 32768; }
              const pcmBlob: Blob = { data: encode(new Uint8Array(int16.buffer)), mimeType: 'audio/pcm;rate=16000' };
              sessionPromise.then((session) => { session.sendRealtimeInput({ media: pcmBlob }); });
            };

            source.connect(inputAnalyzerRef.current!);
            inputAnalyzerRef.current!.connect(scriptProcessor);
            scriptProcessor.connect(inputAudioCtxRef.current!.destination);
          },
          onmessage: async (message: LiveServerMessage) => {
            if (message.serverContent?.outputTranscription) {
              setCurrentOutputText(prev => prev + message.serverContent!.outputTranscription!.text);
            } else if (message.serverContent?.inputTranscription) {
              setCurrentInputText(prev => prev + message.serverContent!.inputTranscription!.text);
            }

            if (message.serverContent?.turnComplete) {
              // Use functional setState to get the most recent values
              setCurrentInputText(currentInput => {
                setCurrentOutputText(currentOutput => {
                  setHistory(prev => [
                    ...prev,
                    { role: 'user', text: currentInput, timestamp: Date.now() },
                    { role: 'model', text: currentOutput, timestamp: Date.now() }
                  ]);
                  return '';
                });
                return '';
              });
            }

            const audioData = message.serverContent?.modelTurn?.parts[0]?.inlineData?.data;
            if (audioData) {
              setIsGeminiSpeaking(true);
              const audioCtx = outputAudioCtxRef.current!;
              nextStartTimeRef.current = Math.max(nextStartTimeRef.current, audioCtx.currentTime);
              const buffer = await decodeAudioData(decode(audioData), audioCtx, 24000, 1);
              const source = audioCtx.createBufferSource();
              source.buffer = buffer;
              source.connect(outputAnalyzerRef.current!);
              outputAnalyzerRef.current!.connect(audioCtx.destination);
              source.addEventListener('ended', () => {
                audioSourcesRef.current.delete(source);
                if (audioSourcesRef.current.size === 0) setIsGeminiSpeaking(false);
              });
              source.start(nextStartTimeRef.current);
              nextStartTimeRef.current += buffer.duration;
              audioSourcesRef.current.add(source);
            }

            if (message.serverContent?.interrupted) stopAllAudio();
          },
          onerror: (e) => {
            console.error("Live Error", e);
            setStatus(s => ({ ...s, error: "Connection lost. Please try again." }));
          },
          onclose: () => disconnect()
        },
        config: {
          responseModalities: [Modality.AUDIO],
          systemInstruction,
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: voice } } },
          inputAudioTranscription: {},
          outputAudioTranscription: {},
        }
      });

      sessionRef.current = await sessionPromise;
    } catch (err: any) {
      console.error("Connection failed", err);
      setStatus({ isConnected: false, isConnecting: false, error: err.message || "Failed to connect." });
      setStage('setup');
    }
  };

  const toggleMute = () => setIsMuted(!isMuted);

  const renderSetup = () => (
    <div className="flex-1 flex flex-col items-center justify-center p-12 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="w-full max-w-4xl bg-white border border-slate-200 rounded-[48px] p-12 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#0ea5e9] to-transparent opacity-50" />
        
        <div className="flex justify-between items-start mb-12">
          <div>
            <h1 className="text-5xl font-black tracking-tight mb-2 text-slate-900">VocaFlow <span className="text-[#0ea5e9]">Lab</span></h1>
            <p className="text-xl text-slate-600 font-medium">Advanced Immersive Learning</p>
          </div>
          <div className="flex gap-2 bg-slate-100 p-1.5 rounded-2xl border border-slate-200">
            {['A1','A2','B1','B2','C1','C2'].map(l => (
              <button 
                key={l}
                onClick={() => setLevel(l as CEFRLevel)}
                className={`w-11 h-11 rounded-xl text-xs font-black transition-all ${level === l ? 'bg-[#0ea5e9] text-white shadow-[0_0_20px_rgba(14,165,233,0.3)]' : 'text-slate-500 hover:text-slate-700'}`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-10 mb-12">
          <div className="space-y-6">
            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-[#0ea5e9]/80">Instructional Framework</h3>
            <div className="space-y-5">
              <div className="group">
                <label className="block text-[10px] uppercase font-black text-slate-500 mb-2 tracking-widest group-focus-within:text-[#0ea5e9] transition-colors">Target Persona</label>
                <input value={scenario.persona} onChange={e => setScenario({...scenario, persona: e.target.value})} className="w-full bg-white border border-slate-200 rounded-2xl px-5 py-4 text-sm text-slate-900 focus:outline-none focus:border-[#0ea5e9]/50 focus:bg-slate-50 transition-all" placeholder="e.g. A store clerk..." />
              </div>
              <div className="group">
                <label className="block text-[10px] uppercase font-black text-slate-500 mb-2 tracking-widest group-focus-within:text-[#0ea5e9] transition-colors">Learning Theme</label>
                <input value={scenario.theme} onChange={e => setScenario({...scenario, theme: e.target.value})} className="w-full bg-white border border-slate-200 rounded-2xl px-5 py-4 text-sm text-slate-900 focus:outline-none focus:border-[#0ea5e9]/50 focus:bg-slate-50 transition-all" placeholder="e.g. Daily routines..." />
              </div>
            </div>
          </div>
          
          <div className="space-y-6">
             <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Studio Parameters</h3>
             <div className="bg-slate-50 rounded-3xl p-8 space-y-8 border border-slate-200">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-slate-600">Voice Engine</span>
                  <div className="custom-dropdown" style={{position: 'relative', width: '200px'}}>
                    <div className="dropdown-trigger" style={{width: '100%', padding: '8px 16px', border: '2px solid #e5e7eb', borderRadius: '8px', background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px', fontWeight: '600', color: '#667eea', transition: 'all 0.3s ease', boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)'}} onClick={() => document.getElementById('voiceOptions')!.style.display = document.getElementById('voiceOptions')!.style.display === 'none' ? 'block' : 'none'}>
                      <span style={{textAlign: 'left', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{voice}</span>
                      <div className="dropdown-arrow" style={{width: '0', height: '0', borderLeft: '4px solid transparent', borderRight: '4px solid transparent', borderTop: '4px solid #667eea', transition: 'transform 0.3s ease', flexShrink: 0, marginLeft: '12px'}}></div>
                    </div>
                    <div className="dropdown-options" id="voiceOptions" style={{position: 'absolute', top: 'calc(100% + 4px)', left: '0', right: '0', background: 'white', border: '2px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.08)', zIndex: '1000', maxHeight: '250px', overflowY: 'auto', display: 'none'}}>
                      {Object.values(VoiceName).map(v => (
                        <div key={v} className="dropdown-option" style={{padding: '8px 16px', cursor: 'pointer', borderBottom: '1px solid #f3f4f6', transition: 'all 0.2s ease', fontSize: '13px', color: '#374151', textAlign: 'left', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}} onClick={() => {setVoice(v); document.getElementById('voiceOptions')!.style.display = 'none';}} onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'} onMouseLeave={(e) => e.currentTarget.style.background = 'white'}>
                          {v}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-slate-600">Language</span>
                  <div className="custom-dropdown" style={{position: 'relative', width: '200px'}}>
                    <div className="dropdown-trigger" style={{width: '100%', padding: '8px 16px', border: '2px solid #e5e7eb', borderRadius: '8px', background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px', fontWeight: '600', color: '#667eea', transition: 'all 0.3s ease', boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)'}} onClick={() => document.getElementById('languageOptions')!.style.display = document.getElementById('languageOptions')!.style.display === 'none' ? 'block' : 'none'}>
                      <span style={{textAlign: 'left', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{getLanguageByCode(language)?.flag} {getLanguageByCode(language)?.name}</span>
                      <div className="dropdown-arrow" style={{width: '0', height: '0', borderLeft: '4px solid transparent', borderRight: '4px solid transparent', borderTop: '4px solid #667eea', transition: 'transform 0.3s ease', flexShrink: 0, marginLeft: '12px'}}></div>
                    </div>
                    <div className="dropdown-options" id="languageOptions" style={{position: 'absolute', top: 'calc(100% + 4px)', left: '0', right: '0', background: 'white', border: '2px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.08)', zIndex: '1000', maxHeight: '250px', overflowY: 'auto', display: 'none'}}>
                      {LANGUAGES.map(lang => (
                        <div key={lang.code} className="dropdown-option" style={{padding: '8px 16px', cursor: 'pointer', borderBottom: '1px solid #f3f4f6', transition: 'all 0.2s ease', fontSize: '13px', color: '#374151', textAlign: 'left', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}} onClick={() => {setLanguage(lang.code); document.getElementById('languageOptions')!.style.display = 'none';}} onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'} onMouseLeave={(e) => e.currentTarget.style.background = 'white'}>
                          {lang.flag} {lang.name}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-slate-600">Grammar Scaffolding</span>
                  <button
                    onClick={() => setScaffoldingEnabled(!scaffoldingEnabled)}
                    className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                      scaffoldingEnabled ? 'bg-[#10b981]' : 'bg-slate-300'
                    }`}
                  >
                    <span
                      className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                        scaffoldingEnabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
                <div className="pt-4 border-t border-slate-200 text-[10px] text-slate-500 font-bold leading-relaxed">
                  Real-time pedagogical feedback enabled. Mic access required for live interaction.
                </div>
             </div>
          </div>
        </div>

        <button 
          onClick={startSession}
          className="w-full py-7 rounded-[32px] bg-[#10b981] hover:bg-[#059669] text-white text-lg font-black tracking-widest transition-all shadow-[0_25px_50px_rgba(16,185,129,0.25)] active:scale-[0.98] flex items-center justify-center gap-4"
        >
          <div className="w-2 h-2 rounded-full bg-white animate-ping" />
          ENTER IMMERSIVE STUDIO
        </button>
      </div>
    </div>
  );

  const renderActive = () => (
    <div className="flex-1 relative flex flex-col z-10 p-6 lg:p-8 animate-in fade-in duration-1000">
      
      {/* Immersive View Layer */}
      <div className="flex-1 relative rounded-[64px] overflow-hidden shadow-[0_50px_100px_rgba(0,0,0,0.1)] border border-slate-200 bg-white">
        
        {/* Avatar Layer */}
        <div className={`absolute inset-0 transition-all duration-[10000ms] ${status.isConnected ? 'saturate-110' : 'blur-xl opacity-20'}`}>
          <div className="absolute inset-0 bg-gradient-to-br from-[#0ea5e9]/10 via-[#10b981]/10 to-[#ea580c]/5" />
          {/* Professional Cinematographic Overlays */}
          <div className="absolute inset-0 bg-gradient-to-t from-white via-transparent to-slate-50/30" />
          <div className="absolute inset-0 bg-[#0ea5e9]/5 mix-blend-overlay" />
        </div>

        {/* Audio Reactive Glow */}
        <div className={`absolute inset-0 transition-opacity duration-1000 pointer-events-none ${isGeminiSpeaking ? 'opacity-100' : 'opacity-0'}`}>
           <div className="absolute bottom-0 left-0 right-0 h-[60%] bg-[#10b981]/10 blur-[120px]" />
        </div>

        {/* Waveform Visualization */}
        {isGeminiSpeaking && outputAnalyzerRef.current && (
          <div className="absolute inset-0 pointer-events-none">
            <AudioVisualizer analyzer={outputAnalyzerRef.current} color="#0ea5e9" />
          </div>
        )}

        {/* Floating Context Hub */}
        <div className="absolute top-12 right-12 flex flex-col items-end gap-4 animate-in slide-in-from-right-8 duration-1000">
           <div className="p-7 bg-white/90 backdrop-blur-3xl border border-slate-200 rounded-[36px] w-80 shadow-2xl">
              <h4 className="text-[9px] font-black uppercase tracking-[0.3em] text-[#0ea5e9] mb-3">Pedagogical Framework</h4>
              <p className="text-sm font-bold text-slate-800 leading-relaxed mb-5">{scenario.act}</p>
              <div className="flex items-center gap-3 pt-4 border-t border-slate-200">
                <span className="px-3 py-1 bg-[#10b981]/10 text-[#10b981] text-[10px] font-black rounded-lg border border-[#10b981]/20">{level}</span>
                <span className="px-3 py-1 bg-[#0ea5e9]/10 text-[#0ea5e9] text-[10px] font-black rounded-lg border border-[#0ea5e9]/20">
                  {getLanguageByCode(language)?.flag} {getLanguageByCode(language)?.nativeName}
                </span>
                <span className="text-[10px] text-slate-500 font-black uppercase tracking-widest">{scenario.theme}</span>
              </div>
           </div>
        </div>

        {/* Status Hub */}
        <div className="absolute top-12 left-12">
           <div className="px-6 py-3 bg-white/80 backdrop-blur-2xl border border-slate-200 rounded-full flex items-center gap-3">
             <div className={`w-2 h-2 rounded-full ${status.isConnected ? 'bg-[#10b981] shadow-[0_0_12px_rgba(16,185,129,0.8)] animate-pulse' : 'bg-slate-300'}`} />
             <span className="text-[10px] font-black tracking-[0.3em] text-slate-700 uppercase">
               {status.isConnected ? 'Live Interaction' : 'Initializing...'}
             </span>
           </div>
        </div>

        {/* Elli Profile Info */}
        <div className="absolute bottom-20 left-16 text-slate-800 z-10 pointer-events-none">
           <h2 className="text-7xl font-black tracking-tighter mb-2 drop-shadow-[0_10px_10px_rgba(255,255,255,0.8)]">{PERSONA.name}</h2>
           <div className="flex items-center gap-5">
              <p className="text-2xl text-slate-600 font-medium tracking-tight">AI {PERSONA.role}</p>
              <div className="w-1.5 h-1.5 rounded-full bg-[#0ea5e9]/40" />
              <span className="text-xs text-slate-400 uppercase tracking-[0.4em] font-black">Native Engine</span>
           </div>
        </div>

      </div>

      {/* Modern Integrated Control Bar */}
      <div className="flex items-center justify-between gap-8 px-12 py-8 mt-8 rounded-[40px] bg-white border border-slate-200 shadow-2xl">
        <div className="flex items-center gap-6">
           <button 
             onClick={toggleMute} 
             className={`p-5 rounded-2xl transition-all flex items-center gap-3 ${isMuted ? 'bg-rose-100 text-rose-600 border border-rose-200' : 'bg-emerald-100 text-emerald-600 border border-emerald-200 shadow-[0_0_12px_rgba(16,185,129,0.3)]'}`}
           >
             <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
               {isMuted ? (
                 <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z M18.364 5.636l-12.728 12.728" />
               ) : (
                 <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
               )}
             </svg>
             <span className="text-[10px] font-black uppercase tracking-widest">{isMuted ? 'Mic Off' : 'Mic Active'}</span>
           </button>
        </div>

        <button 
          onClick={disconnect} 
          className="px-10 py-5 rounded-2xl bg-red-500 hover:bg-red-600 text-white font-black text-xs uppercase tracking-[0.3em] transition-all shadow-lg hover:shadow-xl border border-red-600"
        >
          End Session
        </button>
      </div>
    </div>
  );

  const renderSummary = () => (
    <div className="flex-1 flex flex-col items-center justify-center p-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
       <div className="w-full max-w-4xl bg-white border border-slate-200 rounded-[56px] p-16 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-16 opacity-5 pointer-events-none grayscale">
             <svg className="w-64 h-64" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="#0ea5e9" /></svg>
          </div>
          
          <div className="mb-16">
            <h2 className="text-5xl font-black mb-4 text-slate-900">Insight Report</h2>
            <p className="text-slate-500 font-black uppercase tracking-[0.4em] text-xs">Laboratory Performance Metrics • CEFR {level}</p>
          </div>
          
          <div className="grid grid-cols-2 gap-16 mb-16">
             <div className="space-y-8">
                <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-[#0ea5e9]">Interaction Data</h4>
                <div className="space-y-4">
                   <div className="flex justify-between items-center py-5 border-b border-slate-200">
                      <span className="text-slate-500 text-sm font-bold tracking-tight">Exchanges</span>
                      <span className="text-slate-900 font-black text-xl">{history.length / 2}</span>
                   </div>
                   <div className="flex justify-between items-center py-5 border-b border-slate-200">
                      <span className="text-slate-500 text-sm font-bold tracking-tight">Scaffolding Applied</span>
                      <span className="text-[#10b981] font-black text-xs uppercase tracking-widest">Active</span>
                   </div>
                </div>
             </div>
             <div className="space-y-8">
                <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">Analytical Observations</h4>
                <div className="bg-slate-50 p-8 rounded-[36px] border border-slate-200">
                  <p className="text-sm text-slate-700 leading-[1.8] font-medium italic">
                    "Session target focused on <span className="text-slate-900 font-black">{scenario.theme}</span>. Pronunciation was clear; recommendation to expand use of contextual idiomatic expressions in future {level} tasks."
                  </p>
                </div>
             </div>
          </div>

          <div className="flex gap-4">
            <button onClick={() => window.location.href = '/'} className="flex-1 py-6 rounded-3xl bg-[#0ea5e9] hover:bg-[#0284c7] text-white font-black text-sm uppercase tracking-[0.4em] transition-all shadow-2xl active:scale-[0.98] flex items-center justify-center gap-3">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Back to VocaFlow Home
            </button>
            <button onClick={() => { setStage('setup'); setHistory([]); setCurrentInputText(''); setCurrentOutputText(''); }} className="flex-1 py-6 rounded-3xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-black text-sm uppercase tracking-[0.4em] transition-all border-2 border-slate-200 active:scale-[0.98]">
               Start New Session
            </button>
          </div>
       </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-[#fefefe] font-sans text-slate-900 overflow-hidden select-none">
      {/* Immersive Backdrop Decor */}
      <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 right-0 w-[1000px] h-[1000px] bg-[#0ea5e9]/5 rounded-full blur-[250px]" />
        <div className="absolute bottom-0 left-0 w-[1000px] h-[1000px] bg-[#10b981]/5 rounded-full blur-[250px]" />
      </div>

      {stage === 'setup' && renderSetup()}
      {(stage === 'active' || stage === 'calling') && renderActive()}
      {stage === 'summary' && renderSummary()}

      {/* Transcription Sidebar */}
      <aside className={`h-full bg-white/95 backdrop-blur-3xl border-l border-slate-200 flex flex-col z-30 transition-all duration-1000 ${stage === 'active' ? 'w-[440px]' : 'w-[520px]'}`}>
        <div className="p-12 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-[10px] font-black uppercase tracking-[0.5em] text-slate-500 mb-2">Metadata Stream</h3>
            <p className="text-base font-black text-slate-700">Transcription Log</p>
          </div>
          <div className="flex gap-1.5">
             <div className="w-1.5 h-1.5 rounded-full bg-[#0ea5e9]/40" />
             <div className="w-1.5 h-1.5 rounded-full bg-[#0ea5e9]/20" />
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-12 space-y-12 custom-scrollbar">
          {history.length === 0 && !currentInputText && !currentOutputText && (
            <div className="h-full flex flex-col items-center justify-center text-center opacity-10 px-10">
              <div className="w-20 h-20 mb-8 border border-slate-300 rounded-full flex items-center justify-center">
                <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
              </div>
              <p className="text-[11px] font-black uppercase tracking-[0.4em] text-slate-400">Awaiting Input Stream</p>
            </div>
          )}

          {history.map((entry, i) => (
            <div key={i} className={`flex flex-col ${entry.role === 'user' ? 'items-end' : 'items-start'} animate-in slide-in-from-bottom-4 duration-500`}>
              <div className={`max-w-[95%] px-7 py-6 rounded-[32px] text-[14px] leading-[1.7] transition-all font-medium ${entry.role === 'user' ? 'bg-[#0ea5e9]/10 text-[#0ea5e9] border border-[#0ea5e9]/20 rounded-tr-none' : 'bg-slate-50 text-slate-700 border border-slate-200 rounded-tl-none'}`}>
                <span className="block text-[9px] font-black uppercase tracking-[0.3em] opacity-30 mb-3">{entry.role === 'user' ? 'Student' : 'Coach'}</span>
                {entry.text}
              </div>
            </div>
          ))}

          {(currentInputText || currentOutputText) && (
             <div className="space-y-8 pt-8 border-t border-white/5">
                {currentInputText && (
                  <div className="flex flex-col items-end">
                    <div className="max-w-[95%] px-7 py-6 rounded-[32px] text-[14px] bg-[#0ea5e9]/5 text-[#0ea5e9] border border-[#0ea5e9]/10 rounded-tr-none animate-pulse">
                      <span className="block text-[9px] font-black uppercase tracking-[0.3em] opacity-30 mb-2">Analyzing...</span>
                      {currentInputText}
                    </div>
                  </div>
                )}
                {currentOutputText && (
                  <div className="flex flex-col items-start">
                    <div className="max-w-[95%] px-7 py-6 rounded-[32px] text-[14px] bg-slate-50 text-slate-500 border border-slate-200 rounded-tl-none animate-pulse">
                      <span className="block text-[9px] font-black uppercase tracking-[0.3em] opacity-30 mb-2">Generating...</span>
                      {currentOutputText}
                    </div>
                  </div>
                )}
             </div>
          )}
          <div ref={historyEndRef} />
        </div>

        <div className="p-12 bg-slate-50 border-t border-slate-200">
           <div className="flex justify-center items-center text-[10px] text-slate-400 font-black uppercase tracking-[0.5em]">
             <span>VocaFlow Studio Platform</span>
           </div>
        </div>
      </aside>
    </div>
  );
};

export default App;
