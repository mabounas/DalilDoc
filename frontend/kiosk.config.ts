/**
 * Mode kiosque (CDC §07, PROMPT 9) : navigation navigateur bloquée,
 * retour automatique à l'accueil après 30 s d'inactivité, service worker
 * pour le mode hors ligne.
 */
export const IDLE_TIMEOUT = 30_000; // 30 secondes
export const KIOSK_MODE = (process.env.NEXT_PUBLIC_KIOSK_MODE ?? "true") === "true";

const ACTIVITY_EVENTS = ["touchstart", "mousemove", "mousedown", "keypress", "scroll"] as const;

/** Installe les garde-fous kiosque ; retourne une fonction de nettoyage. */
export function installKioskGuards(): () => void {
  if (!KIOSK_MODE) return () => {};
  const noContext = (e: Event) => e.preventDefault();
  const noReload = (e: KeyboardEvent) => {
    const k = e.key.toLowerCase();
    if (e.key === "F5" || e.key === "F11" || e.key === "F12" || ((e.ctrlKey || e.metaKey) && ["r", "w", "p", "l", "t"].includes(k)) || (e.altKey && e.key === "ArrowLeft")) {
      e.preventDefault();
    }
  };
  document.addEventListener("contextmenu", noContext);
  document.addEventListener("keydown", noReload);
  return () => {
    document.removeEventListener("contextmenu", noContext);
    document.removeEventListener("keydown", noReload);
  };
}

/** Appelle `onIdle` après IDLE_TIMEOUT sans interaction ; retourne le nettoyage. */
export function watchIdle(onIdle: () => void, timeout = IDLE_TIMEOUT): () => void {
  let idleTimer: ReturnType<typeof setTimeout>;
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(onIdle, timeout);
  };
  ACTIVITY_EVENTS.forEach((ev) => window.addEventListener(ev, resetIdle, { passive: true }));
  resetIdle();
  return () => {
    clearTimeout(idleTimer);
    ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, resetIdle));
  };
}

const SW_UPDATE_INTERVAL = 10 * 60_000;

/**
 * Enregistre le service worker et garde la borne à jour : une borne ne recharge
 * jamais sa page, donc on vérifie les mises à jour périodiquement et, quand une
 * nouvelle version prend la main, on recharge — uniquement sur l'écran d'accueil,
 * jamais pendant qu'un citoyen utilise la borne.
 */
export function registerServiceWorker(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
  const hadController = !!navigator.serviceWorker.controller;
  let updatePending = false;

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController) updatePending = true; // première installation : rien à recharger
  });
  navigator.serviceWorker
    .register("/sw.js")
    .then((reg) => setInterval(() => reg.update().catch(() => undefined), SW_UPDATE_INTERVAL))
    .catch(() => undefined);

  setInterval(() => {
    if (updatePending && window.location.pathname === "/") window.location.reload();
  }, 2000);
}
