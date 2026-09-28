"""Banc de la page : trois langues de meme structure, CSP, aucune donnee par innerHTML."""

import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

RACINE = Path(__file__).resolve().parent.parent
SITE = RACINE / "site"
PAGES = {
    "fr": (SITE / "index.html", "https://status.todis.eu/"),
    "en": (SITE / "en" / "index.html", "https://status.todis.eu/en/"),
    "es": (SITE / "es" / "index.html", "https://status.todis.eu/es/"),
}
# Par son code et non par le caractere : ce banc ne doit pas contenir ce qu'il interdit.
TIRET_LONG = chr(0x2014)


class Lecteur(HTMLParser):
    def __init__(self):
        super().__init__()
        self.structure = []
        self.balises = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.balises.append((tag, a))
        self.structure.append((tag, a.get("id"), a.get("class")))


def lire(chemin):
    lecteur = Lecteur()
    lecteur.feed(chemin.read_text(encoding="utf-8"))
    return lecteur


def source_des_releves():
    js = (SITE / "status.js").read_text(encoding="utf-8")
    m = re.search(r'export const SOURCE = "([^"]+)"', js)
    if not m:
        raise AssertionError("SOURCE introuvable dans status.js")
    return m.group(1)


class Pages(unittest.TestCase):
    def test_les_trois_pages_existent_dans_leur_langue(self):
        for langue, (chemin, _) in PAGES.items():
            html = [a for t, a in lire(chemin).balises if t == "html"][0]
            self.assertEqual(html.get("lang"), langue, chemin)

    def test_meme_structure_dans_les_trois_langues(self):
        fr = lire(PAGES["fr"][0]).structure
        for langue in ("en", "es"):
            self.assertEqual(lire(PAGES[langue][0]).structure, fr, langue)

    def test_canonique_et_hreflang(self):
        for langue, (chemin, url) in PAGES.items():
            liens = [a for t, a in lire(chemin).balises if t == "link"]
            canon = [a["href"] for a in liens if a.get("rel") == "canonical"]
            self.assertEqual(canon, [url], langue)
            alternes = {a["hreflang"]: a["href"] for a in liens if a.get("rel") == "alternate"}
            self.assertEqual(
                alternes,
                {
                    "fr": PAGES["fr"][1],
                    "en": PAGES["en"][1],
                    "es": PAGES["es"][1],
                    "x-default": PAGES["en"][1],
                },
                langue,
            )

    def test_csp_identique_et_ouverte_a_la_seule_source_des_releves(self):
        origine = "{0.scheme}://{0.netloc}".format(urlsplit(source_des_releves()))
        csps = []
        for langue, (chemin, _) in PAGES.items():
            metas = [
                a["content"]
                for t, a in lire(chemin).balises
                if t == "meta" and a.get("http-equiv") == "Content-Security-Policy"
            ]
            self.assertEqual(len(metas), 1, langue)
            csps.append(metas[0])
        self.assertEqual(len(set(csps)), 1, "les trois CSP different")
        directives = dict(d.strip().split(" ", 1) for d in csps[0].split(";") if d.strip())
        self.assertEqual(directives["default-src"], "'none'")
        self.assertEqual(directives["connect-src"], origine)
        self.assertEqual(directives["script-src"], "'self'")

    def test_aucune_ressource_d_un_autre_domaine(self):
        for langue, (chemin, _) in PAGES.items():
            for tag, a in lire(chemin).balises:
                for attr in ("src",):
                    if attr in a:
                        self.assertNotRegex(a[attr], r"^(https?:)?//", f"{langue} {tag}")
                if tag == "link" and a.get("rel") in ("stylesheet", "icon"):
                    self.assertNotRegex(a["href"], r"^(https?:)?//", f"{langue} {tag}")

    def test_le_script_est_un_module_local(self):
        for langue, (chemin, _) in PAGES.items():
            scripts = [a for t, a in lire(chemin).balises if t == "script"]
            self.assertEqual(len(scripts), 1, langue)
            self.assertEqual(scripts[0].get("type"), "module", langue)
            self.assertTrue(scripts[0]["src"].endswith("status.js"), langue)


class Script(unittest.TestCase):
    def test_aucune_insertion_de_html(self):
        js = (SITE / "status.js").read_text(encoding="utf-8")
        for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            self.assertFalse(interdit in js, f"status.js contient {interdit}")

    def test_la_source_est_la_branche_des_releves_de_ce_depot(self):
        self.assertEqual(
            source_des_releves(),
            "https://raw.githubusercontent.com/kohex-net/todis-status/releves/status.json",
        )


class Ecriture(unittest.TestCase):
    def test_aucun_tiret_long(self):
        fichiers = [p for p in RACINE.rglob("*") if p.is_file() and ".git" not in p.parts]
        textes = [p for p in fichiers if p.suffix in {".html", ".js", ".mjs", ".css", ".py", ".json", ".md", ".yml"}]
        self.assertTrue(textes)
        for p in textes:
            texte = p.read_text(encoding="utf-8")
            self.assertFalse(TIRET_LONG in texte, f"tiret long dans {p.relative_to(RACINE)}")


if __name__ == "__main__":
    unittest.main()
