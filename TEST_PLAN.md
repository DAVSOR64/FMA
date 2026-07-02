# Plan de test — Portage Odoo Studio vers du code (Phases 1 à 3)

Base cible : **Staging_19** (`davsor64-fma-staging-19-...`, branche Git
`Staging_19`). Ce document couvre le portage complet de ce qui avait été
construit avec Odoo Studio vers du code source normal, en 3 volets :

- **Phase 1** : logique métier cachée (règles automatiques, boutons) —
  module `fma_custom`.
- **Phase 2** : 20 objets métier créés dans Studio (Affaire, Remises,
  Capacité par poste...) — nouveau module `fma_studio_models`.
- **Phase 3** : 234 champs Studio sur des objets standards (devis, factures,
  commandes d'achat, contacts, produits...) — modules `custom` et
  `fma_sale_order_custom`.

**Pourquoi ce portage ?** Tout ce qui a été fait avec Studio n'existait que
dans la base de données, invisible dans le code source (Git). C'est un
risque en cas de migration de version, de restauration de sauvegarde, ou
simplement pour comprendre/faire évoluer le logiciel. Ce portage recopie
fidèlement le comportement existant en code — **rien ne doit changer** pour
les utilisateurs, c'est justement ce que cette checklist vérifie.

**Important** : les automatisations Studio d'origine (Phase 1) sont
**encore actives** pendant cette phase de test. Le code porté s'exécute
donc **en plus** d'elles, pas à leur place — c'est voulu, ça permet de
comparer les deux et de ne rien casser pendant les tests. On ne les
désactivera qu'**après** validation complète (voir la dernière section).

## 0. Préparation et déploiement

**État actuel** : tout le code des Phases 1, 2 et 3 est déjà écrit,
committé et **poussé** sur la branche `Staging_19` (dernier commit
`bb62dce`). Le build Odoo.sh correspondant doit se lancer automatiquement
après le push.

1. Sur [Odoo.sh](https://www.odoo.sh), vérifier que le dernier build de la
   branche **Staging_19** est bien **terminé et vert** (onglet *Builds*) —
   attendre qu'il finisse si besoin.
2. **Faire un backup manuel de la base staging** (bouton *Backup* dans
   Odoo.sh) avant d'aller plus loin. C'est indispensable avant d'installer
   `fma_studio_models` (Phase 2) : ce module reprend les 20 tables créées
   par Studio, et une erreur à ce stade sans backup pourrait faire perdre
   des données (détails dans la section Phase 2 et dans "Rollback" en bas
   de page).
3. Dans Odoo (activer le **mode développeur** si ce n'est pas déjà fait :
   Réglages > Général > tout en bas > *Activer le mode développeur*),
   aller dans **Réglages > Applications**, retirer le filtre "Apps" par
   défaut (icône filtre, puis rechercher chaque module par son nom), et
   traiter **dans cet ordre exact** :
   1. **"FMA: Studio Models"** → bouton **Installer** (nouveau module).
   2. **"FMA: Custom"** → bouton **Mettre à niveau** (doit passer en
      version `19.0.1.0.3`).
   3. **"Custom Field Transfer"** → **Mettre à niveau** (version
      `19.0.1.0.9`).
   4. **"Sale Order Customization"** → **Mettre à niveau** (version
      `19.0.1.0.2`).
4. Après **chaque** étape ci-dessus, vérifier qu'il n'y a **aucune erreur**
   affichée à l'écran, et jeter un œil aux logs serveur (Odoo.sh > onglet
   *Logs*, ou **Réglages > Technique > Logs**) pour repérer un éventuel
   "Traceback" Python. En cas d'erreur à une étape : **s'arrêter, ne pas
   continuer aux modules suivants**, et transmettre le message d'erreur
   exact avant de chercher à corriger.

## 1. Sale order — Client bloqué

- **Pré-requis** : un client (res.partner, société) avec le champ Studio
  "Client Bloqué" (`x_studio_client_bloque`) coché.
- **Test** : créer un nouveau devis pour ce client (Ventes > Devis > Nouveau,
  sélectionner le client, enregistrer).
- **Attendu** : message d'erreur bloquant *"Impossible de créer un
  devis. Ce client est bloqué."* — le devis ne doit pas être créé.
- **Contre-test** : décocher "Client Bloqué" sur le partenaire, recréer un
  devis pour lui → doit fonctionner normalement.

## 2. Sale order — CGV/RIB obligatoires à la confirmation

- **Pré-requis** : un client dont le champ Studio "CGV + RIB"
  (`x_studio_cgv_rib`) est **décoché**.
- **Test** : créer un devis pour ce client, cliquer **Confirmer**.
- **Attendu** : erreur bloquante *"Impossible de confirmer le devis. Le
  client n'a pas validé les CGV + RIB."* — le devis reste à l'état devis
  (pas confirmé).
- **Contre-test** : cocher "CGV + RIB" sur le client, confirmer à nouveau →
  doit passer en état "Bon de commande" normalement.

## 3. Sale order — Sync "Montant à facturer" (`so_mtt_facturer_reel`)

- **Test** : sur un devis confirmé, modifier une ligne (quantité ou prix),
  enregistrer.
- **Attendu** : le champ `so_mtt_facturer_reel` (visible via le menu
  Développeur > Voir les champs, ou dans un des onglets KPI existants) se met
  à jour et correspond au "Montant hors taxes" du devis.
- **Point de vigilance** : vérifier dans les logs serveur qu'il n'y a **pas**
  de boucle infinie ou de warning de récursion au moment de
  l'enregistrement (le code utilise un garde-fou de contexte pour
  l'éviter — à confirmer qu'il fonctionne).

