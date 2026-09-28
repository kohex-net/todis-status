# todis-status

Page de statut des plateformes Todis, publiée sur <https://status.todis.eu>.

Elle mesure depuis l'extérieur : un workflow GitHub Actions, sur un runner hébergé par GitHub, interroge toutes les cinq minutes environ les adresses publiques de chaque plateforme. Rien ici ne dépend d'une machine de Todis ou de Kohex, et la page reste en ligne quand les plateformes ne le sont plus. Décision 0159 du dépôt `eudiw`.

## Ce qui déclenche la mesure

Le `cron` de GitHub ne tient pas cinq minutes : mesuré le 2026-09-28 sur une douzaine de dépôts réglés en `*/5`, il ne déclenche qu'environ toutes les 3 à 7 heures. Une fonction Scaleway programmée, `declencheur/handler.py`, demande donc un passage du workflow `Sonde` toutes les cinq minutes par l'API de GitHub. Elle est privée, et son jeton GitHub ne donne que le droit Actions sur ce dépôt. Le `cron` de GitHub reste déclaré, en appoint.

Chez Scaleway, région `fr-par`, projet par défaut du compte de production :

- espace de noms `todis-status` ;
- fonction `declencheur` : Python 3.12, `handler.handle`, privée, 128 Mo, secret `GITHUB_TOKEN` ;
- cron `sonde-toutes-les-5-min`, `*/5 * * * *`.

Redéployer après une modification de `declencheur/handler.py` : zipper le seul `handler.py` à la racine de l'archive, puis

```sh
scw function deploy namespace-id=<id de todis-status> name=declencheur runtime=python312 zip-file=declencheur.zip
```

Remplacer le jeton : `scw function function update <id de declencheur> secret-environment-variables.0.key=GITHUB_TOKEN secret-environment-variables.0.value=<jeton>`, lancé sans écho. Le jeton est un jeton à grain fin du compte `kohex-net`, limité à ce dépôt et au droit Actions en écriture.

## Ce qui est mesuré

`plateformes.json` déclare les plateformes et leurs sondes. Une plateforme est opérationnelle quand toutes ses sondes répondent comme attendu :

| `attendu` | Ce qui est exigé |
| --- | --- |
| `version` | HTTP 200, JSON portant `service_version` |
| `registre` | HTTP 200, JSON portant au moins une ancre, mdoc et SD-JWT VC confondus |
| `html` | HTTP 200, `text/html` |
| `json` | HTTP 200, JSON lisible |

Ce n'est pas une vérification de bout en bout : un service qui répond à ces routes peut encore échouer une vérification.

Une sonde en échec est rejouée une fois 20 secondes plus tard ; seul un double échec compte. Deux témoins tiers disent si le runner joignait Internet : un échec relevé quand aucun témoin ne répond n'est pas compté.

Une plateforme n'entre dans `plateformes.json` que le jour où elle existe et se mesure.

## Où sont les données

- `main` : le code, la page (`site/`) et les bancs.
- `releves` : un fichier par jour UTC, `releves/AAAA-MM-JJ.jsonl`, une ligne par passage, et `status.json`, les quinze jours que la page dessine. La page le lit sur `raw.githubusercontent.com`.

## Calcul

`agrege.py` fait valoir chaque relevé jusqu'au suivant, plafonné à 15 minutes : un passage sauté par le cron n'est pas une mesure. Les jours sont ceux de l'heure de Paris.

| Statut du jour | Condition |
| --- | --- |
| Panne | disponibilité mesurée sous 99 % |
| Perturbation | au moins une minute d'échec, disponibilité d'au moins 99 % |
| Opérationnel | aucun échec, au moins la moitié du jour mesurée |
| Non mesuré | aucun échec, moins de la moitié du jour mesurée |

Un échec mesuré se montre toujours, même sur un jour peu couvert. La disponibilité sur quinze jours ne s'affiche pas tant que tous les jours sont « Non mesuré ».

## Bancs

```sh
sh bancs.sh                 # tous les bancs, sortie 0 si tous verts
python3 tests/mutations.py  # chaque mutation du code doit faire rougir les bancs
```

Les deux workflows lancent `bancs.sh` avant de mesurer ou de publier. Il faut Python 3.12 ou plus, avec les données de fuseaux, et Node 20 ou plus, avec ICU complet.
