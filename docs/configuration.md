# Configuration

Le reviewer se configure dans le dépôt relu : le modèle et les réglages dans
`.relecteur/config.toml`, les consignes dans `REVIEW.md` et `AGENTS.md`.

## Modèle

Par défaut, relecteur utilise `deepseek-v4-flash-0731`, servi par Albert. Pour changer de modèle, créez un fichier
`.relecteur/config.toml` à la racine du dépôt, avec une table `[model]` :

```toml
[model]
url = "https://api.anthropic.com"
name = "claude-opus-5-5"
```

Ce fichier porte aussi les autres réglages, comme l'effort ou la langue des remarques (voir
[Réglages](#réglages)).

Mettez la clé d'API de ce modèle dans `RELECTEUR_API_KEY` : le secret du dépôt pour la CI, une
variable d'environnement pour `relecteur eval`.

Le modèle doit être accessible par une API compatible OpenAI, comme celle d'Albert, ou par l'API
d'Anthropic.

| Réglage | Défaut | Rôle |
| --- | --- | --- |
| `url` | `https://albert.api.etalab.gouv.fr/v1` | L'adresse de l'API. Pour Anthropic : `https://api.anthropic.com`. |
| `name` | `deepseek-v4-flash-0731` | Le nom du modèle, tel que l'API l'attend. |
| `protocol` | déduit de l'adresse | `anthropic` ou `openai`. Par défaut, `anthropic` pour `api.anthropic.com` et `openai` sinon. À préciser seulement quand l'adresse ne suffit pas, par exemple derrière une passerelle. |

Pour essayer un autre modèle en local sans toucher au fichier, passez `--model-url` et `--model` à
`relecteur eval`. Ils remplacent `url` et `name` le temps d'une exécution. Si `--model-url` change
l'adresse, `protocol` est ignoré.

## Instructions du reviewer

Le reviewer suit `REVIEW.md`, qui dit comment relire, puis `AGENTS.md`, qui donne les conventions
de code. relecteur les transmet au moteur comme consignes pour tous les fichiers.

Le moteur a ses propres consignes : une par langage ou type de fichier (Java, Go, TypeScript,
YAML…), et une par défaut pour les autres, qui pousse à commenter le nommage et la couverture de
tests. Vos consignes les remplacent toutes. Sans `REVIEW.md` ni `AGENTS.md`, le moteur garde les
siennes.

`relecteur eval` lit ces fichiers dans votre copie de travail : vous pouvez donc tester une
modification de `REVIEW.md` avant de la merger. En CI, ils sont lus sur la branche de base.

`relecteur rule` affiche le fichier de règles que reçoit le moteur.

## Réglages

Le fichier `.relecteur/config.toml` fixe le modèle, le juge et les réglages du moteur, pour
`relecteur eval` comme pour la CI :

```toml
effort = "high"
concurrency = 2
max_tokens_budget = 2000000
language = "French"
include = ["**/*_spec.rb", "**/*.erb"]
exclude = ["db/schema.rb", "db/migrate/**", "Gemfile.lock"]

[model]
url = "https://albert.api.etalab.gouv.fr/v1"
name = "deepseek-v4-flash-0731"

[judge]
name = "jev"
threshold = 0.5
```

La table `[model]` est décrite [plus haut](#modèle), la table `[judge]` dans
[Évaluation](evaluation.md#juge). Les autres réglages se placent en tête du fichier :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `effort` | `--effort` | `high` | Le niveau d'effort du moteur : `low`, `medium` ou `high`. Plus il est élevé, plus le moteur dépense de tours et de tokens par groupe de fichiers. |
| `concurrency` | `--concurrency` | `2` | Le nombre de groupes de fichiers relus en même temps. |
| `max_tokens_budget` | | aucun | Le nombre de tokens qu'une review peut dépenser. Au-delà, le moteur ne relit plus de nouveaux fichiers, et la review compte comme non terminée. |
| `language` | | `French` | La langue des remarques, par exemple `English`. |
| `include` | | aucun | Les motifs des fichiers à relire que le moteur écarte par défaut, comme les tests et les templates. |
| `exclude` | | aucun | Les motifs des fichiers à ne jamais relire, comme les fichiers générés, même s'ils correspondent à `include`. |

Pour essayer une autre valeur sans modifier le fichier, passez l'option de la colonne « Option » à
`relecteur eval` : `relecteur eval --effort medium` relit en effort moyen, quel que soit le
réglage.

Albert refuse les requêtes au-delà d'un certain débit (HTTP 429) : c'est pourquoi `concurrency`
vaut 2 par défaut. Avec un modèle sans cette limite, vous pouvez l'augmenter. À l'inverse, sur
Albert, les plus grosses PR ne vont au bout qu'avec `concurrency = 1`.

Si des fichiers restent non relus à cause de la limite de débit ou d'un délai dépassé, relecteur
reprend la review après 1, puis 2, puis 4 minutes, sur les fichiers restants.

## Le relais vers Albert

Pour joindre une API compatible OpenAI, `relecteur eval` et l'action passent par un relais local,
qui écoute sur 127.0.0.1 pendant la review. Il corrige deux problèmes d'Albert :

- **les appels d'outils** : le moteur travaille en faisant appeler des outils au modèle, pour lire
  un fichier ou poster une remarque. Jusqu'à sa version 0.8.0, Albert les désactive quand la
  requête ne précise pas `tool_choice`, et la review n'aboutit pas. Le relais ajoute
  `tool_choice: "auto"` à ces requêtes. Albert 0.9.0 corrige ce comportement
  ([changelog](https://guides.ia.numerique.gouv.fr/albert-api/ressources/changelog)), mais n'est
  pas encore en service ;
- **la limite de débit** : Albert limite les tokens reçus par minute, et une review en effort élevé
  la dépasse. Il répond alors HTTP 429, et le moteur abandonne les fichiers de la requête au bout
  de quelques secondes. Le relais renvoie la requête après 20, puis 40, puis 60 secondes.

Le relais transmet tout le reste tel quel. Avec l'API d'Anthropic, le moteur se connecte
directement, sans relais.

Pour lancer le moteur vous-même, démarrez le relais et faites pointer le moteur dessus :

```sh
relecteur proxy --port 8765        # dans un autre terminal
OCR_LLM_URL=http://127.0.0.1:8765 OCR_LLM_TOKEN=$RELECTEUR_API_KEY \
OCR_LLM_MODEL=deepseek-v4-flash-0731 OCR_LLM_PROTOCOL=openai \
ocr review --from <base> --to <head>
```
