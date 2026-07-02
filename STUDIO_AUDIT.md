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

## Portage réalisé (Phase 2 — modèles métier custom, 2026-07-02)

Nouveau module dédié **`fma_studio_models`** (schéma + vues + sécurité pour
les 20 modèles `x_*` créés par Studio). Noms techniques et noms de champs
**conservés à l'identique** de Studio :
- aucune migration de données nécessaire (mêmes tables, mêmes colonnes) ;
- `mrp_capacity_planning/models/mrp_production.py`
  (`env['x_capacite_par_poste']`, `x_studio_poste`, `x_studio_dure_min/max`,
  `x_studio_nbre_ressources`) et `sqlite_connector/models/sqlite_connector.py`
  (`env['x_affaire']`) continuent de fonctionner sans aucune modification.

**Constat important en écrivant le schéma** : la majorité des modèles
"Remise" (`x_remise`, `x_remises`, `x_remise_affaire`, `x_remises_affaire`,
`x_remise_chantier` + ses 2 modèles de ligne), ainsi que `x_gamme_mtn`,
`x_reglements` et `x_purchase_order_line_35a7b` / `x_account_move_line_803a2`,
**n'ont aucun champ métier réel** — uniquement le squelette par défaut de
Studio (`x_name`, `x_active`, `x_studio_sequence`). Aucun montant, aucun
pourcentage, aucune date. `x_remise_affaire.x_studio_libelle` et
`x_remises_affaire.x_studio_libelle` pointent même sur **leur propre
modèle** (many2one auto-référencé), ce qui a toutes les apparences d'une
mauvaise configuration Studio plutôt que d'un choix voulu. Le schéma a été
porté fidèlement tel quel (aucune tentative de "corriger" un design métier
sur lequel je n'ai pas d'information), mais **à valider avec le métier avant
d'investir plus de temps dessus** : ces modèles sont-ils réellement utilisés,
ou sont-ce des essais Studio abandonnés ?

**Modèles réellement étoffés** (schéma complet porté avec formulaires
dédiés) : `x_affaire` (+ stages/tags), `x_capacite_par_poste` (+ tags,
utilisé par `mrp_capacity_planning`), `x_delai_entre_operatio` (+ lignes/tags),
`x_serie_mtn` (lien vers `x_gamme_mtn`).

**Vérifications faites a posteriori** (accès SSH rétabli après l'incident
Odoo.sh) :
- **Volumes réels par modèle** — contrairement à l'hypothèse initiale
  ("famille Remise probablement abandonnée"), le tableau est contrasté :

  | Modèle | Enregistrements |
  |---|---:|
  | x_affaire | **4059** |
  | x_serie_mtn | 288 |
  | x_remise_chantier | 36 |
  | x_gamme_mtn | 34 |
  | x_remise_chantier_line_da285 | 34 |
  | x_remise_chantier_line_46d7e | 19 |
  | x_reglements | 11 |
  | x_capacite_par_poste | 9 |
  | x_affaire_stage | 3 |
  | x_capacite_par_poste_tag | 1 |
  | x_remise_affaire | 1 |
  | x_remises | 1 |
  | x_remises_affaire, x_affaire_tag, x_delai_entre_operatio_tag, x_account_move_line_803a2, x_delai_entre_operatio_line_07ffc, x_purchase_order_line_35a7b, x_delai_entre_operatio, x_remise | **0** |

  `x_affaire` est donc massivement utilisé (confirme qu'il s'agit bien d'un
  objet métier central, pas d'un essai) ; `x_remise_chantier` (+ ses 2
  modèles de ligne) et `x_gamme_mtn`/`x_serie_mtn` sont réellement utilisés
  malgré leur schéma minimal. En revanche `x_delai_entre_operatio` (le
  modèle entier, malgré sa richesse de champs) et `x_remise` (le modèle de
  base de toute la famille remise) ont **0 enregistrement** — probablement
  vraiment abandonnés, à confirmer avec le métier avant d'investir plus loin
  dessus.
- **Sélection `x_studio_kanban_state`** : confirmée conforme à l'hypothèse
  initiale — `normal`="En cours", `done`="Prêt", `blocked`="Bloqué". Aucun
  changement nécessaire dans le code.
- **Règles d'accès (`ir.model.access`)** : le pattern réel diffère de ce qui
  avait été mis par défaut. Pour la plupart des modèles, "Utilisateur
  interne" a lecture/écriture/création mais **pas** suppression (réservée à
  "Administrator") ; seuls `x_affaire`, `x_affaire_stage` et `x_affaire_tag`
  autorisent la suppression aux utilisateurs internes. **Corrigé** dans
  `security/ir.model.access.csv` (règle `base.group_system` séparée avec
  suppression pour les 17 modèles concernés).
