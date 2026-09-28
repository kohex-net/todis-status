// Page de statut de Todis. Lit status.json sur la branche `releves` de ce
// depot et le dessine. Aucune donnee n'entre dans la page comme du HTML :
// tout passe par textContent et createElement.
//
// Module ES : les bancs l'importent sous Node, ou `document` n'existe pas.

export const SOURCE = "https://raw.githubusercontent.com/kohex-net/todis-status/releves/status.json";
export const PEREMPTION_MIN = 30;
const RAFRAICHISSEMENT_MS = 5 * 60 * 1000;
const LOCALES = { fr: "fr-FR", en: "en-US", es: "es-ES" };

export const TEXTES = {
  fr: {
    chargement: "Chargement des relevés…",
    indisponible: "Les relevés sont indisponibles pour le moment.",
    operationnel: "Tous les services sont opérationnels",
    panne: "Incident en cours : {plateformes}",
    perime: "Données périmées : aucun relevé depuis plus de {minutes} minutes",
    dernierReleve: "Dernier relevé : {heure}, heure de Paris",
    etatOperationnel: "Opérationnel",
    etatPanne: "En panne depuis {heure}",
    etatInconnu: "Non mesuré",
    statut_operationnel: "Opérationnel",
    statut_perturbe: "Perturbation",
    statut_panne: "Panne",
    statut_inconnu: "Non mesuré",
    disponibilite: "{valeur} de disponibilité",
    ilYa: "Il y a {n} jours",
    aujourdhui: "Aujourd'hui",
    nonMesure: "non mesuré",
    aucuneInterruption: "aucune interruption",
    interruption: "interruption : {duree}",
    sondesEnEchec: "en échec : {sondes}",
    couverture: "mesuré sur {valeur} de la journée",
    aide: "Survolez ou touchez une barre pour le détail du jour.",
    sonde_api: "API",
    sonde_registre: "registre de confiance",
    sonde_site: "site",
    sonde_souscription: "souscription",
    sonde_accueil: "page d'accueil",
  },
  en: {
    chargement: "Loading measurements…",
    indisponible: "Measurements are unavailable at the moment.",
    operationnel: "All services are operational",
    panne: "Ongoing incident: {plateformes}",
    perime: "Stale data: no measurement for more than {minutes} minutes",
    dernierReleve: "Last measurement: {heure}, Paris time",
    etatOperationnel: "Operational",
    etatPanne: "Down since {heure}",
    etatInconnu: "Not measured",
    statut_operationnel: "Operational",
    statut_perturbe: "Disruption",
    statut_panne: "Outage",
    statut_inconnu: "Not measured",
    disponibilite: "{valeur} uptime",
    ilYa: "{n} days ago",
    aujourdhui: "Today",
    nonMesure: "not measured",
    aucuneInterruption: "no interruption",
    interruption: "interruption: {duree}",
    sondesEnEchec: "failing: {sondes}",
    couverture: "measured over {valeur} of the day",
    aide: "Hover or tap a bar for the details of that day.",
    sonde_api: "API",
    sonde_registre: "trust registry",
    sonde_site: "website",
    sonde_souscription: "sign-up",
    sonde_accueil: "home page",
  },
  es: {
    chargement: "Cargando las mediciones…",
    indisponible: "Las mediciones no están disponibles en este momento.",
    operationnel: "Todos los servicios están operativos",
    panne: "Incidencia en curso: {plateformes}",
    perime: "Datos caducados: ninguna medición desde hace más de {minutes} minutos",
    dernierReleve: "Última medición: {heure}, hora de París",
    etatOperationnel: "Operativo",
    etatPanne: "Caído desde {heure}",
    etatInconnu: "Sin medir",
    statut_operationnel: "Operativo",
    statut_perturbe: "Perturbación",
    statut_panne: "Caída",
    statut_inconnu: "Sin medir",
    disponibilite: "{valeur} de disponibilidad",
    ilYa: "Hace {n} días",
    aujourdhui: "Hoy",
    nonMesure: "sin medir",
    aucuneInterruption: "ninguna interrupción",
    interruption: "interrupción: {duree}",
    sondesEnEchec: "con fallo: {sondes}",
    couverture: "medido durante el {valeur} del día",
    aide: "Pase el cursor o toque una barra para ver el detalle del día.",
    sonde_api: "API",
    sonde_registre: "registro de confianza",
    sonde_site: "sitio web",
    sonde_souscription: "suscripción",
    sonde_accueil: "página de inicio",
  },
};

export function formater(modele, valeurs) {
  return modele.replace(/\{(\w+)\}/g, (_, cle) => String(valeurs[cle]));
}

