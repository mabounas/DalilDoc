/**
 * Mode dégradé (CDC §07, PROMPT 9) : le paquet `/api/v1/offline-cache`
 * (démarches + chunks FR/AR) est conservé localement ; sans réseau, on
 * répond à partir de ce cache par simple recouvrement lexical — jamais
 * au-delà de ce qu'il contient.
 */
import { API_URL, type QueryResult } from "./api";
import type { Lang } from "./i18n";

const CACHE_KEY = "wathiqadoc-offline-v1";

export interface OfflineDemarche {
  slug: string;
  langue: "fr" | "ar";
  titre: string;
  cout_mad: number | null;
  source_url: string | null;
  documents: QueryResult["documents"];
}

export interface OfflineChunk {
  demarche_slug: string;
  langue: string;
  contenu: string;
}

export interface OfflinePack {
  demarches: OfflineDemarche[];
  chunks: OfflineChunk[];
  saved_at?: string;
}

const normalize = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ًͯ-ٰٟ]/g, "")
    .replace(/[إأآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي");

const tokens = (s: string) => new Set(normalize(s).match(/[\p{L}\p{N}]{3,}/gu) ?? []);

export function loadPack(): OfflinePack | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as OfflinePack) : null;
  } catch {
    return null;
  }
}

export async function refreshPack(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/v1/offline-cache`);
    if (!res.ok) return false;
    const pack = (await res.json()) as OfflinePack;
    localStorage.setItem(CACHE_KEY, JSON.stringify({ ...pack, saved_at: new Date().toISOString() }));
    return true;
  } catch {
    return false;
  }
}

export function answerOffline(question: string, lang: Lang, pack: OfflinePack | null = loadPack()): QueryResult | null {
  if (!pack) return null;
  const cacheLang = lang === "ar" || lang === "darija" ? "ar" : "fr";
  const q = tokens(question);
  if (q.size === 0) return null;
  let best: { slug: string; score: number } | null = null;
  for (const chunk of pack.chunks) {
    if (chunk.langue !== cacheLang) continue;
    const c = tokens(chunk.contenu);
    let overlap = 0;
    q.forEach((t) => {
      if (c.has(t)) overlap += 1;
    });
    const score = overlap / q.size;
    if (!best || score > best.score) best = { slug: chunk.demarche_slug, score };
  }
  const found = best && best.score >= 0.34 ? pack.demarches.find((d) => d.slug === best!.slug && d.langue === cacheLang) : undefined;
  if (!found) return null;
  return {
    reponse: found.titre,
    langue: cacheLang,
    demarche_id: found.slug,
    documents: found.documents,
    score_confiance: best!.score,
    hors_perimetre: false,
    sources: found.source_url ? [found.source_url] : [],
    temps_ms: 0,
    offline: true,
  };
}
