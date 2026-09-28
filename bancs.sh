#!/bin/sh
# Lance tous les bancs du depot. Sortie 0 seulement si tous sont verts.
# Le workflow le lance avant de sonder et avant de publier la page : un
# banc rouge ne mesure ni ne publie rien.
set -eu
cd "$(dirname "$0")"
python3 -m unittest discover -s tests -p 'test_*.py'
# Les fichiers et non le dossier : Node 24 lit un dossier comme un module.
node --test tests/*.test.mjs
