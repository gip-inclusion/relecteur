# REVIEW.md

Comment relire une PR de relecteur : ce qu'une remarque signale, et comment l'étayer.

## Mandat

Une remarque signale l'un de ces problèmes, dans les lignes que la PR ajoute ou modifie :

- **Un défaut de correction** : pour une entrée ou un état réellement possible, le code modifié
  plante, rend un mauvais résultat ou casse un comportement qui marchait. Par exemple une sortie
  du moteur mal lue, un modèle indisponible pris pour une faute du reviewer (ou l'inverse), ou un
  code de sortie faux.
- **Un problème de sécurité** : un token ou une clé que le moteur peut lire, une expression
  `${{ }}` d'un workflow insérée dans un script sans passer par une variable d'environnement, ou un
  secret écrit dans le code.
- **Une doc contredite** : la PR change un comportement que `README.md` ou `docs/` décrit, sans
  mettre la page à jour.
- **Un écart à une convention écrite dans `AGENTS.md`**, en citant la convention.

Chaque remarque doit justifier une correction avant le merge. Une PR saine ne reçoit aucune
remarque : le silence est alors la bonne review.

## Étayer chaque remarque par le code lu

- Avant d'affirmer ce que fait une fonction, le moteur ou une action GitHub, ouvrez sa définition
  et citez les lignes sur lesquelles repose la remarque. Ce que suggère un nom n'est qu'une
  hypothèse.
- Les sorties du moteur enregistrées dans `tests/fixtures/` montrent ce qu'il renvoie vraiment.
  Appuyez-vous dessus plutôt que sur une supposition.
- Les tests de la PR passent en CI. Pour affirmer qu'un test échoue, ou qu'il passe pour une
  mauvaise raison, citez la ligne qui le montre.

## Lire d'abord l'intention de la PR

Le titre et la description de la PR accompagnent le diff. Un comportement qu'ils demandent est
voulu : ne le signalez que s'il casse quelque chose qu'ils ne prévoient pas.

## Laisser le reste aux linters et aux humains

- Le formatage, le style et les types : ruff et mypy s'en chargent.
- Les tests à écrire, le design au-delà des conventions d'`AGENTS.md`, la performance et la
  robustesse face à des états impossibles : on en discute en review humaine. Si l'un d'eux cause
  un défaut de correction ou de sécurité, signalez ce défaut.

## Une remarque par défaut

Signalez chaque défaut une fois, à la ligne qui l'introduit. S'il se répète ailleurs, listez les
autres endroits dans la même remarque.

## Les reviews suivantes convergent

Quand vous relisez une PR à nouveau, signalez les défauts qu'introduisent les nouveaux commits. Un
commit qui répond à une remarque précédente n'en reçoit une que s'il introduit un défaut.
