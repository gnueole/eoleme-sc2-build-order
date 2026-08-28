/* Dictionnaire d'interface. Même structure que trail-mapper/public/js/translations.js :
   une clé par chaîne, appliquée via les attributs data-i18n du HTML.
   « Build Order Forge » n'est pas traduit : c'est le nom du produit. */

export const TRANSLATIONS = {
  fr: {
    tagline: "Déposez un replay StarCraft II, récupérez sa build order en Markdown, prête à coller dans Claude.",

    panel_replay: "Le replay",
    privacy: "rien n'est conservé sur le serveur",
    drop_big: "Glissez un fichier .SC2Replay ici",
    drop_small: "ou cliquez pour le choisir — il se trouve dans Documents / StarCraft II / Accounts / … / Replays",
    drop_aria: "Choisir un fichier de replay",

    label_cutoff: "Arrêter à",
    ph_cutoff: "8:00 — vide = toute la partie",
    label_players: "Joueur",
    ph_players: "vide = les deux camps",
    label_format: "Format",
    opt_table: "Tableau",
    opt_list: "Liste",
    opt_raw: "Brut",
    label_workers: "Travailleurs",
    opt_summary: "Résumés",
    opt_all: "Listés un par un",
    opt_none: "Masqués",
    check_prompt: "Ajouter la consigne de coaching",

    btn_extract: "Extraire la build order",
    panel_markdown: "La build order",
    view_pretty: "Aperçu",
    view_markdown: "Markdown",
    btn_copy: "Copier le Markdown",
    btn_download: "Télécharger le .md",
    panel_failure: "Échec",

    reading: "Lecture du replay…",
    copied: "Copié — collez-le dans Claude.",
    copy_blocked: "Copie bloquée — sélectionnez le texte ci-dessus.",
    no_response: "Le serveur n'a pas répondu. Vérifiez votre connexion et réessayez.",
    error_status: "Erreur {status}.",
    read_in: "lu en {ms} ms",

    chip_map: "Carte",
    chip_matchup: "Matchup",
    chip_duration: "Durée",
    chip_players: "Joueurs",
    chip_lines: "Lignes",

    footer: "Le replay est lu en mémoire puis effacé : rien n'est stocké, rien n'est partagé. Les chiffres d'économie viennent des relevés que le jeu écrit lui-même dans le fichier.",
    footer_source: "Code source",

    theme_light: "Thème clair",
    theme_dark: "Thème sombre",
    theme_system: "Suivre le système",
    lang_switch: "Langue de l'interface et du Markdown",
  },

  en: {
    tagline: "Drop a StarCraft II replay, get its build order as Markdown, ready to paste into Claude.",

    panel_replay: "The replay",
    privacy: "nothing is kept on the server",
    drop_big: "Drop a .SC2Replay file here",
    drop_small: "or click to pick one — it lives in Documents / StarCraft II / Accounts / … / Replays",
    drop_aria: "Choose a replay file",

    label_cutoff: "Stop at",
    ph_cutoff: "8:00 — empty = the whole game",
    label_players: "Player",
    ph_players: "empty = both sides",
    label_format: "Format",
    opt_table: "Table",
    opt_list: "List",
    opt_raw: "Raw",
    label_workers: "Workers",
    opt_summary: "Summarised",
    opt_all: "Listed one by one",
    opt_none: "Hidden",
    check_prompt: "Add the coaching prompt",

    btn_extract: "Extract the build order",
    panel_markdown: "The build order",
    view_pretty: "Preview",
    view_markdown: "Markdown",
    btn_copy: "Copy the Markdown",
    btn_download: "Download the .md",
    panel_failure: "Failed",

    reading: "Reading the replay…",
    copied: "Copied — paste it into Claude.",
    copy_blocked: "Copy blocked — select the text above.",
    no_response: "The server did not answer. Check your connection and try again.",
    error_status: "Error {status}.",
    read_in: "read in {ms} ms",

    chip_map: "Map",
    chip_matchup: "Matchup",
    chip_duration: "Length",
    chip_players: "Players",
    chip_lines: "Lines",

    footer: "The replay is read in memory then erased: nothing is stored, nothing is shared. The economy figures come from the samples the game itself writes into the file.",
    footer_source: "Source code",

    theme_light: "Light theme",
    theme_dark: "Dark theme",
    theme_system: "Follow the system",
    lang_switch: "Interface and Markdown language",
  },
};

export const LOCALES = Object.keys(TRANSLATIONS);
