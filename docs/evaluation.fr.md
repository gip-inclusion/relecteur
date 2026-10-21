# Évaluation

`relecteur eval` fait relire d'anciennes PR du dépôt au reviewer de la CI, et vérifie qu'il se
comporte comme attendu : il doit se taire sur une PR saine et signaler le défaut d'une PR qu'il a
fallu corriger. Chaque PR est décrite par un cas.

## Prérequis

- Python 3.11 ou plus, et git 2.41 ou plus (open-code-review en a besoin).
- La CLI d'open-code-review en version 1.12.13, qui fournit la commande `ocr` :

  ```sh
  npm install --global @alibaba-group/open-code-review@1.12.13
  ```

- La clé d'API du modèle, dans `RELECTEUR_API_KEY`. Pour le modèle par défaut, vous pouvez en
  générer une sur [Albert](https://guides.ia.numerique.gouv.fr/albert-api/compte-and-usage/api-keys).
- La clé d'API du juge, dans `RELECTEUR_JUDGE_API_KEY` : une clé Albert pour le juge `albert`, ou
  une clé [TypeSafe](https://typesafe.ai) pour le juge `jev`. Si Albert sert déjà le reviewer, le
  juge `albert` reprend sa clé et cette variable est inutile.

Vous pouvez aussi mettre ces clés dans un fichier `.env` à la racine du dépôt évalué. Une variable
déjà définie dans l'environnement garde sa valeur. Ne versionnez pas ce fichier. Seules les clés
se lisent dans l'environnement : le modèle et le juge se choisissent dans `.relecteur/config.toml`
(voir [Réglages](configuration.fr.md#réglages)).

## Installation

Installez la commande `relecteur` une fois pour toutes avec [pipx](https://pipx.pypa.io), qui lui
donne son propre environnement (`brew install pipx` sur macOS). Le paquet n'est pas encore
publié : installez-le depuis une copie locale du dépôt.

```sh
pipx install --editable ../relecteur
```

En CI, où l'environnement est jetable, un simple `pip install` suffit.

## Cas

Un cas est un fichier TOML qui décrit une ancienne PR, figée par ses commits de base et de tête.
Les cas se trouvent dans le dossier `.relecteur/cases` du dépôt, un fichier par cas. Le nom du
fichier sert de nom au cas.

Il y a deux sortes de cas :

- un **cas de silence** décrit une PR approuvée sans le moindre commentaire : le reviewer doit se
  taire ;
- un **cas de défaut** liste des défauts qu'il a fallu corriger, après le merge ou pendant la
  review : le reviewer doit signaler chacun d'eux.

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
| `pull_request` | Lien ou numéro de la PR, pour les personnes qui lisent le cas. |
| `notes` | Ce que le reviewer doit faire, et pourquoi. Le reviewer ne le voit jamais. |
| `base`, `head` | Les SHA complets du code relu par un humain : les commits de base et de tête de la PR. Pour un défaut repéré pendant la review, `head` est le commit commenté. |
| `max_findings` | Le nombre maximal de remarques : au-delà, le cas échoue. |
| `expected_defects` | Facultatif. Les défauts que le reviewer doit signaler, qui font du cas un cas de défaut (voir plus bas). |
| `pr` | Facultatif, en fin de fichier. Le `title` et la `description` de la PR, tels que son auteur les a écrits. Le reviewer y lit l'intention du changement, comme en CI. |

Un cas de défaut décrit chaque défaut en quelques mots, avec le lien vers sa correction :

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
| `path`, `line` | L'emplacement du défaut dans le commit `head`. `line` peut être une liste (`line = [28, 35]`) quand le défaut peut se signaler à plusieurs endroits, par exemple une fonction et son appel. |
| `also_at` | Facultatif. D'autres fichiers où le défaut peut se signaler, avec leurs lignes : `also_at = [{ path = "src/invoice.py", line = 7 }]`. |
| `concept` | Le défaut, en quelques mots simples. Le juge le compare au texte des remarques. |
| `fix` | Le lien vers la correction, pour les personnes qui lisent le cas : sa PR, ou son commit s'il n'y a pas de PR. Pour un défaut repéré pendant la review, c'est le commit de correction dans la PR. |
| `escaped_review` | Vrai si la review humaine a laissé passer le défaut. Le rapport montre ainsi ce que le reviewer trouve en plus des humains, et pas seulement à quel point il leur ressemble. |

Prévoyez dans `max_findings` au moins une remarque par défaut attendu.

Vous pouvez écrire un cas à la main ou le faire rédiger par un agent (voir plus bas). Dans les deux
cas, ajoutez-le par une PR : c'est en la relisant qu'une personne le valide.

Le harnais retrouve le code de chaque PR à partir des commits du cas, avec git, quel que soit
l'état actuel des branches. S'il manque un commit en local, par exemple la tête d'une PR mergée en
squash, il le récupère sur le remote `origin`.

### Rédiger des cas avec un agent

Le skill [`skills/build-eval-cases/SKILL.md`](../skills/build-eval-cases/SKILL.md) permet à un
agent de rédiger des cas à partir de l'historique d'un dépôt GitHub :

- des cas de silence à partir de PR approuvées sans commentaire ;
- des cas de défaut à partir de commits de correction, ou de commentaires de review que l'auteur
  a suivis, qu'ils signalent un défaut ou une convention écrite non respectée.

L'agent vérifie ses cas avec `relecteur validate` et les laisse non commités, chacun avec ses
preuves. Vous les relisez, gardez ceux qui tiennent et les ajoutez par une PR.

Un skill est un fichier Markdown que n'importe quel agent peut suivre. Avec Claude Code, copiez le
dossier `build-eval-cases` dans le dossier `.claude/skills` du dépôt, puis lancez
`/build-eval-cases` suivi du nombre de cas voulu (5 par défaut). Avec un autre agent, demandez-lui
de lire le fichier et de le suivre.

## Utilisation

Depuis n'importe quel dossier du dépôt évalué :

```sh
relecteur validate      # vérifie le format de chaque cas
relecteur eval          # fait relire chaque cas et rend un verdict
```

Par défaut, les deux commandes lisent le dossier `.relecteur/cases` à la racine du dépôt, et
s'arrêtent avec un message clair s'il n'existe pas. Vous pouvez aussi leur passer des fichiers ou
des dossiers : `relecteur eval .relecteur/cases/pr-1234.toml` ne lance qu'un cas.

Une évaluation prend du temps, et les reviews varient d'une exécution à l'autre. Avec
`--save-reviews DIR`, chaque review est enregistrée dans `DIR/<cas>.json` dès qu'elle se termine,
et le modèle utilisé dans `DIR/reviewer.json`. `relecteur score DIR` juge ensuite ces reviews à
nouveau, avec un autre juge ou un autre seuil, sans les refaire. Un cas sans review enregistrée
est une erreur.

```sh
relecteur eval --save-reviews runs/1     # fait les reviews et les garde
relecteur score runs/1 --judge jev       # juge à nouveau les mêmes reviews
```

`validate` sort avec le code 1 si un cas est invalide, en indiquant chaque fichier et son
problème. Les codes de sortie d'`eval` :

| Code | Signification |
| --- | --- |
| 0 | Tous les cas de silence sont passés. |
| 1 | Au moins un cas de silence a échoué : le reviewer a fait trop de remarques, ou n'a pas terminé sa review. |
| 2 | Entrée invalide : cas mal formé, clé d'API manquante, option invalide ou dépôt introuvable. |
| 3 | Pas de verdict : aucun cas de silence n'a échoué, mais l'un d'eux n'a pas pu être relu (modèle indisponible, quota atteint, délai dépassé, moteur absent, ou PR dont le moteur ne relit aucun fichier). |

Pour chaque cas, le rapport donne la durée de la review, pauses comprises, et les tokens
consommés. Il se termine par leur total et leur moyenne par review.

Seuls les cas de silence décident du verdict. Une remarque sur une PR saine est une régression,
alors qu'un défaut manqué n'en est pas une. Les cas de défaut apparaissent dans le rapport, avec
les défauts trouvés et ceux que la review humaine avait laissés passer, mais ils ne changent
jamais le code de sortie.

Une review incomplète n'est jamais notée. Si le modèle ou le moteur était injoignable, le cas est
en erreur, sans verdict. Si le reviewer a répondu mais n'a pas terminé, par exemple parce qu'il a
épuisé ses tours, le cas échoue : un reviewer mal configuré ne doit pas passer pour un modèle
indisponible. Une PR dont le moteur ne relit aucun fichier ne teste rien et n'a pas de verdict non
plus.

## Juge

Pour savoir si une remarque trouve un défaut attendu, relecteur procède en deux temps. La remarque
doit d'abord porter sur le fichier du défaut, à quelques lignes près, sans quoi elle n'est pas
soumise au juge. Le juge donne ensuite la probabilité que la remarque décrive le défaut : au-delà
d'un seuil, le défaut est trouvé. Une remarque ne trouve qu'un défaut, celui qu'elle décrit le plus
probablement. Elle ne compte jamais pour un défaut voisin.

Le juge se choisit dans la table `[judge]` de `.relecteur/config.toml` (voir
[Réglages](configuration.fr.md#réglages)). Ces options de `relecteur eval` et `relecteur score` la
remplacent :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `name` | `--judge` | `albert` | `albert` interroge un modèle d'Albert ; `jev` interroge [Jev](https://typesafe.ai), le modèle de jugement de TypeSafe. |
| `model` | `--judge-model` | `deepseek-v4-flash-0731` pour `albert`, `jev-latest` pour `jev` | |
| `threshold` | `--judge-threshold` | `0.5` | La probabilité à partir de laquelle un défaut est trouvé. |
| | `--line-tolerance` | `5` | L'écart maximal, en lignes, entre une remarque et un défaut pour interroger le juge. |

La clé d'API du juge est `RELECTEUR_JUDGE_API_KEY`. Le juge `albert` demande au modèle de
répondre par oui ou par non, et lit la probabilité du oui dans les logprobs. Il interroge toujours
Albert, quel que soit le modèle qui relit, pour que tous les reviewers soient notés par le même
juge. Si Albert sert aussi le reviewer, il reprend sa clé. Le juge `jev` appelle l'API System One
de TypeSafe, comme le fait RubyLLM.

Si le juge ne peut pas répondre, parce que le modèle est indisponible ou que sa réponse est
illisible, le cas est en erreur. Ce n'est jamais compté comme un défaut manqué.
