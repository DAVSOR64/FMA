# Audit des personnalisations Odoo Studio — Staging_19 (2026-07-02)

Base auditée : `davsor64-fma-staging-19-34289959` (Odoo.sh, branche Staging_19).
Tout ce qui suit vient du module `studio_customization` (généré automatiquement par
Odoo Studio, `ir_model_data.module = 'studio_customization'`). Ce module contient
**tout** ce qui a été créé/modifié via Studio — c'est la source de vérité pour l'audit.

## Vue d'ensemble

| Type d'objet                 | Nombre |
|-------------------------------|-------:|
| Champs personnalisés (`ir.model.fields`) | 415 |
| Vues modifiées/créées (`ir.ui.view`)     | 222 |
| Options de sélection (`ir.model.fields.selection`) | 55 |
| Valeurs par défaut (`ir.default`)        | 43 |
| Règles d'accès (`ir.model.access`)       | 42 |
| Modèles métier créés (`ir.model`)        | 20 |
| Menus (`ir.ui.menu`)                     | 19 |
| Actions fenêtre (`ir.actions.act_window`)| 17 |
| Vues d'action (`ir.actions.act_window.view`) | 5 |
| Rapports PDF/QWeb (`ir.actions.report`)  | 5 |
| Actions serveur / code Python (`ir.actions.server`) | 4 |
| Automatisations (`base.automation`)      | 4 |
| Format de page (`report.paperformat`)    | 1 |

## Risque le plus important : 20 modèles métier entièrement créés via Studio

Ces objets n'existent **nulle part dans le code** — uniquement dans la base. Si la
base est un jour recréée uniquement à partir du code (restauration, nouvelle
instance, migration majeure), **ces données et cette logique disparaissent** :

- `x_affaire`, `x_affaire_stage`, `x_affaire_tag` — gestion de "chantiers/affaires" (18 champs)
- `x_capacite_par_poste`, `x_capacite_par_poste_tag` — capacité par poste de travail (8 champs)
- `x_delai_entre_operatio`, `x_delai_entre_operatio_line_07ffc`, `x_delai_entre_operatio_tag` — délais entre opérations de fabrication (11+3+2 champs)
- `x_gamme_mtn`, `x_serie_mtn` — gammes/séries "maintenance" (3+4 champs)
- `x_reglements` — règlements/paiements (4 champs)
- `x_remise`, `x_remises`, `x_remise_affaire`, `x_remises_affaire`, `x_remise_chantier`, `x_remise_chantier_line_46d7e`, `x_remise_chantier_line_da285` — gestion des remises (6+3+4+4+8+3+3 champs)
- `x_purchase_order_line_35a7b`, `x_account_move_line_803a2` — lignes complémentaires liées aux achats/comptabilité (3+3 champs)

Chacun de ces modèles a ses propres vues (9 pour `x_affaire`, 5+ pour les remises...),
son menu dédié (19 menus au total, listés plus bas) et ses règles d'accès.

## Champs ajoutés sur les modèles standards (415 champs au total)

| Modèle              | Champs `x_studio_*` |
|----------------------|---------------------:|
| sale.order            | 79 |
| res.partner            | 39 |
| account.move           | 39 |
| stock.picking           | 28 |
| product.product          | 26 |
| purchase.order            | 25 |
| account.move.line          | 15 |
| stock.move.line              | 12 |
| sale.order.line                | 10 |
| stock.move                       | 9 |
| purchase.order.line                | 8 |
| mrp.production                       | 8 |
| product.template                       | 5 |
| product.category, helpdesk.ticket        | 2 chacun |
| uom.uom, mrp.workcenter.productivity, account.payment.term, account.analytic.line | 1 chacun |

