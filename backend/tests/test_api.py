"""Tests d'intégration de l'API (CDC §12)."""

import base64
import time
from concurrent.futures import ThreadPoolExecutor

from app.middleware.security import anonymize_text, anonymous_session_id, hash_password, totp_now, verify_password, verify_totp


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["services"]["database"] == "ok" and body["rag_mode"] == "local"


def test_demarches_actives(client):
    r = client.get("/api/v1/demarches")
    slugs = {d["slug"] for d in r.json()}
    assert {"cin-premiere-demande", "cin-renouvellement", "cin-perte-vol-deterioration"} <= slugs


def test_query_cin_fr(client):
    """'Documents pour CIN' → liste correcte en FR."""
    r = client.post("/api/v1/query", json={"text": "Documents pour CIN", "borne_id": "b1", "langue": "fr"})
    assert r.status_code == 200
    body = r.json()
    assert body["langue"] == "fr" and not body["hors_perimetre"]
    noms = " ".join(d["nom"] for d in body["documents"])
    assert "Certificat de résidence" in noms and "photographies" in noms
    assert body["temps_ms"] < 3000


def test_query_cin_ar(client):
    r = client.post("/api/v1/query", json={"text": "ما هي الوثائق المطلوبة للبطاقة الوطنية لأول مرة", "borne_id": "b1"})
    body = r.json()
    assert body["langue"] == "ar" and not body["hors_perimetre"]
    assert any("شهادة الإقامة" in d["nom"] for d in body["documents"])


def test_query_hors_perimetre(client):
    """'Météo à Casablanca' → orientation guichet."""
    r = client.post("/api/v1/query", json={"text": "Météo à Casablanca", "borne_id": "b1", "langue": "fr"})
    body = r.json()
    assert body["hors_perimetre"] is True
    assert "guichet" in body["reponse"]


def test_rate_limit(client):
    for _ in range(30):
        assert client.post("/api/v1/query", json={"text": "CIN", "borne_id": "rl"}).status_code == 200
    assert client.post("/api/v1/query", json={"text": "CIN", "borne_id": "rl"}).status_code == 429


def test_voice_sans_cle(client):
    audio = base64.b64encode(b"\x1aE\xdf\xa3fake-webm").decode()
    assert client.post("/api/v1/voice/transcribe", json={"audio": audio, "borne_id": "v"}).status_code == 503
    assert client.post("/api/v1/voice/transcribe", json={"audio": "@@not-base64@@", "borne_id": "v"}).status_code == 400
    assert client.post("/api/v1/voice/synthesize", json={"text": "Bonjour", "langue": "fr"}).status_code == 503
    assert client.get("/api/v1/voice/capabilities").json() == {"stt": False, "tts": False}


def test_concurrent_bornes(client):
    """10 bornes simultanées sans dégradation."""
    def ask(i):
        t = time.perf_counter()
        r = client.post("/api/v1/query", json={"text": "renouvellement carte d'identité", "borne_id": f"borne-{i}"})
        return r.status_code, time.perf_counter() - t

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(ask, range(10)))
    assert all(code == 200 for code, _ in results)
    assert max(d for _, d in results) < 3


def test_anonymisation_session(client, admin_headers):
    """session_id jamais lié à une identité ; données personnelles expurgées du journal."""
    assert anonymous_session_id("pas-un-uuid") != "pas-un-uuid"
    assert "AB123456" not in anonymize_text("Ma CIN AB123456, tel 0612345678, mail a@b.ma")
    client.post("/api/v1/query", json={"text": "J'ai perdu ma CIN BK654321, appelez le 0612345678", "borne_id": "anon"})
    items = client.get("/api/admin/interactions", headers=admin_headers).json()["items"]
    logged = next(i for i in items if i["borne_id"] == "anon")
    assert "BK654321" not in logged["requete"] and "0612345678" not in logged["requete"]


def test_offline_cache(client):
    body = client.get("/api/v1/offline-cache").json()
    assert body["demarches"] and {c["langue"] for c in body["chunks"]} == {"fr", "ar"}


def test_passwords_et_totp():
    h = hash_password("x")
    assert verify_password("x", h) and not verify_password("y", h)
    secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp(secret, totp_now(secret)) and not verify_totp(secret, "000000" if totp_now(secret) != "000000" else "111111")


def test_admin_auth_requise(client):
    assert client.get("/api/admin/demarches").status_code == 401
    assert client.post("/api/admin/auth/login", json={"email": "admin@test.ma", "password": "faux"}).status_code == 401


def test_workflow_publication_et_rollback(client, admin_headers):
    """BROUILLON → REVIEW → PRODUCTION, versionnement, borne mise à jour, rollback."""
    demarches = client.get("/api/admin/demarches", headers=admin_headers).json()
    d = next(x for x in demarches if x["slug"] == "cin-premiere-demande")
    contenu = d["contenu"]
    body = {k: contenu.get(k) for k in ("slug", "categorie", "titres", "mots_cles", "synonymes", "conditions", "documents", "exceptions",
                                        "tarifs", "faq", "administration", "delai_jours", "cout_mad", "source_url")}
    body["documents"] = body["documents"] + [{"ordre": 99, "nom": {"fr": "Pièce de test WathiqaDoc"}, "obligatoire": True,
                                              "condition": None, "format": []}]

    r = client.put(f"/api/admin/demarches/{d['id']}", json=body, headers=admin_headers)
    assert r.status_code == 200 and r.json()["statut"] == "brouillon" and r.json()["version"] == d["version"] + 1

    # Le brouillon n'est pas encore visible sur la borne.
    q = client.post("/api/v1/query", json={"text": "Documents pour CIN", "borne_id": "wf", "langue": "fr"}).json()
    assert all("Pièce de test" not in doc["nom"] for doc in q["documents"])

    assert client.post(f"/api/admin/demarches/{d['id']}/submit", headers=admin_headers).json()["statut"] == "review"
    pub = client.post(f"/api/admin/demarches/{d['id']}/publish", headers=admin_headers)
    assert pub.status_code == 200 and pub.json()["statut"] == "production"

    q = client.post("/api/v1/query", json={"text": "Documents pour CIN", "borne_id": "wf", "langue": "fr"}).json()
    assert any("Pièce de test" in doc["nom"] for doc in q["documents"])

    versions = client.get(f"/api/admin/demarches/{d['id']}/versions", headers=admin_headers).json()
    assert [v["version"] for v in versions][:2] == [d["version"] + 1, d["version"]]
    rb = client.post(f"/api/admin/demarches/{d['id']}/rollback/{d['version']}", headers=admin_headers)
    assert rb.status_code == 200
    client.post(f"/api/admin/demarches/{d['id']}/publish", headers=admin_headers)
    q = client.post("/api/v1/query", json={"text": "Documents pour CIN", "borne_id": "wf", "langue": "fr"}).json()
    assert all("Pièce de test" not in doc["nom"] for doc in q["documents"])


def test_analytics(client, admin_headers):
    body = client.get("/api/admin/analytics", headers=admin_headers).json()
    assert body["total"] > 0 and "fr" in body["par_langue"]
