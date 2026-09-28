"""Banc de sonde.py : jugement d'une reponse, rejeu, temoin, ecriture du releve."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import configuration  # noqa: E402
import sonde  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent

VERSION_OK = json.dumps({"service": "verify-service", "service_version": "7.10.2"}).encode()
REGISTRE_OK = json.dumps({"mdoc": {"anchors": [{"x": 1}]}, "sd_jwt_vc": {"anchors": []}}).encode()
REGISTRE_VIDE = json.dumps({"mdoc": {"anchors": []}, "sd_jwt_vc": {"anchors": []}}).encode()

CONFIG = {
    "fuseau": "Europe/Paris",
    "jours": 15,
    "plafond_intervalle_min": 15,
    "temoins": ["https://temoin.test/a", "https://temoin.test/b"],
    "plateformes": [
        {
            "id": "production",
            "nom": {"fr": "P", "en": "P", "es": "P"},
            "description": {"fr": "d", "en": "d", "es": "d"},
            "sondes": [
                {"nom": "api", "url": "https://p.test/version", "attendu": "version"},
                {"nom": "registre", "url": "https://p.test/reg", "attendu": "registre"},
            ],
        },
        {
            "id": "integration",
            "nom": {"fr": "I", "en": "I", "es": "I"},
            "description": {"fr": "d", "en": "d", "es": "d"},
            "sondes": [{"nom": "api", "url": "https://i.test/version", "attendu": "version"}],
        },
    ],
}

T0 = datetime(2026, 9, 28, 10, 15, 0, tzinfo=timezone.utc)


class Lecteur:
    """Rend, pour chaque URL, les reponses prevues dans l'ordre des appels."""

    def __init__(self, reponses, defaut=None):
        self.reponses = {u: list(r) for u, r in reponses.items()}
        self.defaut = defaut
        self.appels = []

    def __call__(self, url):
        self.appels.append(url)
        file = self.reponses.get(url)
        rep = file.pop(0) if file else self.defaut
        if rep is None:
            raise AssertionError(f"appel imprevu : {url}")
        if isinstance(rep, Exception):
            raise rep
        return rep


def tout_ok():
    return {
        "https://p.test/version": [(200, "application/json", VERSION_OK)] * 2,
        "https://p.test/reg": [(200, "application/json", REGISTRE_OK)] * 2,
        "https://i.test/version": [(200, "application/json", VERSION_OK)] * 2,
        "https://temoin.test/a": [(204, "", b"")] * 2,
        "https://temoin.test/b": [(200, "text/plain", b"ok")] * 2,
    }


class Juger(unittest.TestCase):
    def test_version_valide(self):
        self.assertIsNone(sonde.juger("version", 200, "application/json", VERSION_OK))

    def test_version_sans_numero(self):
        corps = json.dumps({"service": "verify-service"}).encode()
        self.assertEqual(sonde.juger("version", 200, "application/json", corps), "version absente")

    def test_code_http_autre_que_200(self):
        self.assertEqual(sonde.juger("version", 502, "text/html", b"Bad Gateway"), "HTTP 502")

    def test_json_illisible(self):
        self.assertEqual(sonde.juger("json", 200, "application/json", b"{pas du json"), "JSON illisible")

    def test_json_valide(self):
        self.assertIsNone(sonde.juger("json", 200, "application/json", b'{"a": 1}'))

    def test_html_attend_un_type_html(self):
        self.assertIsNone(sonde.juger("html", 200, "text/html; charset=utf-8", b"<!doctype html>"))
        self.assertEqual(sonde.juger("html", 200, "application/json", b"{}"), "type application/json")

    def test_registre_avec_au_moins_une_ancre(self):
        self.assertIsNone(sonde.juger("registre", 200, "application/json", REGISTRE_OK))

    def test_registre_vide(self):
        self.assertEqual(sonde.juger("registre", 200, "application/json", REGISTRE_VIDE), "registre vide")

    def test_registre_sans_liste_d_ancres(self):
        corps = json.dumps({"mdoc": {"anchors": 3}, "sd_jwt_vc": "x"}).encode()
        self.assertEqual(sonde.juger("registre", 200, "application/json", corps), "registre vide")

    def test_registre_qui_n_est_pas_un_objet(self):
        self.assertEqual(sonde.juger("registre", 200, "application/json", b"[]"), "registre illisible")


