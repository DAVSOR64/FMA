# FMA — Ordonnancement & Scores

Reprise dans Odoo du classeur `Ordre de production FMA - Copie.xlsm`.

## Principe

Le classeur reposait sur quatre onglets d'export Odoo collés à la main
(`import_odoo`, `of 26 stock`, `ORDRE_TRAVAIL`, `PO`) et un onglet de travail
(`TDB_SAISIE`) qui les rapatriait par `XLOOKUP` et `FILTER`.

Ici, chaque colonne du `TDB_SAISIE` devient un champ de `mrp.production`,
**calculé et stocké**. Le stockage est ce qui rend la donnée filtrable,
groupable et utilisable en tableau croisé — c'est-à-dire dynamique. Les
onglets d'export n'ont plus de raison d'être.

## Correspondance avec le classeur

| Colonne | Champ Odoo | Origine |
|---|---|---|
| A, B, I | `name`, `product_id`, `state` | natif |
| C Atelier | `atelier_id` | `fma_atelier` |
| D Complexité | `x_studio_niveau_de_complexite` | `custom` |
| E Début débit | `fma_date_debut_debit` | `macro_planned_start` de l'opération de débit |
| F planifier | `fma_planifie` | ce module |
| G Fin prod | `fma_date_fin_prod` | recopie de `x_studio_date_de_fin` |
| H Date liv. initiale | `fma_date_liv_initiale` | `so_date_de_livraison_prevu`, puis `commitment_date` |
| J Date liv. actuelle | `fma_date_livraison` | date planifiée du BL de la commande de vente |
| K Statut livraison | `fma_statut_livraison` | `delivery_status`, repli sur les BL |
| L à Q Appro par famille | `fma_date_arrivee_*`, `fma_statut_reception_*` | ce module |
| R nom d'affaire nettoyé | *supprimée* | remplacée par la relation réelle |
| S Commentaires | `fma_commentaire` | ce module |
| T Nb repères | `fma_nb_reperes` | lignes de la commande de vente |
| U Score complexité | `fma_score_complexite` | ce module |
| V + banc/usinage/montage | `fma_score_*` | ce module |
| W à AA Heures par poste | `fma_heure_*` | ce module |

Trois colonnes ne se lisent pas là où le classeur les prenait :

- **E Début débit** : ce n'est pas la date de l'OF mais le `macro_planned_start`
  de la première opération de débit, quel que soit l'atelier (Débit FMA,
  Débit F2M).
- **H Date liv. initiale** : l'engagement pris au devis. FMA ne renseigne pas
  `commitment_date` : la promesse est portée par `so_date_de_livraison_prevu`
  (module `custom`). On applique la même chaîne de priorité que
  `mrp_capacity_planning._get_macro_target_date`, pour que l'ordonnancement et
  le macro-planning lisent la même date.
- **J et K Livraison** : les bons de livraison appartiennent à la commande de
  vente, pas à l'OF. `mrp.production.picking_ids` ne porte que les mouvements
  de composants et de produit fini — jamais le BL client.
- **T Nb repères** : le classeur recopiait à la main les multiplicateurs du
  champ de complexité (« A*3 » = 3 repères). On compte directement les lignes
  de la commande de vente portant un bien non stockable, hors lignes cochées
  « Exclu du comptage des repères ».

L'onglet `SEQUENCAGE` donne trois modèles de configuration :
`fma.complexite.niveau` (poids A=1, B=2, C=3, M=0),
`fma.complexite.regle` (matrice gammiste × typologie) et
`fma.bareme.score` (tranches heures/repère → score).

## Ce qui réactualise quoi

Les champs stockés ne se recalculent que si Odoo peut relier le changement au
champ. Là où aucun chemin de dépendance n'existe, l'invalidation est explicite.

| Champs | Déclencheur | Mécanisme |
|---|---|---|
| `fma_heure_*` | ordre de travail créé, replanifié, durée modifiée, poste changé | `@api.depends` |
| `fma_nb_reperes`, `fma_score_complexite` | champ complexité de l'OF | `@api.depends` |
| `fma_date_livraison`, `fma_statut_livraison` | transferts, `delivery_status` du SO | `@api.depends` |
| `fma_score_*` | **modification d'un barème** | invalidation explicite depuis `fma.bareme.score` |
| `fma_score_complexite` | **modification d'un poids de niveau** | invalidation explicite depuis `fma.complexite.niveau` |
| `fma_heure_*`, `fma_score_*` | **typage d'un poste de charge** | invalidation explicite depuis `mrp.workcenter` |
| `fma_*_appro` | **achat créé, confirmé, annulé, date d'arrivée modifiée** | invalidation explicite depuis `purchase.order` |
| `fma_*_appro` | **réception validée ou annulée** | invalidation explicite depuis `stock.picking` |
| `fma_*_appro` | **famille d'appro d'une famille ou sous-famille modifiée** | invalidation explicite depuis `product.family` et `product.subfamily` |
| `fma_date_fin_prod` | **`x_studio_date_de_fin` modifié** | surcharge de `write` sur l'OF |
| `fma_nb_reperes` | lignes de la commande de vente | `@api.depends` |
| `fma_date_debut_debit` | `macro_planned_start` des OT de débit | `@api.depends` |
| `fma_date_liv_initiale`, `fma_statut_livraison`, `fma_date_livraison` | commande de vente et ses BL | `@api.depends` |
| tous | filet de sécurité | cron quotidien |