## 4. Purchase order — Propagation de la ventilation analytique

- **Pré-requis** : un devis client confirmé avec une ventilation analytique
  renseignée sur au moins une ligne, et une commande d'achat liée (via
  réappro/MTO ou création manuelle avec origine = ce devis).
- **Test** : ouvrir/modifier la commande d'achat liée, enregistrer.
- **Attendu** : toutes les lignes de la commande d'achat récupèrent la même
  ventilation analytique que la première ligne du devis qui en a une.

## 5. Purchase order — Référence auto-générée

- **Pré-requis** : une commande d'achat liée soit à une "Affaire"
  (`x_studio_many2one_field_LCOZX`), soit à un "Projet du SO"
  (`x_studio_projet_du_so`), soit ni l'un ni l'autre.
- **Test** : créer/enregistrer la commande d'achat dans chacun des 3 cas.
- **Attendu** (champ `x_studio_rfrence`, lecture seule en formulaire) :
  - Avec projet : `<fonction acheteur> - <nom projet> - <nom PO>`
  - Avec affaire seule (pas de projet) : `<fonction> - <nom affaire> - <nom PO>`
  - Ni l'un ni l'autre : `<fonction> - <nom PO>`
- **Test spécifique multi-lignes** : sélectionner 2+ commandes d'achat dans
  la vue liste et faire une action groupée qui déclenche un write group (ex:
  changer le vendeur puis annuler, ou tout autre write en masse) — vérifie
  que **chaque** commande reçoit sa propre référence correcte (et pas la
  référence d'une seule commande recopiée sur toutes — c'est le bug corrigé
  dans le code d'origine, à vérifier qu'il ne réapparaît pas).

## 6. Purchase order — Responsable synchronisé depuis le projet

- **Pré-requis** : une commande d'achat avec "Projet du SO" renseigné, où le
  projet a un responsable (`user_id`) différent de l'acheteur actuel de la PO.
- **Test** : enregistrer la commande d'achat (ou juste re-sauvegarder).
- **Attendu** : le champ "Acheteur" (`user_id`) de la commande d'achat prend
  la valeur du responsable du projet.
- **Contre-test** : retirer le projet → l'acheteur repasse à vide (`False`).

## 7. Mrp production — Lien vers le devis d'origine

- **Pré-requis** : un ordre de fabrication généré depuis un devis confirmé
  (avec `sale_order_count` > 0, ce qui est le cas standard pour un MTO).
- **Test** : ouvrir/enregistrer l'ordre de fabrication.
- **Attendu** : le champ `x_studio_mtn_mrp_sale_order` se remplit avec le
  devis d'origine.

## 8. Account move — Activité facture fournisseur

- **Pré-requis** : une facture fournisseur (`move_type = in_invoice`) avec
  une "Origine facture" correspondant au nom d'une commande d'achat dont le
  type d'opération est rattaché à un entrepôt contenant "REGRIPPIERE" ou
  "REMAUDIERE" dans son nom.
- **Test** : créer/enregistrer la facture fournisseur.
- **Attendu** : le champ `inv_activite` prend "ALU" (REGRIPPIERE) ou "ACIER"
  (REMAUDIERE) selon l'entrepôt.
- **Non-régression** : créer une facture **client** (out_invoice) liée à un
  devis taggé FMA/F2M → vérifier que `inv_activite` est toujours renseigné
  par la logique existante (`custom_invoice`), pas affecté par ce nouveau
  code (qui ne s'applique qu'aux `in_invoice`).

