import { useEffect, useState } from "react";
import { Card } from "../components/ui";
import { API_URL, LANGS, api } from "../lib/api";
import type { AnalyticsData } from "./Dashboard";

interface Health {
  status: string;
  services: Record<string, string>;
  rag_mode: string;
}

/** Paramètres : état des services, bornes actives et langues (configuration via variables d'environnement). */
export default function Settings() {
  const [health, setHealth] = useState<Health | null>(null);
  const [bornes, setBornes] = useState<Record<string, number>>({});
  const [me, setMe] = useState<{ email: string; role: string; totp: boolean } | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/health`).then((r) => r.json()).then(setHealth).catch(() => undefined);
    api<AnalyticsData>("/api/admin/analytics?days=30").then((a) => setBornes(a.par_borne)).catch(() => undefined);
    api<{ email: string; role: string; totp: boolean }>("/api/admin/me").then(setMe).catch(() => undefined);
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold">Paramètres</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Services">
          {health ? (
            <ul className="space-y-1 text-sm">
              <li>Statut global : <b className={health.status === "ok" ? "text-emerald-700" : "text-amber-700"}>{health.status}</b></li>
              <li>Moteur RAG : <b>{health.rag_mode}</b></li>
              {Object.entries(health.services).map(([k, v]) => <li key={k}>{k} : {v}</li>)}
            </ul>
          ) : <p className="text-sm text-slate-500">API injoignable ({API_URL}).</p>}
        </Card>
        <Card title="Bornes actives (30 j)">
          <ul className="space-y-1 text-sm">
            {Object.entries(bornes).map(([b, n]) => <li key={b}><b>{b}</b> — {n} interactions</li>)}
            {!Object.keys(bornes).length && <li className="text-slate-500">Aucune activité.</li>}
          </ul>
          <p className="mt-3 text-xs text-slate-500">Identifiant d'une borne : variable <code>NEXT_PUBLIC_BORNE_ID</code> du frontend.</p>
        </Card>
        <Card title="Langues supportées">
          <div className="flex flex-wrap gap-2">{LANGS.map((l) => <span key={l} className="rounded-full bg-slate-100 px-3 py-1 text-sm">{l}</span>)}</div>
          <p className="mt-3 text-xs text-slate-500">Configurable côté API via <code>SUPPORTED_LANGUAGES</code>.</p>
        </Card>
        <Card title="Mon compte">
          {me && (
            <ul className="space-y-1 text-sm">
              <li>{me.email}</li>
              <li>Rôle : <b>{me.role}</b></li>
              <li>2FA : {me.totp ? "activée" : me.role === "super-admin" ? "⚠ à activer (totp_secret)" : "non requise"}</li>
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
