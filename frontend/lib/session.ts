/** Session anonyme : UUID en mémoire uniquement (aucun cookie, reset à chaque retour accueil). */
let current: string | null = null;

const uuid = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
      });

export const getSessionId = () => (current ??= uuid());
export const resetSession = () => {
  current = null;
};