## 9. Bouton "Recalculer Restant HT (pivot)"

- **Test** : sur un ou plusieurs devis (sélection dans la vue liste), menu
  Actions (⚙) > **Recalculer Restant HT (pivot)**.
- **Attendu** : le champ `x_studio_restant_a_facturer_ht_pivot` prend la
  valeur de `x_studio_calcul_raf_ht` sur chaque devis sélectionné (0 si vide
  ou non numérique).

## 10. Bouton "Calcul PRI" (le plus critique — moteur de coût)

- **Pré-requis** : un devis confirmé avec au moins une ligne dont le produit
  a une nomenclature (BOM), un ordre de fabrication généré, et des
  commandes d'achat liées via le "Projet du SO" pour les composants.
- **Test** : ouvrir le devis, menu Actions (⚙) > **Calcul PRI**.
- **Attendu** : les champs suivants se mettent à jour de façon cohérente
  (comparer aux montants visibles sur les commandes d'achat/mouvements de
  stock liés) :
  `so_achat_matiere_reel`, `so_achat_vitrage_reel`,
  `x_studio_so_cout_appro_affaire`, `x_studio_so_cout_appro_stock`,
  `x_studio_montant_total_appro`, `x_studio_montant_non_livr_non_factur`,
  `x_studio_montant_livr_non_factur`, `x_studio_montant_livr_factur`.
