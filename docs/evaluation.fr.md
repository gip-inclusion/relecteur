# Évaluation

`relecteur eval` rejoue d'anciennes pull requests du dépôt, décrites par des cas, avec le reviewer
de la CI, et vérifie qu'il se comporte comme attendu : se taire sur une pull request saine,
signaler le défaut d'une pull request qu'il a fallu corriger.

## Prérequis

- Python 3.11 ou plus récent, et git 2.41 ou plus récent (open-code-review s'appuie sur ses
  options récentes).
- La CLI d'open-code-review, en version 1.12.13, qui fournit la commande `ocr` :

  ```sh
  npm install --global @alibaba-group/open-code-review@1.12.13
  ```

- La clé d'API du modèle qui relit, dans `RELECTEUR_API_KEY`. Pour le modèle par défaut, vous
  pouvez en générer une sur
  [Albert](https://guides.ia.numerique.gouv.fr/albert-api/compte-and-usage/api-keys).
- La clé d'API du juge, dans `RELECTEUR_JUDGE_API_KEY` : une clé Albert pour le juge `albert`,
  inutile quand Albert sert aussi le reviewer, ou une clé [TypeSafe](https://typesafe.ai) pour le
  juge `jev`.

Ces variables peuvent aussi être définies dans le fichier `.env` à la racine du dépôt évalué, que
`relecteur eval` lit comme le ferait dotenv : une variable déjà définie dans l'environnement garde
sa valeur. Ne versionnez pas ce fichier. Les clés sont les seuls réglages lus dans
l'environnement : le modèle et le juge se choisissent dans le fichier de configuration du dépôt
(voir [Réglages](configuration.fr.md#réglages)).

## Installation

Installez la commande `relecteur` une fois pour toutes, dans son propre environnement, avec
[pipx](https://pipx.pypa.io) (`brew install pipx` sur macOS). Tant que le paquet n'est pas
publié, installez-le depuis une copie locale du dépôt :

```sh
pipx install --editable ../relecteur
```

Dans un job de CI, où le Python du runner est jetable, un simple `pip install` suffit.

## Cas

Un cas est un fichier TOML qui décrit une pull request passée, figée par ses commits de base et
de tête. Les cas d'un dépôt se trouvent dans son dossier `.relecteur/cases`, un fichier par cas ;
le nom du fichier est celui du cas.

Un cas qui liste des défauts attendus est un cas de défaut : une pull request contenant un défaut
qu'il a fallu corriger, après le merge ou pendant la review, et sur laquelle le reviewer doit
signaler chaque défaut. Tous les autres sont des cas de silence : une pull request approuvée sans
le moindre commentaire, sur laquelle le reviewer doit se taire.

```toml
pull_request = "https://github.com/team/app/pull/1234"
notes = "Applique la remise avant le total. Approuvée sans aucun commentaire : le reviewer doit se taire."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 0

[pr]
title = "Appliquer la remise avant le total"
description = '''
La remise s'appliquait au total TTC, contrairement aux conditions de vente.
'''
```

| Champ | Rôle |
| --- | --- |
| `pull_request` | Lien ou identifiant de la pull request, pour les humains qui lisent le cas. |
| `notes` | Ce que le reviewer doit faire, et pourquoi. Réservé aux humains : le reviewer ne le voit jamais. |
| `base`, `head` | SHA complets du code qu'un humain a relu : les commits de base et de tête de la pull request, ou, pour un défaut repéré pendant la review, le commit commenté, comme `head`. |
| `max_findings` | Le cas échoue dès que le reviewer fait plus de remarques que ce nombre. |
| `expected_defects` | Facultatif. Les défauts que le reviewer doit signaler, ce qui fait du cas un cas de défaut : voir plus bas. |
| `pr` | Facultatif, en fin de fichier. Le `title` et la `description` de la pull request, tels que son auteur les a écrits : le reviewer y lit l'intention du changement, comme il le fera en CI. |

Un cas de défaut s'appuie sur un commit de correction, et décrit chaque défaut avec des mots
simples :

```toml
pull_request = "https://github.com/team/app/pull/1234"
notes = "Applique la remise deux fois, corrigé par #1240 le lendemain du merge : le reviewer doit le signaler."
base = "b2f7f9a327f098f6ef64d91d13c193353d92ab5d"
head = "38ed0cb00af75b0fd9b533521af64be6dd397be0"
max_findings = 2

[[expected_defects]]
path = "src/billing.py"
line = 42
concept = "Applique la remise une seconde fois quand le total de la facture est recalculé."
fix = "https://github.com/team/app/pull/1240"
escaped_review = true
```

| Champ | Rôle |
| --- | --- |
| `path`, `line` | Où se trouve le défaut, dans le commit `head` : une ligne, ou une liste de lignes (`line = [28, 35]`) quand un reviewer peut le signaler à plusieurs endroits, comme une fonction et son appel. |
| `also_at` | Facultatif. D'autres fichiers où un reviewer peut signaler le défaut, chacun avec ses lignes : `also_at = [{ path = "src/invoice.py", line = 7 }]`. |
| `concept` | Le défaut, avec des mots simples : le juge le compare au texte des remarques. |
| `fix` | Lien vers le changement qui a corrigé le défaut, pour les humains qui lisent le cas : sa pull request, son commit s'il n'en a pas, ou, pour un défaut repéré pendant la review, le commit de correction dans la pull request. |
| `escaped_review` | Si la review humaine a laissé passer le défaut : le rapport dit ainsi ce que le reviewer apporte en plus des humains, plutôt qu'à quel point il leur ressemble. |

`max_findings` doit laisser de la place pour chaque défaut attendu.

Un cas peut s'écrire à la main ou être rédigé par un agent, avec le skill ci-dessous. Dans les
deux cas, il ne compte qu'une fois mergé : ajoutez les cas par une pull request, dont la review
est le moment où un humain s'en porte garant.

Le harnais rejoue une pull request à partir de ses commits enregistrés, avec git seul, quel que
soit l'état actuel des branches : quand un commit manque en local, comme la tête d'une pull
request mergée en squash, il le récupère depuis le remote `origin`.

### Rédiger des cas avec un agent

Avec [`skills/build-eval-cases/SKILL.md`](../skills/build-eval-cases/SKILL.md), un agent rédige
des cas à partir de l'historique d'un dépôt GitHub : des cas de silence à partir de pull requests
approuvées sans commentaire, des cas de défaut à partir de commits de correction et de
commentaires de review que l'auteur a suivis, qu'ils portent sur un défaut ou sur une convention
écrite. L'agent vérifie ses cas avec `relecteur validate` et les laisse non commités, chacun avec
ses preuves : la personne qui l'a lancé les relit, garde ceux qui tiennent, et les ajoute par une
pull request.

Un skill est un fichier Markdown que n'importe quel agent peut suivre. Avec Claude Code, copiez le
dossier `build-eval-cases` dans le dossier `.claude/skills` du dépôt, puis lancez
`/build-eval-cases`, suivi du nombre de cas à rédiger (5 par défaut). Avec un autre agent,
demandez-lui de lire le fichier et de le suivre.

## Utilisation

Depuis n'importe quel dossier du dépôt évalué :

```sh
relecteur validate      # vérifie le format de chaque cas de .relecteur/cases
relecteur eval          # relit chaque cas de .relecteur/cases et rend un verdict
```

Les deux commandes lisent par défaut le dossier `.relecteur/cases` à la racine du dépôt, et
s'arrêtent avec un message clair s'il n'existe pas. Pour utiliser d'autres cas, passez des
fichiers ou des dossiers : `relecteur eval .relecteur/cases/pr-1234.toml` ne rejoue qu'un cas.

Les reviews varient d'une exécution à l'autre, et une exécution prend du temps :
`--save-reviews DIR` écrit chaque review dans `DIR/<cas>.json` dès qu'elle se termine, et le
modèle qui les a faites dans `DIR/reviewer.json` ; `relecteur score DIR` les juge à nouveau, avec
un autre juge ou un autre seuil, sans refaire les reviews. Un cas sans review enregistrée est une
erreur.

```sh
relecteur eval --save-reviews runs/1     # relit, et garde les reviews
relecteur score runs/1 --judge jev       # juge à nouveau les mêmes reviews
```

`validate` sort avec le code 1 quand un cas est invalide, en nommant chaque fichier et son
problème. `eval` sort avec :

| Code | Signification |
| --- | --- |
| 0 | Tous les cas de silence sont passés. |
| 1 | Au moins un cas de silence a échoué : le reviewer a fait trop de remarques, ou n'a pas terminé sa review. |
| 2 | Entrée invalide : cas mal formé, clé d'API manquante, option invalide, aucun dépôt trouvé. |
| 3 | Pas de verdict : aucun cas de silence n'a échoué, mais l'un d'eux n'a pas pu être relu : modèle indisponible (surcharge, quota atteint, délai dépassé), moteur absent, ou pull request dont le moteur ne relit aucun fichier. |

La ligne de chaque cas indique la durée de sa review, pauses comprises, et les tokens consommés
par le modèle ; le rapport se termine par leur total et leur moyenne par review.

Seuls les cas de silence décident du verdict : une remarque sur une pull request saine est une
régression du reviewer, un défaut manqué ne l'est pas. Les cas de défaut figurent dans le
rapport, avec les défauts trouvés et, parmi eux, ceux que la review humaine avait laissés passer,
mais ils ne changent jamais le code de sortie.

Une review qui n'a pas couvert tous les fichiers de la pull request n'est jamais notée sur ses
remarques. Si le modèle ou le moteur était injoignable, c'est une erreur, sans verdict. Si le
reviewer a été joint mais n'a pas terminé, par exemple faute de tours, le cas échoue : un reviewer
mal configuré ne doit pas se cacher derrière un « pas de verdict ». Une pull request dont le
moteur ne relit aucun fichier ne teste rien, et ne donne pas de verdict non plus.

## Juge

Une remarque est rapprochée d'un défaut attendu en deux temps. D'abord, elle doit porter sur le
fichier du défaut, à quelques lignes près ; une remarque située ailleurs n'est jamais soumise au
juge. Ensuite, le juge donne la probabilité que la remarque décrive le défaut, considéré comme
trouvé au-delà d'un seuil. Une remarque trouve au plus un défaut, celui qu'elle décrit le plus
probablement selon le juge : une remarque sur un défaut ne compte jamais pour un défaut voisin.

Le juge se choisit dans la table `[judge]` du fichier de configuration (voir
[Réglages](configuration.fr.md#réglages)), que ces options de `relecteur eval` et
`relecteur score` remplacent :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `name` | `--judge` | `albert` | `albert` interroge un modèle d'Albert ; `jev` interroge [Jev](https://typesafe.ai), le modèle de jugement de TypeSafe. |
| `model` | `--judge-model` | `deepseek-v4-flash-0731` pour `albert`, `jev-latest` pour `jev` | |
| `threshold` | `--judge-threshold` | `0.5` | Probabilité à partir de laquelle un défaut est trouvé. |
| | `--line-tolerance` | `5` | Écart maximal, en lignes, entre une remarque et un défaut pour que le juge soit interrogé. |

La clé d'API du juge est `RELECTEUR_JUDGE_API_KEY`. Le juge `albert` demande une réponse en un
mot, oui ou non, et lit la probabilité du oui dans les logprobs de ce mot. Il interroge Albert
quel que soit le modèle qui relit, pour que tous les reviewers soient comparés avec le même juge ;
quand Albert sert aussi le reviewer, la clé du reviewer sert au juge. La requête du juge `jev`
suit l'API System One de TypeSafe, telle que RubyLLM l'implémente.

Un juge qui ne peut pas répondre, parce que le modèle est indisponible ou la réponse illisible,
met le cas en erreur : ce n'est jamais compté comme un défaut manqué.
