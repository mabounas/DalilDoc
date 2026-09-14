import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Select, Stat } from "../components/ui";
import { api } from "../lib/api";
import type { AnalyticsData } from "./Dashboard";

const COLORS = ["#2A9D8F", "#C9A84C", "#0D0D20", "#6B7FD7", "#E76F51", "#8AB17D"];

interface Interaction {
  id: string;
  borne_id: string;
  requete: string;
  langue: string;
  demarche: string | null;
  score: number;
  hors_perimetre: boolean;
  temps_ms: number;
  cree_le: string;
}

const toSeries = (o: Record<string, number>) => Object.entries(o).map(([name, value]) => ({ name, value }));

export default function Analytics() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [items, setItems] = useState<Interaction[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AnalyticsData>(`/api/admin/analytics?days=${days}`).then(setData).catch((e) => setError(e.message));
    api<{ items: Interaction[] }>("/api/admin/interactions?limit=50").then((r) => setItems(r.items)).catch(() => undefined);
  }, [days]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analytics (données anonymisées)</h1>
        <Select value={days} onChange={(e) => setDays(Number(e.target.value))} className="max-w-[160px]">
          {[7, 30, 90].map((d) => <option key={d} value={d}>{d} jours</option>)}
        </Select>
      </div>
      {error && <p className="text-red-600">{error}</p>}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Interactions" value={data.total} />
            <Stat label="Hors périmètre" value={`${Math.round(data.taux_hors_perimetre * 100)} %`} />
            <Stat label="Temps moyen" value={`${data.temps_moyen_ms} ms`} />
            <Stat label="> 3 s" value={data.au_dela_3s} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Interactions par jour">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={toSeries(data.par_jour)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#2A9D8F" strokeWidth={2} name="Interactions" />
                </LineChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Langues détectées">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={toSeries(data.par_langue)} dataKey="value" nameKey="name" outerRadius={90} label>
                    {toSeries(data.par_langue).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Démarches demandées" className="lg:col-span-2">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={toSeries(data.par_demarche)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#C9A84C" name="Questions" />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </>
      )}
      <Card title="Dernières interactions">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr><th className="p-2">Date</th><th className="p-2">Borne</th><th className="p-2">Requête (expurgée)</th><th className="p-2">Langue</th><th className="p-2">Démarche</th><th className="p-2">Score</th><th className="p-2">ms</th></tr>
            </thead>
            <tbody className="divide-y">
              {items.map((i) => (
                <tr key={i.id} className={i.hors_perimetre ? "bg-amber-50" : ""}>
                  <td className="p-2 text-slate-500">{new Date(i.cree_le).toLocaleString("fr-MA")}</td>
                  <td className="p-2">{i.borne_id}</td>
                  <td className="p-2" dir="auto">{i.requete}</td>
                  <td className="p-2">{i.langue}</td>
                  <td className="p-2">{i.demarche ?? "hors périmètre"}</td>
                  <td className="p-2">{i.score?.toFixed(2)}</td>
                  <td className="p-2">{i.temps_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
