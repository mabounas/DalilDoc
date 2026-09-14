import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, Stat, StatusBadge } from "../components/ui";
import { api, type Demarche } from "../lib/api";

export interface AnalyticsData {
  total: number;
  hors_perimetre: number;
  taux_hors_perimetre: number;
  temps_moyen_ms: number;
  au_dela_3s: number;
  par_langue: Record<string, number>;
  par_demarche: Record<string, number>;
  par_borne: Record<string, number>;
  par_jour: Record<string, number>;
  demarches_actives: number;
}

export default function Dashboard() {
  const [stats, setStats] = useState<AnalyticsData | null>(null);
  const [demarches, setDemarches] = useState<Demarche[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<AnalyticsData>("/api/admin/analytics?days=7"), api<Demarche[]>("/api/admin/demarches")])
      .then(([s, d]) => {
        setStats(s);
        setDemarches(d);
      })
      .catch((e) => setError(e.message));
  }, []);

  const alerts = [
    ...(stats && stats.taux_hors_perimetre > 0.3 ? [`Taux hors périmètre élevé : ${Math.round(stats.taux_hors_perimetre * 100)} %`] : []),
    ...(stats && stats.au_dela_3s > 0 ? [`${stats.au_dela_3s} réponse(s) au-delà de 3 s`] : []),
    ...demarches.filter((d) => d.statut === "review").map((d) => `« ${d.titres.fr} » attend une validation`),
  ];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold">Tableau de bord</h1>
      {error && <p className="text-red-600">{error}</p>}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Interactions (7 j)" value={stats?.total ?? "—"} />
        <Stat label="Hors périmètre" value={stats ? `${Math.round(stats.taux_hors_perimetre * 100)} %` : "—"} sub={`${stats?.hors_perimetre ?? 0} questions`} />
        <Stat label="Temps moyen" value={stats ? `${stats.temps_moyen_ms} ms` : "—"} sub="objectif < 3000 ms" />
        <Stat label="Démarches en production" value={stats?.demarches_actives ?? "—"} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Alertes">
          {alerts.length ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">{alerts.map((a) => <li key={a}>{a}</li>)}</ul>
          ) : (
            <p className="text-sm text-slate-500">Aucune alerte.</p>
          )}
        </Card>
        <Card title="Démarches" actions={<Link className="text-sm text-mint" to="/demarches">Tout voir →</Link>}>
          <ul className="divide-y text-sm">
            {demarches.slice(0, 6).map((d) => (
              <li key={d.id} className="flex items-center justify-between py-2">
                <Link to={`/demarches/${d.id}/edit`} className="hover:underline">{d.titres.fr}</Link>
                <StatusBadge statut={d.statut} />
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
