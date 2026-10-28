# relecteur

relecteur fait relire les pull requests (PR) d'un dépôt par un reviewer automatique qui s'appuie
sur [open-code-review](https://github.com/alibaba/open-code-review), et mesure la qualité de ce
reviewer sur d'anciennes PR.

En CI, une action GitHub relit chaque nouvelle PR et commente les lignes concernées. En local, un
harnais d'évaluation fait relire d'anciennes PR au même reviewer et vérifie qu'il se comporte
comme attendu : il doit se taire sur une PR approuvée sans le moindre commentaire, et signaler un
défaut qu'il a fallu corriger, après le merge ou pendant la review.

relecteur fonctionne avec n'importe quel langage, framework ou métier : c'est le dépôt qui fournit
ses cas et ses consignes.

## Démarrage rapide

### Faire relire les pull requests d'un dépôt

Pas besoin de cas d'évaluation pour commencer.

1. Choisissez le modèle. Par défaut, relecteur utilise `deepseek-v4-flash-0731`, servi par
   [Albert](https://guides.ia.numerique.gouv.fr/albert-api), où vous pouvez
   [générer une clé](https://guides.ia.numerique.gouv.fr/albert-api/compte-and-usage/api-keys).
   Pour un autre modèle, accessible par l'API d'Anthropic ou par une API compatible OpenAI,
   indiquez-le dans un fichier `.relecteur/config.toml` à la racine du dépôt :

   ```toml
   [model]
   url = "https://api.anthropic.com"
   name = "claude-opus-5-5"
   ```

   Sans ce fichier, relecteur envoie la clé à Albert, qui refuse les autres clés. Les autres
   réglages sont décrits dans [Configuration](docs/configuration.md).
2. Créez dans le dépôt un secret `RELECTEUR_API_KEY` avec la clé d'API de ce modèle.
3. Copiez ce workflow dans `.github/workflows/review.yml` et mergez-le. Remplacez d'abord
   `<commit>` par le SHA complet du dernier commit de `main` de relecteur :

   ```yaml
   name: Review

   on:
     pull_request:
       types: [opened, ready_for_review, synchronize]
     issue_comment:
       types: [created]

   permissions:
     contents: read
     pull-requests: write
     statuses: write

   jobs:
     relecteur:
       name: Relecteur
       if: >-
         (github.event_name == 'pull_request' && !github.event.pull_request.draft
           && github.event.pull_request.user.type != 'Bot'
           && github.event.pull_request.head.repo.full_name == github.repository)
         || (github.event_name == 'issue_comment' && github.event.issue.pull_request
           && github.event.issue.state == 'open' && github.event.issue.user.type != 'Bot'
           && github.event.comment.user.type != 'Bot'
           && contains(github.event.comment.body, '@relecteur'))
       runs-on: ubuntu-latest
       timeout-minutes: 180
       concurrency:
         group: relecteur-${{ github.event.pull_request.number || github.event.issue.number }}
         cancel-in-progress: ${{ github.event_name == 'pull_request' }}
       steps:
         - uses: gip-inclusion/relecteur@<commit>
           with:
             api_key: ${{ secrets.RELECTEUR_API_KEY }}
   ```

4. Si vous le souhaitez, ajoutez à la racine un `REVIEW.md` qui précise ce que relecteur doit
   relever (voir [Instructions du reviewer](docs/configuration.md#instructions-du-reviewer)).

relecteur relit chaque PR à son ouverture, ou quand elle sort de brouillon. Si vous poussez un
commit avant la fin de la review, il reprend sur le nouveau commit. Il commente les lignes
concernées et publie un résumé. Pour relancer une review, écrivez `@relecteur` dans un
commentaire. Plus de détails dans [Review en CI](docs/ci.md).

### Évaluer relecteur sur d'anciennes pull requests

1. Installez le moteur et `relecteur`, puis mettez la clé d'API du modèle dans
   `RELECTEUR_API_KEY`. Il vous faut Python 3.11, git 2.41 et [pipx](https://pipx.pypa.io) (voir
   [Prérequis](docs/evaluation.md#prérequis)) :

   ```sh
   npm install --global @alibaba-group/open-code-review@1.12.13
   git clone https://github.com/gip-inclusion/relecteur.git
   pipx install --editable ./relecteur
   export RELECTEUR_API_KEY=<votre clé>
   ```

   Avec les réglages par défaut, cette clé sert aussi au juge, qui note les remarques avec un
   modèle d'Albert. Si le reviewer n'est pas sur Albert, ou pour changer de juge, voir
   [Juge](docs/evaluation.md#juge).

2. Créez un dossier `.relecteur/cases` à la racine du dépôt et écrivez-y quelques cas (voir
   [Cas](docs/evaluation.md#cas)), ou faites-en rédiger par un agent (voir
   [Rédiger des cas avec un agent](docs/evaluation.md#rédiger-des-cas-avec-un-agent)).
3. Depuis le dépôt, lancez `relecteur validate` pour vérifier les cas, puis `relecteur eval` pour
   les faire relire.

## Ce qu'apporte relecteur

open-code-review fait la review : il relit le diff, en local ou en CI, et commente les lignes
concernées. relecteur y ajoute :

- **la mesure du reviewer sur votre dépôt** : `relecteur eval` lui fait relire d'anciennes PR du
  dépôt dont on connaît la bonne réponse, se taire ou signaler un défaut précis, et un juge note
  ses remarques (voir [Cas](docs/evaluation.md#cas) et [Juge](docs/evaluation.md#juge)). On
  peut ainsi comparer deux modèles, ou tester une consigne avant de la déployer ;
- **une relecture selon les consignes du dépôt** : open-code-review prend ses consignes dans un
  fichier de règles à son format, et applique sinon ses propres règles, dont une règle par défaut
  qui pousse à commenter le nommage et la couverture de tests. relecteur construit ce fichier à
  partir de `REVIEW.md` et `AGENTS.md`, sans rien d'autre à maintenir (voir
  [Instructions du reviewer](docs/configuration.md#instructions-du-reviewer)) ;
- **une review qui va au bout malgré les limites du modèle** : open-code-review réessaie une
  requête refusée pendant quelques secondes, puis abandonne ses fichiers. Le relais de relecteur
  la renvoie une fois la limite de débit passée, et une review écourtée malgré tout reprend sur
  les fichiers restants. Pour l'instant, le relais rétablit aussi les appels d'outils que la
  passerelle d'Albert désactive (voir
  [Le relais vers Albert](docs/configuration.md#le-relais-vers-albert)) ;
- **en CI, la configuration évaluée** : l'action GitHub d'open-code-review prend le modèle et les
  réglages en paramètres du workflow, à recopier depuis ce qu'on a évalué. Celle de relecteur les
  lit dans `.relecteur/config.toml`, comme `relecteur eval` ;
- **un résumé qui dit comment la review s'est terminée** : quand le moteur échoue, l'action
  d'open-code-review fait échouer le job sans rien poster, et sinon son résumé ne dit pas si des
  fichiers sont restés sans review. Celui de relecteur dit si la review est complète, quels
  fichiers n'ont pas été relus et comment la relancer, et le job n'échoue que lorsque le reviewer
  est en cause, pas quand le modèle est indisponible (voir [Review en CI](docs/ci.md)).

Pour situer relecteur face à des services de review comme Claude Code Review, CodeRabbit ou
Greptile, voir [Comparaisons](docs/comparaisons.md).

## Documentation

- [Review en CI](docs/ci.md) : quand l'action relit, `@relecteur`, ce qu'on voit sur la PR et ce
  qui se passe quand la review n'aboutit pas.
- [Évaluation](docs/evaluation.md) : installation, cas, commandes et juge.
- [Configuration](docs/configuration.md) : modèle, consignes du reviewer, réglages et relais
  vers Albert.
- [Comparaisons](docs/comparaisons.md) : relecteur face à Claude Code Review, CodeRabbit et
  Greptile.
- [Contribuer](CONTRIBUTING.md) : développement et tests.
