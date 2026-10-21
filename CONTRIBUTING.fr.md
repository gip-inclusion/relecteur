# Contribuer

```sh
python3 -m venv .venv
.venv/bin/pip install --editable '.[dev]'
.venv/bin/pytest
.venv/bin/mypy
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

La suite de tests n'a besoin ni d'un dépôt applicatif, ni d'accès réseau, ni d'un modèle : un
test qui tente d'ouvrir une connexion échoue. Les tests couvrent :

- le scorer, avec un juge déterministe ;
- le chargement des cas et le fichier de configuration ;
- le choix du protocole du modèle et des clés des juges ;
- la combinaison des instructions du reviewer ;
- les reviews enregistrées ;
- l'adaptateur du moteur et le résumé d'une review en CI, sur des sorties du moteur enregistrées
  ou écrites d'après son code source ;
- le placement des remarques sur les lignes d'un diff ;
- la lecture des réponses par le juge `albert`, enregistrées ou construites pour un cas limite ;
- la règle du relais pour `tool_choice`.

L'exécution de git, du moteur, des juges et du relais lui-même est vérifiée par des passages
réels.
