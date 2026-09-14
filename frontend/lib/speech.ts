import type { Lang } from "./i18n";

/** Balises BCP-47 pour la reconnaissance et la synthèse du navigateur (borne au Maroc). */
export const SPEECH_LANG: Record<Lang, string> = {
  darija: "ar-MA",
  ar: "ar-MA",
  fr: "fr-FR",
  en: "en-US",
  pt: "pt-PT",
  es: "es-ES",
};

// ── Détection de fin de parole ─────────────────────────────────────────────

export type VadState = "calibrating" | "waiting" | "speaking" | "stop" | "nospeech";

export interface VadOptions {
  calibrationMs: number; // mesure du bruit ambiant au démarrage
  silenceMs: number; // silence après la parole → fin du message
  noSpeechMs: number; // aucune parole → abandon
  minSpeechMs: number; // durée de voix minimale pour considérer qu'on a parlé
  minLevel: number; // seuil RMS plancher
  maxThreshold: number; // plafond (si l'usager parle dès le démarrage)
  ratio: number; // seuil = bruit ambiant × ratio
}

const VAD_DEFAULTS: VadOptions = {
  calibrationMs: 300, silenceMs: 1300, noSpeechMs: 7000, minSpeechMs: 250, minLevel: 0.02, maxThreshold: 0.08, ratio: 2.5,
};

/**
 * Détecteur de silence : alimenté par le niveau RMS du micro (0-1), il indique
 * quand l'usager a fini de parler pour déclencher la transcription sans bouton.
 */
export class SilenceDetector {
  heardSpeech = false;
  private readonly o: VadOptions;
  private startedAt: number | null = null;
  private lastT = 0;
  private noise = 0;
  private samples = 0;
  private speechMs = 0;
  private lastVoiceAt = 0;

  constructor(options: Partial<VadOptions> = {}) {
    this.o = { ...VAD_DEFAULTS, ...options };
  }

  update(level: number, now: number): VadState {
    if (this.startedAt === null) {
      this.startedAt = now;
      this.lastT = now;
    }
    const dt = now - this.lastT;
    this.lastT = now;
    const elapsed = now - this.startedAt;
    if (elapsed < this.o.calibrationMs) {
      this.noise = (this.noise * this.samples + level) / ++this.samples;
      return "calibrating";
    }
    const threshold = Math.max(this.o.minLevel, Math.min(this.noise * this.o.ratio, this.o.maxThreshold));
    if (level >= threshold) {
      this.speechMs += dt;
      this.lastVoiceAt = now;
      if (this.speechMs >= this.o.minSpeechMs) this.heardSpeech = true;
    }
    if (this.heardSpeech) return now - this.lastVoiceAt >= this.o.silenceMs ? "stop" : "speaking";
    return elapsed >= this.o.noSpeechMs ? "nospeech" : "waiting";
  }
}

