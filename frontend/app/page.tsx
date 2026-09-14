"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import IdleScreen from "@/components/IdleScreen";
import LanguageSelector from "@/components/LanguageSelector";
import type { Lang } from "@/lib/i18n";
import { resetSession } from "@/lib/session";

/** Écran d'accueil : sélection de la langue. */
export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    resetSession();
    document.documentElement.dir = "ltr";
  }, []);

  return (
    <IdleScreen>
      <LanguageSelector onSelect={(lang: Lang) => router.push(`/${lang}`)} />
    </IdleScreen>
  );
}
