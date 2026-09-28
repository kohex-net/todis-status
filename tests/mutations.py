#!/usr/bin/env python3
"""Verifie que les bancs mordent : chaque mutation doit les faire rougir.

Usage : python3 tests/mutations.py   (depuis la racine, avec node dans le PATH)

Travaille sur une copie du depot dans un dossier temporaire ; ne touche
jamais aux fichiers suivis. A relancer quand un banc nait vert.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

MUTATIONS = [
    ("agrege.py", "min((suivant - t).total_seconds() / 60, plafond)", "(suivant - t).total_seconds() / 60", "plafond retire"),
    ("agrege.py", 'return "panne" if releve.get("temoin") else None', 'return "panne"', "temoin ignore"),
    ("agrege.py", "return round((debut_du_jour(d + timedelta(days=1), fuseau)", "return 1440 or round((debut_du_jour(d + timedelta(days=1), fuseau)", "jour de 1440 min fixe"),
    ("agrege.py", 'if acc["panne"] > 0:', 'if acc["panne"] > 0 and couverture >= SEUIL_COUVERTURE:', "panne cachee sur jour peu couvert"),
    ("agrege.py", '"perturbe" if dispo >= SEUIL_PANNE else "panne"', '"panne" if dispo >= SEUIL_PANNE else "perturbe"', "seuils inverses"),
    ("agrege.py", "if d == jours[-1]:", "if False:", "aujourd'hui sur 24 h"),
    ("agrege.py", "d = t.astimezone(fuseau).date()", "d = t.date()", "jours en UTC"),
    ("sonde.py", "if any(causes.values()):", "if False:", "pas de rejeu"),
    ("sonde.py", "temoin = any(", "temoin = all(", "temoin exige tous"),
    ("sonde.py", "return None if ancres > 0 else", "return None if ancres >= 0 else", "registre vide accepte"),
    ("site/status.js", "Math.floor(x * 10000 + 1e-9)", "Math.round(x * 10000)", "pourcentage arrondi"),
    ("site/status.js", "PEREMPTION_MIN * 60 * 1000", "PEREMPTION_MIN * 60 * 10000", "peremption decuplee"),
]


def bancs_verts(dossier):
    r = subprocess.run(["sh", "bancs.sh"], cwd=dossier, capture_output=True)
    return r.returncode == 0


def main():
    survivantes = []
    with tempfile.TemporaryDirectory() as tmp:
        for fichier, avant, apres, nom in MUTATIONS:
            copie = Path(tmp) / "depot"
            if copie.exists():
                shutil.rmtree(copie)
            shutil.copytree(RACINE, copie, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            cible = copie / fichier
            texte = cible.read_text(encoding="utf-8")
            if texte.count(avant) != 1:
                print(f"INTROUVABLE : {nom} ({fichier})")
                survivantes.append(nom)
                continue
            cible.write_text(texte.replace(avant, apres), encoding="utf-8")
            if bancs_verts(copie):
                print(f"SURVIT : {nom}")
                survivantes.append(nom)
            else:
                print(f"tuee : {nom}")
    print(f"{len(MUTATIONS) - len(survivantes)} mutations tuees sur {len(MUTATIONS)}")
    return 1 if survivantes else 0


if __name__ == "__main__":
    sys.exit(main())