/** Niveau RMS (0-1) d'un buffer temporel 8 bits d'un AnalyserNode. */
export function rmsLevel(data: Uint8Array): number {
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    const v = (data[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / (data.length || 1));
}

// ── Reconnaissance vocale du navigateur (repli sans Whisper) ────────────────

export interface RecognitionAlternative { transcript: string }
export interface RecognitionResult { isFinal: boolean; 0: RecognitionAlternative; length: number }
export interface RecognitionEvent { results: { length: number; [i: number]: RecognitionResult } }
export interface RecognitionErrorEvent { error: string }
export interface BrowserRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

/** Constructeur SpeechRecognition (Chrome / Edge : préfixe webkit), ou null. */
export function getRecognitionCtor(): (new () => BrowserRecognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => BrowserRecognition; webkitSpeechRecognition?: new () => BrowserRecognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// ── Synthèse vocale du navigateur (repli sans ElevenLabs) ───────────────────

export interface VoiceLike { lang: string; name: string; localService?: boolean }

/**
 * Choisit une voix de la bonne langue. Ne renvoie jamais une voix d'une autre
 * langue : un texte arabe lu par une voix française est incompréhensible.
 */
export function pickVoice<V extends VoiceLike>(voices: V[], lang: Lang): V | null {
  const wanted = SPEECH_LANG[lang].toLowerCase(); // ex. ar-ma
  const base = wanted.split("-")[0]; // ex. ar
  let best: V | null = null;
  let bestScore = 0;
  for (const v of voices) {
    const tag = v.lang.toLowerCase().replace("_", "-");
    if (tag.split("-")[0] !== base) continue;
    let score = tag === wanted ? 4 : 2;
    if (/natural|online|neural|premium|enhanced/i.test(v.name)) score += 2; // voix neuronales, plus naturelles
    if (score > bestScore) {
      best = v;
      bestScore = score;
    }
  }
  return best;
}

function synth(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
}

/**
 * Les voix se chargent de façon asynchrone : Edge expose d'abord ses voix locales puis,
 * un peu plus tard, ses voix neuronales en ligne (dont les voix marocaines). Si `wanted`
 * est fourni, on attend qu'une voix correspondante apparaisse (jusqu'au délai).
 */
export function loadVoices(timeoutMs = 1500, wanted?: (v: SpeechSynthesisVoice) => boolean): Promise<SpeechSynthesisVoice[]> {
  const s = synth();
  if (!s) return Promise.resolve([]);
  const now = s.getVoices();
  if (now.length && (!wanted || now.some(wanted))) return Promise.resolve(now);
  return new Promise((resolve) => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      s.removeEventListener?.("voiceschanged", onChange);
      resolve(s.getVoices());
    };
    const onChange = () => {
      const voices = s.getVoices();
      if (voices.length && (!wanted || voices.some(wanted))) finish();
    };
    s.addEventListener?.("voiceschanged", onChange);
    setTimeout(finish, timeoutMs);
  });
}

const isMoroccan = (v: VoiceLike) => v.lang.toLowerCase().replace("_", "-") === "ar-ma";

/**
 * Voix marocaine du navigateur (Edge : « Microsoft Jamal / Mouna Online (Natural) »).
 * Prioritaire pour la darija et l'arabe : accent marocain, gratuite, sans crédit ElevenLabs.
 * Le texte lu (réponse publique de la borne) est traité par le service vocal de Microsoft.
 */
export async function moroccanBrowserVoice(lang: Lang, timeoutMs = 1500): Promise<SpeechSynthesisVoice | null> {
  if (lang !== "darija" && lang !== "ar") return null;
  const voice = pickVoice(await loadVoices(timeoutMs, isMoroccan), lang);
  return voice && isMoroccan(voice) ? voice : null;
}

/** Adapte le texte à l'oral (séparateurs arabes, symboles). */
export function toSpeech(text: string, lang: Lang): string {
  const rtl = lang === "ar" || lang === "darija";
  let out = text.replace(/\s*·\s*/g, rtl ? "، " : ", ").replace(/(\d)\s*[x×]\s*(\d)/g, "$1 × $2").replace(/\n+/g, rtl ? "، " : ". ");
  if (rtl) out = out.replace(/\bDhs\b|\bMAD\b/g, "درهم");
  return out.replace(/\s{2,}/g, " ").trim();
}

/**
 * Lit un texte (ou une liste de phrases, lues à la suite) avec une voix du navigateur
 * de la bonne langue. Retourne false si aucune voix adaptée.
 * Phrase par phrase : les longues lectures du navigateur peuvent s'interrompre.
 */
export async function speakWithBrowser(text: string | string[], lang: Lang): Promise<boolean> {
  const s = synth();
  if (!s) return false;
  const voice = (await moroccanBrowserVoice(lang)) ?? pickVoice(await loadVoices(), lang);
  if (!voice) return false;
  s.cancel();
  for (const phrase of (Array.isArray(text) ? text : [text]).filter((t) => t.trim())) {
    const u = new SpeechSynthesisUtterance(toSpeech(phrase, lang));
    u.voice = voice;
    u.lang = voice.lang;
    u.rate = 0.9;
    s.speak(u); // file d'attente du navigateur : lecture dans l'ordre
  }
  return true;
}

/** Coupe toute lecture en cours (avant d'ouvrir le micro). */
export function stopSpeaking(): void {
  synth()?.cancel();
}
