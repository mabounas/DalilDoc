"use client";

import { useEffect, useRef, useState } from "react";
import { getVoiceCapabilities, transcribe } from "@/lib/api";
import { T, type Lang } from "@/lib/i18n";
import { getSessionId } from "@/lib/session";
import { type BrowserRecognition, getRecognitionCtor, rmsLevel, SilenceDetector, SPEECH_LANG, stopSpeaking } from "@/lib/speech";

export const MAX_RECORDING_MS = 30_000;

interface Props {
  lang: Lang;
  onTranscript: (text: string) => void;
  onError?: (message: string) => void;
}

const blobToBase64 = (blob: Blob) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });

/**
 * Bouton micro « voice-first » : la question part toute seule dès que l'usager se tait.
 *
 * - Whisper configuré sur le serveur : MediaRecorder + détection de silence, puis envoi base64.
 * - Sinon : reconnaissance vocale du navigateur (Chrome/Edge), qui détecte aussi la fin de phrase.
 * Arrêt manuel toujours possible, arrêt forcé à 30 s.
 */
export default function VoiceInput({ lang, onTranscript, onError }: Props) {
  const t = T[lang];
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(MAX_RECORDING_MS / 1000);
  const [interim, setInterim] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<BrowserRecognition | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<SilenceDetector | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const tickRef = useRef<ReturnType<typeof setInterval>>();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>();
  const audioCtxRef = useRef<AudioContext | null>(null);

  const cleanup = () => {
    clearTimeout(timeoutRef.current);
    clearInterval(tickRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
    streamRef.current = null;
    audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
  };

  useEffect(
    () => () => {
      cleanup();
      recognitionRef.current?.abort();
    },
    [],
  );

  const stop = () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    recognitionRef.current?.stop();
  };

  const startTimers = () => {
    setRecording(true);
    setRemaining(MAX_RECORDING_MS / 1000);
    timeoutRef.current = setTimeout(stop, MAX_RECORDING_MS);
    tickRef.current = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
  };

  /** Forme d'onde + détection de silence sur le flux micro. */
  const monitor = (stream: MediaStream) => {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    const canvas = canvasRef.current;
    if (!Ctx) return;
    const ctx = new Ctx();
    audioCtxRef.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const freq = new Uint8Array(analyser.frequencyBinCount);
    const wave = new Uint8Array(analyser.fftSize);
    const detector = new SilenceDetector();
    detectorRef.current = detector;
    const g = canvas?.getContext("2d");
    const render = () => {
      analyser.getByteTimeDomainData(wave);
      const state = detector.update(rmsLevel(wave), performance.now());
      if (state === "stop" || state === "nospeech") {
        stop(); // fin du message détectée : la transcription se déclenche
        return;
      }
      if (g && canvas) {
        analyser.getByteFrequencyData(freq);
        g.clearRect(0, 0, canvas.width, canvas.height);
        const bars = 40;
        const w = canvas.width / bars;
        for (let i = 0; i < bars; i++) {
          const v = freq[Math.floor((i * freq.length) / bars)] / 255;
          const h = Math.max(4, v * canvas.height);
          g.fillStyle = i % 2 ? "#2A9D8F" : "#C9A84C";
          g.fillRect(i * w + 2, (canvas.height - h) / 2, w - 4, h);
        }
      }
      rafRef.current = requestAnimationFrame(render);
    };
    render();
  };

  const startServer = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    streamRef.current = stream;
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;
    detectorRef.current = null;
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = async () => {
      cleanup();
      setRecording(false);
      // Sans voix détectée, on n'envoie rien (évite une transcription vide ou hallucinée).
      if (detectorRef.current && !detectorRef.current.heardSpeech) {
        chunks.length = 0;
        setNotice(t.noSpeech);
        return;
      }
      if (!chunks.length) return;
      setBusy(true);
      try {
        const audio = await blobToBase64(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        chunks.length = 0; // RGPD : l'audio n'est conservé nulle part côté borne
        const res = await transcribe(audio, lang, getSessionId());
        if (res.text.trim()) onTranscript(res.text);
        else setNotice(t.noSpeech);
      } catch {
        onError?.(t.error);
      } finally {
        setBusy(false);
      }
    };
    recorder.start(250);
    startTimers();
    monitor(stream);
  };

  const startBrowser = (Recognition: new () => BrowserRecognition) => {
    const rec = new Recognition();
    recognitionRef.current = rec;
    rec.lang = SPEECH_LANG[lang];
    rec.continuous = false; // le navigateur termine seul à la fin de la phrase
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    let finalText = "";
    let failed = false;
    rec.onresult = (e) => {
      let partial = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else partial += r[0].transcript;
      }
      setInterim(`${finalText}${partial}`);
    };
    rec.onerror = (e) => {
      failed = true;
      if (e.error === "not-allowed" || e.error === "service-not-allowed" || e.error === "audio-capture") onError?.(t.micDenied);
      else if (e.error === "no-speech") setNotice(t.noSpeech);
      else if (e.error !== "aborted") onError?.(t.error);
    };
    rec.onend = () => {
      clearTimeout(timeoutRef.current);
      clearInterval(tickRef.current);
      recognitionRef.current = null;
      setRecording(false);
      setInterim("");
      const text = finalText.trim();
      if (text) onTranscript(text);
      else if (!failed) setNotice(t.noSpeech);
    };
    rec.start();
    startTimers();
  };

  const start = async () => {
    if (recording || busy) return;
    setNotice(null);
    stopSpeaking(); // le micro ne doit pas capter la réponse lue
    let serverStt = false;
    try {
      serverStt = (await getVoiceCapabilities()).stt;
    } catch {
      serverStt = false; // API injoignable : on tente la reconnaissance du navigateur
    }
    try {
      const Recognition = getRecognitionCtor();
      if (serverStt) await startServer();
      else if (Recognition) startBrowser(Recognition);
      else onError?.(t.micDenied);
    } catch {
      cleanup();
      setRecording(false);
      onError?.(t.micDenied);
    }
  };

  const status = busy ? t.thinking : recording ? interim || `${t.listening} ${remaining}s` : notice ?? t.tapToSpeak;

  return (
    <div className="flex flex-col items-center gap-6">
      <button
        type="button"
        aria-pressed={recording}
        aria-label={recording ? t.stop : t.tapToSpeak}
        onClick={recording ? stop : start}
        disabled={busy}
        className={`relative flex h-44 w-44 items-center justify-center rounded-full text-7xl shadow-2xl transition active:scale-95 ${
          recording ? "bg-gold text-night" : "bg-mint text-night"
        } disabled:opacity-60`}
      >
        {recording && <span className="absolute inset-0 animate-pulseRing rounded-full bg-gold" />}
        <span className="relative">{recording ? "■" : "🎤"}</span>
      </button>
      <canvas ref={canvasRef} width={480} height={80} className={`h-20 w-full max-w-md ${recording && !interim ? "" : "invisible"}`} aria-hidden />
      <p className="max-w-2xl text-center text-2xl" aria-live="polite" dir="auto">
        {status}
      </p>
    </div>
  );
}
