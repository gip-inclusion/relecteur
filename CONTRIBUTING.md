# Contribuer

```sh
python3 -m venv .venv
.venv/bin/pip install --editable '.[dev]'
.venv/bin/pytest
.venv/bin/mypy
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Review des PR

Chaque PR sur relecteur est relue par relecteur, avec l'action et le code de cette PR : la review
sert aussi de test de bout en bout. Le reviewer suit `REVIEW.md` et les conventions
d'`AGENTS.md`.

## Tests

La suite de tests n'a besoin ni d'un dépôt applicatif, ni du réseau, ni d'un modèle : un test qui
tente d'ouvrir une connexion échoue. Elle couvre :

- le scorer, avec un juge déterministe ;
- le chargement des cas et du fichier de configuration ;
- le choix du protocole du modèle et des clés des juges ;
- la combinaison des instructions du reviewer ;
- les reviews enregistrées ;
- l'adaptateur du moteur et le résumé de la CI, à partir de sorties du moteur enregistrées ou
  reconstituées d'après son code source ;
- le placement des remarques sur les lignes d'un diff ;
- la lecture des réponses du juge `albert`, enregistrées ou construites pour les cas limites ;
- la règle du relais pour `tool_choice`.

Ce qui s'exécute pour de vrai, git, le moteur, les juges et le relais, se vérifie en lançant de
vraies évaluations.

## Changer de version d'open-code-review

La version du moteur est fixée à deux endroits : dans `action.yml`, qui l'installe, et dans la
commande d'installation que `relecteur eval` affiche quand le moteur manque. Modifiez les deux en
même temps, ainsi que les commandes d'installation du [README](README.md) et des
[prérequis](docs/evaluation.md#prérequis).