class Sonder(unittest.TestCase):
    def test_tout_repond(self):
        attentes = []
        lecteur = Lecteur(tout_ok())
        releve = sonde.sonder(CONFIG, lire=lecteur, attendre=attentes.append, maintenant=T0)
        self.assertEqual(releve["t"], "2026-09-28T10:15:00Z")
        self.assertTrue(releve["temoin"])
        self.assertEqual(
            releve["plateformes"],
            {"production": {"ok": True, "echecs": []}, "integration": {"ok": True, "echecs": []}},
        )
        self.assertEqual(attentes, [], "aucun rejeu quand tout repond")

    def test_un_echec_rattrape_au_rejeu_ne_compte_pas(self):
        reponses = tout_ok()
        reponses["https://p.test/reg"] = [(502, "text/html", b""), (200, "application/json", REGISTRE_OK)]
        attentes = []
        releve = sonde.sonder(CONFIG, lire=Lecteur(reponses), attendre=attentes.append, maintenant=T0)
        self.assertEqual(releve["plateformes"]["production"], {"ok": True, "echecs": []})
        self.assertEqual(attentes, [sonde.ATTENTE_REJEU_S])

    def test_un_double_echec_compte_avec_la_cause_du_rejeu(self):
        reponses = tout_ok()
        reponses["https://p.test/reg"] = [(502, "text/html", b""), (200, "application/json", REGISTRE_VIDE)]
        lecteur = Lecteur(reponses)
        releve = sonde.sonder(CONFIG, lire=lecteur, attendre=lambda s: None, maintenant=T0)
        self.assertEqual(
            releve["plateformes"]["production"],
            {"ok": False, "echecs": [{"sonde": "registre", "cause": "registre vide"}]},
        )
        self.assertEqual(releve["plateformes"]["integration"], {"ok": True, "echecs": []})
        self.assertEqual(lecteur.appels.count("https://p.test/version"), 1, "seul l'echec est rejoue")

    def test_une_exception_reseau_est_une_cause(self):
        reponses = tout_ok()
        reponses["https://i.test/version"] = [TimeoutError("lent"), TimeoutError("lent")]
        releve = sonde.sonder(CONFIG, lire=Lecteur(reponses), attendre=lambda s: None, maintenant=T0)
        self.assertEqual(
            releve["plateformes"]["integration"],
            {"ok": False, "echecs": [{"sonde": "api", "cause": "injoignable (TimeoutError)"}]},
        )

    def test_temoin_tombe_si_les_deux_temoins_tombent(self):
        reponses = tout_ok()
        reponses["https://temoin.test/a"] = [OSError("reseau")]
        reponses["https://temoin.test/b"] = [OSError("reseau")]
        releve = sonde.sonder(CONFIG, lire=Lecteur(reponses), attendre=lambda s: None, maintenant=T0)
        self.assertFalse(releve["temoin"])

    def test_temoin_tient_si_un_temoin_repond_meme_en_erreur_http(self):
        reponses = tout_ok()
        reponses["https://temoin.test/a"] = [OSError("reseau")]
        reponses["https://temoin.test/b"] = [(503, "text/html", b"")]
        releve = sonde.sonder(CONFIG, lire=Lecteur(reponses), attendre=lambda s: None, maintenant=T0)
        self.assertTrue(releve["temoin"])


class Ecrire(unittest.TestCase):
    def test_ajoute_une_ligne_au_fichier_du_jour_utc(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d) / "releves"
            un = {"t": "2026-09-28T23:55:00Z", "temoin": True, "plateformes": {}}
            deux = {"t": "2026-09-28T23:59:59Z", "temoin": False, "plateformes": {}}
            sonde.ajouter_releve(dossier, un)
            sonde.ajouter_releve(dossier, deux)
            lignes = (dossier / "2026-09-28.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(l) for l in lignes], [un, deux])


class Configuration(unittest.TestCase):
    def test_la_configuration_du_depot_est_valide(self):
        config = configuration.charger(RACINE / "plateformes.json")
        self.assertGreaterEqual(len(config["plateformes"]), 1)

    def test_refuse_un_attendu_inconnu(self):
        mauvaise = json.loads(json.dumps(CONFIG))
        mauvaise["plateformes"][0]["sondes"][0]["attendu"] = "vert"
        with self.assertRaisesRegex(ValueError, "attendu"):
            configuration.valider(mauvaise)

    def test_refuse_deux_plateformes_de_meme_id(self):
        mauvaise = json.loads(json.dumps(CONFIG))
        mauvaise["plateformes"][1]["id"] = "production"
        with self.assertRaisesRegex(ValueError, "production"):
            configuration.valider(mauvaise)

    def test_refuse_une_langue_manquante(self):
        mauvaise = json.loads(json.dumps(CONFIG))
        del mauvaise["plateformes"][0]["nom"]["es"]
        with self.assertRaisesRegex(ValueError, "es"):
            configuration.valider(mauvaise)

    def test_refuse_deux_sondes_de_meme_nom(self):
        mauvaise = json.loads(json.dumps(CONFIG))
        mauvaise["plateformes"][0]["sondes"][1]["nom"] = "api"
        with self.assertRaisesRegex(ValueError, "api"):
            configuration.valider(mauvaise)

    def test_refuse_une_url_non_https(self):
        mauvaise = json.loads(json.dumps(CONFIG))
        mauvaise["plateformes"][0]["sondes"][0]["url"] = "http://p.test/version"
        with self.assertRaisesRegex(ValueError, "https"):
            configuration.valider(mauvaise)


if __name__ == "__main__":
    unittest.main()
