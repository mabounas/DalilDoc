import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button, Card, Input, Label, Select, StatusBadge, Textarea } from "../components/ui";
import { api, emptyContent, LANGS, type Demarche, type DemarcheContent, type DocumentRequis, type Lang, type Multi } from "../lib/api";

const LANG_LABEL: Record<Lang, string> = { fr: "Français", ar: "العربية", darija: "Darija", en: "English", pt: "Português", es: "Español" };
const RTL = (l: Lang) => l === "ar" || l === "darija";
const CATEGORIES = [["identite", "Identité"], ["logement", "Logement"], ["reclamation", "Réclamation"], ["autre", "Autre"]];

/** Textarea « un élément par ligne » pour une liste multilingue, dans la langue active. */
function MultiLines({ items, lang, onChange }: { items: Multi[]; lang: Lang; onChange: (items: Multi[]) => void }) {
  const text = items.map((i) => i[lang] ?? "").join("\n");
  return (
    <Textarea
      dir={RTL(lang) ? "rtl" : "ltr"}
      rows={Math.max(3, items.length + 1)}
      value={text}
      onChange={(e) => {
        const lines = e.target.value.split("\n");
        const next = lines.map((line, idx) => ({ ...(items[idx] ?? {}), [lang]: line }));
        // Supprime les éléments entièrement vides (toutes langues) en fin de liste.
        while (next.length && Object.values(next[next.length - 1]).every((v) => !v)) next.pop();
        onChange(next);
      }}
    />
  );
}

