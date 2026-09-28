#!/usr/bin/env python3
"""Construit status.json, les quinze jours de la page, a partir des releves.

Usage : python3 agrege.py plateformes.json dossier-des-releves sortie.json

Chaque releve vaut l'intervalle jusqu'au suivant, plafonne a
`plafond_intervalle_min` : le cron de GitHub saute des passages, et un
trou ne doit pas compter comme mesure. Les jours sont ceux de `fuseau`.

Statut d'un jour :
- panne : disponibilite mesuree sous SEUIL_PANNE ;
- perturbe : au moins une minute d'echec, disponibilite au moins SEUIL_PANNE ;
- operationnel : aucun echec, et au moins SEUIL_COUVERTURE du jour mesure ;
- inconnu : aucun echec, mais trop peu mesure pour l'affirmer.
Un echec mesure se montre toujours, meme sur un jour peu couvert.
"""

import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import configuration

UTC = timezone.utc
SEUIL_PANNE = 0.99
SEUIL_COUVERTURE = 0.5
FORMAT_T = "%Y-%m-%dT%H:%M:%SZ"


def iso(t):
    return t.astimezone(UTC).strftime(FORMAT_T)


def lire_t(texte):
    return datetime.strptime(texte, FORMAT_T).replace(tzinfo=UTC)


def debut_du_jour(d, fuseau):
    return datetime.combine(d, time(0), fuseau).astimezone(UTC)


def minutes_du_jour(d, fuseau):
    # Differences en UTC : entre deux instants du meme fuseau, Python
    # soustrait les heures murales et rendrait 1440 un jour de 25 heures.
    return round((debut_du_jour(d + timedelta(days=1), fuseau) - debut_du_jour(d, fuseau)).total_seconds() / 60)


def fenetre(config, maintenant):
    fuseau = ZoneInfo(config["fuseau"])
    aujourdhui = maintenant.astimezone(fuseau).date()
    n = config["jours"]
    return fuseau, [aujourdhui - timedelta(days=n - 1 - i) for i in range(n)]


def charger_releves(dossier, config, maintenant):
    """Lit les fichiers qui peuvent couvrir la fenetre. Rend (releves, lignes abimees)."""
    _, jours = fenetre(config, maintenant)
    dossier = Path(dossier)
    releves, abimees = [], 0
    d = jours[0] - timedelta(days=1)
    while d <= jours[-1] + timedelta(days=1):
        fichier = dossier / f"{d.isoformat()}.jsonl"
        if fichier.exists():
            for ligne in fichier.read_text(encoding="utf-8").splitlines():
                if not ligne.strip():
                    continue
                try:
                    r = json.loads(ligne)
                    lire_t(r["t"])
                    releves.append(r)
                except (ValueError, KeyError, TypeError):
                    abimees += 1
        d += timedelta(days=1)
    releves.sort(key=lambda r: r["t"])
    return releves, abimees


def etat_de(releve, pid):
    """ok, panne, ou None quand la plateforme n'a pas ete mesuree par ce releve."""
    entree = releve.get("plateformes", {}).get(pid)
    if not entree:
        return None
    if entree.get("ok"):
        return "ok"
    return "panne" if releve.get("temoin") else None


def agreger(config, releves, maintenant):
    fuseau, jours = fenetre(config, maintenant)
    plafond = config["plafond_intervalle_min"]
    dans_fenetre = set(jours)
    serie = [(lire_t(r["t"]), r) for r in releves if lire_t(r["t"]) <= maintenant]
    serie.sort(key=lambda x: x[0])
    durees = []
    for i, (t, _) in enumerate(serie):
        suivant = serie[i + 1][0] if i + 1 < len(serie) else maintenant
        durees.append(min((suivant - t).total_seconds() / 60, plafond))

    plateformes = []
    for p in config["plateformes"]:
        pid = p["id"]
        par_jour = {d: {"mesure": 0.0, "panne": 0.0, "sondes": set()} for d in jours}
        etat = None
        for (t, r), duree in zip(serie, durees):
            e = etat_de(r, pid)
            if e is None:
                continue
            echecs = sorted({x["sonde"] for x in r["plateformes"][pid].get("echecs", [])}) if e == "panne" else []
            statut = "operationnel" if e == "ok" else "panne"
            if etat is None or etat["statut"] != statut:
                etat = {"statut": statut, "depuis": iso(t)}
            etat["releve"] = iso(t)
            etat["sondes_en_echec"] = echecs
            d = t.astimezone(fuseau).date()
            if d not in dans_fenetre:
                continue
            par_jour[d]["mesure"] += duree
            if e == "panne":
                par_jour[d]["panne"] += duree
                par_jour[d]["sondes"].update(echecs)

        sortie_jours = []
        mesure_totale = panne_totale = 0.0
        for d in jours:
            acc = par_jour[d]
            mesure_totale += acc["mesure"]
            panne_totale += acc["panne"]
            if d == jours[-1]:
                reference = max((maintenant - debut_du_jour(d, fuseau)).total_seconds() / 60, 1)
            else:
                reference = minutes_du_jour(d, fuseau)
            couverture = min(acc["mesure"] / reference, 1.0)
            dispo = 1 - acc["panne"] / acc["mesure"] if acc["mesure"] else None
            if acc["panne"] > 0:
                statut = "perturbe" if dispo >= SEUIL_PANNE else "panne"
            elif couverture >= SEUIL_COUVERTURE:
                statut = "operationnel"
            else:
                statut = "inconnu"
            sortie_jours.append(
                {
                    "date": d.isoformat(),
                    "statut": statut,
                    "disponibilite": None if dispo is None else round(dispo, 6),
                    "minutes_panne": round(acc["panne"]),
                    "couverture": round(couverture, 3),
                    "sondes_en_echec": sorted(acc["sondes"]),
                }
            )
        plateformes.append(
            {
                "id": pid,
                "nom": p["nom"],
                "description": p["description"],
                "disponibilite": round(1 - panne_totale / mesure_totale, 6) if mesure_totale else None,
                "etat": etat,
                "jours": sortie_jours,
            }
        )

    return {
        "genere_a": iso(maintenant),
        "dernier_releve": iso(serie[-1][0]) if serie else None,
        "fuseau": config["fuseau"],
        "jours": [d.isoformat() for d in jours],
        "plateformes": plateformes,
    }


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    config = configuration.charger(argv[1])
    maintenant = datetime.now(UTC).replace(microsecond=0)
    releves, abimees = charger_releves(argv[2], config, maintenant)
    resultat = agreger(config, releves, maintenant)
    sortie = Path(argv[3])
    provisoire = sortie.with_suffix(".tmp")
    provisoire.write_text(json.dumps(resultat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(provisoire, sortie)
    print(f"{len(releves)} releves lus, {abimees} lignes abimees ignorees, {sortie} ecrit")
    for p in resultat["plateformes"]:
        print(f"{p['id']} : disponibilite {p['disponibilite']}, etat {p['etat'] and p['etat']['statut']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
