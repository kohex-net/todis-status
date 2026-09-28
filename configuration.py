"""Lecture et validation de plateformes.json, commune a la sonde et a l'agregation.

Une configuration fausse doit arreter le workflow, pas produire un releve
qui ne dit pas ce qu'il croit dire.
"""

import json
from pathlib import Path

ATTENDUS = {"version", "registre", "html", "json"}
LANGUES = ("fr", "en", "es")


def valider(config):
    for cle in ("fuseau", "jours", "plafond_intervalle_min", "temoins", "plateformes"):
        if cle not in config:
            raise ValueError(f"cle manquante : {cle}")
    if not isinstance(config["jours"], int) or config["jours"] < 1:
        raise ValueError("jours doit etre un entier positif")
    if not config["temoins"]:
        raise ValueError("il faut au moins un temoin")
    for url in config["temoins"]:
        _https(url)
    vus = set()
    for p in config["plateformes"]:
        pid = p.get("id")
        if not pid or pid in vus:
            raise ValueError(f"id de plateforme absent ou en double : {pid}")
        vus.add(pid)
        for champ in ("nom", "description"):
            for langue in LANGUES:
                if not p.get(champ, {}).get(langue):
                    raise ValueError(f"{pid} : {champ} sans langue {langue}")
        if not p.get("sondes"):
            raise ValueError(f"{pid} : aucune sonde")
        noms = set()
        for s in p["sondes"]:
            if s.get("nom") in noms or not s.get("nom"):
                raise ValueError(f"{pid} : sonde sans nom ou en double : {s.get('nom')}")
            noms.add(s["nom"])
            if s.get("attendu") not in ATTENDUS:
                raise ValueError(f"{pid}.{s['nom']} : attendu inconnu {s.get('attendu')!r}")
            _https(s.get("url", ""))
    return config


def _https(url):
    if not url.startswith("https://"):
        raise ValueError(f"URL qui n'est pas en https : {url!r}")


def charger(chemin):
    return valider(json.loads(Path(chemin).read_text(encoding="utf-8")))
