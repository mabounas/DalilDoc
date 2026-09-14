import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LANGS, api, type Lang } from "../lib/api";

interface PreviewData {
  titre: string | null;
  cout_mad: number | null;
  documents: { ordre: number; nom: string | null; obligatoire: boolean; condition: string | null }[];
}

/** Prévisualisation du rendu borne (couleurs et tailles de la borne). */
export default function Preview() {
  const { id } = useParams();
  const [lang, setLang] = useState<Lang>("fr");
  const [data, setData] = useState<PreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<PreviewData>(`/api/admin/demarches/${id}/preview?langue=${lang}`).then(setData).catch((e) => setError(e.message));
  }, [id, lang]);

  const rtl = lang === "ar" || lang === "darija";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Aperçu borne</h1>
        <Link to={`/demarches/${id}/edit`} className="text-sm text-mint">← Retour à l'édition</Link>
      </div>
      <div className="flex gap-2">
        {LANGS.map((l) => (
          <button key={l} onClick={() => setLang(l)} className={`rounded-md px-3 py-1 text-sm ${l === lang ? "bg-night text-white" : "bg-slate-200"}`}>{l}</button>
        ))}
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <div className="mx-auto w-full max-w-[720px] rounded-[32px] border-8 border-slate-800 bg-[#0D0D20] p-8 text-[#F4F1E8]" dir={rtl ? "rtl" : "ltr"}>
        <h2 className="text-2xl font-bold text-[#C9A84C]">{data?.titre ?? "— titre manquant dans cette langue —"}</h2>
        <ol className="mt-6 flex flex-col gap-4">
          {data?.documents.map((d) => (
            <li key={d.ordre} className="flex gap-4 text-xl">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#2A9D8F] font-bold text-[#0D0D20]">{d.ordre}</span>
              <span>
                {d.nom ?? <i className="text-red-300">traduction manquante</i>}
                {(d.condition || !d.obligatoire) && <span className="block text-base text-slate-400">{[!d.obligatoire && "facultatif", d.condition].filter(Boolean).join(" · ")}</span>}
              </span>
            </li>
          ))}
        </ol>
        {data?.cout_mad ? <p className="mt-6 text-lg text-[#C9A84C]">{data.cout_mad} MAD</p> : null}
      </div>
    </div>
  );
}
