# Comparaisons

relecteur, [Claude Code Review](https://code.claude.com/docs/en/code-review),
[CodeRabbit](https://www.coderabbit.ai) et [Greptile](https://www.greptile.com) relisent tous les PR
et commentent les lignes concernées. Ils diffèrent sur le modèle, l'hébergement, le prix et ce
qu'ils font en plus de la review. Les informations sur les trois services viennent de leur
documentation et de leur page de prix, consultées en octobre 2026 : elles changent vite.

## En bref

| | relecteur | Claude Code Review | CodeRabbit | Greptile |
| --- | --- | --- | --- | --- |
| Modèle | Au choix, Albert par défaut | Choisi par Anthropic | Non précisé | Non précisé, modèles personnalisés en auto-hébergement |
| Où part le code | Chez le fournisseur du modèle choisi | Anthropic | CodeRabbit, ou chez vous en Enterprise | Greptile, ou chez vous en Enterprise |
| Prix | Les appels au modèle choisi : leur coût dépend du modèle, de l'effort et de la taille des PR | Facturé à l'usage, en crédits, sans prix fixe par review | 24 à 72 $ par développeur et par mois, gratuit sur les dépôts publics | 1 $ par review de base, gratuit pour l'open source non commercial |
| Quand il relit | À l'ouverture, puis sur `@relecteur` | À l'ouverture, à chaque push ou sur demande | À l'ouverture, puis à chaque push sur les nouveaux changements | À chaque PR |
| Mesure sur vos anciennes PR | `relecteur eval` | Pas d'équivalent documenté | Pas d'équivalent documenté | Pas d'équivalent documenté |
| Hébergeurs de code | GitHub | GitHub | GitHub, GitLab, Azure DevOps, Bitbucket | GitHub, GitLab, Bitbucket, Gitea… |

## Ce que relecteur apporte

- **La mesure** : `relecteur eval` dit ce que vaut le reviewer sur vos anciennes PR, avant de le
  déployer ou après avoir changé une consigne (voir [Évaluation](evaluation.md)).
- **Le choix du modèle et de son fournisseur** : le code relu part chez le fournisseur que vous
  choisissez, Albert par défaut. Pour les services, il part chez eux, sauf en auto-hébergement,
  réservé aux offres Enterprise.
- **L'accès** : un secret et un workflow dans le dépôt suffisent. Claude Code Review demande en
  plus un plan Claude Team ou Enterprise, et l'installation de son application GitHub par un owner
  de l'organisation.
- **La maîtrise** : le code de relecteur est public, et l'équipe décide de ce qu'il fait.

## Ce que relecteur perd

- **La profondeur d'analyse** : Claude Code Review fait chercher plusieurs agents, puis vérifie
  chaque remarque avant de la publier. Greptile indexe tout le code du dépôt sous forme de graphe.
  CodeRabbit ajoute plus de 50 linters et scanners de sécurité. relecteur publie ce que le moteur
  trouve, en une seule passe.
- **Le suivi de la PR** : CodeRabbit relit chaque push en se concentrant sur les nouveaux
  changements, et Claude Code Review peut le faire aussi. Claude Code Review résout ses propres
  fils quand le problème est corrigé. relecteur relit une fois, puis sur `@relecteur`.
- **Les outils autour de la review** : discuter avec le bot dans la PR (CodeRabbit), corriger une
  remarque en un clic avec un agent (Greptile), classer les remarques par gravité et suivre les
  coûts dans un tableau de bord (Claude Code Review).
- **La rapidité** : sur Albert, une review prend de quelques minutes à plus d'une demi-heure.
  Greptile annonce environ 3 minutes.
- **La maintenance** : relecteur est à maintenir par l'équipe. Les trois autres sont des services
  gérés.

## Ce qui n'est pas comparé

La qualité des remarques. Seul relecteur a été mesuré sur nos cas : les trois services ne l'ont
pas été.
