export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const LANGS = ["fr", "ar", "darija", "en", "pt", "es"] as const;
export type Lang = (typeof LANGS)[number];
export type Multi = Partial<Record<Lang, string | null>>;

export interface DocumentRequis {
  ordre: number;
  nom: Multi;
  obligatoire: boolean;
  condition: Multi | null;
  format: string[];
}

export interface DemarcheContent {
  slug: string;
  categorie: string;
  titres: Multi;
  mots_cles: Partial<Record<Lang, string[]>>;
  synonymes: Partial<Record<Lang, string[]>>;
  conditions: Multi[];
  documents: DocumentRequis[];
  exceptions: Multi[];
  tarifs: Multi[];
  faq: { question: Multi; reponse: Multi }[];
  administration: string;
  delai_jours: number | null;
  cout_mad: number;
  source_url: string | null;
}

export type Statut = "brouillon" | "review" | "valide" | "production" | "inactif";

export interface Demarche {
  id: string;
  slug: string;
  categorie: string;
  titres: Multi;
  administration: string | null;
  cout_mad: number;
  delai_jours: number | null;
  source_url: string | null;
  statut: Statut;
  version: number;
  valide_par: string | null;
  contenu: DemarcheContent;
}

const TOKEN_KEY = "wathiqadoc-admin-token";
const REFRESH_KEY = "wathiqadoc-admin-refresh";

// sessionStorage : la session admin ne survit pas à la fermeture du navigateur.
export const auth = {
  get token() {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  save(access: string, refresh: string) {
    sessionStorage.setItem(TOKEN_KEY, access);
    sessionStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  },
};

async function refreshToken(): Promise<boolean> {
  const refresh = sessionStorage.getItem(REFRESH_KEY);
  if (!refresh) return false;
  const res = await fetch(`${API_URL}/api/admin/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return false;
  const body = await res.json();
  auth.save(body.access_token, body.refresh_token);
  return true;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}), ...init.headers },
  });
  if (res.status === 401 && retry && (await refreshToken())) return api<T>(path, init, false);
  if (res.status === 401) {
    auth.clear();
    window.location.assign("/login");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* corps non JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await res.json()) as T;
}

export async function login(email: string, password: string, totp?: string) {
  const res = await fetch(`${API_URL}/api/admin/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, totp: totp || null }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Échec de connexion");
  const body = await res.json();
  auth.save(body.access_token, body.refresh_token);
  return body as { role: string };
}

export const emptyContent = (): DemarcheContent => ({
  slug: "",
  categorie: "identite",
  titres: { fr: "" },
  mots_cles: {},
  synonymes: {},
  conditions: [],
  documents: [],
  exceptions: [],
  tarifs: [],
  faq: [],
  administration: "",
  delai_jours: null,
  cout_mad: 0,
  source_url: null,
});
