"use client";

import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";
import { getSpokenSegments, getVoiceCapabilities, synthesize, type QueryResult } from "@/lib/api";
import { isRtl, T, type Lang } from "@/lib/i18n";
import { moroccanBrowserVoice, speakWithBrowser, stopSpeaking } from "@/lib/speech";

interface Props {
  result: QueryResult;
  lang: Lang;
  question: string;
  onNewQuestion: () => void;
}

/** Texte à lire : titre + documents numérotés (ou message d'orientation). */
export function spokenText(result: QueryResult, lang: Lang): string {
  if (result.hors_perimetre || !result.documents.length) return result.reponse;
  const t = T[lang];
  const sep = isRtl(lang) ? "، " : ". ";
  const docs = result.documents.map((d, i) => `${d.ordre ?? i + 1}. ${d.nom}`).join(sep);
  return `${result.reponse.split("\n")[0]}${sep}${t.requiredDocs} : ${docs}`;
}

/**
 * Lance la synthèse de toutes les phrases (3 en parallèle, dans l'ordre) et renvoie
 * une promesse d'URL audio par phrase : la lecture commence dès que la première est prête.
 */
function synthesizeAll(segments: string[], lang: Lang, concurrency = 3): Promise<string>[] {
  const slots = segments.map(() => {
    let resolve!: (v: string) => void;
    let reject!: (e: unknown) => void;
    const promise = new Promise<string>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    promise.catch(() => undefined);
    return { promise, resolve, reject };
  });
  let next = 0;
  const worker = async () => {
    while (next < segments.length) {
      const i = next++;
      try {
        const { audio, mime_type } = await synthesize(segments[i].slice(0, 2000), lang);
        slots[i].resolve(`data:${mime_type};base64,${audio}`);
      } catch (e) {
        slots[i].reject(e);
      }
    }
  };
  for (let w = 0; w < Math.min(concurrency, segments.length); w++) void worker();
  return slots.map((s) => s.promise);
}

