"""Banc du declencheur : la fonction Scaleway qui demande un passage de la sonde."""

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "declencheur"))

import handler  # noqa: E402

JETON = "jeton-de-test"


class Reponse:
    def __init__(self, statut):
        self.status = statut

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Envoyeur:
    def __init__(self, statut=204, erreur=None):
        self.statut = statut
        self.erreur = erreur
        self.requetes = []

    def __call__(self, requete, timeout):
        self.requetes.append(requete)
        if self.erreur:
            raise urllib.error.HTTPError(requete.full_url, self.erreur, "refus", {}, io.BytesIO(b""))
        return Reponse(self.statut)


class Declencher(unittest.TestCase):
    def test_demande_un_passage_de_la_sonde_sur_main(self):
        envoyeur = Envoyeur()
        with mock.patch.object(handler, "ENVOYER", envoyeur):
            self.assertEqual(handler.declencher(JETON), 204)
        (r,) = envoyeur.requetes
        self.assertEqual(
            r.full_url,
            "https://api.github.com/repos/kohex-net/todis-status/actions/workflows/sonde.yml/dispatches",
        )
        self.assertEqual(r.get_method(), "POST")
        self.assertEqual(json.loads(r.data), {"ref": "main"})
        self.assertEqual(r.get_header("Authorization"), f"Bearer {JETON}")

    def test_un_refus_de_github_rend_son_code(self):
        with mock.patch.object(handler, "ENVOYER", Envoyeur(erreur=401)):
            self.assertEqual(handler.declencher(JETON), 401)


class Handle(unittest.TestCase):
    def test_succes(self):
        with mock.patch.object(handler, "ENVOYER", Envoyeur()), mock.patch.dict("os.environ", {"GITHUB_TOKEN": JETON}):
            rep = handler.handle({}, None)
        self.assertEqual(rep["statusCode"], 200)

    def test_echec_de_github_est_visible_et_ne_montre_pas_le_jeton(self):
        with mock.patch.object(handler, "ENVOYER", Envoyeur(erreur=401)), mock.patch.dict(
            "os.environ", {"GITHUB_TOKEN": JETON}
        ):
            rep = handler.handle({}, None)
        self.assertEqual(rep["statusCode"], 502)
        self.assertIn("401", rep["body"])
        self.assertNotIn(JETON, json.dumps(rep))

    def test_sans_jeton_rien_n_est_envoye(self):
        envoyeur = Envoyeur()
        with mock.patch.object(handler, "ENVOYER", envoyeur), mock.patch.dict("os.environ", {}, clear=True):
            rep = handler.handle({}, None)
        self.assertEqual(rep["statusCode"], 500)
        self.assertEqual(envoyeur.requetes, [])


if __name__ == "__main__":
    unittest.main()