→ Détail complet (nom technique, type, libellé, relation) : voir
`custom_fields.csv` (généré pendant l'audit, à récupérer si besoin).

**Point notable** : votre code contient déjà des références directes à 98 champs
`x_studio_*` (dans `fma_sale_order_custom`, `custom_sale_order`, `fma_mrp_dashboard`,
`mrp_capacity_planning`, `fma_invoice_export`, etc.) — donc une partie de ces champs
est déjà un point de couplage fort entre code et personnalisation Studio non versionnée.

## Logique métier cachée dans Studio (le plus risqué à perdre silencieusement)

**Mise à jour** : l'inventaire initial (basé uniquement sur `ir_model_data.module =
'studio_customization'`) sous-comptait largement cette catégorie. En interrogeant
directement les tables `base_automation` et `ir_act_server`, on trouve **13
automatisations** (9 non rattachées au suivi Studio — créées via *Paramètres >
Technique > Règles d'automatisation* plutôt que via l'onglet Studio, ou tracking
perdu) et plusieurs actions serveur autonomes substantielles.

### Automatisations (`base.automation`) — 13 au total

| Nom | Modèle | Déclencheur | Actif | Suivi Studio |
|---|---|---|---|---|
| MTN : Commercial vente = commercial client modifiable | sale.order | on_create_or_write | non | oui |
| MTN : SO sur MO pour récupérer projet | mrp.production | on_create_or_write | oui | **non** |
| MTN : Update avancement quand SO validé | sale.order | on_create_or_write | oui (code vide) | **non** |
| MTN : Propagation du compte analytique SO sur PO | purchase.order | on_create_or_write | oui | oui |
| MTN : Propagation du compte analytique MO sur PO | purchase.order | on_create_or_write | oui | oui |
| DSA Reference compute PO | purchase.order | on_create_or_write | oui | **non** |
| DSA : Mise à jour du responsable PO par le responsable PROJECT | purchase.order | on_create_or_write | oui | **non** |
| Bloquer confirmation si champ vide | sale.order | on_create_or_write, domaine state=sale | non | oui |
| MAJ Champs Mtt A facturer | sale.order | on_create_or_write | oui | **non** |
| Affaire | account.move | on_time_created | non | **non** |
| Facture fournisseur | account.move | on_create_or_write, domaine move_type=in_invoice | oui | **non** |
| Bloquer la confirmation de devis si pas de CGV et RIB | sale.order | on_state_set, domaine state=sale | oui | **non** |
| Client bloqué | sale.order | on_state_set, domaine state=draft | oui | **non** |

Détail du code de chacune : voir `custom_automations.csv` / requêtes d'audit (session).
Points notables :
- « Bloquer la confirmation de devis si pas de CGV et RIB » et « Client bloqué »
  bloquent activement des workflows de vente en production — code Python non
  versionné.
- « MTN : Update avancement quand SO validé » est active mais son code est **vide**
  (probablement cassée/désactivée en pratique, à confirmer).
- 2 règles inactives (« Commercial vente... », « Bloquer confirmation si champ
  vide ») — dette ou expérimentation abandonnée, à trancher (porter ou supprimer).

### Actions serveur autonomes avec logique métier réelle (hors boutons génériques déjà versionnés)

Les actions serveur qui ne font qu'appeler une méthode déjà définie dans vos
modules Python (`cron_send_po_xml_to_sftp`, `cron_generate_journal_items_file`,
`cron_export_entreprises_and_quotes`, etc. — modules `purchase_order_export`,
`fma_invoice_export`, `fma_invoice_status`, `fma_customer_export`,
`fma_customer_outstanding`, `hubspot_webhook_export_odoo17`, `update_sales_kpi`)
sont **déjà correctement versionnées** (XML + Python en code) — pas de risque là.

Les suivantes contiennent en revanche de la vraie logique métier **écrite
directement dans Studio, jamais versionnée** :

| Action | Modèle | Déclenchement | Description |
|---|---|---|---|
| Recalculer "Restant HT (pivot)" | sale.order | bouton manuel | Recopie `x_studio_calcul_raf_ht` vers `x_studio_restant_a_facturer_ht_pivot` (~10 lignes) |
| **Calcul PRI** (id 1214) | sale.order | bouton manuel | Moteur de calcul de coût de revient (~500 lignes) : reconstitue le coût matière/vitrage/appro d'un devis à partir des ordres de fabrication, nomenclatures, mouvements de stock et lignes de commande d'achat liées, avec conversion devise/UdM |
| **Calcul PRI** (id 1215) | sale.order | **aucun binding UI** (orphelin) | Quasi-identique à 1214, mais enveloppé pour traiter **tous les devis en cours** en lot (boucle + commit par devis) — ressemble à une version "cron batch" jamais rattachée à une planification ni un bouton |
| Fichier clients Iziqo | res.partner | bouton manuel | Génère un export CSV clients (nom, contact, commercial, adresse livraison...) en pièce jointe |
| Création Facture Fournisseur en masse | stock.picking | bouton manuel | Crée les factures fournisseurs à partir des réceptions sélectionnées |

**Le plus critique : "Calcul PRI"**. C'est un calcul métier substantiel (prix de
revient industriel) qui n'existe nulle part dans git, déclenché manuellement, avec
une deuxième version orpheline (1215) qui suggère une tentative d'automatisation en
cron jamais finalisée. À clarifier avec le métier : quelle version fait foi, et
faut-il la brancher sur un cron ?

**Code mort probable à nettoyer plutôt qu'à migrer** : deux actions serveur
« Envoyer rapports ventes (Ventes FMA & Ventes F2M) » / « Envoi hebdo rapports
ventes » (ids 1207/1208) sur le modèle `ir.actions.server` lui-même envoient un
email de **test** codé en dur (« TEST - Envoi automatique Odoo ») à une adresse
personnelle — ce n'est pas une vraie fonctionnalité métier, probablement un essai
laissé en place.

## Rapports personnalisés (5)

| Rapport | Modèle |
|---|---|
| Bon de colisage | stock.picking |
| Bon de commande Remplissage | purchase.order |
| Bon de Commande | purchase.order |
| Bon de laquage | purchase.order |
| Bon de livraison | stock.picking |

(Recoupe avec vos modules `custom_purchase_documents`, `custom_colisage`,
`fma_laquage_subcontracting` déjà présents dans le repo — probablement lié/complémentaire.)

## Menus créés (19)

Organisés sous Ventes, Achats et Fabrication : Affaire, Configuration personnalisée,
Gamme mtn, Série mtn, Remises/Remise/Remise Affaire/Remises Affaire/Remise Chantier,
Ligne de commande, Réglements, Délai entre opérations (+Tags), Capacité par poste
(+Tags), Temps de Production.

## Fichiers bruts générés pendant l'audit

Disponibles dans le scratchpad de cette session (à récupérer si besoin de détail
champ par champ) : `custom_models.csv`, `custom_fields.csv`, `custom_views.csv`,
`custom_menus.csv`, `custom_actions_window.csv`, `custom_server_actions.csv`,
`custom_automations.csv`, `custom_reports.csv`.

## Portage réalisé (Phase 1 — logique métier, 2026-07-02)

Ajouté dans le module `fma_custom` (déjà dépositaire d'un patch lié à Studio via
`hooks.py`) : `models/sale_order.py`, `models/purchase_order.py`,
`models/mrp_production.py`, `models/account_move.py`, `models/res_partner.py`,
`models/stock_picking.py`, plus les actions serveur/cron XML associées.

**Automatisations actives portées** (code désormais versionné, comportement
préservé) :
- Propagation du compte analytique SO → PO (les deux automatisations
  identiques dédupliquées en une seule méthode)
- DSA Reference compute PO — **bug corrigé au passage** : le code Studio
  original bouclait sur `records` mais lisait/écrivait `record` (variable
  du contexte single-record), ce qui aurait silencieusement corrompu les
  données en cas de déclenchement multi-enregistrements ; la version portée
  utilise correctement la variable de boucle.
- DSA : mise à jour du responsable PO par le responsable du projet
- MTN : SO sur MO pour récupérer le projet
- MAJ Champs "Montant à facturer" (sale.order) — synchronisation live en
  complément du job KPI périodique existant (`update_sales_kpi`), pas de
  conflit
- Facture fournisseur : déduction de `inv_activite` depuis l'entrepôt du bon
  de commande (complémentaire, ne duplique pas la logique déjà en code dans
  `custom_invoice`)
- Blocage de confirmation de devis si CGV+RIB non validées par le client
- Blocage de création de devis si le client est marqué "bloqué"

**Actions serveur portées** :
- Recalculer "Restant HT (pivot)" (bouton)
- **Calcul PRI** (bouton, logique fidèle à la version 1214) + nouvelle entrée
  cron `cron_calcul_pri_batch` reprenant la version orpheline 1215 (jamais
  branchée par personne côté Studio) — **le cron est livré désactivé**
  (`active=False`) car il s'agit d'un comportement automatique qui n'existait
  pas réellement en production ; à activer et calendrier (fréquence) à
  valider avec le métier avant mise en route.
- Fichier clients Iziqo (bouton, export CSV)
- Création Facture Fournisseur en masse (bouton sur réceptions)

**Non porté délibérément** (voir décisions ci-dessus) :
- 3 automatisations inactives dans Studio (« Commercial vente = commercial
  client modifiable » — champ marqué "OLD" côté métier, « Bloquer
  confirmation si champ vide », « Affaire ») — laissées en l'état, à trancher
  si besoin de les activer un jour.
- « MTN : Update avancement quand SO validé » — active mais code vide côté
  Studio, rien à porter.
- Les deux actions serveur "Envoyer rapports ventes" (emails de test codés en
  dur) — laissées de côté à la demande, à nettoyer plus tard.

**Limite connue** : le blocage CGV/RIB est accroché sur `action_confirm()`
(le chemin standard de confirmation d'un devis) plutôt que sur *tout* write
mettant `state` à `sale`, contrairement à l'automatisation Studio d'origine
qui interceptait n'importe quel chemin. À surveiller si un flux tiers
(portail, API) confirme des devis sans passer par `action_confirm()`.

**Prochaine étape recommandée** : tester ce portage en staging (créer un
devis client bloqué, confirmer sans CGV/RIB, lancer "Calcul PRI" sur un devis
avec OF, vérifier la réception de commande d'achat), puis désactiver le
déclenchement des automatisations Studio équivalentes côté `base.automation`
(mettre `active=False` sur les 9 non trackées + les 2 déjà actives portées)
pour éviter une double exécution, sans les supprimer immédiatement (garder
un filet de sécurité le temps de valider).

## Plan de migration proposé (par ordre de priorité / risque)

1. **Logique métier (automatisations + actions serveur)** — 4+4 blocs, petit volume,
   risque business le plus élevé s'ils sont perdus silencieusement. À porter en
   premier dans un module Python (override `create`/`write` ou `@api.constrains`).
2. **20 modèles métier custom** (`x_affaire`, `x_remise*`, `x_capacite_par_poste`,
   `x_delai_entre_operatio*`, `x_reglements`, `x_gamme_mtn`, `x_serie_mtn`) — recréer
   comme modèles Odoo réels (`models.Model`) + vues + sécurité + menus dans un
   nouveau module dédié. C'est le chantier le plus gros mais le plus structurant.
3. **Champs ajoutés sur modèles standards**, module par domaine métier (vente,
   achat, stock, compta) — en réutilisant si possible les modules custom déjà
   existants (`fma_sale_order_custom`, `custom_sale_order`, etc.) plutôt que d'en
   créer de nouveaux.
4. **Rapports QWeb** (5) — portage direct, volume faible.
5. **Nettoyage final** : une fois tout porté et vérifié en staging, désinstaller
   `studio_customization` pour que Studio ne soit plus la source de vérité.

Point d'attention pour la phase 2/3 : garder les noms techniques `x_studio_*` /
`x_*` existants évite une migration de données (colonnes déjà en base avec les
bonnes valeurs) ; les renommer proprement demande un script de migration en plus.
