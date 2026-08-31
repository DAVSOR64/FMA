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
| A, B, E, G, H, I | `name`, `product_id`, `date_start`, `date_finished`, `date_deadline`, `state` | natif |
| C Atelier | `atelier_id` | `fma_atelier` |
| D Complexité | `x_studio_niveau_de_complexite` | `custom` |
| F planifier | `is_programmed` | `mrp_capacity_planning` |
| J Date liv. actuelle | `fma_date_livraison` | ce module |
| K Statut livraison | `fma_statut_livraison` | ce module |
| L à Q Appro par famille | `fma_date_arrivee_*`, `fma_statut_reception_*` | ce module |
| R nom d'affaire nettoyé | *supprimée* | remplacée par la relation réelle |
| S Commentaires | `fma_commentaire` | ce module |
| T, U | `fma_nb_reperes`, `fma_score_complexite` | ce module |
| V + banc/usinage/montage | `fma_score_*` | ce module |
| W à AA Heures par poste | `fma_heure_*` | ce module |

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
| `fma_*_appro` | **famille d'un fournisseur modifiée** | invalidation explicite depuis `res.partner` |
| tous | filet de sécurité | cron quotidien |

Les invalidations venant de l'achat ne recalculent **pas** tous les OF : la
résolution inverse `purchase.order._fma_productions_liees()` cible les OF
concernés via la chaîne d'approvisionnement, l'origine, puis le projet du SO.
Un OF qui échapperait à ces trois voies est rattrapé par le cron nocturne.

## À l'installation

Le `post_init_hook` :

1. type les postes de charge existants d'après leur libellé (Débit, CU, …) ;
2. amorce la famille d'approvisionnement des fournisseurs listés en dur dans
   les formules `J2`, `K2`, `L2`, `M2` de l'onglet `PO` du classeur ;
3. lance un premier calcul sur les OF ouverts.

Ces trois opérations ne servent qu'au démarrage. Ensuite, tout se règle en
configuration : type de poste sur la fiche du poste de charge, famille sur la
fiche fournisseur, barèmes dans le menu Séquencement.

## Points d'attention repris du classeur

- **`RODENBERG`** figurait à la fois dans la liste « panneaux » et dans la
  liste « complémentaire ». Il est amorcé en « panneaux » ; à trancher avec FMA.
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
- La colonne `R` du classeur, qui découpait le nom d'affaire au texte pour
  joindre les achats, était en `#VALUE!` sur la première ligne. Elle disparaît :
  la jonction passe par la relation réelle.

## Limite de périmètre

L'onglet `SEQUENCAGE` contient aussi des **règles de constitution de lot**
(10 repères max/jour, 8 h de débit max/jour, mixage A/B/C). Elles ne sont pas
reprises ici : ce n'est pas de la restitution mais de l'ordonnancement, et le
lotissement FMA est constitué dans LOGIKAL puis récupéré par Odoo. Ce module
fournit les scores sur lesquels ces règles s'appuient, pas les règles.
