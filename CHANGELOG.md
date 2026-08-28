# Changelog

Toutes les évolutions notables de SC2 Build Order Forge.
Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le versionnage [SemVer](https://semver.org/lang/fr/).

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