Les invalidations venant de l'achat ne recalculent **pas** tous les OF : la
résolution inverse `purchase.order._fma_productions_liees()` cible les OF
concernés via la chaîne d'approvisionnement, l'origine, puis le projet du SO.
Un OF qui échapperait à ces trois voies est rattrapé par le cron nocturne.

## À l'installation

Le `post_init_hook` :

1. type les postes de charge existants d'après leur libellé (Débit, CU, …) ;
2. rattache `01_PROFILS_BARRES_TOLES` à « profilé » ; les autres familles
   restent à renseigner, dont `02_Remplissage` au niveau sous-famille ;
3. lance un premier calcul sur les OF ouverts.

Ces trois opérations ne servent qu'au démarrage. Ensuite, tout se règle en
configuration, sous le menu Séquencement : type de poste, famille
d'approvisionnement par famille puis par sous-famille, exclusions du comptage
des repères, barèmes.

## Points d'attention repris du classeur

- **Famille d'approvisionnement** : le classeur devinait la famille depuis le
  nom du fournisseur, avec quatre listes codées en dur dans les formules. C'est
  structurellement faux — `RODENBERG` figurait à la fois dans « panneaux » et
  dans « complémentaire », parce qu'un fournisseur vend plusieurs familles. La
  famille est désormais portée par le référentiel **`product.family`** de
  `product_subfamily`, qui est déjà la source de `categ_id` via le triplet, et
  la ventilation se fait ligne à ligne.

  Le référentiel FMA ne se superpose pas exactement aux familles
  d'approvisionnement du classeur : **`02_Remplissage` recouvre le vitrage et
  les panneaux**, que le classeur suivait dans deux colonnes distinctes. La
  famille d'appro se renseigne donc à deux niveaux, la **sous-famille
  l'emportant sur la famille**. `01_PROFILS_BARRES_TOLES` est rattachée
  automatiquement à « profilé » ; `02_Remplissage` doit être tranchée
  sous-famille par sous-famille ; les complémentaires restent à définir avec le
  métier.
- **Éco-participation** : identifiée par la case « Exclu du comptage des
  repères » sur la fiche produit, à cocher par FMA. Aucune détection par le
  libellé, qui serait fragile.
- **`SHUECO`** (lignes 6 et 10 de `SEQUENCAGE`) et **`SCHUECO`** (ligne 15)
  désignaient le même gammiste. Normalisé en `SCHUECO`.
- **`REYNAERS` niveau B** n'avait aucune typologie renseignée : aucune règle
  n'est créée pour ce cas.
- Le champ complexité contient, en production, des valeurs qui ne sont pas des
  niveaux : `FOUR`, `FOURN`, `CIN`. Le classeur les comptait comme un repère de
  poids nul ; le module fait de même, à l'identique. À nettoyer côté données.
- **Différence assumée** : pour les heures par poste, le classeur utilisait un
  `XLOOKUP` qui ne retenait que le premier ordre de travail d'un poste. Le
  module **somme** les ordres de travail, afin qu'un OF repassant deux fois sur
  le même poste soit correctement valorisé.
- **Colonne F** : le « P » du classeur était une saisie manuelle de
  l'ordonnanceur, pas un état déduit. Elle devient `fma_planifie`, champ
  booléen ordinaire. À ne pas confondre avec `is_programmed`
  (`mrp_capacity_planning`), qui vaut vrai dès qu'un ordre de travail porte une
  date : ce champ est calculé **non stocké**, donc affichable mais ni
  filtrable, ni groupable, ni triable. Les deux sont exposés côte à côte dans
  la vue, « Planifié » et « OT datés ».
- La colonne `R` du classeur, qui découpait le nom d'affaire au texte pour
  joindre les achats, était en `#VALUE!` sur la première ligne. Elle disparaît :
  la jonction passe par la relation réelle.

## Limite de périmètre

L'onglet `SEQUENCAGE` contient aussi des **règles de constitution de lot**
(10 repères max/jour, 8 h de débit max/jour, mixage A/B/C). Elles ne sont pas
reprises ici : ce n'est pas de la restitution mais de l'ordonnancement, et le
lotissement FMA est constitué dans LOGIKAL puis récupéré par Odoo. Ce module
fournit les scores sur lesquels ces règles s'appuient, pas les règles.

## Migrations

Odoo ne recalcule pas un champ stocké dont seule la **formule** change : la
colonne existe déjà, l'ORM la laisse en l'état et les valeurs héritées de la
version précédente restent en base, silencieusement fausses.

Toute version qui modifie la sémantique d'un champ stocké doit donc embarquer
un `migrations/<version>/post-migrate.py` appelant
`_cron_fma_recalcul_ordonnancement()`. Le `post_init_hook` ne suffit pas : il
ne s'exécute qu'à la première installation.
