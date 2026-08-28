# Changelog

Toutes les évolutions notables de SC2 Build Order Forge.
Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le versionnage [SemVer](https://semver.org/lang/fr/).

## [1.3.0] — 2026-08-28

### Ajouté
- **La build order s'affiche en HTML** plutôt qu'en Markdown brut : vraies
  tables, ravitaillement en couleur, ⚡ sur les productions accélérées,
  ravitaillement en butée signalé en rouge dans le tableau d'économie, verdicts
  et blocages en pastilles. Le bouton **Copier le Markdown** reste, et une
  bascule *Aperçu / Markdown* permet de voir ce que l'on copie.

### Modifié
- Le moteur expose désormais `build_report()`, une structure intermédiaire dont
  le Markdown **et** le HTML dérivent tous les deux. Sans elle, le serveur
  rendrait le Markdown pendant que le client fabriquerait son HTML de son côté,
  et les deux dériveraient au premier changement. `render_replay()` est conservé
  comme raccourci : la sortie Markdown est inchangée, vérifiée par comparaison
  de 24 rendus (8 replays × 3 combinaisons d'options) avant et après le
  découpage — zéro différence.
- La réponse de `/api/extract` transporte le rapport **et les libellés employés**.
  Le client rend donc son HTML avec exactement les mots du Markdown, sans en
  tenir une seconde copie. Un test relie les clés utilisées par `app.js` au
  dictionnaire Python : en supprimer une casserait l'affichage en silence.

## [1.2.0] — 2026-08-28

### Ajouté
- **Thème clair / sombre / système**, à trois états comme `trail-mapper` : clé
  `preferred-theme` (défaut `system`), classes `theme-light` / `theme-dark` de la
  charte, et ré-application quand la préférence du système change en cours de
  route. Un script inline pose le thème *avant* le premier rendu : sans lui, une
  préférence claire voyait passer un éclair sombre.
- **Interface bilingue FR / EN.** Clé `preferred-locale` comme `trail-mapper`, et
  paramètre `?hl=fr` / `?hl=en` comme le blog, qui se nettoie de la barre
  d'adresse après lecture. À la première visite, la langue du navigateur décide.
- La traduction couvre aussi **le Markdown produit et les messages d'erreur du
  serveur** : une interface anglaise qui rend des tableaux français et des
  erreurs françaises serait une demi-traduction. `cli.py` gagne `--lang`.
- L'anglais suit sa propre typographie : `**Map:**` sans espace avant les
  deux-points, là où le français écrit `**Carte :**`.

### Modifié
- Le script de la page passe dans `public/js/`, en deux modules — `translations.js`
  et `app.js` — sur le modèle de `trail-mapper`.

## [1.1.0] — 2026-08-28

### Modifié
- L'interface suit la charte graphique eole.me (`www/DESIGN_SYSTEM.md`).
  Persona *business* : fond `#080b11`, accent cyan `#38bdf8`, halo ambiant.
  Typographie **Outfit / Inter / Fira Code**, les trois familles nommées dans la
  charte. Les deux thèmes documentés sont gérés, là où `trail-mapper` s'en tient
  au sombre.
- Le style passe dans `public/css/styles.css`, comme chez `trail-mapper`, en
  reprenant les *noms* de tokens de la charte plutôt que des valeurs isolées.
- Points de rupture alignés sur la paire `767.98px` / `768px` imposée par
  `www/CSS_TOPOLOGY.md`, et `100dvh` en complément de `100vh`.

## [1.0.0] — 2026-08-28

### Ajouté
- Extraction de la build order d'un replay StarCraft II en Markdown, prête à
  coller dans Claude : service web sur `sc2.eole.me` et CLI `cli.py`, moteur
  commun dans `sc2bo/`.
- Économie tirée des relevés `PlayerStatsEvent` du jeu (ravitaillement utilisé
  et capacité, travailleurs actifs, ressources, revenus), ce qui rend la
  détection des blocages de ravitaillement exacte plutôt qu'estimée.
- Pertes au combat séparées des drones mutés en bâtiments.
- Garde-fou sur `add_upgrade_event` de spawningtool, seul gestionnaire de la
  bibliothèque à indexer la table des joueurs sans vérifier la clé : fait passer
  un corpus de 495 replays de 483 à 495 lus.
