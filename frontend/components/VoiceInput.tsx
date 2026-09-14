"use client";

import { useEffect, useRef, useState } from "react";
import { transcribe } from "@/lib/api";
import { T, type Lang } from "@/lib/i18n";
import { getSessionId } from "@/lib/session";

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

/** Bouton micro : MediaRecorder, forme d'onde temps réel, arrêt auto à 30 s, envoi base64 à Whisper. */
export default function VoiceInput({ lang, onTranscript, onError }: Props) {
  const t = T[lang];
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(MAX_RECORDING_MS / 1000);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
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

  useEffect(() => cleanup, []);

  const drawWaveform = (stream: MediaStream) => {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    const canvas = canvasRef.current;
    if (!Ctx || !canvas) return;
    const ctx = new Ctx();
    audioCtxRef.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const g = canvas.getContext("2d");
    const render = () => {
      if (!g) return;
      analyser.getByteFrequencyData(data);
      g.clearRect(0, 0, canvas.width, canvas.height);
      const bars = 40;
      const w = canvas.width / bars;
      for (let i = 0; i < bars; i++) {
        const v = data[Math.floor((i * data.length) / bars)] / 255;
        const h = Math.max(4, v * canvas.height);
        g.fillStyle = i % 2 ? "#2A9D8F" : "#C9A84C";
        g.fillRect(i * w + 2, (canvas.height - h) / 2, w - 4, h);
      }
      rafRef.current = requestAnimationFrame(render);
    };
    render();
  };

  const start = async () => {
    if (recording || busy) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = async () => {
        cleanup();
        setRecording(false);
        if (!chunks.length) return;
        setBusy(true);
        try {
          const audio = await blobToBase64(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
          chunks.length = 0; // RGPD : l'audio n'est conservé nulle part côté borne
          const res = await transcribe(audio, lang, getSessionId());
          if (res.text) onTranscript(res.text);
        } catch {
          onError?.(t.error);
        } finally {
          setBusy(false);
        }
      };
      recorder.start();
      setRecording(true);
      setRemaining(MAX_RECORDING_MS / 1000);
      drawWaveform(stream);
      timeoutRef.current = setTimeout(stop, MAX_RECORDING_MS);
      tickRef.current = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    } catch {
      cleanup();
      onError?.(t.micDenied);
    }
  };

  const stop = () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
  };

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
      <canvas ref={canvasRef} width={480} height={80} className={`h-20 w-full max-w-md ${recording ? "" : "invisible"}`} aria-hidden />
      <p className="text-center text-2xl" aria-live="polite">
        {busy ? t.thinking : recording ? `${t.listening} ${remaining}s` : t.tapToSpeak}
      </p>
    </div>
  );
}
