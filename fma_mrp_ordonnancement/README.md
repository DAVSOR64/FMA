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
| E Début débit | `date_start` | natif |
| F planifier | `fma_planifie` | ce module |
| G Fin prod | `fma_date_fin_prod` | recopie de `x_studio_date_de_fin` |
| H Date liv. initiale | `fma_date_liv_initiale` | `commitment_date` du SO |
| J Date liv. actuelle | `fma_date_livraison` | date planifiée du BL de la commande de vente |
| K Statut livraison | `fma_statut_livraison` | `delivery_status`, repli sur les BL |
| L à Q Appro par famille | `fma_date_arrivee_*`, `fma_statut_reception_*` | ce module |
| R nom d'affaire nettoyé | *supprimée* | remplacée par la relation réelle |
| S Commentaires | `fma_commentaire` | ce module |
| T Nb repères | `fma_nb_reperes` | lignes de devis portant une position de repère |
| U Score complexité | `fma_score_complexite` | ce module |
| V + banc/usinage/montage | `fma_score_*` | ce module |
| W à AA Heures par poste | `fma_heure_*` | ce module |

Trois colonnes ne se lisent pas là où le classeur les prenait :

- **H Date liv. initiale** : la livraison **promise**, portée par
  `commitment_date`. À ne pas confondre avec `so_date_de_livraison_prevu`, qui
  porte la date *révisée* : sur `A25-07-02581/2` l'engagement est au 26/08
  alors que le client a demandé le 01/09 par la suite. C'est bien le 26/08 qui
  mesure la tenue du délai.
- **J et K Livraison** : les bons de livraison appartiennent à la commande de
  vente, pas à l'OF. `mrp.production.picking_ids` ne porte que les mouvements
  de composants et de produit fini — jamais le BL client.

Tout ce qui vient du devis passe par **`fma_sale_order_id`**, un point de
résolution unique et stocké : `sale_line_id.order_id`, puis
`x_studio_mtn_mrp_sale_order` (module `custom`). `sale_line_id` n'est pas
toujours renseigné chez FMA ; s'y fier seul vidait d'un coup la date
d'engagement, les colonnes de livraison, le nombre de repères, et donc les
quatre scores, qui se divisent par ce nombre.
- **T Nb repères** : le classeur recopiait à la main les multiplicateurs du
  champ de complexité (« A*3 » = 3 repères). On compte les lignes de devis
  portant une **position de repère** (`x_studio_position`, related du produit) :
  sur `A25-07-02581/2`, les dix lignes menuiserie la portent, tandis que
  l'éco-contribution, la ligne d'affaire et la remise commerciale ne la portent
  pas. Le seul critère « bien non stockable » en retenait douze. Repli sur ce
  critère pour les commandes où aucune ligne ne porte de position.

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
| `purchase.order.line.fma_famille_appro` | **famille d'appro modifiée sur une catégorie, famille ou sous-famille** | invalidation explicite : aucun `@api.depends` ne remonte quand la valeur est portée par une catégorie parente |
| `fma_*_appro` | idem, puis reclassement des lignes | invalidation explicite depuis `product.category`, `product.family`, `product.subfamily` |
| `fma_date_fin_prod` | **`x_studio_date_de_fin` modifié** | surcharge de `write` sur l'OF |
| `fma_nb_reperes` | lignes de la commande de vente | `@api.depends` |
| `fma_date_debut_debit` | `macro_planned_start` des OT de débit | `@api.depends` |
| `fma_sale_order_id` | `sale_line_id` ou `x_studio_mtn_mrp_sale_order` | `@api.depends` |
| `fma_date_liv_initiale`, `fma_statut_livraison`, `fma_date_livraison`, `fma_nb_reperes` | `fma_sale_order_id` et ses BL | `@api.depends` |
| tous | filet de sécurité | cron quotidien |

Les invalidations venant de l'achat ne recalculent **pas** tous les OF : la
résolution inverse `purchase.order._fma_productions_liees()` cible les OF
concernés via la chaîne d'approvisionnement, l'origine, puis le projet du SO.
Un OF qui échapperait à ces trois voies est rattrapé par le cron nocturne.

## À l'installation

Le `post_init_hook` :

