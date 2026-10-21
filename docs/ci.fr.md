# Review en CI

`action.yml` est une action GitHub qui relit une pull request comme `relecteur eval` rejoue un
cas : `relecteur review-pr` lance la même version du moteur, avec la règle tirée de `REVIEW.md` et
d'`AGENTS.md`, les réglages et le modèle de `.relecteur/config.toml`, le tout lu sur la branche de
base, et le titre et la description de la pull request comme intention du changement. Cette étape
tourne sans token GitHub. Ensuite, `relecteur post-review` poste chaque remarque sur les lignes
qu'elle concerne, ainsi qu'un résumé qui liste les remarques portant sur des lignes absentes du
diff. L'action ne fait que commenter : elle n'approuve jamais une pull request et ne demande
jamais de modification.

## Quand l'action relit

C'est le workflow du dépôt qui décide quand relire. Celui du
[démarrage rapide](../README.fr.md#faire-relire-les-pull-requests-dun-dépôt) relit une pull
request une seule fois, à son ouverture ou à sa sortie de brouillon, pour que le coût des reviews
ne suive pas le nombre de pushes, puis à nouveau quand un commentaire appelle `@relecteur`. Il ne
relit jamais les pull requests des bots. Celles des forks n'ont pas accès aux secrets du dépôt :
c'est un commentaire de l'équipe qui les fait relire.

Un commentaire appelle le reviewer quand l'une de ses propres lignes, et non une ligne citée,
contient `@relecteur`, et que son auteur peut pousser sur le dépôt. Les remarques sont signées par
le bot de GitHub Actions. Une review relancée relit toute la pull request, sans reposter de
remarque sur des lignes qui en portent déjà une.

## Résumé et statut du job

Le résumé est un commentaire de la pull request : il annonce que la review est en cours, puis dit
comment elle s'est terminée, en français. Comme `relecteur eval`, l'action reprend une review que
la limite de débit du modèle ou les délais ont écourtée (voir
[Réglages](configuration.fr.md#réglages)).

Quand le modèle a malgré tout écourté la review (surcharge, limite de débit, délai dépassé,
réponse 5xx), le résumé dit quels fichiers n'ont pas été relus et comment relancer la review, et
le job réussit, comme lorsque la review atteint son budget de tokens, s'il y en a un. Quand c'est
le reviewer lui-même qui a empêché la review (clé refusée, tours épuisés, moteur sans sortie), le
résumé le dit, et le job échoue, pour que la personne qui maintient l'installation s'en aperçoive.
Dans aucun des deux cas la pull request n'est bloquée, tant que le job n'est pas un check requis.

## Limites

L'action ne relit que les dépôts publics : elle récupère la tête de la pull request sans
identifiants, et les garde hors de la configuration git du dépôt, pour que le moteur n'y trouve
pas le token.

La version d'open-code-review est épinglée à deux endroits : dans `action.yml`, qui l'installe, et
dans la commande d'installation qu'affiche `relecteur eval` quand le moteur est absent.
