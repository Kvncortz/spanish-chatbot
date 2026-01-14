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
    act: "Engaging in conversation based on the persona and theme",
    recipient: "A language learning student",
    theme: "",
    structure: "Start by greeting the student warmly. If they make a mistake, gently correct them after their full sentence."
  });

  // --- Session State ---
  const [status, setStatus] = useState<ConnectionStatus>({ isConnected: false, isConnecting: false, error: null });
  const [history, setHistory] = useState<TranscriptionEntry[]>([]);
  const [currentInputText, setCurrentInputText] = useState('');
  const [currentOutputText, setCurrentOutputText] = useState('');
  const currentInputRef = useRef('');
  const currentOutputRef = useRef('');
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
    // Validate required fields
    const personaValid = scenario.persona.trim().length > 0;
    const themeValid = scenario.theme.trim().length > 0;
    
    if (!personaValid || !themeValid) {
      setStatus({ isConnected: false, isConnecting: false, error: "⚠️ Please fill in both Target Persona and Learning Theme fields before starting." });
      return;
    }

    setStage('calling');
    setStatus({ isConnected: false, isConnecting: true, error: null });

    try {
      createAudioContexts();
      const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const systemInstruction = `
        You are Elli, a professional Language Coach.
        PEDAGOGICAL LEVEL: ${level} (CEFR). Speak at a speed and vocabulary complexity appropriate for this level.
        LANGUAGE: Respond in ${getLanguageByCode(language)?.name || 'Spanish'}. Use authentic, natural ${getLanguageByCode(language)?.nativeName || 'Español'} expressions and cultural context.
        
        CRITICAL: You must fully embody the persona and focus on the theme throughout the conversation.
        
        SESSION SCENARIO (PARTS):
        - PERSONA: ${scenario.persona} (You MUST act as this character)
        - ACTING AS: ${scenario.act}
        - RECIPIENT: ${scenario.recipient}
        - THEME: ${scenario.theme} (All conversation should revolve around this topic)
        - STRUCTURE: ${scenario.structure}

        EXAMPLE: If persona is "hotel concierge" and theme is "check in", you should greet them as a hotel concierge and help them with the check-in process.

        GENERAL RULES:
        1. Keep responses concise (under 30 words) to mimic a real conversation.
        2. ${scaffoldingEnabled ? 'Correct the user\'s grammar GENTLY but only after they finish their thought.' : 'Do NOT correct the user\'s grammar - focus on natural conversation flow.'}
        3. Use your voice naturally, expressing warmth and encouragement.
        4. ALWAYS stay in character as the specified persona.
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
              const newText = message.serverContent!.outputTranscription!.text;
              setCurrentOutputText(prev => prev + newText);
              currentOutputRef.current = currentOutputRef.current + newText;
            } else if (message.serverContent?.inputTranscription) {
              const newText = message.serverContent!.inputTranscription!.text;
              setCurrentInputText(prev => prev + newText);
              currentInputRef.current = currentInputRef.current + newText;
            }

            if (message.serverContent?.turnComplete) {
              // Use refs to get the actual current values
              const finalInput = currentInputRef.current;
              const finalOutput = currentOutputRef.current;
              
              // Add both messages to history if there's content
              if (finalInput.trim() || finalOutput.trim()) {
                setHistory(prev => [
                  ...prev,
                  { role: 'user', text: finalInput, timestamp: Date.now() },
                  { role: 'model', text: finalOutput, timestamp: Date.now() }
                ]);
              }
              
              // Clear current texts and refs
              setCurrentInputText('');
              setCurrentOutputText('');
              currentInputRef.current = '';
              currentOutputRef.current = '';
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

  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 768 || /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
      console.log('Mobile detection:', mobile, 'Width:', window.innerWidth, 'UserAgent:', navigator.userAgent);
      setIsMobile(mobile);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const renderSetup = () => (
    <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 lg:p-12 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="w-full max-w-4xl bg-white border border-slate-200 rounded-[24px] md:rounded-[36px] lg:rounded-[48px] p-6 md:p-8 lg:p-12 shadow-2xl relative overflow-hidden setup-container">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#0ea5e9] to-transparent opacity-50" />
        
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-8 lg:mb-12">
          <div>
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-black tracking-tight mb-2 text-slate-900 setup-header">VocaFlow <span className="text-[#0ea5e9]">Lab</span></h1>
            <p className="text-lg md:text-xl text-slate-600 font-medium">Advanced Immersive Learning</p>
          </div>
          <div className="flex gap-2 bg-slate-100 p-1.5 rounded-2xl border border-slate-200 level-selector">
            {['A1','A2','B1','B2','C1','C2'].map(l => (
              <button 
                key={l}
                onClick={() => setLevel(l as CEFRLevel)}
                className={`w-10 h-10 md:w-11 md:h-11 rounded-xl text-xs font-black transition-all level-btn ${level === l ? 'bg-[#0ea5e9] text-white shadow-[0_0_20px_rgba(14,165,233,0.3)]' : 'text-slate-500 hover:text-slate-700'}`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-10 mb-8 lg:mb-12 setup-grid">
          <div className="space-y-6">
            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-[#0ea5e9]/80">Instructional Framework</h3>
            <div className="space-y-5">
              <div className="group">
                <label className="block text-[10px] uppercase font-black text-slate-500 mb-2 tracking-widest group-focus-within:text-[#0ea5e9] transition-colors">Target Persona *</label>
                <input 
                  value={scenario.persona} 
                  onChange={e => {
                    setScenario({...scenario, persona: e.target.value});
                    // Clear error when user starts typing
                    if (status.error) {
                      setStatus({...status, error: null});
                    }
                  }} 
                  className="w-full bg-white border border-slate-200 rounded-2xl px-5 py-4 text-sm text-slate-900 focus:outline-none focus:border-[#0ea5e9]/50 focus:bg-slate-50 transition-all" 
                  placeholder="e.g. A store clerk..." 
                />
              </div>
              <div className="group">
                <label className="block text-[10px] uppercase font-black text-slate-500 mb-2 tracking-widest group-focus-within:text-[#0ea5e9] transition-colors">Learning Theme *</label>
                <input 
                  value={scenario.theme} 
                  onChange={e => {
                    setScenario({...scenario, theme: e.target.value});
                    // Clear error when user starts typing
                    if (status.error) {
                      setStatus({...status, error: null});
                    }
                  }} 
                  className="w-full bg-white border border-slate-200 rounded-2xl px-5 py-4 text-sm text-slate-900 focus:outline-none focus:border-[#0ea5e9]/50 focus:bg-slate-50 transition-all" 
                  placeholder="e.g. Daily routines..." 
                />
              </div>
            </div>
          </div>
          
          <div className="space-y-6">
             <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Studio Parameters</h3>
             <div className="bg-slate-50 rounded-3xl p-6 md:p-8 space-y-6 md:space-y-8 border border-slate-200 studio-params">
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
                <div className="pt-4 border-t border-slate-200 text-[10px] text-slate-500 font-bold leading-relaxed hidden md:block">
                  Real-time pedagogical feedback enabled. Mic access required for live interaction.
                </div>
             </div>
          </div>
        </div>

        <button 
          onClick={startSession}
          className="w-full py-5 md:py-6 lg:py-7 rounded-[24px] md:rounded-[28px] lg:rounded-[32px] bg-[#10b981] hover:bg-[#059669] text-white text-base md:text-lg font-black tracking-widest transition-all shadow-[0_25px_50px_rgba(16,185,129,0.25)] active:scale-[0.98] flex items-center justify-center gap-4 disabled:opacity-50 disabled:cursor-not-allowed enter-btn"
          disabled={status.isConnecting}
        >
          <div className="w-2 h-2 rounded-full bg-white animate-ping" />
          {status.isConnecting ? 'CONNECTING...' : 'ENTER IMMERSIVE STUDIO'}
        </button>

        {status.error && (
          <div className="mt-4 p-4 bg-red-50 border-2 border-red-200 rounded-2xl text-red-700 text-sm font-medium animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              {status.error}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  const renderActive = () => (
    <div className="flex-1 relative flex flex-col z-10 p-4 md:p-6 lg:p-8 animate-in fade-in duration-1000 main-content">
      
      {/* Immersive View Layer */}
      <div className="flex-1 relative rounded-[32px] md:rounded-[48px] lg:rounded-[64px] overflow-hidden shadow-[0_25px_50px_rgba(0,0,0,0.1)] md:shadow-[0_50px_100px_rgba(0,0,0,0.1)] border border-slate-200 bg-white">
        
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
        <div className="absolute top-8 md:top-10 lg:top-12 right-8 md:right-10 lg:right-12 flex flex-col items-end gap-4 animate-in slide-in-from-right-8 duration-1000 floating-context">
           <div className="p-3 md:p-5 lg:p-7 bg-white/90 backdrop-blur-3xl border border-slate-200 rounded-[20px] md:rounded-[30px] lg:rounded-[36px] w-56 md:w-72 lg:w-80 shadow-2xl">
              {/* Mobile: Only show level and language */}
              <div className="md:hidden">
                <div className="flex flex-wrap items-center gap-2 justify-center">
                  <span className="px-2 py-1 bg-[#10b981]/10 text-[#10b981] text-[8px] font-black rounded-lg border border-[#10b981]/20">{level}</span>
                  <span className="px-2 py-1 bg-[#0ea5e9]/10 text-[#0ea5e9] text-[8px] font-black rounded-lg border border-[#0ea5e9]/20">
                    {getLanguageByCode(language)?.flag} {getLanguageByCode(language)?.nativeName}
                  </span>
                </div>
              </div>
              
              {/* Desktop/Tablet: Show full framework */}
              <div className="hidden md:block">
                <h4 className="text-[9px] font-black uppercase tracking-[0.3em] text-[#0ea5e9] mb-3">Pedagogical Framework</h4>
                <p className="text-sm font-bold text-slate-800 leading-relaxed mb-5">{scenario.act}</p>
                <div className="flex flex-wrap items-center gap-3 pt-4 border-t border-slate-200">
                  <span className="px-3 py-1 bg-[#10b981]/10 text-[#10b981] text-[10px] font-black rounded-lg border border-[#10b981]/20">{level}</span>
                  <span className="px-3 py-1 bg-[#0ea5e9]/10 text-[#0ea5e9] text-[10px] font-black rounded-lg border border-[#0ea5e9]/20">
                    {getLanguageByCode(language)?.flag} {getLanguageByCode(language)?.nativeName}
                  </span>
                  <span className="text-[10px] text-slate-500 font-black uppercase tracking-widest">{scenario.theme}</span>
                </div>
              </div>
           </div>
        </div>

        {/* Status Hub */}
        <div className="absolute top-8 md:top-10 lg:top-12 left-8 md:left-10 lg:left-12 status-hub">
           <div className="px-4 py-2 md:px-6 md:py-3 bg-white/80 backdrop-blur-2xl border border-slate-200 rounded-full flex items-center gap-2 md:gap-3">
             <div className={`w-2 h-2 rounded-full ${status.isConnected ? 'bg-[#10b981] shadow-[0_0_12px_rgba(16,185,129,0.8)] animate-pulse' : 'bg-slate-300'}`} />
             <span className="text-[8px] md:text-[10px] font-black tracking-[0.3em] text-slate-700 uppercase">
               {status.isConnected ? 'Live Interaction' : 'Initializing...'}
             </span>
           </div>
        </div>

        {/* Elli Profile Info */}
        <div className="absolute bottom-8 md:bottom-12 lg:bottom-20 left-8 md:left-12 lg:left-16 text-slate-800 z-10 pointer-events-none profile-info">
           <h2 className="text-3xl md:text-5xl lg:text-7xl font-black tracking-tighter mb-2 drop-shadow-[0_10px_10px_rgba(255,255,255,0.8)]">{PERSONA.name}</h2>
           <div className="flex flex-col md:flex-row items-start md:items-center gap-3 md:gap-5">
              <p className="text-lg md:text-2xl text-slate-600 font-medium tracking-tight">AI {PERSONA.role}</p>
              <div className="w-1.5 h-1.5 rounded-full bg-[#0ea5e9]/40 hidden md:block" />
              <span className="text-xs text-slate-400 uppercase tracking-[0.4em] font-black">Native Engine</span>
           </div>
        </div>

      </div>

      {/* Modern Integrated Control Bar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 md:gap-8 px-6 md:px-8 lg:px-12 py-4 md:py-6 lg:py-8 mt-4 md:mt-6 lg:mt-8 rounded-[24px] md:rounded-[32px] lg:rounded-[40px] bg-white border border-slate-200 shadow-2xl control-bar">
        <div className="flex items-center gap-4 md:gap-6">
           <button 
             onClick={toggleMute} 
             className={`p-3 md:p-4 lg:p-5 rounded-xl md:rounded-2xl transition-all flex items-center gap-2 md:gap-3 ${isMuted ? 'bg-rose-100 text-rose-600 border border-rose-200' : 'bg-emerald-100 text-emerald-600 border border-emerald-200 shadow-[0_0_12px_rgba(16,185,129,0.3)]'}`}
           >
             <svg className="w-4 h-4 md:w-5 md:h-6 lg:w-6 lg:h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
               {isMuted ? (
                 <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z M18.364 5.636l-12.728 12.728" />
               ) : (
                 <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
               )}
             </svg>
             <span className="text-[8px] md:text-[10px] font-black uppercase tracking-widest hidden md:block">{isMuted ? 'Mic Off' : 'Mic Active'}</span>
           </button>
        </div>

        <button 
          onClick={disconnect} 
          className="px-6 py-3 md:px-8 md:py-4 lg:px-10 lg:py-5 rounded-xl md:rounded-2xl bg-red-500 hover:bg-red-600 text-white font-black text-xs uppercase tracking-[0.3em] transition-all shadow-lg hover:shadow-xl border border-red-600"
        >
          <span className="hidden md:inline">End Session</span>
          <span className="md:hidden">End</span>
        </button>
      </div>
    </div>
  );

  const renderSummary = () => (
    <div className="flex-1 flex flex-col items-center justify-center p-6 md:p-8 lg:p-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
       <div className="w-full max-w-4xl bg-white border border-slate-200 rounded-[32px] md:rounded-[48px] lg:rounded-[56px] p-8 md:p-12 lg:p-16 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 md:p-12 lg:p-16 opacity-5 pointer-events-none grayscale">
             <svg className="w-32 h-32 md:w-48 md:h-48 lg:w-64 lg:h-64" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="#0ea5e9" /></svg>
          </div>
          
          <div className="mb-8 md:mb-12 lg:mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-black mb-4 text-slate-900">Insight Report</h2>
            <p className="text-slate-500 font-black uppercase tracking-[0.4em] text-xs">Laboratory Performance Metrics • CEFR {level}</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12 lg:gap-16 mb-8 md:mb-12 lg:mb-16">
             <div className="space-y-6 md:space-y-8">
                <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-[#0ea5e9]">Interaction Data</h4>
                <div className="space-y-4">
                   <div className="flex justify-between items-center py-4 md:py-5 border-b border-slate-200">
                      <span className="text-slate-500 text-sm font-bold tracking-tight">Exchanges</span>
                      <span className="text-slate-900 font-black text-lg md:text-xl">{history.length / 2}</span>
                   </div>
                   <div className="flex justify-between items-center py-4 md:py-5 border-b border-slate-200">
                      <span className="text-slate-500 text-sm font-bold tracking-tight">Scaffolding Applied</span>
                      <span className="text-[#10b981] font-black text-xs uppercase tracking-widest">Active</span>
                   </div>
                </div>
             </div>
             <div className="space-y-6 md:space-y-8">
                <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-500">Analytical Observations</h4>
                <div className="bg-slate-50 p-6 md:p-8 rounded-[24px] md:rounded-[32px] lg:rounded-[36px] border border-slate-200">
                  <p className="text-sm text-slate-700 leading-[1.6] md:leading-[1.8] font-medium italic">
                    "Session target focused on <span className="text-slate-900 font-black">{scenario.theme}</span>. Pronunciation was clear; recommendation to expand use of contextual idiomatic expressions in future {level} tasks."
                  </p>
                </div>
             </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <button onClick={() => window.location.href = '/'} className="flex-1 py-4 md:py-6 rounded-2xl md:rounded-3xl bg-[#0ea5e9] hover:bg-[#0284c7] text-white font-black text-sm uppercase tracking-[0.4em] transition-all shadow-2xl active:scale-[0.98] flex items-center justify-center gap-3">
              <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              <span className="hidden sm:inline">Back to VocaFlow Home</span>
              <span className="sm:hidden">Back Home</span>
            </button>
            <button onClick={() => { setStage('setup'); setHistory([]); }} className="flex-1 py-4 md:py-6 rounded-2xl md:rounded-3xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-black text-sm uppercase tracking-[0.4em] transition-all border-2 border-slate-200 active:scale-[0.98]">
               <span className="hidden sm:inline">Start New Session</span>
               <span className="sm:hidden">New Session</span>
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

      {/* Mobile Layout - Full Screen Content */}
      {isMobile ? (
        <div className="flex-1 flex flex-col">
          {stage === 'setup' && renderSetup()}
          {(stage === 'active' || stage === 'calling') && renderActive()}
          {stage === 'summary' && renderSummary()}
        </div>
      ) : (
        /* Desktop/Tablet Layout - Sidebar */
        <div className="flex flex-1">
          <div className="flex-1 flex flex-col">
            {stage === 'setup' && renderSetup()}
            {(stage === 'active' || stage === 'calling') && renderActive()}
            {stage === 'summary' && renderSummary()}
          </div>

          {/* Transcription Sidebar - Desktop/Tablet Only */}
          <aside className={`h-full bg-white/95 backdrop-blur-3xl border-l border-slate-200 flex flex-col z-30 transition-all duration-1000 ${stage === 'active' ? 'w-[380px] lg:w-[440px]' : 'w-[440px] lg:w-[520px]'}`}>
            <div className="p-6 lg:p-12 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-[10px] font-black uppercase tracking-[0.5em] text-slate-500 mb-2">Metadata Stream</h3>
                <p className="text-base font-black text-slate-700">Transcription Log</p>
              </div>
              <div className="flex gap-1.5">
                 <div className="w-1.5 h-1.5 rounded-full bg-[#0ea5e9]/40" />
                 <div className="w-1.5 h-1.5 rounded-full bg-[#0ea5e9]/20" />
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 lg:p-12 space-y-8 lg:space-y-12 custom-scrollbar">
              {history.length === 0 && !currentInputText && !currentOutputText && (
                <div className="h-full flex flex-col items-center justify-center text-center opacity-10 px-6 lg:px-8">
                  <div className="w-16 h-16 lg:w-20 lg:h-20 mb-6 lg:mb-8 border border-slate-300 rounded-full flex items-center justify-center">
                    <svg className="w-6 h-6 lg:w-8 lg:h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                  </div>
                  <p className="text-[10px] lg:text-[11px] font-black uppercase tracking-[0.4em] text-slate-400">Awaiting Input Stream</p>
                </div>
              )}

              {history.map((entry, i) => (
                <div key={i} className={`flex flex-col ${entry.role === 'user' ? 'items-end' : 'items-start'} animate-in slide-in-from-bottom-4 duration-500`}>
                  <div className={`max-w-[95%] px-4 lg:px-7 py-4 lg:py-6 rounded-[20px] lg:rounded-[32px] text-[12px] lg:text-[14px] leading-[1.6] lg:leading-[1.7] transition-all font-medium ${entry.role === 'user' ? 'bg-[#0ea5e9]/10 text-[#0ea5e9] border border-[#0ea5e9]/20 rounded-tr-none' : 'bg-slate-50 text-slate-700 border border-slate-200 rounded-tl-none'}`}>
                    <span className="block text-[8px] lg:text-[9px] font-black uppercase tracking-[0.3em] opacity-30 mb-2 lg:mb-3">{entry.role === 'user' ? 'Student' : 'Coach'}</span>
                    {entry.text}
                  </div>
                </div>
              ))}

              {(currentInputText || currentOutputText) && (
                 <div className="space-y-6 lg:space-y-8 pt-6 lg:pt-8 border-t border-white/5">
                    {currentInputText && (
                      <div className="flex flex-col items-end">
                        <div className="max-w-[95%] px-4 lg:px-7 py-4 lg:py-6 rounded-[20px] lg:rounded-[32px] text-[12px] lg:text-[14px] bg-[#0ea5e9]/5 text-[#0ea5e9] border border-[#0ea5e9]/10 rounded-tr-none animate-pulse">
                          <span className="block text-[8px] lg:text-[9px] font-black uppercase tracking-[0.3em] opacity-30 mb-2">Analyzing...</span>
                          {currentInputText}
                        </div>
                      </div>
                    )}
                    {currentOutputText && (
                      <div className="flex flex-col items-start">
                        <div className="max-w-[95%] px-4 lg:px-7 py-4 lg:py-6 rounded-[20px] lg:rounded-[32px] text-[12px] lg:text-[14px] bg-slate-50 text-slate-500 border border-slate-200 rounded-tl-none animate-pulse">
                          <span className="block text-[8px] lg:text-[9px] font-black uppercase tracking-[0.3em] opacity-30 mb-2">Generating...</span>
                          {currentOutputText}
                        </div>
                      </div>
                    )}
                 </div>
              )}
              <div ref={historyEndRef} />
            </div>

            <div className="p-6 lg:p-12 bg-slate-50 border-t border-slate-200">
               <div className="flex justify-center items-center text-[10px] text-slate-400 font-black uppercase tracking-[0.5em]">
                 <span>VocaFlow Studio Platform</span>
               </div>
            </div>
          </aside>
        </div>
      )}

      </div>
  );
};

export default App;