1. type les postes de charge existants d'après leur libellé (Débit, CU, …) ;
2. rattache les catégories `01_PROFILS_BARRES_TOLES` à « profilé » et
   `02_REMPLISSAGE` à « vitrage » — cette dernière suivant la convention déjà
   retenue par `fma_custom._is_vitrage`. Les autres restent à renseigner,
   notamment les complémentaires (`03_QUINCAILLERIE`, `07_JOINTS`,
   `All / Accessoire`...) ;
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
  famille se règle désormais sur le produit, et la ventilation se fait ligne à
  ligne.

  La résolution se fait à trois niveaux, du plus précis au plus général :
  **sous-famille**, puis **famille**, puis **catégorie** (en remontant les
  parents). La catégorie est le niveau indispensable : les articles achetés —
  un couvre-joint TECHNAL, un vitrage TIV — portent leur `categ_id`
  (« All / 01_PROFILS_BARRES_TOLES », « All / 02_REMPLISSAGE ») sans avoir
  nécessairement de triplet famille renseigné. S'appuyer sur `product.family`
  seul laissait toutes les colonnes d'approvisionnement à « Aucune commande »
  alors que les commandes d'achat étaient bien retrouvées.

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

## Couleurs

**Les lignes restent noires.** Aucune décoration au niveau de la ligne : le
classeur n'en avait pas, et un tableau entièrement colorié ne hiérarchise
plus rien.

Les colonnes colorées sont exactement celles que colorait le `TDB_SAISIE` —
relevé fait sur les 78 règles de mise en forme conditionnelle du fichier :

| Colonne | Règle du classeur | Rendu |
|---|---|---|
| J Date liv. actuelle | `J < AUJOURD'HUI + 9` (priorité 56) | rouge |
| J Date liv. actuelle | `J > H`, livraison repoussée (priorité 58) | orange |
| K Statut livraison | valeur | pastille |
| M, Q Statuts de réception | valeur | pastille |

Les deux conditions sont portées par des booléens **non stockés**, calculés à
la lecture. Deux raisons : la règle des 9 jours dépend de la date du jour,
qu'un champ stocké figerait à son dernier recalcul ; et un champ non stocké
n'exige aucune colonne en base, donc aucune mise à jour de module.

Les pastilles de score ont été retirées : le classeur n'en avait pas.

## Saisie

**Le commentaire est la seule donnée modifiable** de l'écran, et seulement
pour les membres du groupe **« Modif Ordo »**. Tout le reste est en lecture
seule, y compris le marqueur « Planifié » et le niveau de complexité.

Le groupe **n'est pas livré par le module** : il se crée à la main dans Odoo,
sous le nom exact **« Modif Ordo »**. La déclaration XML d'un `res.groups`
échouait à l'installation en v19, où ce modèle a été remanié ; plutôt que de
deviner la bonne forme, le module retrouve le groupe **par son nom**.

Deux conséquences :

- tant que le groupe n'existe pas, l'écran est en lecture seule pour tout le
  monde, commentaire compris — un défaut qui se voit tout de suite, à
  l'inverse d'un droit ouvert par défaut ;
- le nom doit correspondre **exactement**. Le renommer coupe la saisie. Il est
  porté par la constante `FMA_GROUPE_MODIF` dans `mrp_production.py`.

Le contrôle passe par `fma_peut_modifier_ordo`, booléen calculé non stocké.
Odoo n'a pas de droit d'écriture par champ : poser `groups` sur le champ le
rendrait **invisible** aux autres utilisateurs, alors qu'on veut qu'ils le
lisent.

## Dates et fuseau horaire

`purchase.order.line.date_planned`, `stock.picking.scheduled_date` et
`sale.order.commitment_date` sont des **Datetime stockés en UTC**. « 24/08 à
00:00 » heure de Paris vaut « 23/08 22:00 » en base : appeler `.date()` dessus
perd un jour. Le module a eu ce défaut, visible sur `A25-07-02581/2` où
l'arrivée TECHNAL du 24 août s'affichait au 23.

Les champs concernés restent donc des **Datetime** et sont affichés avec
`widget="date"` : Odoo convertit dans le fuseau de l'utilisateur, le widget
masque l'heure. Aucune troncature côté serveur. Là où une date est réellement
nécessaire — comparer la fin de production à la promesse —, la conversion
passe par `_fma_en_date_locale`.

