import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Input, Select, StatusBadge } from "../components/ui";
import { api, type Demarche } from "../lib/api";

export default function Demarches() {
  const [items, setItems] = useState<Demarche[]>([]);
  const [q, setQ] = useState("");
  const [statut, setStatut] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (statut) params.set("statut", statut);
    const timer = setTimeout(() => {
      api<Demarche[]>(`/api/admin/demarches?${params}`).then(setItems).catch((e) => setError(e.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [q, statut]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Démarches</h1>
        <Link to="/demarches/new"><Button>+ Nouvelle démarche</Button></Link>
      </div>
      <div className="flex gap-3">
        <Input placeholder="Rechercher (titre, slug)…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm" />
        <Select value={statut} onChange={(e) => setStatut(e.target.value)} className="max-w-[180px]">
          <option value="">Tous les statuts</option>
          {["brouillon", "review", "valide", "production", "inactif"].map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr><th className="p-3">Titre</th><th className="p-3">Catégorie</th><th className="p-3">Statut</th><th className="p-3">Version</th><th className="p-3">Validé par</th><th className="p-3" /></tr>
          </thead>
          <tbody className="divide-y">
            {items.map((d) => (
              <tr key={d.id} className="hover:bg-slate-50">
                <td className="p-3">
                  <p className="font-medium">{d.titres.fr}</p>
                  <p className="text-xs text-slate-400" dir="rtl">{d.titres.ar}</p>
                </td>
                <td className="p-3">{d.categorie}</td>
                <td className="p-3"><StatusBadge statut={d.statut} /></td>
                <td className="p-3">v{d.version}</td>
                <td className="p-3 text-slate-500">{d.valide_par ?? "—"}</td>
                <td className="p-3 text-right">
                  <Link className="mr-3 text-mint hover:underline" to={`/demarches/${d.id}/preview`}>Aperçu</Link>
                  <Link className="text-night hover:underline" to={`/demarches/${d.id}/edit`}>Modifier</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
