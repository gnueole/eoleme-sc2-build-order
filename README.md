# ⚔️ SC2 Build Order Forge

Déposez un replay StarCraft II, récupérez sa build order en Markdown, prête à coller
dans Claude pour une analyse de coach.

En production sur **[sc2.eole.me](https://sc2.eole.me)**. Le même moteur s'utilise en
ligne de commande, sans passer par le site.

---

## Ce que ça extrait

Au-delà de la suite « ravitaillement / temps / action », le rendu contient trois
sections que le replay permet de calculer sans rien deviner :

| Section | D'où viennent les chiffres |
|---|---|
| **Économie** | Les relevés que le jeu écrit lui-même toutes les ~160 frames : ravitaillement utilisé *et* capacité, travailleurs actifs, ressources en banque, revenus. |
| **Ravitaillement bloqué** | Les plages où l'utilisé rejoint la capacité — la production est alors à l'arrêt. Le plafond de 200 est ignoré : ce n'est pas une erreur de joueur. |
| **Pertes au combat** | Les unités mortes avec un tueur identifié. Les drones mutés en bâtiments sont exclus : sur une partie de test, 67 « pertes » de drones se décomposaient en 36 vraies morts et 31 mutations. |

Le symbole ⚡ marque une production accélérée au Chrono Boost.

---

## En ligne de commande

`cli.py` déclare ses dépendances dans son en-tête : `uv` les installe au premier
lancement, il n'y a rien à préparer.

```bash
uv run cli.py --last                       # la dernière partie jouée
uv run cli.py --last 3 --cutoff 8:00 --clip
uv run cli.py --list 20                    # lister les replays récents
uv run cli.py "partie.SC2Replay" --player Éole --format raw --output bo.md
```

Le dossier de replays est détecté tout seul, y compris à travers la redirection
OneDrive sous WSL. `SC2_REPLAY_DIR` ou `--replay-dir` le forcent.

| Option | Effet |
|---|---|
| `--cutoff MM:SS` | Ne garder que le début de la partie — souvent le seul moment qui compte. |
| `--player NOM` | Un seul camp. Répétable. Accepte un nom partiel ou un numéro. |
| `--all-players` | Inclure l'IA et les forces neutres (Coop). |
| `--workers` | `summary` (défaut), `all` pour lister chaque travailleur, `none`. |
| `--format` | `table` (défaut), `list`, ou `raw` aligné en colonnes. |
| `--lang` | `fr` (défaut) ou `en` — langue du Markdown produit. |
| `--no-prompt` | Sans la consigne de coaching en tête. |

---

## Développement

```bash
make venv     # environnement Python
make test     # 58 tests
make up       # conteneur sur http://localhost:3050
make logs
make down
```

## Déploiement

```bash
make deploy   # image ghcr.io + secrets Doppler + redémarrage sur le VPS
make checklogs
```

L'image est construite et poussée sur `ghcr.io` par GitHub Actions à chaque push sur
`main`, après passage des tests. `make deploy` ne fait que tirer l'image et
redémarrer le conteneur.

> [!IMPORTANT]
> `sc2.eole.me` doit avoir un enregistrement DNS **A** vers l'IP du VPS *avant* le
> premier déploiement. Traefik obtient son certificat par challenge HTTP : sans
> résolution DNS, Let's Encrypt échoue et le service reste inaccessible en HTTPS.
> Il n'y a pas de wildcard sur `eole.me`, chaque sous-domaine a son enregistrement.

---

## Architecture

```text
sc2bo/extract.py     Moteur : lecture du replay, calculs, rendu Markdown
cli.py               Interface ligne de commande (script uv autonome)
server.py            Service HTTP FastAPI
public/index.html    Interface web, sans build ni dépendance JS
public/css/styles.css Charte graphique eole.me
public/js/            translations.js (FR/EN) et app.js (thème, langue, envoi)
docker/              Dockerfile + compose local et production
```

L'interface suit la charte documentée dans `www/DESIGN_SYSTEM.md` du dépôt
`eoleme-www` : persona *business*, fond `#080b11`, accent cyan `#38bdf8`,
typographie Outfit / Inter / Fira Code. Comme `trail-mapper`, c'est une
feuille de style locale qui reprend les **noms de tokens** de la charte plutôt
qu'un import distant — les sous-pages autonomes ne partagent pas le bundle du
site. Les pièges de `www/CSS_TOPOLOGY.md` sont respectés : pas de `100vw`,
`100dvh` en complément de `100vh`, points de rupture `767.98px` / `768px`.

La CLI et le site partagent exactement le même moteur : une correction faite dans
`sc2bo/` vaut pour les deux.

### Le contrat du service

| Route | Rôle |
|---|---|
| `POST /api/extract` | Multipart : `replay`, plus `cutoff`, `players`, `format`, `workers`, `prompt`, `lang`. Renvoie `{markdown, report, labels, meta, ms}`. |
| `GET /api/health` | État, version, plafond de taille, usage du jour. |
| `GET /` | L'interface. |

Le replay est écrit dans un fichier temporaire le temps du parsing puis supprimé
dans un `finally` : **rien n'est conservé**. La télémétrie ne transporte ni
pseudonyme ni contenu de replay — carte, matchup, durées et tailles suffisent.

### Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `SC2BO_MAX_UPLOAD_BYTES` | 12 Mo | Plafond de taille. Un replay dépasse rarement 3 Mo. Traefik coupe déjà au même seuil. |
| `SC2BO_PARSE_TIMEOUT_S` | 45 | Au-delà, la requête rend la main plutôt que d'occuper le serveur. |
| `SC2BO_FEEDBACK_THRESHOLD` | 50 | Extractions par jour au-delà desquelles un événement `usage_threshold_crossed` est émis. Le site n'est pas limité pour autant : ce seuil sert à décider s'il faut le devenir. |
| `TELEMETRY_WEBHOOK_URL` | `http://vector:8080` | Vector, qui relaie vers Axiom. Vide = les événements restent sur la sortie standard. |

Le compteur d'usage vit en mémoire : un redémarrage le remet à zéro. C'est
volontaire — on cherche un ordre de grandeur, pas une comptabilité.

---

## Une bizarrerie de spawningtool à connaître

`spawningtool` perd **12 replays sur 495** sur ce corpus, tous avec un `KeyError`.
En Coop et sur les cartes à camps neutres, le replay porte des améliorations
appartenant à des joueurs absents de sa table (forces d'Amon, civils). Tous ses
gestionnaires d'événements vérifient l'appartenance avant d'indexer — sauf
`add_upgrade_event`, qui ne teste que le joueur 0.

`patch_spawningtool()` lui ajoute le même garde-fou au chargement, ce qui ramène le
corpus à **495/495**. Le correctif est idempotent et vérifie qu'il ne s'applique
qu'une fois. À retirer le jour où la bibliothèque le corrige en amont.

Deuxième piège du même terrain : certaines unités Coop arrivent **sans nom**.
`pretty()` les rend « unité inconnue » plutôt que de faire tomber le rendu.

---

## Tests

Aucun replay n'est versionné : ce sont des parties privées, et un `.SC2Replay`
contient les pseudonymes des deux joueurs. La suite couvre donc les fonctions pures
(découpage des noms, détection des blocages, cohérence du tableau d'économie,
sélection des joueurs) et le contrat HTTP (validation, plafond de taille, fichier
illisible, compteur d'usage). Les vérifications sur de vrais fichiers se font à la
main avec `cli.py`.

---

*Julien (Éole) Avarre — MIT*
