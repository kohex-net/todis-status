"""Fonction Scaleway : demande a GitHub un passage du workflow Sonde.

Le cron de GitHub ne tient pas cinq minutes : mesure le 2026-09-28 sur une
douzaine de depots en `*/5`, il ne declenche qu'environ toutes les 3 a 7
heures. Un cron Scaleway appelle donc cette fonction toutes les cinq
minutes, et elle ne fait qu'appuyer sur le bouton : la mesure et la page
restent chez GitHub. Decision 0161 du depot eudiw.

La fonction est privee : seul son cron l'appelle. Le jeton GitHub est un
secret de la fonction, limite a ce depot et au droit Actions.
"""

import json
import os
import urllib.error
import urllib.request

URL = "https://api.github.com/repos/kohex-net/todis-status/actions/workflows/sonde.yml/dispatches"
ENVOYER = urllib.request.urlopen


def declencher(jeton):
    requete = urllib.request.Request(
        URL,
        data=json.dumps({"ref": "main"}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {jeton}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "todis-status-declencheur",
        },
    )
    try:
        with ENVOYER(requete, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def handle(event, context):
    jeton = os.environ.get("GITHUB_TOKEN")
    if not jeton:
        return {"statusCode": 500, "body": "GITHUB_TOKEN absent"}
    code = declencher(jeton)
    return {"statusCode": 200 if code == 204 else 502, "body": f"GitHub a repondu {code}"}