- **Comparaison avant/après** : si possible, note les valeurs de ces champs
  **avant** de cliquer sur le bouton (ils ont peut-être déjà été calculés par
  l'ancien bouton Studio), clique, et vérifie que les nouvelles valeurs sont
  identiques ou cohérentes — pas de différence inexpliquée.
- **Cas limite** : tester aussi sur un devis **sans** commande d'achat liée
  (pas de projet ou aucune PO) → tous les champs doivent repasser à 0 sans
  erreur.

## 11. Bouton "Fichier clients Iziqo"

- **Test** : depuis n'importe quelle fiche client ou la liste, menu Actions
  (⚙) > **Fichier clients Iziqo**.
- **Attendu** : une pièce jointe CSV `customers_<date>.csv` apparaît (dans
  Documents ou les pièces jointes du modèle `res.partner`), contenant
  **toutes** les entreprises clientes (pas seulement celle sélectionnée —
  comportement volontairement identique à l'original Studio).
- Ouvrir le CSV, vérifier l'en-tête et quelques lignes (nom, téléphone,
  commercial, adresse de livraison).

## 12. Bouton "Création Facture Fournisseur en masse"

- **Pré-requis** : une ou plusieurs réceptions (stock.picking) liées à des
  commandes d'achat au statut "à facturer".
- **Test** : sélectionner les réceptions dans la vue liste, menu Actions (⚙)
  > **Création Facture Fournisseur en masse**.
- **Attendu** : une facture fournisseur (ou un choix de méthode de
  facturation) s'ouvre pour les commandes concernées.
- **Cas d'erreur** : sélectionner une réception dont la commande liée est
  déjà entièrement facturée → message d'erreur *"Aucune commande à facturer
  parmi les réceptions sélectionnées."*

## 13. Non-régression générale

- Créer un devis "normal" (client non bloqué, CGV/RIB OK) de bout en bout :
  devis → confirmation → livraison → facturation, sans aucune erreur.
- Créer une commande d'achat normale de bout en bout.
- Vérifier dans **Réglages > Technique > Logs** (ou les logs serveur
  Odoo.sh) qu'aucune erreur Python n'apparaît pendant toute la session de
  test (chercher "Traceback", "fma_custom").

## 14. Une fois tout validé — désactivation des automatisations Studio

Pour éviter la double exécution permanente une fois le code confirmé fiable :

1. **Réglages > Technique > Automatisations** (mode développeur), repérer les
   9 automatisations listées dans STUDIO_AUDIT.md (celles avec logique
   portée : propagation analytique x2, DSA Reference, DSA responsable, MTN SO
   sur MO, Facture fournisseur, CGV/RIB, Client bloqué — pas "MAJ Champs Mtt
   A facturer" à garder actif ou désactiver selon préférence puisqu'il fait
   la même chose que le nouveau code).
2. Décocher "Actif" sur chacune (ne pas les supprimer tout de suite — garder
   un filet de sécurité 2-3 semaines avant suppression définitive).
3. Rejouer rapidement les tests 1, 2, 4, 5, 6, 7, 8 ci-dessus pour confirmer
   que le code versionné suffit seul.

## Phase 2 — Modèles métier custom (`fma_studio_models`)

**Préalable critique** : ce module crée des `_name` (`x_affaire`,
`x_capacite_par_poste`, etc.) identiques aux modèles "manuels" déjà
existants côté Studio, sur les **mêmes tables**. Il ne doit **jamais**
être installé en même temps que les définitions manuelles Studio actives
pour ces modèles, sous peine de conflit de schéma. Avant toute installation
en staging :

1. Vérifier via **Réglages > Technique > Modèles** que chacun des 20
   modèles (`x_affaire`, `x_affaire_stage`, `x_affaire_tag`,
   `x_capacite_par_poste`, `x_capacite_par_poste_tag`,
   `x_delai_entre_operatio` (+ ligne + tag), `x_gamme_mtn`, `x_serie_mtn`,
   `x_reglements`, `x_remise`, `x_remises`, `x_remise_affaire`,
   `x_remises_affaire`, `x_remise_chantier` (+ 2 lignes),
   `x_purchase_order_line_35a7b`, `x_account_move_line_803a2`) a bien
   `Enregistrement modifiable` = état **"manuel"** (Studio) avant d'installer
   `fma_studio_models` — sinon l'installation du nouveau module va entrer en
   collision avec la définition Studio du même modèle.
2. **Faire un snapshot/backup de la base staging** avant ce test précis (via
   Odoo.sh, bouton backup manuel) — c'est le test le plus risqué de tous
   ceux de ce document puisqu'il touche à la définition même des tables.

### Test 1 — Installation du module

- **Réglages > Applications**, retirer le filtre, chercher "FMA: Studio
  Models", cliquer **Activer**.
- **Attendu** : installation sans erreur. Vérifier immédiatement après dans
  les logs qu'il n'y a **aucune** erreur de type "table already exists avec
  colonnes incompatibles" ou "Wrong external id".
- **En cas d'échec** : ne pas insister, restaurer le backup, et revenir vers
  moi avec le message d'erreur exact avant de réessayer.

### Test 2 — Non-régression des données existantes

- Ouvrir un enregistrement `x_affaire` existant (créé avant le portage,
  via l'ancien menu Studio) depuis le nouveau menu **Ventes > Affaire**.
- **Attendu** : toutes les valeurs déjà saisies (nom, étape, contact, dates,
  tags...) sont toujours là, rien n'a été perdu ni réinitialisé.
- Refaire ce test sur `x_capacite_par_poste` (comparer avec les règles
  utilisées par `mrp_capacity_planning`) et `x_delai_entre_operatio`.

### Test 3 — Non-régression des modules déjà en code

- Lancer un scénario qui déclenche `mrp_capacity_planning`
  (`_get_effective_duration_hours` — planifier un ordre de fabrication) et
  vérifier dans les logs (`CAPACITY_RULE_SEARCH`, `CAPACITY_RULE_CHECK`) que
  les règles `x_capacite_par_poste` sont toujours trouvées et appliquées
  normalement.
- Vérifier que `sqlite_connector` (recherche `x_affaire` par nom) fonctionne
  toujours (si ce connecteur est testable en staging).

### Test 4 — Formulaires et menus des nouveaux modèles

- Parcourir chaque nouveau menu (Ventes > Affaire / Configuration
  personnalisée ; Achats > Remises ; Fabrication > Délai entre opérations /
  Capacité par poste) : les listes et formulaires s'affichent sans erreur,
  les champs correspondent à ceux visibles avant migration.
- Créer un nouvel enregistrement de test sur `x_affaire` (avec étape,
  contact, tag) et sur `x_capacite_par_poste` (avec poste de travail,
  durée min/max) — sauvegarder sans erreur.

### Test 5 — Sélection `x_studio_kanban_state`

- Ouvrir un `x_affaire` existant qui avait déjà une valeur d'état kanban
  renseignée côté Studio.
- **Attendu** : la valeur affichée correspond bien à l'ancienne (pas de
  "Valeur invalide" ni de champ vide inattendu) — **sinon** cela confirme
  qu'il faut ajuster les valeurs de sélection dans le code
  (`models/x_affaire.py`) avant d'aller plus loin.

### Test 6 — Famille "Remise" et modèles vides

- Vérifier dans **Réglages > Technique > Modèles**, onglet du modèle
  concerné, ou en ouvrant les menus Achats > Remises, si des enregistrements
  existent réellement pour `x_remise`, `x_remises`, `x_remise_affaire`,
  `x_remises_affaire`, `x_remise_chantier`, `x_gamme_mtn`, `x_reglements`.
- Si **0 enregistrement** partout : confirme l'hypothèse que c'est du code
  Studio expérimental jamais utilisé — à discuter avec le métier pour savoir
  s'il faut le garder, le simplifier, ou le retirer du portage.
- Si des enregistrements existent : les ouvrir pour vérifier qu'ils
  s'affichent correctement malgré l'absence de champs métier réels.

## Phase 3 — Champs sur modèles standards (`custom`, `fma_sale_order_custom`)

234 champs portés sur 15 modèles standards (sale.order, res.partner,
account.move, stock.picking, purchase.order, product.product,
product.template, et les modèles de ligne associés). Contrairement aux
Phases 1/2, il n'y a pas de logique métier nouvelle ici — uniquement des
déclarations de champs qui existaient déjà côté Studio. Le risque principal
est un **conflit de déclaration** (même champ déclaré deux fois avec un
type différent) ou une **dépendance manquante** (module cible d'une
relation many2one pas installé).

### Test 1 — Installation/mise à niveau sans erreur

- Mettre à niveau les modules `custom`, `fma_sale_order_custom` et
  `fma_studio_models` (dans cet ordre, ou laisser Odoo résoudre l'ordre des
  dépendances automatiquement).
- **Attendu** : aucune erreur au chargement. Erreurs à surveiller
  particulièrement : `KeyError` sur un nom de modèle (relation vers un
  modèle inexistant), ou avertissement de type de champ incompatible entre
  deux déclarations du même champ.

### Test 2 — Non-régression des valeurs existantes

- Ouvrir plusieurs enregistrements existants (un devis, une facture, une
  commande d'achat, un contact, un produit) créés **avant** le portage.
- **Attendu** : tous les champs Studio affichent toujours leur valeur
  d'origine (aucune donnée réinitialisée ou vidée).

### Test 3 — Champs désormais sécurisés (déjà utilisés par du code)

Ces champs étaient déjà lus/écrits par du code existant sans être déclarés
— vérifier spécifiquement qu'ils fonctionnent toujours normalement :
- `res.partner.x_studio_compte` / `x_studio_gneration_n_compte_1` :
  cocher la case de génération automatique sur une nouvelle société,
  vérifier qu'un numéro de compte est bien attribué.
- `purchase.order.x_studio_rfrence` : créer/modifier une commande d'achat,
  vérifier que la référence auto-générée (Phase 1) apparaît toujours
  correctement.
- `mrp.production.x_studio_mtn_mrp_sale_order` : sur un ordre de
  fabrication lié à un devis, vérifier que le lien vers le devis se
  renseigne toujours.

### Test 4 — Points de vigilance spécifiques

- **stock.picking** : les 7 champs "Affaire" quasi-identiques
  (`x_studio_affaire`, `x_studio_many2one_field_J9w45/Luqxc/Vc214/fQVOa/
  oYral/uBzGv`, `x_studio_many2many_field_JTFem`) s'affichent tous — vérifier
  avec le métier lequel est réellement utilisé sur les vues existantes.
- **x_studio_mtn_projet_mo** (stock.picking → `stock.reference`) n'a **pas**
  été porté (modèle cible non vérifié). Si ce champ est utilisé quelque
  part, il continue de fonctionner via le mécanisme Studio — pas de
  régression, juste pas encore sécurisé en code.

## Rollback si problème bloquant

- **Phase 1 (`fma_custom`)** : peut être remis à sa version précédente en
  revenant au commit précédent (`git revert` ou retour à `19.0.1.0.2`) et en
  remettant à niveau le module — aucune donnée n'est supprimée par ce
  portage (uniquement des écritures de champs existants), donc le rollback
  est sans risque de perte de données.

- **Phase 2 (`fma_studio_models`) — ATTENTION, rollback différent et plus
  risqué** : une fois ce module installé, Odoo "adopte" les tables des 20
  modèles `x_*` (elles passent du statut "manuel" Studio au statut "défini
  par un module"). **Ne jamais désinstaller `fma_studio_models` comme méthode
  de rollback** : désinstaller un module supprime les modèles qu'il possède
  — ça **supprimerait les tables et toutes les données** (`x_affaire`,
  `x_capacite_par_poste`, etc.), y compris celles créées avant le portage.
  Le seul rollback sûr pour la Phase 2 est de **restaurer le backup pris
  juste avant le test** (voir préalable du Test 1 ci-dessous) — d'où
  l'importance de ne pas sauter cette étape de sauvegarde.