Corollaire : ne pas comparer une `Date` et un `Datetime` dans une décoration de
vue, où la comparaison se fait côté navigateur sur deux types différents. C'est
la raison d'être de `fma_retard_previsionnel`, calculé côté serveur.

## Approvisionnements : ce qui est retenu

**La date** est l'arrivée **prévue la plus tardive** parmi les lignes d'achat
de la famille, **y compris les lignes déjà réceptionnées**. La colonne affiche
donc la promesse du fournisseur, pas un reste à livrer ; c'est le statut qui
dit ce qui est arrivé — « Partiellement reçu » tant que tout n'est pas là.

**Le statut** s'agrège ligne à ligne sur les quantités reçues, ce qui reste
juste quand une commande mélange plusieurs familles.

**Le complémentaire est la famille par défaut.** Tout ce qui n'est ni profilé,
ni vitrage, ni panneau y tombe — y compris les catégories non encore
paramétrées. Aucune commande de l'affaire n'est ainsi perdue, et la colonne
« Arr. complém. » donne la date la plus lointaine de ce reste.

**Le détail** se consulte par le bouton camion, en liste comme sur la fiche :
il ouvre les **lignes d'achat** de l'affaire, groupées par famille, avec
fournisseur, arrivée prévue, quantité commandée et quantité reçue. Six
colonnes de dates en liste seraient illisibles ; c'est ici qu'on voit d'où
sort la date affichée. Les lignes plutôt que les commandes, parce que c'est au
niveau de la ligne que se lisent la famille et la date.

**Les commandes d'achat** sont cherchées par quatre voies cumulées : la
méthode native côté OF (`purchase_mrp`), la méthode native côté commande de
vente — celle que compte le bouton « Achats » du SO —, l'origine, puis le
projet du SO pour les achats saisis à la main.

## Robustesse en production

Le module se greffe sur des opérations métier : `purchase.order.button_confirm`,
`stock.picking.button_validate`, l'écriture sur une ligne d'achat, les
transitions d'état de l'OF. Une exception dans un recalcul y ferait échouer
l'opération elle-même — une réception qu'on ne peut plus valider bloquerait
l'atelier.

Tous ces points d'accroche sont donc protégés : en cas d'échec, l'exception
est tracée dans le journal, les colonnes concernées prennent des valeurs
neutres, et l'opération métier se termine normalement. Le cron de 4 h
rattrape. Une restitution périmée jusqu'au lendemain est un moindre mal.

Conséquence à connaître : une anomalie ne se voit pas à l'écran, elle se lit
dans les logs, sur les lignes « Ordonnancement FMA : … ignoré ».

## Quand les colonnes se mettent à jour

| Événement | Effet |
|---|---|
| Achat confirmé, annulé, date d'arrivée modifiée | immédiat, sur les OF concernés |
| Réception validée ou annulée | immédiat |
| Ordre de travail replanifié, durée modifiée | immédiat |
| Complexité, commentaire, marqueur planifié | immédiat |
| Barème, poids de niveau, famille d'appro, typage de poste | immédiat, sur tous les OF ouverts |
| Installation ou mise à jour du module | recalcul complet |
| Chaque nuit à 4 h | recalcul complet, filet de sécurité |

## Livraison : ce qu'un déploiement exige

Un champ **stocké** ne crée sa colonne qu'à la **mise à jour du module**. Un
simple déploiement de code laisse alors Odoo interroger une colonne
inexistante, et toute lecture du modèle échoue — y compris celle du menu
d'activités, ce qui rend le client web inutilisable. C'est arrivé en
production le 31/08/2026 avec `fma_livraison_imminente`.

Deux règles en découlent :

1. **Tout lot ajoutant un champ stocké doit s'accompagner d'une mise à jour du
   module, vérifiée**, pas seulement d'un push.
2. **Un champ qui ne sert qu'à l'affichage n'a pas à être stocké.** Le
   stockage ne se justifie que pour filtrer, regrouper, trier ou agréger. Les
   deux booléens de couleur sont dans ce cas et sont restés non stockés.

Même précaution pour les données du module : le groupe « Modif Ordo » est créé
par la mise à jour. Sa lecture passe par `env.ref(..., raise_if_not_found=False)`
afin qu'un module non mis à jour dégrade l'écran en lecture seule, plutôt que
de lever sur un identifiant introuvable.
