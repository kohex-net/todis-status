"""Banc de agrege.py : du fil des releves aux quinze jours de la page."""

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agrege  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
UTC = timezone.utc

CONFIG = {
    "fuseau": "Europe/Paris",
    "jours": 15,
    "plafond_intervalle_min": 15,
    "temoins": ["https://temoin.test/a"],
    "plateformes": [
        {
            "id": "production",
            "nom": {"fr": "Production", "en": "Production", "es": "Producción"},
            "description": {"fr": "d", "en": "d", "es": "d"},
            "sondes": [{"nom": "api", "url": "https://p.test/v", "attendu": "version"}],
        },
        {
            "id": "integration",
            "nom": {"fr": "Intégration", "en": "Integration", "es": "Integración"},
            "description": {"fr": "d", "en": "d", "es": "d"},
            "sondes": [{"nom": "api", "url": "https://i.test/v", "attendu": "version"}],
        },
    ],
}

# Midi a Paris le 28 septembre 2026, soit 10 h UTC.
MAINTENANT = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
# Minuit a Paris le 27 septembre 2026.
DEBUT_27 = datetime(2026, 9, 26, 22, 0, tzinfo=UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def serie(debut, fin, pas_min=5, plateformes=("production", "integration")):
    """Un releve toutes les `pas_min` minutes de `debut` inclus a `fin` exclu, tout va bien."""
    releves = []
    t = debut
    while t < fin:
        releves.append(
            {
                "t": iso(t),
                "temoin": True,
                "plateformes": {p: {"ok": True, "echecs": []} for p in plateformes},
            }
        )
        t += timedelta(minutes=pas_min)
    return releves


def en_panne(releves, debut, fin, plateforme="production", sonde="api", temoin=True):
    """Met `plateforme` en echec sur les releves de [debut, fin)."""
    for r in releves:
        t = datetime.strptime(r["t"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if debut <= t < fin:
            r["plateformes"][plateforme] = {"ok": False, "echecs": [{"sonde": sonde, "cause": "HTTP 502"}]}
            r["temoin"] = temoin
    return releves


def jour(resultat, plateforme, date_iso):
    p = next(p for p in resultat["plateformes"] if p["id"] == plateforme)
    return next(j for j in p["jours"] if j["date"] == date_iso)


def plateforme(resultat, pid):
    return next(p for p in resultat["plateformes"] if p["id"] == pid)


class Calendrier(unittest.TestCase):
    def test_quinze_jours_du_plus_ancien_a_aujourd_hui_a_paris(self):
        res = agrege.agreger(CONFIG, [], MAINTENANT)
        self.assertEqual(res["jours"][0], "2026-09-14")
        self.assertEqual(res["jours"][-1], "2026-09-28")
        self.assertEqual(len(res["jours"]), 15)
        self.assertEqual([j["date"] for j in plateforme(res, "production")["jours"]], res["jours"])

    def test_longueur_des_jours_aux_changements_d_heure(self):
        self.assertEqual(agrege.minutes_du_jour(date(2026, 9, 27), PARIS), 1440)
        self.assertEqual(agrege.minutes_du_jour(date(2026, 10, 25), PARIS), 1500)
        self.assertEqual(agrege.minutes_du_jour(date(2026, 3, 29), PARIS), 1380)

    def test_un_releve_apres_minuit_a_paris_compte_pour_le_lendemain(self):
        # 22 h 30 UTC le 27 = 0 h 30 a Paris le 28.
        t = datetime(2026, 9, 27, 22, 30, tzinfo=UTC)
        releves = en_panne(serie(t, t + timedelta(minutes=5)), t, t + timedelta(minutes=5))
        res = agrege.agreger(CONFIG, releves, MAINTENANT)
        # Releve isole : il vaut le plafond de 15 minutes.
        self.assertEqual(jour(res, "production", "2026-09-28")["minutes_panne"], 15)
        self.assertEqual(jour(res, "production", "2026-09-27")["minutes_panne"], 0)


class Jours(unittest.TestCase):
    def test_jour_entier_sans_echec(self):
        res = agrege.agreger(CONFIG, serie(DEBUT_27, MAINTENANT), MAINTENANT)
        j = jour(res, "production", "2026-09-27")
        self.assertEqual(j["statut"], "operationnel")
        self.assertEqual(j["disponibilite"], 1.0)
        self.assertEqual(j["minutes_panne"], 0)
        self.assertEqual(j["couverture"], 1.0)
        self.assertEqual(j["sondes_en_echec"], [])

    def test_un_releve_en_echec_est_une_perturbation(self):
        panne = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, panne + timedelta(minutes=5))
        j = jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")
        self.assertEqual(j["statut"], "perturbe")
        self.assertEqual(j["minutes_panne"], 5)
        self.assertEqual(j["disponibilite"], round(1 - 5 / 1440, 6))
        self.assertEqual(j["sondes_en_echec"], ["api"])

    def test_trois_heures_d_echec_sont_une_panne(self):
        panne = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, panne + timedelta(hours=3))
        res = agrege.agreger(CONFIG, releves, MAINTENANT)
        self.assertEqual(jour(res, "production", "2026-09-27")["statut"], "panne")
        self.assertEqual(jour(res, "production", "2026-09-27")["minutes_panne"], 180)
        self.assertEqual(jour(res, "integration", "2026-09-27")["statut"], "operationnel")

    def test_le_seuil_de_la_panne_est_un_pour_cent(self):
        # 14 minutes sur 1440 : 99,03 %, perturbation. 15 minutes : 98,96 %, panne.
        debut = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        releves = serie(DEBUT_27, MAINTENANT, pas_min=1)
        en_panne(releves, debut, debut + timedelta(minutes=14))
        self.assertEqual(jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")["statut"], "perturbe")
        en_panne(releves, debut, debut + timedelta(minutes=15))
        self.assertEqual(jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")["statut"], "panne")

    def test_un_echec_sous_temoin_tombe_n_est_pas_mesure(self):
        panne = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, panne + timedelta(hours=3), temoin=False)
        j = jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")
        self.assertEqual(j["minutes_panne"], 0)
        self.assertEqual(j["statut"], "operationnel")
        self.assertEqual(j["couverture"], round(1 - 180 / 1440, 3))

    def test_un_succes_sous_temoin_tombe_reste_mesure(self):
        releves = serie(DEBUT_27, MAINTENANT)
        for r in releves:
            r["temoin"] = False
        j = jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")
        self.assertEqual(j["couverture"], 1.0)
        self.assertEqual(j["statut"], "operationnel")

    def test_un_trou_ne_compte_que_le_plafond(self):
        # Releves de 0 h a 1 h, puis plus rien jusqu'a 23 h (heures de Paris).
        releves = serie(DEBUT_27, DEBUT_27 + timedelta(hours=1)) + serie(
            DEBUT_27 + timedelta(hours=23), MAINTENANT
        )
        j = jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")
        # 11 intervalles de 5 min, le dernier avant le trou plafonne a 15, puis 1 h pleine.
        self.assertEqual(j["couverture"], round((55 + 15 + 60) / 1440, 3))
        self.assertEqual(j["statut"], "inconnu")
        self.assertIsNotNone(j["disponibilite"])

    def test_une_panne_mesuree_se_montre_meme_sur_un_jour_peu_couvert(self):
        releves = serie(DEBUT_27, DEBUT_27 + timedelta(hours=2))
        en_panne(releves, DEBUT_27, DEBUT_27 + timedelta(hours=1))
        j = jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-27")
        self.assertEqual(j["statut"], "panne")
        self.assertEqual(j["minutes_panne"], 60)

    def test_jour_sans_aucun_releve(self):
        j = jour(agrege.agreger(CONFIG, [], MAINTENANT), "production", "2026-09-20")
        self.assertEqual(
            j,
            {
                "date": "2026-09-20",
                "statut": "inconnu",
                "disponibilite": None,
                "minutes_panne": 0,
                "couverture": 0.0,
                "sondes_en_echec": [],
            },
        )

    def test_aujourd_hui_se_mesure_sur_le_temps_ecoule(self):
        minuit_28 = datetime(2026, 9, 27, 22, 0, tzinfo=UTC)
        # Midi a Paris : 720 minutes ecoulees, releves depuis 6 h seulement.
        releves = serie(minuit_28 + timedelta(hours=6), MAINTENANT)
        j = jour(agrege.agreger(CONFIG, releves, MAINTENANT), "production", "2026-09-28")
        self.assertEqual(j["couverture"], 0.5)
        self.assertEqual(j["statut"], "operationnel")

    def test_couverture_d_un_jour_de_vingt_cinq_heures(self):
        maintenant = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)
        minuit_25 = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
        releves = serie(minuit_25, minuit_25 + timedelta(minutes=780))
        j = jour(agrege.agreger(CONFIG, releves, maintenant), "production", "2026-10-25")
        # 155 intervalles de 5 min plus le dernier au plafond : 790 minutes
        # sur 1500, et non sur 1440.
        self.assertEqual(j["couverture"], round(790 / 1500, 3))

    def test_une_plateforme_absente_des_releves_reste_grise(self):
        config = json.loads(json.dumps(CONFIG))
        config["plateformes"].append(
            {
                "id": "shopify",
                "nom": {"fr": "S", "en": "S", "es": "S"},
                "description": {"fr": "d", "en": "d", "es": "d"},
                "sondes": [{"nom": "api", "url": "https://s.test/v", "attendu": "version"}],
            }
        )
        res = agrege.agreger(config, serie(DEBUT_27, MAINTENANT), MAINTENANT)
        s = plateforme(res, "shopify")
        self.assertEqual({j["statut"] for j in s["jours"]}, {"inconnu"})
        self.assertIsNone(s["disponibilite"])
        self.assertIsNone(s["etat"])

    def test_un_releve_futur_est_ignore(self):
        futur = MAINTENANT + timedelta(minutes=10)
        releves = en_panne(serie(futur, futur + timedelta(minutes=5)), futur, futur + timedelta(minutes=5))
        res = agrege.agreger(CONFIG, releves, MAINTENANT)
        self.assertEqual(jour(res, "production", "2026-09-28")["minutes_panne"], 0)
        self.assertIsNone(res["dernier_releve"])


class Synthese(unittest.TestCase):
    def test_disponibilite_sur_la_periode(self):
        panne = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, panne + timedelta(minutes=30))
        res = agrege.agreger(CONFIG, releves, MAINTENANT)
        mesure = (MAINTENANT - DEBUT_27).total_seconds() / 60
        self.assertEqual(plateforme(res, "production")["disponibilite"], round(1 - 30 / mesure, 6))
        self.assertEqual(plateforme(res, "integration")["disponibilite"], 1.0)

    def test_pas_de_disponibilite_sur_la_periode_tant_que_tous_les_jours_sont_gris(self):
        # Quelques minutes de mesure ne font pas « 100 % sur quinze jours ».
        releves = serie(MAINTENANT - timedelta(minutes=20), MAINTENANT)
        res = agrege.agreger(CONFIG, releves, MAINTENANT)
        self.assertEqual({j["statut"] for j in plateforme(res, "production")["jours"]}, {"inconnu"})
        self.assertIsNone(plateforme(res, "production")["disponibilite"])
        self.assertEqual(plateforme(res, "production")["etat"]["statut"], "operationnel")

    def test_etat_courant_en_panne_depuis_le_premier_echec(self):
        panne = MAINTENANT - timedelta(minutes=15)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, MAINTENANT, sonde="registre")
        etat = plateforme(agrege.agreger(CONFIG, releves, MAINTENANT), "production")["etat"]
        self.assertEqual(
            etat,
            {
                "statut": "panne",
                "depuis": iso(panne),
                "releve": iso(MAINTENANT - timedelta(minutes=5)),
                "sondes_en_echec": ["registre"],
            },
        )

    def test_etat_courant_retabli(self):
        panne = MAINTENANT - timedelta(minutes=30)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, MAINTENANT - timedelta(minutes=10))
        etat = plateforme(agrege.agreger(CONFIG, releves, MAINTENANT), "production")["etat"]
        self.assertEqual(etat["statut"], "operationnel")
        self.assertEqual(etat["depuis"], iso(MAINTENANT - timedelta(minutes=10)))
        self.assertEqual(etat["sondes_en_echec"], [])

    def test_etat_courant_ignore_un_echec_sous_temoin_tombe(self):
        panne = MAINTENANT - timedelta(minutes=5)
        releves = en_panne(serie(DEBUT_27, MAINTENANT), panne, MAINTENANT, temoin=False)
        etat = plateforme(agrege.agreger(CONFIG, releves, MAINTENANT), "production")["etat"]
        self.assertEqual(etat["statut"], "operationnel")
        self.assertEqual(etat["releve"], iso(MAINTENANT - timedelta(minutes=10)))

    def test_en_tete(self):
        res = agrege.agreger(CONFIG, serie(DEBUT_27, MAINTENANT), MAINTENANT)
        self.assertEqual(res["genere_a"], "2026-09-28T10:00:00Z")
        self.assertEqual(res["dernier_releve"], "2026-09-28T09:55:00Z")
        self.assertEqual(res["fuseau"], "Europe/Paris")
        self.assertEqual([p["id"] for p in res["plateformes"]], ["production", "integration"])
        self.assertEqual(plateforme(res, "integration")["nom"]["es"], "Integración")


class Lecture(unittest.TestCase):
    def test_lit_les_fichiers_autour_de_la_fenetre_et_saute_une_ligne_abimee(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d)
            bon = {"t": "2026-09-27T12:00:00Z", "temoin": True, "plateformes": {}}
            (dossier / "2026-09-27.jsonl").write_text(
                json.dumps(bon) + "\n" + '{"t": "2026-09-27T12:05' + "\n", encoding="utf-8"
            )
            (dossier / "2026-09-13.jsonl").write_text(
                json.dumps({"t": "2026-09-13T21:59:00Z", "temoin": True, "plateformes": {}}) + "\n",
                encoding="utf-8",
            )
            (dossier / "2026-09-01.jsonl").write_text(json.dumps(bon) + "\n", encoding="utf-8")
            releves, abimees = agrege.charger_releves(dossier, CONFIG, MAINTENANT)
            self.assertEqual(abimees, 1)
            self.assertEqual([r["t"] for r in releves], ["2026-09-13T21:59:00Z", "2026-09-27T12:00:00Z"])


if __name__ == "__main__":
    unittest.main()
