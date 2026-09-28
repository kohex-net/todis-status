// Banc des fonctions de site/status.js, sans navigateur.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as S from "../site/status.js";

// Intl separe par des espaces insecables, fines ou non : on les ramene a une espace.
const espaces = (s) => s.replace(/\s/g, " ");
// Par son code et non par le caractere : ce banc ne doit pas contenir ce qu il interdit.
const TIRET_LONG = String.fromCharCode(0x2014);

test("les trois langues ont les memes textes, sans tiret long", () => {
  const cles = Object.keys(S.TEXTES.fr).sort();
  for (const langue of ["en", "es"]) {
    assert.deepEqual(Object.keys(S.TEXTES[langue]).sort(), cles, langue);
  }
  for (const langue of ["fr", "en", "es"]) {
    for (const [cle, valeur] of Object.entries(S.TEXTES[langue])) {
      assert.ok(!String(valeur).includes(TIRET_LONG), `${langue}.${cle}`);
    }
  }
});

test("pourcentage tronque et ne montre jamais 100 % sur une panne", () => {
  assert.equal(espaces(S.pourcentage(0.99996, "fr")), "99,99 %");
  assert.equal(espaces(S.pourcentage(0.99996, "en")), "99.99%");
  assert.equal(espaces(S.pourcentage(1, "fr")), "100,00 %");
  assert.equal(S.pourcentage(null, "fr"), S.TEXTES.fr.nonMesure);
});

test("un releve de plus de 30 minutes est perime", () => {
  const maintenant = new Date("2026-09-28T09:31:00Z");
  assert.equal(S.estPerime("2026-09-28T09:00:00Z", maintenant), true);
  assert.equal(S.estPerime("2026-09-28T09:02:00Z", maintenant), false);
  assert.equal(S.estPerime(null, maintenant), true);
});

const statut = (etats) => ({
  dernier_releve: "2026-09-28T09:55:00Z",
  plateformes: Object.entries(etats).map(([id, s]) => ({ id, etat: s && { statut: s } })),
});

test("etat global", () => {
  const maintenant = new Date("2026-09-28T10:00:00Z");
  assert.deepEqual(S.etatGlobal(statut({ production: "operationnel", integration: "operationnel" }), maintenant), {
    cle: "operationnel",
    plateformes: [],
  });
  assert.deepEqual(S.etatGlobal(statut({ production: "operationnel", integration: "panne" }), maintenant), {
    cle: "panne",
    plateformes: ["integration"],
  });
  assert.deepEqual(S.etatGlobal(statut({ production: "operationnel", shopify: null }), maintenant), {
    cle: "operationnel",
    plateformes: [],
  });
  assert.deepEqual(S.etatGlobal(statut({ production: "panne" }), new Date("2026-09-28T11:00:00Z")), {
    cle: "perime",
    plateformes: [],
  });
  assert.deepEqual(S.etatGlobal(null, maintenant), { cle: "indisponible", plateformes: [] });
});

test("duree lisible", () => {
  assert.equal(S.duree(0, "fr"), S.TEXTES.fr.aucuneInterruption);
  assert.equal(S.duree(5, "fr"), "5 min");
  assert.equal(S.duree(125, "en"), "2 h 5 min");
  assert.equal(S.duree(120, "es"), "2 h");
});

test("date longue au fuseau de Paris", () => {
  assert.equal(S.dateLongue("2026-09-27", "fr"), "27 septembre 2026");
  assert.equal(S.dateLongue("2026-09-27", "en"), "September 27, 2026");
});
