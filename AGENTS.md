# AGENTS.md

relecteur fait relire les PR par un reviewer automatique qui s'appuie sur open-code-review, et
mesure ce reviewer sur d'anciennes PR. Pour installer, tester et linter, voir `CONTRIBUTING.md`.

## Conventions de code

Le code se lit comme le domaine qu'il décrit, sans couches inutiles.

### Le domaine d'abord

- Un module par concept du domaine : `cases`, `review`, `scorer`, `judges`… Pas de module
  fourre-tout (`utils`, `helpers`).
- Un concept qui a des données et un comportement devient une classe dans son module. Sans état,
  des fonctions suffisent : pas de classe qui ne contient que des méthodes statiques.
- Les objets du domaine sont des `@dataclass(frozen=True)`. Une valeur calculée à partir de leurs
  champs est une propriété ou une méthode de la classe, pas une fonction ailleurs qui fouille dans
  ses champs.
- Un ensemble fermé de valeurs, comme un statut ou un verdict, est un `Enum`, pas une chaîne.
- Des implémentations interchangeables partagent un `Protocol`, comme les juges.
- Une erreur du domaine a sa propre exception (`InvalidCases`, `JudgeUnavailable`), attrapée là
  où on sait quoi en faire.
- Seul `open_code_review.py` connaît le moteur. Le scorer ne fait aucune entrée-sortie.

### Des fonctions courtes, lues de haut en bas

- Une fonction publique se lit comme la suite des étapes qu'elle accomplit. Dès qu'une étape
  demande des détails, elle part dans une fonction privée bien nommée, placée sous celle qui
  l'appelle.
- Le nom d'une fonction dit ce qu'elle renvoie (`_verdict`, `locations`), ou ce qu'elle fait si
  elle agit (`save`, `evaluate`), sans répéter le nom du module.
- Les fonctions et classes publiques ont des annotations de type et une docstring. Une fonction
  privée s'en passe quand son nom suffit.
- Une valeur utilisée une seule fois s'écrit directement, sans variable intermédiaire. Pas de
  garde pour un cas qui ne peut pas arriver.

### La sobriété

- La bibliothèque standard d'abord : une dépendance ne s'ajoute que si elle évite beaucoup de
  code.
- Pas d'abstraction pour un besoin qui n'existe pas encore : une classe de base, un paramètre ou
  un point d'extension arrive avec son deuxième usage.
- Des commentaires seulement pour ce qui n'est pas évident à la lecture. Une docstring dit ce que
  fait le code, pas comment.

### Les tests

- Les tests passent par l'interface publique et vérifient des résultats : valeurs renvoyées,
  fichiers écrits, sorties. Ils ne testent pas de fonction privée.
- Le moteur et les modèles sont représentés par des sorties enregistrées dans `tests/fixtures/`.
  Aucun test n'accède au réseau.

### Les commits

- Les messages de commit sont en anglais : `type(scope): Une phrase qui dit ce que fait le
  changement, et pourquoi`.