// Tronque a deux decimales plutot que d'arrondir : 99,996 % ne doit pas
// s'afficher 100,00 % sur un jour qui a connu une interruption.
export function pourcentage(x, langue) {
  if (x === null || x === undefined) return TEXTES[langue].nonMesure;
  const tronque = Math.floor(x * 10000 + 1e-9) / 10000;
  return new Intl.NumberFormat(LOCALES[langue], {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(tronque);
}

export function estPerime(dernier, maintenant) {
  if (!dernier) return true;
  return maintenant.getTime() - Date.parse(dernier) > PEREMPTION_MIN * 60 * 1000;
}

export function etatGlobal(statut, maintenant) {
  if (!statut) return { cle: "indisponible", plateformes: [] };
  if (estPerime(statut.dernier_releve, maintenant)) return { cle: "perime", plateformes: [] };
  const pannes = statut.plateformes.filter((p) => p.etat && p.etat.statut === "panne").map((p) => p.id);
  return { cle: pannes.length ? "panne" : "operationnel", plateformes: pannes };
}

export function duree(minutes, langue) {
  if (!minutes) return TEXTES[langue].aucuneInterruption;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function dateLongue(jour, langue) {
  return new Intl.DateTimeFormat(LOCALES[langue], {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${jour}T12:00:00Z`));
}

function heure(iso, langue) {
  return new Intl.DateTimeFormat(LOCALES[langue], {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  }).format(new Date(iso));
}

function nomSonde(nom, langue) {
  return TEXTES[langue][`sonde_${nom}`] || nom;
}

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

function detailDuJour(j, langue) {
  const T = TEXTES[langue];
  const morceaux = [dateLongue(j.date, langue), T[`statut_${j.statut}`]];
  if (j.disponibilite !== null) morceaux.push(pourcentage(j.disponibilite, langue));
  if (j.minutes_panne) morceaux.push(formater(T.interruption, { duree: duree(j.minutes_panne, langue) }));
  if (j.sondes_en_echec.length) {
    morceaux.push(formater(T.sondesEnEchec, { sondes: j.sondes_en_echec.map((s) => nomSonde(s, langue)).join(", ") }));
  }
  if (j.couverture < 1) morceaux.push(formater(T.couverture, { valeur: pourcentage(j.couverture, langue) }));
  return morceaux.join(" · ");
}

function carte(p, statut, langue) {
  const T = TEXTES[langue];
  const article = el("article", "plateforme");
  const tete = el("div", "tete");
  const titre = el("div", "titre");
  titre.append(el("h3", "", p.nom[langue]), el("p", "description", p.description[langue]));
  let etat;
  if (!p.etat) etat = el("p", "etat inconnu", T.etatInconnu);
  else if (p.etat.statut === "panne") etat = el("p", "etat panne", formater(T.etatPanne, { heure: heure(p.etat.depuis, langue) }));
  else etat = el("p", "etat operationnel", T.etatOperationnel);
  tete.append(titre, etat);

  const detail = el("p", "detail", T.aide);
  detail.setAttribute("aria-live", "polite");
  const barres = el("div", "barres");
  for (const j of p.jours) {
    const b = el("button", `barre ${j.statut}`);
    b.type = "button";
    const texte = detailDuJour(j, langue);
    b.setAttribute("aria-label", texte);
    const montrer = () => {
      detail.textContent = texte;
    };
    b.addEventListener("mouseenter", montrer);
    b.addEventListener("focus", montrer);
    b.addEventListener("click", montrer);
    barres.append(b);
  }

  const pied = el("div", "pied");
  pied.append(
    el("span", "", formater(T.ilYa, { n: statut.jours.length })),
    el("span", "dispo", formater(T.disponibilite, { valeur: pourcentage(p.disponibilite, langue) })),
    el("span", "", T.aujourdhui),
  );
  article.append(tete, barres, pied, detail);
  return article;
}

function rendre(statut, langue) {
  const T = TEXTES[langue];
  const global = etatGlobal(statut, new Date());
  const bandeau = document.getElementById("bandeau");
  bandeau.className = `bandeau ${global.cle}`;
  if (global.cle === "panne") {
    const noms = statut.plateformes.filter((p) => global.plateformes.includes(p.id)).map((p) => p.nom[langue]);
    bandeau.textContent = formater(T.panne, { plateformes: noms.join(", ") });
  } else if (global.cle === "perime") {
    bandeau.textContent = formater(T.perime, { minutes: PEREMPTION_MIN });
  } else {
    bandeau.textContent = T[global.cle];
  }
  if (!statut) return;
  document.getElementById("releve").textContent = statut.dernier_releve
    ? formater(T.dernierReleve, { heure: heure(statut.dernier_releve, langue) })
    : "";
  document.getElementById("plateformes").replaceChildren(...statut.plateformes.map((p) => carte(p, statut, langue)));
}

async function charger(langue) {
  let statut = null;
  try {
    const reponse = await fetch(SOURCE, { cache: "no-store" });
    if (reponse.ok) statut = await reponse.json();
  } catch {
    statut = null;
  }
  rendre(statut, langue);
}

function demarrer() {
  const langue = TEXTES[document.documentElement.lang] ? document.documentElement.lang : "en";
  charger(langue);
  setInterval(() => charger(langue), RAFRAICHISSEMENT_MS);
}

if (typeof document !== "undefined") demarrer();
