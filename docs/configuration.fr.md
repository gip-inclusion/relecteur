# Configuration

Le reviewer se configure dans le dépôt relu : le modèle et les réglages dans
`.relecteur/config.toml`, les consignes dans `REVIEW.md` et `AGENTS.md`. `relecteur eval` et
l'action de CI lisent les mêmes fichiers.

## Modèle

open-code-review se connecte au modèle par une API compatible OpenAI, comme celle d'Albert, ou par
l'API d'Anthropic. Le modèle se choisit dans la table `[model]` de `.relecteur/config.toml` (voir
[Réglages](#réglages)). Ces options de `relecteur eval` la remplacent :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `url` | `--model-url` | `https://albert.api.etalab.gouv.fr/v1` | L'adresse de l'API. Celle d'Anthropic est `https://api.anthropic.com`, sans `/v1`. |
| `name` | `--model` | `deepseek-v4-flash-0731` | |
| `protocol` | | `anthropic` pour `api.anthropic.com`, `openai` sinon | `openai` ou `anthropic`, à préciser quand l'adresse ne permet pas de le deviner, par exemple derrière une passerelle. |

La clé d'API du modèle est `RELECTEUR_API_KEY`. Si `--model-url` change l'adresse, le protocole
configuré est ignoré.

```toml
[model]
url = "https://api.anthropic.com"
name = "claude-opus-5-5"
```

Le moteur tourne avec un dossier personnel vide : une configuration personnelle d'open-code-review
ne peut donc pas remplacer le modèle choisi ici. git garde la configuration globale de votre vrai
dossier personnel.

## Instructions du reviewer

Le reviewer suit le `REVIEW.md` du dépôt, qui dit comment relire, puis son `AGENTS.md`, qui donne
les conventions de code. `relecteur eval` les lit dans votre copie de travail : on évalue ainsi
les consignes d'aujourd'hui sur d'anciennes PR.

open-code-review n'applique qu'une règle par fichier. relecteur combine donc les deux fichiers en
une seule règle, appliquée à tous les fichiers. Pour les fichiers Python, elle s'ajoute à la règle
du moteur. Pour les autres, elle la remplace, qu'il s'agisse des règles du moteur pour quelques
types de fichiers (Maven, Gradle, package.json…) ou de sa règle par défaut, qui pousse à commenter
le nommage et la couverture de tests. S'il n'y a qu'un des deux fichiers, la règle est ce fichier.
S'il n'y en a aucun, le moteur garde ses propres règles.

`relecteur rule` affiche la règle que reçoit le moteur, dans son format, avec les motifs `include`
et `exclude` des réglages. Sans `REVIEW.md` ni `AGENTS.md`, cette règle est vide et le moteur
garde les siennes.

## Réglages

Le fichier `.relecteur/config.toml` fixe ce que mesure une évaluation : le moteur et le modèle qui
relisent, pour `relecteur eval` comme pour la CI, et le juge. Il ne contient aucun secret et se
versionne avec les cas : on sait ainsi toujours quel reviewer et quel juge ont produit un score.
Les options de `relecteur eval` et `relecteur score` le remplacent le temps d'une exécution.

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

Le modèle est décrit plus haut, et le juge dans [Évaluation](evaluation.fr.md#juge). Les réglages
du moteur se placent en tête du fichier :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `effort` | `--effort` | `high` | Le niveau d'effort du moteur : `low`, `medium` ou `high`. Plus il est élevé, plus le moteur dépense de tours et de tokens par groupe de fichiers. |
| `concurrency` | `--concurrency` | `2` | Le nombre de groupes de fichiers relus en même temps. |
| `max_tokens_budget` | | aucun | Le nombre de tokens qu'une review peut dépenser. Au-delà, le moteur ne relit plus de nouveaux fichiers, et la review compte comme non terminée. |
| `language` | | anglais | La langue des remarques. |
| `include` | | aucun | Les motifs des fichiers à relire que le moteur écarte par défaut, comme les tests et les templates. |
| `exclude` | | aucun | Les motifs des fichiers à ne jamais relire, comme les fichiers générés, même s'ils correspondent à `include`. |

Le moteur relit les fichiers par groupes, et chaque groupe envoie ses propres requêtes. Albert
refuse les requêtes trop nombreuses (HTTP 429), c'est pourquoi relecteur relit 2 groupes à la
fois par défaut. Avec un modèle sans cette limite, vous pouvez augmenter ce nombre. En effort
élevé, chaque requête contient toute la conversation de son groupe : sur Albert, les plus grosses
PR ne vont donc au bout qu'avec un seul groupe à la fois. On y perd peu de temps, car c'est la
limite par minute qui ralentit la review.

Quand une requête est refusée, le moteur réessaie pendant quelques secondes, puis abandonne les
fichiers concernés. Il fait de même avec les fichiers qui dépassent son délai. Le relais (voir
plus bas) renvoie la requête refusée une fois la minute passée, si bien que le moteur voit
rarement le refus. S'il reste malgré tout des fichiers non relus, `relecteur eval` reprend la
session du moteur après 1, puis 2, puis 4 minutes, et le moteur ne relit que les fichiers
restants. Un cas encore incomplet après ces reprises n'a pas de verdict.

## Le relais vers Albert

Le moteur travaille en faisant appeler des outils par le modèle : lire un fichier, chercher dans le
code, poster une remarque. Jusqu'à sa version 0.8.0, la passerelle d'Albert transforme une requête
qui ne précise pas `tool_choice` en `tool_choice: "none"`. C'est l'inverse de la convention OpenAI
sur laquelle compte le moteur : DeepSeek n'appelle alors aucun outil, et la review n'aboutit pas.
Albert 0.9.0 corrige ce comportement
([changelog](https://guides.ia.numerique.gouv.fr/albert-api/ressources/changelog)), mais n'est
pas encore en service.

Albert limite aussi le nombre de tokens qu'un modèle reçoit par minute, et une review en effort
élevé dépasse cette limite. Albert répond alors HTTP 429, et le moteur abandonne les fichiers de la
requête au bout de quelques secondes.

`relecteur eval` et l'action passent donc par un relais local pour joindre une API compatible
OpenAI. C'est un petit processus qui écoute sur 127.0.0.1 pendant la review. Il ajoute
`tool_choice: "auto"` aux requêtes qui utilisent des outils, renvoie une requête refusée en 429
après 20, puis 40, puis 60 secondes, et transmet tout le reste tel quel. Avec l'API d'Anthropic,
le moteur se connecte directement.

Pour lancer le moteur vous-même, démarrez le relais et faites pointer le moteur dessus :

```sh
relecteur proxy --port 8765        # dans un autre terminal
OCR_LLM_URL=http://127.0.0.1:8765 OCR_LLM_TOKEN=$RELECTEUR_API_KEY \
OCR_LLM_MODEL=deepseek-v4-flash-0731 OCR_LLM_PROTOCOL=openai \
ocr review --from <base> --to <head>
```

Une fois la correction en service sur Albert, le relais ne servira plus qu'à gérer la limite de
débit.