/** Affiche la réponse (≥ 24px), la lit à voix haute et propose Répéter / Nouvelle question / Imprimer. */
export default function ResponseDisplay({ result, lang, question, onNewQuestion }: Props) {
  const t = T[lang];
  const rtl = isRtl(lang);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [voiceMissing, setVoiceMissing] = useState(false);
  const [needsTap, setNeedsTap] = useState(false);

  const runRef = useRef(0);

  const speak = useCallback(async () => {
    const run = ++runRef.current;
    const text = spokenText(result, lang);
    audioRef.current?.pause();
    stopSpeaking();
    // Découpage en phrases fourni par l'API (identique au pré-chargement du cache).
    let segments = [text];
    if (result.demarche_id && result.documents.length && !result.hors_perimetre) {
      try {
        const { segments: fromApi } = await getSpokenSegments(result.demarche_id, lang);
        if (fromApi?.length) segments = fromApi;
      } catch {
        segments = [text];
      }
    }
    if (run !== runRef.current) return;

    // Darija / arabe : une voix marocaine du navigateur (Edge) a la priorité sur ElevenLabs,
    // dont les voix gratuites prononcent la darija avec un accent égyptien.
    if (await moroccanBrowserVoice(lang)) {
      if (run !== runRef.current) return;
      setNeedsTap(false);
      setVoiceMissing(!(await speakWithBrowser(segments, lang)));
      return;
    }

    let serverTts = false;
    try {
      serverTts = (await getVoiceCapabilities()).tts;
    } catch {
      serverTts = false;
    }
    if (serverTts) {
      const audios = synthesizeAll(segments, lang);
      let played = 0;
      for (const pending of audios) {
        let src: string;
        try {
          src = await pending;
        } catch {
          break; // ElevenLabs en échec sur cette phrase : on s'arrête (repli si rien n'a été lu)
        }
        if (run !== runRef.current) return; // nouvelle lecture ou écran quitté
        const el = new Audio(src);
        audioRef.current = el;
        try {
          await el.play();
        } catch {
          // Lecture automatique bloquée par le navigateur : l'audio est prêt, « Répéter » le lira.
          setNeedsTap(true);
          return;
        }
        setNeedsTap(false);
        setVoiceMissing(false);
        await new Promise<void>((done) => {
          el.onpause = () => done(); // fin de phrase (ou lecture interrompue)
          el.onerror = () => done();
        });
        if (run !== runRef.current) return;
        played++;
      }
      if (played > 0) return;
    }
    // Uniquement une voix de la bonne langue : pas de lecture arabe par une voix française.
    if (run === runRef.current) setVoiceMissing(!(await speakWithBrowser(segments, lang)));
  }, [result, lang]);

  useEffect(() => {
    speak();
    return () => {
      runRef.current++;
      audioRef.current?.pause();
      stopSpeaking();
    };
  }, [speak]);

  const title = result.reponse.split("\n")[0];
  const qrUrl = result.sources[0];

  return (
    <section dir={rtl ? "rtl" : "ltr"} className="flex flex-1 flex-col gap-6" aria-live="polite">
      <p className="text-lg text-ink-muted">« {question} »</p>
      {result.offline && <p className="rounded-xl bg-night-700 px-4 py-2 text-lg text-gold">{t.offline}</p>}
      {voiceMissing && <p className="no-print text-base text-ink-muted">🔇 {t.noVoice}</p>}

      {result.hors_perimetre ? (
        <div className="rounded-3xl border-2 border-gold bg-night-800 p-8 text-center">
          <p className="text-3xl font-semibold text-gold">{t.outOfScope}</p>
          <p className="mt-4 text-2xl">{result.reponse}</p>
        </div>
      ) : (
        <div className="rounded-3xl bg-night-800 p-6 md:p-8">
          <h2 className="text-2xl font-bold text-gold">{title}</h2>
          {result.documents.length > 0 ? (
            <>
              <h3 className="mt-5 text-xl font-semibold text-mint">{t.requiredDocs}</h3>
              <ol className="mt-3 flex flex-col gap-4">
                {result.documents.map((d, i) => (
                  <li key={`${d.ordre}-${i}`} className="flex gap-4 text-xl leading-snug">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-mint font-bold text-night">
                      {d.ordre ?? i + 1}
                    </span>
                    <span>
                      {d.nom}
                      {(!d.obligatoire || d.condition) && (
                        <span className="mt-1 block text-lg text-ink-muted">
                          {[!d.obligatoire ? t.optional : null, d.condition].filter(Boolean).join(" · ")}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <p className="mt-4 whitespace-pre-line text-xl">{result.reponse.split("\n").slice(1).join("\n")}</p>
          )}
        </div>
      )}

      {qrUrl && !result.hors_perimetre && (
        <div className="flex items-center gap-5 rounded-2xl bg-night-700 p-4">
          <div className="rounded-lg bg-white p-2">
            <QRCodeSVG value={qrUrl} size={96} />
          </div>
          <div>
            <p className="text-lg">{t.scanQr}</p>
            <p className="text-base text-ink-muted" dir="ltr">{t.source} : {new URL(qrUrl).hostname}</p>
          </div>
        </div>
      )}

      <div className="no-print mt-auto grid grid-cols-3 gap-4">
        <button
          onClick={speak}
          className={`min-h-[72px] rounded-2xl text-xl active:bg-night-600 ${needsTap ? "animate-pulse bg-mint text-night" : "bg-night-700"}`}
        >
          🔊 {t.repeat}
        </button>
        <button onClick={onNewQuestion} className="min-h-[72px] rounded-2xl bg-gold text-xl font-semibold text-night active:bg-gold-light">
          {t.newQuestion}
        </button>
        <button onClick={() => window.print()} className="min-h-[72px] rounded-2xl bg-night-700 text-xl active:bg-night-600">🖨 {t.print}</button>
      </div>
    </section>
  );
}
