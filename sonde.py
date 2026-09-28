#!/usr/bin/env python3
"""Sonde les routes publiques des plateformes Todis et ajoute un releve.

Usage : python3 sonde.py plateformes.json dossier-des-releves

Un releve par passage, une ligne JSON dans releves/AAAA-MM-JJ.jsonl (date
UTC). Une sonde en echec est rejouee une fois apres ATTENTE_REJEU_S : seul
un double echec compte, pour ne pas peindre en rouge un hoquet reseau.
Le temoin dit si le runner lui-meme joignait Internet ; l'agregation ne
compte pas un echec mesure sous temoin tombe.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import configuration

DELAI_S = 10
ATTENTE_REJEU_S = 20
TAILLE_MAX = 4_000_000
AGENT = "todis-status/1 (+https://status.todis.eu)"


def lire_url(url):
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_S) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(TAILLE_MAX)
    except urllib.error.HTTPError as e:
        return e.code, (e.headers.get("Content-Type", "") if e.headers else ""), b""


def juger(attendu, statut, type_contenu, corps):
    """Rend None si la reponse est celle attendue, sinon la cause en quelques mots."""
    if statut != 200:
        return f"HTTP {statut}"
    if attendu == "html":
        return None if "text/html" in type_contenu else f"type {type_contenu or 'absent'}"
    try:
        doc = json.loads(corps)
    except ValueError:
        return "JSON illisible"
    if attendu == "json":
        return None
    if attendu == "version":
        v = doc.get("service_version") if isinstance(doc, dict) else None
        return None if isinstance(v, str) and v else "version absente"
    if attendu == "registre":
        if not isinstance(doc, dict):
            return "registre illisible"
        # Au moins une ancre, tous formats confondus : la production ne sert
        # aujourd'hui aucune ancre SD-JWT VC, et ce n'est pas une panne.
        ancres = 0
        for format_ in ("mdoc", "sd_jwt_vc"):
            bloc = doc.get(format_)
            if isinstance(bloc, dict) and isinstance(bloc.get("anchors"), list):
                ancres += len(bloc["anchors"])
        return None if ancres > 0 else "registre vide"
    raise ValueError(f"attendu inconnu : {attendu}")


def essayer(sonde_, lire):
    try:
        statut, type_contenu, corps = lire(sonde_["url"])
    except Exception as e:  # reseau, TLS, delai depasse
        return f"injoignable ({type(e).__name__})"
    return juger(sonde_["attendu"], statut, type_contenu, corps)


def joignable(url, lire):
    try:
        lire(url)
    except Exception:
        return False
    return True


def sonder(config, lire=lire_url, attendre=time.sleep, maintenant=None):
    t = maintenant or datetime.now(timezone.utc)
    causes = {}
    for p in config["plateformes"]:
        for s in p["sondes"]:
            causes[(p["id"], s["nom"])] = essayer(s, lire)
    if any(causes.values()):
        attendre(ATTENTE_REJEU_S)
        for p in config["plateformes"]:
            for s in p["sondes"]:
                if causes[(p["id"], s["nom"])]:
                    causes[(p["id"], s["nom"])] = essayer(s, lire)
    temoin = any(joignable(u, lire) for u in config["temoins"])
    plateformes = {}
    for p in config["plateformes"]:
        echecs = [
            {"sonde": s["nom"], "cause": causes[(p["id"], s["nom"])]}
            for s in p["sondes"]
            if causes[(p["id"], s["nom"])]
        ]
        plateformes[p["id"]] = {"ok": not echecs, "echecs": echecs}
    return {
        "t": t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temoin": temoin,
        "plateformes": plateformes,
    }


def ajouter_releve(dossier, releve):
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / f"{releve['t'][:10]}.jsonl"
    with fichier.open("a", encoding="utf-8") as f:
        f.write(json.dumps(releve, ensure_ascii=False, sort_keys=True) + "\n")
    return fichier


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    config = configuration.charger(argv[1])
    releve = sonder(config)
    fichier = ajouter_releve(argv[2], releve)
    for pid, r in releve["plateformes"].items():
        detail = ", ".join(f"{e['sonde']} : {e['cause']}" for e in r["echecs"])
        print(f"{pid} : {'ok' if r['ok'] else 'ECHEC ' + detail}")
    print(f"temoin : {'ok' if releve['temoin'] else 'TOMBE'} ; releve ajoute a {fichier}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
