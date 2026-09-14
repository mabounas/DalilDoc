"use client";

import { useEffect, useState } from "react";
import { LANG_META, LANGS, T, type Lang } from "@/lib/i18n";

const INVITE_DELAY_MS = 5000;

/** 6 boutons de langue (texte natif + drapeau) ; invitation vocale animée après 5 s. */
export default function LanguageSelector({ onSelect }: { onSelect: (lang: Lang) => void }) {
  const [invite, setInvite] = useState(false);
  const [greeting, setGreeting] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setInvite(true), INVITE_DELAY_MS);
    const rotate = setInterval(() => setGreeting((g) => (g + 1) % LANGS.length), 2500);
    return () => {
      clearTimeout(timer);
      clearInterval(rotate);
    };
  }, []);

  const current = LANGS[greeting];

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-10 px-6 py-10">
      <img src="/logo.svg" alt="WathiqaDoc" className="h-28 w-28" />
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gold">WathiqaDoc · وثيقة دوك</h1>
        <p className="mt-3 text-2xl" dir={current === "ar" || current === "darija" ? "rtl" : "ltr"} aria-live="polite">
          {T[current].welcome} — {T[current].chooseLang}
        </p>
      </div>

      <div className="grid w-full max-w-3xl grid-cols-2 gap-5 md:grid-cols-3">
        {LANGS.map((lang) => (
          <button
            key={lang}
            onClick={() => onSelect(lang)}
            lang={LANG_META[lang].htmlLang}
            className="flex min-h-[110px] flex-col items-center justify-center gap-2 rounded-3xl border-2 border-night-600 bg-night-700 text-2xl font-semibold transition active:scale-95 active:border-gold"
          >
            <span className="text-4xl" aria-hidden>{LANG_META[lang].flag}</span>
            {LANG_META[lang].native}
          </button>
        ))}
      </div>

      {invite && (
        <div data-testid="voice-invite" className="flex items-center gap-4 text-xl text-mint">
          <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-mint text-3xl text-night">
            <span className="absolute inset-0 animate-pulseRing rounded-full bg-mint" />🎤
          </span>
          <span dir={current === "ar" || current === "darija" ? "rtl" : "ltr"}>{T[current].tapToSpeak}</span>
        </div>
      )}
    </div>
  );
}
