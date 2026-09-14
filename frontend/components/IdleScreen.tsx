"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IDLE_TIMEOUT, watchIdle } from "@/kiosk.config";
import { LANGS, T } from "@/lib/i18n";
import { resetSession } from "@/lib/session";

interface Props {
  children: React.ReactNode;
  /** Action à l'expiration ; par défaut retour à l'accueil. */
  onIdle?: () => void;
  timeout?: number;
}

/**
 * Retour à l'accueil après 30 s d'inactivité. Sur l'accueil (pas de `onIdle`),
 * affiche un écran d'attraction animé qui disparaît au premier toucher.
 */
export default function IdleScreen({ children, onIdle, timeout = IDLE_TIMEOUT }: Props) {
  const router = useRouter();
  const [attract, setAttract] = useState(false);
  const [i, setI] = useState(0);

  useEffect(
    () =>
      watchIdle(() => {
        resetSession();
        if (onIdle) onIdle();
        else {
          router.push("/");
          setAttract(true);
        }
      }, timeout),
    [onIdle, router, timeout],
  );

  useEffect(() => {
    if (!attract) return;
    const id = setInterval(() => setI((x) => (x + 1) % LANGS.length), 2500);
    return () => clearInterval(id);
  }, [attract]);

  if (attract) {
    const lang = LANGS[i];
    return (
      <button
        data-testid="attract-screen"
        onClick={() => setAttract(false)}
        onTouchStart={() => setAttract(false)}
        className="flex min-h-screen w-full flex-col items-center justify-center gap-8 bg-night"
      >
        <img src="/logo.svg" alt="WathiqaDoc" className="h-40 w-40 animate-floatY" />
        <p className="text-3xl font-bold text-gold">WathiqaDoc · وثيقة دوك</p>
        <p className="text-2xl" dir={lang === "ar" || lang === "darija" ? "rtl" : "ltr"}>{T[lang].idleTitle}</p>
        <p className="animate-pulse text-xl text-mint" dir={lang === "ar" || lang === "darija" ? "rtl" : "ltr"}>{T[lang].idleTouch}</p>
      </button>
    );
  }
  return <>{children}</>;
}
