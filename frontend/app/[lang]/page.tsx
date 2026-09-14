"use client";

import { notFound, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import IdleScreen from "@/components/IdleScreen";
import ResponseDisplay from "@/components/ResponseDisplay";
import TextInput from "@/components/TextInput";
import VoiceInput from "@/components/VoiceInput";
import { askQuestion, type QueryResult } from "@/lib/api";
import { EXAMPLES, isLang, isRtl, LANG_META, T, type Lang } from "@/lib/i18n";
import { answerOffline } from "@/lib/offline";
import { moroccanBrowserVoice } from "@/lib/speech";
import { getSessionId, resetSession } from "@/lib/session";

type Mode = "voice" | "text";

/** Écran principal d'interaction citoyen. */
export default function InteractionPage({ params }: { params: { lang: string } }) {
  const validLang = isLang(params.lang);
  const lang: Lang = validLang ? (params.lang as Lang) : "fr";
  const t = T[lang];
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("voice");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dir = isRtl(lang) ? "rtl" : "ltr";
    document.documentElement.lang = LANG_META[lang].htmlLang;
    // Recherche de la voix marocaine dès l'ouverture : aucune attente au moment de lire la réponse.
    void moroccanBrowserVoice(lang);
  }, [lang]);

  const ask = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q) return;
      setQuestion(q);
      setLoading(true);
      setError(null);
      setResult(null);
      try {
        setResult(await askQuestion(q, lang, getSessionId()));
      } catch {
        const offline = answerOffline(q, lang);
        if (offline) setResult(offline);
        else setError(t.error);
      } finally {
        setLoading(false);
      }
    },
    [lang, t.error],
  );

  const reset = () => {
    setResult(null);
    setQuestion("");
    setError(null);
  };

  const goHome = () => {
    resetSession();
    router.push("/");
  };

  if (!validLang) notFound();

  return (
    <IdleScreen onIdle={goHome}>
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-8">
        <header className="no-print flex items-center justify-between">
          <button onClick={goHome} className="min-h-touch rounded-2xl bg-night-700 px-6 text-lg text-ink-muted active:bg-night-600">
            ⟵ {t.back}
          </button>
          <div className="flex items-center gap-3">
            <img src="/logo.svg" alt="" className="h-12 w-12" />
            <span className="text-xl font-semibold text-gold">WathiqaDoc</span>
          </div>
        </header>

        {result ? (
          <ResponseDisplay result={result} lang={lang} question={question} onNewQuestion={reset} />
        ) : (
          <section className="flex flex-1 flex-col items-center justify-center gap-8">
            {loading ? (
              <p role="status" className="animate-pulse text-2xl text-gold">{t.thinking}</p>
            ) : mode === "voice" ? (
              <VoiceInput lang={lang} onTranscript={ask} onError={(msg) => { setError(msg); setMode("text"); }} />
            ) : (
              <TextInput lang={lang} onSubmit={ask} />
            )}

            {error && <p role="alert" className="max-w-2xl text-center text-xl text-red-300">{error}</p>}

            {!loading && (
              <>
                <button
                  onClick={() => setMode(mode === "voice" ? "text" : "voice")}
                  className="no-print min-h-touch rounded-full border-2 border-mint px-8 text-lg text-mint active:bg-mint active:text-night"
                >
                  {mode === "voice" ? `⌨ ${t.useKeyboard}` : `🎤 ${t.useVoice}`}
                </button>
                <div className="w-full">
                  <p className="mb-3 text-center text-ink-muted">{t.examples}</p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {EXAMPLES[lang].map((ex) => (
                      <button key={ex} onClick={() => ask(ex)} className="min-h-touch rounded-2xl bg-night-700 p-4 text-lg active:bg-night-600">
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </IdleScreen>
  );
}