export default function DemarcheForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lang, setLang] = useState<Lang>("fr");
  const [data, setData] = useState<DemarcheContent>(emptyContent());
  const [meta, setMeta] = useState<Demarche | null>(null);
  const [versions, setVersions] = useState<{ version: number; auteur: string | null; cree_le: string }[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!id) return;
    const d = await api<Demarche>(`/api/admin/demarches/${id}`);
    setMeta(d);
    setData({ ...emptyContent(), ...d.contenu });
    setVersions(await api(`/api/admin/demarches/${id}/versions`));
  };

  useEffect(() => {
    load().catch((e) => setMessage({ type: "err", text: e.message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const set = <K extends keyof DemarcheContent>(key: K, value: DemarcheContent[K]) => setData((d) => ({ ...d, [key]: value }));

  const setDoc = (idx: number, patch: Partial<DocumentRequis>) =>
    set("documents", data.documents.map((doc, i) => (i === idx ? { ...doc, ...patch } : doc)));

  const reorder = (from: number, to: number) => {
    const docs = [...data.documents];
    const [moved] = docs.splice(from, 1);
    docs.splice(to, 0, moved);
    set("documents", docs.map((d, i) => ({ ...d, ordre: i + 1 })));
  };

  const run = async (label: string, fn: () => Promise<Demarche>) => {
    setBusy(true);
    setMessage(null);
    try {
      const d = await fn();
      setMeta(d);
      setData({ ...emptyContent(), ...d.contenu });
      setMessage({ type: "ok", text: label });
      if (!id) navigate(`/demarches/${d.id}/edit`, { replace: true });
      else setVersions(await api(`/api/admin/demarches/${d.id}/versions`));
    } catch (e) {
      setMessage({ type: "err", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const payload = () => JSON.stringify({ ...data, documents: data.documents.map((d, i) => ({ ...d, ordre: i + 1 })) });
  const saveDraft = () =>
    run("Brouillon enregistré (nouvelle version)", () =>
      id ? api(`/api/admin/demarches/${id}`, { method: "PUT", body: payload() }) : api("/api/admin/demarches", { method: "POST", body: payload() }));

  const action = (path: string, label: string) => run(label, () => api(`/api/admin/demarches/${meta!.id}/${path}`, { method: "POST" }));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">{id ? "Modifier la démarche" : "Nouvelle démarche"}</h1>
          {meta && <StatusBadge statut={meta.statut} />}
          {meta && <span className="text-sm text-slate-500">v{meta.version}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={saveDraft} disabled={busy}>Enregistrer brouillon</Button>
          {meta && <Button variant="outline" onClick={() => action("submit", "Soumis en review")} disabled={busy}>Soumettre review</Button>}
          {meta && <Button variant="success" onClick={() => action("publish", "Validé & publié : borne mise à jour")} disabled={busy}>Valider & Publier</Button>}
          {meta && meta.statut !== "inactif" && <Button variant="destructive" onClick={() => action("deactivate", "Démarche désactivée")} disabled={busy}>Désactiver</Button>}
          {meta && <Link to={`/demarches/${meta.id}/preview`}><Button variant="ghost">Aperçu borne</Button></Link>}
        </div>
      </div>
      {message && <p className={message.type === "ok" ? "text-emerald-700" : "text-red-600"}>{message.text}</p>}

      <div className="flex gap-1 rounded-lg bg-slate-200 p-1">
        {LANGS.map((l) => (
          <button key={l} onClick={() => setLang(l)} className={`flex-1 rounded-md px-3 py-1.5 text-sm ${lang === l ? "bg-white font-semibold shadow" : "text-slate-600"}`}>
            {LANG_LABEL[l]}
          </button>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="flex flex-col gap-5 lg:col-span-2">
          <Card title="Informations générales">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Catégorie</Label>
                <Select value={data.categorie} onChange={(e) => set("categorie", e.target.value)}>
                  {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </div>
              <div>
                <Label hint="a-z, 0-9, -">Slug</Label>
                <Input value={data.slug} onChange={(e) => set("slug", e.target.value)} disabled={!!id} pattern="[a-z0-9-]{3,100}" />
              </div>
              <div className="md:col-span-2">
                <Label hint={LANG_LABEL[lang]}>Titre</Label>
                <Input dir={RTL(lang) ? "rtl" : "ltr"} value={data.titres[lang] ?? ""} onChange={(e) => set("titres", { ...data.titres, [lang]: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <Label>Administration responsable</Label>
                <Input value={data.administration} onChange={(e) => set("administration", e.target.value)} />
              </div>
              <div>
                <Label>Délai de traitement (jours)</Label>
                <Input type="number" min={0} value={data.delai_jours ?? ""} onChange={(e) => set("delai_jours", e.target.value === "" ? null : Number(e.target.value))} />
              </div>
              <div>
                <Label>Coût (MAD)</Label>
                <Input type="number" min={0} step="0.01" value={data.cout_mad} onChange={(e) => set("cout_mad", Number(e.target.value))} />
              </div>
              <div className="md:col-span-2">
                <Label>URL source officielle</Label>
                <Input type="url" value={data.source_url ?? ""} onChange={(e) => set("source_url", e.target.value || null)} />
              </div>
              <div className="md:col-span-2">
                <Label hint="séparés par des virgules — orientent vers cette démarche">Mots-clés ({LANG_LABEL[lang]})</Label>
                <Input dir={RTL(lang) ? "rtl" : "ltr"} value={(data.mots_cles[lang] ?? []).join(", ")}
                  onChange={(e) => set("mots_cles", { ...data.mots_cles, [lang]: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
              </div>
            </div>
          </Card>

          <Card title={`Documents requis (${data.documents.length})`} actions={
            <Button variant="outline" onClick={() => set("documents", [...data.documents, { ordre: data.documents.length + 1, nom: {}, obligatoire: true, condition: null, format: [] }])}>+ Document</Button>
          }>
            <p className="mb-3 text-xs text-slate-500">Glissez-déposez pour réordonner. Champs affichés : {LANG_LABEL[lang]}.</p>
            <ol className="flex flex-col gap-3">
              {data.documents.map((doc, i) => (
                <li
                  key={i}
                  draggable
                  onDragStart={() => setDragIndex(i)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (dragIndex !== null && dragIndex !== i) reorder(dragIndex, i);
                    setDragIndex(null);
                  }}
                  className={`grid grid-cols-[28px_1fr_auto] gap-3 rounded-lg border p-3 ${dragIndex === i ? "border-gold bg-amber-50" : "border-slate-200"}`}
                >
                  <span className="cursor-grab select-none pt-2 text-center text-slate-400" title="Déplacer">⋮⋮ {i + 1}</span>
                  <div className="grid gap-2 md:grid-cols-2">
                    <Input dir={RTL(lang) ? "rtl" : "ltr"} placeholder={`Nom (${lang})`} value={doc.nom[lang] ?? ""} onChange={(e) => setDoc(i, { nom: { ...doc.nom, [lang]: e.target.value } })} className="md:col-span-2" />
                    <Input dir={RTL(lang) ? "rtl" : "ltr"} placeholder={`Condition (${lang})`} value={doc.condition?.[lang] ?? ""} onChange={(e) => setDoc(i, { condition: { ...(doc.condition ?? {}), [lang]: e.target.value } })} />
                    <Input placeholder="Format (ex. original, copie)" value={doc.format.join(", ")} onChange={(e) => setDoc(i, { format: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={doc.obligatoire} onChange={(e) => setDoc(i, { obligatoire: e.target.checked })} /> Obligatoire
                    </label>
                  </div>
                  <Button variant="ghost" onClick={() => set("documents", data.documents.filter((_, j) => j !== i))} aria-label="Supprimer">✕</Button>
                </li>
              ))}
            </ol>
          </Card>

          <Card title="Conditions d'éligibilité" actions={<span className="text-xs text-slate-400">une par ligne</span>}>
            <MultiLines items={data.conditions} lang={lang} onChange={(v) => set("conditions", v)} />
          </Card>
          <Card title="Exceptions & cas particuliers" actions={<span className="text-xs text-slate-400">une par ligne</span>}>
            <MultiLines items={data.exceptions} lang={lang} onChange={(v) => set("exceptions", v)} />
          </Card>
          <Card title="Tarifs & délais" actions={<span className="text-xs text-slate-400">une par ligne</span>}>
            <MultiLines items={data.tarifs} lang={lang} onChange={(v) => set("tarifs", v)} />
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card title="Workflow">
            <ol className="space-y-2 text-sm">
              {["brouillon", "review", "valide", "production"].map((s, i) => (
                <li key={s} className={`flex items-center gap-2 ${meta?.statut === s ? "font-semibold text-night" : "text-slate-400"}`}>
                  <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${meta?.statut === s ? "bg-gold text-night" : "bg-slate-200"}`}>{i + 1}</span>
                  {s.toUpperCase()}
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-slate-500">La borne sert toujours la dernière version <b>publiée</b> : un brouillon n'affecte pas les citoyens.</p>
          </Card>
          {meta && (
            <Card title="Historique des versions">
              <ul className="divide-y text-sm">
                {versions.map((v) => (
                  <li key={v.version} className="flex items-center justify-between py-2">
                    <span>
                      <b>v{v.version}</b> <span className="text-slate-500">{v.auteur}</span>
                      <br />
                      <span className="text-xs text-slate-400">{new Date(v.cree_le).toLocaleString("fr-MA")}</span>
                    </span>
                    {v.version !== meta.version && (
                      <Button variant="ghost" onClick={() => run(`Restauré depuis v${v.version} (à republier)`, () => api(`/api/admin/demarches/${meta.id}/rollback/${v.version}`, { method: "POST" }))}>
                        Restaurer
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
