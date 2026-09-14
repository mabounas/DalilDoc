"use client";

import { useEffect } from "react";
import { installKioskGuards, registerServiceWorker } from "@/kiosk.config";
import { refreshPack } from "@/lib/offline";

/** Layout plein écran sans navigation : garde-fous kiosque + préchargement du cache hors ligne. */
export default function KioskLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const cleanup = installKioskGuards();
    registerServiceWorker();
    refreshPack();
    const interval = setInterval(refreshPack, 60 * 60 * 1000);
    return () => {
      cleanup();
      clearInterval(interval);
    };
  }, []);

  return <main className="relative flex min-h-screen w-full flex-col overflow-hidden bg-night">{children}</main>;
}