- **Découverte incidente, investiguée** : le 21e modèle custom
  `x_project_task_worksheet_template_1` (3 champs : `x_name`, `x_comments`,
  `x_project_task_id` obligatoire vers `project.task`) a **0 enregistrement**
  et **aucun champ nulle part ne pointe vers lui** (pas de one2many sur
  `project.task`, donc inaccessible depuis l'UI standard). Conclusion :
  essai Studio abandonné avant d'être finalisé. **Non porté** — sans intérêt
  tant qu'il reste inutilisé et inaccessible.

**Menus** : recréés sous les menus racines standards Ventes / Achats /
Fabrication (`sale.sale_menu_root`, `purchase.menu_purchase_root`,
`mrp.menu_mrp_root`) plutôt que de tenter de reproduire l'emplacement exact
des 19 menus Studio d'origine (dont les ids internes n'ont pas pu être
résolus en xmlid stables pendant l'incident réseau) — à réorganiser si
besoin après validation visuelle en staging.

## Portage réalisé (Phase 3 — champs sur modèles standards, en cours)

Recoupement fait entre les 415 champs `x_studio_*`/`so_*` de l'audit initial
et le code déjà versionné : **106 étaient déjà déclarés** (modules `custom`
et `custom_colisage` notamment), laissant un écart réel de **302 champs**
répartis sur ~15 modèles standards. Traités modèle par modèle, en réutilisant
le module existant le plus pertinent plutôt que d'en créer de nouveaux.

**Champs systématiquement exclus du portage automatique, quel que soit le
modèle** (documentés dans le code au fur et à mesure) :
- Sélections (`selection`) dont les valeurs n'ont pas pu être vérifiées en
  base au moment du portage.
- Champs "liés" (`related_field_*`, souvent en lecture seule) dont la cible
  (`related=`) n'a pas pu être vérifiée en base.
- Champs non stockés (`store=false`) portés comme simple champ stocké
  aurait figé leur valeur au lieu de la garder synchronisée — exclus tant
  que leur définition réelle (related/compute) n'est pas connue.
- Champs explicitement marqués "OLD"/déprécié par le métier lui-même dans
  Studio.

### sale.order — fait

77 champs manquants, 56 portés dans `fma_sale_order_custom/models/sale_order.py`
(déjà le module dédié à la personnalisation des devis/commandes). 21 exclus
pour les raisons ci-dessus (détail en commentaire dans le fichier).
Dépendances ajoutées au manifest : `fma_studio_models` (pour `x_gamme_mtn`,
`x_serie_mtn`, `x_affaire`), `crm`, `project`, `documents` (modèles ciblés
par des many2one/many2many Studio).

**Observation** : le fichier contenait déjà un champ `date_bpe` (sans
préfixe `x_studio_`) au même sens que le nouveau `x_studio_date_bpe` porté
ici — deux colonnes distinctes pour a priori le même concept métier. Pas
touché dans cette passe (pas assez d'information pour savoir laquelle fait
foi), mais à clarifier avec le métier.

### res.partner — fait

37 champs manquants, 29 portés dans `custom/models/res_partner.py` (module
"Custom Field Transfer", déjà le point d'entrée générique pour les champs
transverses — il a aussi des fichiers `account_move.py`, `mrp_production.py`,
`stock_picking.py` déjà en place, qui serviront de point d'ancrage pour la
suite). 8 exclus (4 sélections, 3 champs liés, 1 "OLD"). Dépendances
ajoutées : `hr` (pour `x_studio_commercial_1` → `hr.employee`),
`fma_studio_models` (pour `x_studio_mode_de_rglement_dsa` → `x_reglements`).

**Point de vigilance repéré en même temps** : `x_studio_compte`,
`x_studio_gneration_n_compte_1` et `x_studio_mode_de_rglement` étaient déjà
**utilisés** (non déclarés) dans `create()`/`write()`/`_prepare_order()` de
ce même fichier — génération automatique de numéro de compte client. Ils
fonctionnaient uniquement grâce au mécanisme Studio ; maintenant déclarés en
code, ce point de la logique métier est sécurisé.

**Découverte incidente (hygiène du repo, hors périmètre de ce portage)** :
`custom_colisage/custom/` est un **module dupliqué** — dossier `custom`
imbriqué dans `custom_colisage`, même nom technique "Custom Field Transfer"
que le module `custom` à la racine, versions différentes (`1.0` vs
`19.0.1.0.6`). Si ce chemin est sur l'addons_path d'Odoo.sh, ça peut créer
un conflit de nom de module. À vérifier/nettoyer séparément — non touché ici.

### account.move — fait

35 champs manquants, seulement **8 portés** dans `custom/models/account_move.py`
(module déjà en place pour ce modèle). 27 exclus : **19** sont des champs
"related_field_*" (record le plus élevé de tous les modèles traités jusqu'ici),
5 sélections à valeurs inconnues, 1 "OLD", 2 non stockés.

### stock.picking — fait

28 champs manquants, 16 portés dans `custom/models/stock_picking.py`. 12
exclus (10 related_field_*, 1 sélection, 1 many2one vers un modèle
`stock.reference` dont l'existence n'a pas pu être confirmée — accès SSH
indisponible au moment du portage, **à vérifier avant de porter ce champ**,
une relation vers un modèle inexistant ferait échouer l'installation).
Dépendance `project` ajoutée au module `custom`.

**Point notable** : 7 champs différents, tous étiquetés "Affaire" et tous
liés à `x_affaire` (`x_studio_affaire`, `x_studio_many2one_field_J9w45`,
`_Luqxc`, `_Vc214`, `_fQVOa`, `_oYral`, `_uBzGv`, `_many2many_field_JTFem`)
— jamais renommés, signe probable d'essais répétés côté Studio. Portés tels
quels (fidélité du schéma), à clarifier avec le métier lequel fait foi.

### purchase.order — fait

24 champs manquants, 13 portés dans un nouveau fichier
`custom/models/purchase_order.py` (module `custom` — cohérent avec le reste
de la Phase 3). 11 exclus (10 related_field_*, 1 champ de test non stocké).
`x_studio_rfrence`, `x_studio_many2one_field_LCOZX` et `x_studio_projet_du_so`
étaient déjà utilisés sans être déclarés dans le portage Phase 1
(`fma_custom/models/purchase_order.py`) et dans les gabarits d'export
`purchase_order_export` — désormais sécurisés en code.

### Modèles restants — tous faits

Traités en un seul lot, mêmes règles d'exclusion, tous dans le module
`custom` (nouveaux fichiers `account_move_line.py`, `stock_move_line.py`,
`sale_order_line.py`, `stock_move.py`, `purchase_order_line.py`, `product.py`
pour product.product/product.template, `misc_studio_fields.py` pour les 6
modèles à 1-2 champs ; `mrp_production.py` existant complété) :

| Modèle | Manquants | Portés | Exclus |
|---|---:|---:|---:|
| product.product | 26 | 24 | 2 (related) |
| account.move.line | 15 | 3 | 12 (related/sélection) |
| stock.move.line | 12 | 2 | 10 (related/non stocké) |
| sale.order.line | 10 | 4 | 6 (related/non stocké) |
| mrp.production | 8 | 7 | 1 (sélection) |
| purchase.order.line | 8 | 5 | 3 (related/non stocké) |
| stock.move | 9 | 5 | 4 (related/non stocké) |
| product.template | 5 | 4 | 1 (one2many sans inverse_name connu) |
| helpdesk.ticket | 2 | 2 | 0 |
| product.category | 2 | 2 | 0 |
| account.analytic.line | 1 | 1 | 0 |
| account.payment.term | 1 | 1 | 0 |
| mrp.workcenter.productivity | 1 | 1 | 0 |
| uom.uom | 1 | 1 | 0 |

`x_studio_mtn_mrp_sale_order` (mrp.production) était déjà utilisé sans être
déclaré par le portage Phase 1 (`fma_custom/models/mrp_production.py`) —
désormais sécurisé. Dépendance `helpdesk` ajoutée au module `custom`.

## Bilan Phase 3

**302 champs identifiés, 234 portés en code, 68 volontairement exclus**
(sélections à valeurs inconnues, champs liés dont la cible n'est pas
vérifiable, champs non stockés, ou explicitement dépréciés). Tous les
champs exclus sont documentés en commentaire dans le fichier de code
correspondant, avec la raison précise. Prochaine étape : repasser dessus
une fois un accès SSH stable retrouvé, pour récupérer les valeurs de
sélection et les cibles `related=` manquantes.

### Vérifications encore en attente (accès SSH à repasser dessus)

- Valeurs des sélections `x_studio_avancement` (sale.order — **utilisé
  activement dans `fma_sale_order_custom`, `action_validation()`, avec la
  valeur `"5"`** : au moins cette valeur doit figurer dans les options),
  `x_studio_bureau_etudes`, `x_studio_com`, `x_studio_commercial_si_prospect`,
  `x_studio_deviseur_1`, `x_studio_motif_annul`, `x_studio_nom_com_2`, et
  toutes les autres sélections manquantes des modèles suivants.
- Cible (`related`) des champs `x_studio_related_field_*` sur tous les
  modèles.
- Définition réelle de `x_studio_calcul_raf_ht` (non stocké côté Studio).

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
