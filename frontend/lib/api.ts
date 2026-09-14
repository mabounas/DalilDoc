import type { Lang } from "./i18n";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const BORNE_ID = process.env.NEXT_PUBLIC_BORNE_ID ?? "borne-dev";

export interface DocumentItem {
  ordre: number | null;
  nom: string | null;
  obligatoire: boolean;
  condition: string | null;
  format: string[];
}

export interface QueryResult {
  reponse: string;
  langue: string;
  demarche_id: string | null;
  documents: DocumentItem[];
  score_confiance: number;
  hors_perimetre: boolean;
  sources: string[];
  temps_ms: number;
  offline?: boolean;
}

async function post<T>(path: string, body: unknown, timeoutMs = 10000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const askQuestion = (text: string, langue: Lang, sessionId: string) =>
  post<QueryResult>("/api/v1/query", { text, langue, session_id: sessionId, borne_id: BORNE_ID });

export const transcribe = (audioBase64: string, langue: Lang, sessionId: string) =>
  post<{ text: string; langue: Lang; confidence: number }>(
    "/api/v1/voice/transcribe",
    { audio: audioBase64, langue, session_id: sessionId, borne_id: BORNE_ID },
    30000,
  );

export interface VoiceCapabilities {
  stt: boolean;
  tts: boolean;
}

const CAPS_TTL_MS = 5 * 60_000;
let capsCache: { at: number; promise: Promise<VoiceCapabilities> } | null = null;

/** Moteurs vocaux du serveur (Whisper / ElevenLabs), mis en cache 5 min. */
export const getVoiceCapabilities = (): Promise<VoiceCapabilities> => {
  if (!capsCache || Date.now() - capsCache.at > CAPS_TTL_MS) {
    const promise = fetch(`${API_URL}/api/v1/voice/capabilities`).then(async (res) => {
      if (!res.ok) throw new ApiError(res.status, await res.text());
      return (await res.json()) as VoiceCapabilities;
    });
    promise.catch(() => { capsCache = null; });
    capsCache = { at: Date.now(), promise };
  }
  return capsCache.promise;
};

export const synthesize = (text: string, langue: Lang) =>
  post<{ audio: string; mime_type: string; cached?: boolean }>(
    "/api/v1/voice/synthesize",
    { text, langue, borne_id: BORNE_ID },
    45000, // première génération d'une longue réponse arabe ; ensuite servie depuis le cache
  );
