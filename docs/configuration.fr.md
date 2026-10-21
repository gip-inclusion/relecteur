# Configuration

Le reviewer se règle dans le dépôt relu : son modèle et ses réglages dans `.relecteur/config.toml`,
ses consignes dans `REVIEW.md` et `AGENTS.md`. `relecteur eval` et l'action de CI lisent les
mêmes fichiers.

## Modèle

open-code-review joint le modèle par une API compatible OpenAI, comme celle d'Albert, ou par
l'API d'Anthropic. Le modèle se choisit dans la table `[model]` du fichier de configuration (voir
[Réglages](#réglages)), que ces options de `relecteur eval` remplacent :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `url` | `--model-url` | `https://albert.api.etalab.gouv.fr/v1` | L'adresse de l'API ; celle d'Anthropic est `https://api.anthropic.com`, sans `/v1`. |
| `name` | `--model` | `deepseek-v4-flash-0731` | |
| `protocol` | | `anthropic` pour `api.anthropic.com`, `openai` sinon | `openai` ou `anthropic`, quand l'adresse ne permet pas de le deviner, comme pour une passerelle. |

Sa clé d'API est `RELECTEUR_API_KEY`. Un `--model-url` qui désigne une autre adresse que celle
de la configuration ignore le protocole configuré.

```toml
[model]
url = "https://api.anthropic.com"
name = "claude-opus-5-5"
```

Le moteur tourne avec un dossier personnel vide, pour qu'une configuration personnelle
d'open-code-review ne remplace jamais le modèle choisi ici ; git garde la configuration globale
du vrai dossier personnel.

## Instructions du reviewer

Le reviewer suit le `REVIEW.md` du dépôt, qui dit comment relire, puis son `AGENTS.md`, qui
donne les conventions de code, tels qu'ils sont dans la copie de travail : ce sont les
instructions d'aujourd'hui qu'on évalue sur des pull requests passées. Le moteur n'applique
qu'une règle par fichier ; `relecteur eval` combine donc les deux fichiers en une seule règle,
appliquée à tous les fichiers. Pour les fichiers Python, cette règle s'ajoute à celle du moteur.
Ailleurs, elle la remplace, qu'il s'agisse des règles du moteur pour quelques types de fichiers
(Maven, Gradle, package.json…) ou de la règle par défaut de tous les autres, qui pousse le
reviewer à commenter le nommage et la couverture de tests. Avec un seul des deux fichiers, la
règle est ce fichier ; sans aucun des deux, le moteur relit selon ses propres règles.

`relecteur rule` affiche le fichier de règles que reçoit le moteur, dans son format, avec les
motifs `include` et `exclude` des réglages ci-dessous ; sans aucun des deux fichiers, sa règle
est vide, et le moteur garde les siennes.

## Réglages

Le fichier `.relecteur/config.toml` du dépôt fixe ce que mesure une évaluation : le moteur et le
modèle qui relisent, pour `relecteur eval` et donc pour la CI, ainsi que le juge. Il ne contient
aucun secret, et il est versionné avec les cas : un score dit ainsi toujours quel reviewer et
quel juge l'ont produit. Les options de `relecteur eval` et `relecteur score` le remplacent le
temps d'une exécution.

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

Le modèle est décrit plus haut, et le juge dans [Évaluation](evaluation.fr.md#juge) ; les
réglages du moteur se placent en tête de fichier :

| Réglage | Option | Défaut | |
| --- | --- | --- | --- |
| `effort` | `--effort` | `high` | Le niveau d'effort du moteur, `low`, `medium` ou `high` : plus il est élevé, plus le moteur dépense de tours et de tokens sur chaque groupe de fichiers. |
| `concurrency` | `--concurrency` | `2` | Nombre de groupes de fichiers relus en même temps. |
| `max_tokens_budget` | | aucun | Tokens qu'une review peut dépenser ; au-delà, le moteur ne relit plus d'autres fichiers, et la review compte comme non terminée. |
| `language` | | anglais | La langue des remarques. |
| `include` | | aucun | Motifs des fichiers à relire que le moteur écarte par défaut, comme les tests et les templates. |
| `exclude` | | aucun | Motifs des fichiers à ne jamais relire, comme les fichiers générés, quoi que dise `include`. |

Chaque groupe envoie ses propres requêtes au modèle. Albert répond HTTP 429 quand il en reçoit
trop à la fois, d'où 2 groupes en même temps par défaut, un nombre qu'on peut augmenter avec un
modèle servi sans ces limites. En effort élevé, chaque requête transporte toute la conversation
de son groupe : sur Albert, les plus grosses pull requests ne vont au bout qu'avec 1 groupe à la
fois, ce qui coûte peu de temps puisque c'est la limite par minute qui ralentit une review.

Le moteur réessaie une requête refusée pendant quelques secondes, puis abandonne ses fichiers,
comme il le fait pour les fichiers qui dépassent son délai. Le relais décrit plus bas renvoie une
requête refusée par la limite de débit une fois la minute passée, si bien que le moteur voit
rarement le refus. Quand la limite de débit ou les délais ont malgré tout laissé des fichiers
non relus, `relecteur eval` reprend la session du moteur après 1, puis 2, puis 4 minutes, et le
moteur ne relit que les fichiers restants. Un cas encore incomplet après cela n'a pas de verdict.

## Le relais vers Albert

Le moteur fonctionne en faisant appeler ses outils par le modèle : lire un fichier, chercher dans
le code, poster une remarque. Jusqu'à sa version 0.8.0, la passerelle d'Albert transforme une
requête qui ne précise pas `tool_choice` en `tool_choice: "none"`, à l'inverse de la convention
OpenAI sur laquelle compte le moteur : DeepSeek n'appelle alors aucun outil, et chaque review
s'épuise sans résultat. Albert 0.9.0 corrige ce comportement
([changelog](https://guides.ia.numerique.gouv.fr/albert-api/ressources/changelog)), mais n'est
pas encore en service.

Albert limite aussi le nombre de tokens qu'un modèle reçoit par minute, et une review en effort
élevé dépasse cette limite : Albert répond alors HTTP 429, et le moteur ne réessaie que quelques
secondes avant d'abandonner les fichiers de la requête.

`relecteur eval` et l'action font donc passer les requêtes du moteur vers une API compatible
OpenAI par un relais local, un processus qui écoute sur 127.0.0.1, sur la même machine, le temps
de la review. Le relais ajoute `tool_choice: "auto"` aux requêtes qui portent des outils, renvoie
une requête refusée en 429 après 20, puis 40, puis 60 secondes, et transmet tout le reste tel
quel ; vers l'API d'Anthropic, le moteur passe en direct. Pour lancer le moteur vous-même,
démarrez le relais et faites pointer le moteur dessus :

```sh
relecteur proxy --port 8765        # dans un autre terminal
OCR_LLM_URL=http://127.0.0.1:8765 OCR_LLM_TOKEN=$RELECTEUR_API_KEY \
OCR_LLM_MODEL=deepseek-v4-flash-0731 OCR_LLM_PROTOCOL=openai \
ocr review --from <base> --to <head>
```

Une fois la passerelle corrigée en service sur Albert, le relais ne servira plus qu'à attendre la
fin de la limite de débit.
