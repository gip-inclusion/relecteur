# Review en CI

L'action relit une PR de la même façon que `relecteur eval` relit un cas : même moteur, mêmes
consignes, même modèle. Elle lit `REVIEW.md`, `AGENTS.md` et `.relecteur/config.toml` sur la
branche de base. Le reviewer reçoit aussi le titre et la description de la PR, pour comprendre
l'intention du changement.

L'action poste chaque remarque sur les lignes concernées et publie un résumé, qui reprend les
remarques portant sur des lignes hors du diff. Elle ne fait que commenter : elle n'approuve jamais
une PR et ne demande jamais de modifications.

## Quand l'action relit

Le workflow du [démarrage rapide](../README.md#faire-relire-les-pull-requests-dun-dépôt) relit une
PR une seule fois, à son ouverture ou quand elle sort de brouillon, pour que le coût ne dépende pas
du nombre de pushes. Si vous poussez un commit avant la fin de la review, elle s'arrête et reprend
sur le nouveau commit. Une fois la review terminée, un push ne la relance plus. Vous pouvez changer
ces déclencheurs dans le workflow. Il ne relit jamais les PR des bots. Les PR venant d'un fork ne
sont relues que si un membre de l'équipe écrit `@relecteur` en commentaire.

Pour relancer une review, écrivez `@relecteur` dans un commentaire de la PR. Il faut avoir le
droit de pousser sur le dépôt, et `@relecteur` doit figurer dans votre propre texte, pas dans une
citation. La nouvelle review relit toute la PR, sans reposter de remarque sur une ligne qui en a
déjà une. Les remarques apparaissent au nom du bot GitHub Actions.

## Résumé et statut du job

Le résumé est un commentaire de la PR. Il indique d'abord que la review est en cours, avec un lien
pour la suivre, puis comment elle s'est terminée. Comme `relecteur eval`, l'action reprend une
review que la limite de débit du modèle ou les délais ont écourtée (voir
[Réglages](configuration.md#réglages)).

Si la review reste malgré tout incomplète à cause du modèle (surcharge, limite de débit, délai
dépassé, erreur 5xx), le résumé liste les fichiers non relus et explique comment relancer. Le job
reste vert, comme quand la review atteint son budget de tokens. Si c'est le reviewer qui est en
cause (clé refusée, tours épuisés, moteur sans sortie), le résumé le dit et le job échoue : la
personne qui maintient l'installation est ainsi prévenue. Dans les deux cas, la PR n'est pas
bloquée, sauf si le job est un check requis.

Une review annulée, par un push ou à la main, ou arrêtée par `timeout-minutes`, ne publie rien : le
résumé reste « en cours », et le prochain push relance la review.

## La clé d'API

Toute personne qui peut pousser sur le dépôt peut lire ses secrets, `RELECTEUR_API_KEY` compris :
c'est le fonctionnement de GitHub Actions. Utilisez une clé dédiée à relecteur, rattachée à un
compte de service, que vous pouvez révoquer sans rien casser d'autre.

## Dépôts privés

L'action relit aussi les dépôts privés. Elle récupère le code de la PR avec le token GitHub, dans
une étape à part : le token n'est jamais écrit dans la configuration git, où le moteur pourrait le
lire.

Comme pour un dépôt public, le code relu part chez le fournisseur du modèle. Choisissez-en un à qui
vous pouvez confier ce code.
