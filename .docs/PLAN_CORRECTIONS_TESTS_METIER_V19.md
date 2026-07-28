# Plan de correction — Retours des tests métier v19 (mise à jour 20/07/2026)

Source : `TEST v19(Anomalies).csv` (VALLEM, ELOGAU, MATANG, 15/07), complété
par les vagues suivantes (Nolhan Pavin, EMIDAV, CLEGIS) puis **arbitré en
réunion le 20/07/2026** — le tableau officiel de cette réunion (29 lignes,
colonnes Décision/Action à faire/Responsable/Commentaire) fait désormais foi
et prévaut sur les échanges informels précédents dans ce document.

Décodage des pseudos testeurs (3 lettres prénom + 3 lettres nom) :
VALLEM = Valentin Lemonnier, ELOGAU = Elowen Gauthier, MATANG = Mathieu
Angibault, EMIDAV = Emilien Davoine. CLEGIS non décodé avec certitude.

---

## 🚨 Découverte critique du 21/07/2026 : `fma_custom/models/` jamais chargé

En reprenant les points non résolus avec un environnement local restauré
depuis un backup pré-prod du jour même (voir contexte de restauration
plus haut dans la conversation), correction du point #7/#29 a révélé un
bug bien plus large que prévu.

**Cause** : `fma_custom/__init__.py` n'importait que `wizard`, **jamais
`models`** :
```python
from . import wizard   # ligne unique, avant correctif
```
Résultat : les 6 fichiers de `fma_custom/models/` (`purchase_order.py`,
`sale_order.py`, `mrp_production.py`, `account_move.py`,
`res_partner.py`, `stock_picking.py`) n'ont **jamais été chargés dans le
registre ORM**, malgré le module marqué `state = installed`. Vérifié
noir sur blanc : `type(env['purchase.order']).__mro__` ne contient
aucune classe de `fma_custom`, alors que `custom`, `purchase_order_export`,
`fma_studio_models` y figurent bien.

**Pourquoi ça n'a rien cassé de visible jusqu'ici** : les 4
`base.automation` Studio d'origine que ce code était censé remplacer
(`MTN : Propagation du compte analytique SO sur PO`, `... MO sur PO`,
`DSA Reference compute PO`, `DSA : Mise à jour du responsable PO par le
responsable PROJECT`) sont **encore actives en base** et ont continué à
faire le travail à la place du code mort. Le "portage" documenté comme
`fait` dans ce plan pour la réf/responsable/analytique (#6, #12) n'a en
réalité jamais tourné — le comportement observé en test venait des
automatisations Studio, pas du code.

**Impact concret, vérifié en direct (pas juste théorique)** — deux
**actions cliquables réelles**, présentes dans le menu ⚙️ Actions de
l'interface, plantaient avec une `AttributeError` avant correctif :
- **"Fichier clients Iziqo"** (liste/fiche Contact) —
  `res.partner.action_export_iziqo_customers`
- **"Création Facture Fournisseur en masse"** (liste/fiche Livraison) —
  `stock.picking.action_create_supplier_invoices`, exactement le bouton
  discuté au point #24 de ce plan (dont la conclusion "comportement
  standard confirmé" était donc basée sur une lecture de code mort —
  la vraie conclusion est : **ce bouton plantait pour quiconque
  cliquait dessus**)
- Un cron désactivé par défaut (`Calcul PRI (devis en cours)`,
  `sale.order.cron_calcul_pri_batch`) — pas de risque immédiat tant
  qu'il reste désactivé, mais aurait planté à chaque exécution s'il
  avait été activé.

**Corrigé** (`fma_custom` → 19.0.1.0.4) : ajout de `from . import
models` dans `fma_custom/__init__.py`. Testé en direct après correctif :
les 3 méthodes existent désormais et s'exécutent (le cron PRI a même
tourné sur plusieurs milliers de devis réels lors du test avant d'être
interrompu, sans erreur).

**Point de vigilance pour le déploiement** : ce correctif réactive aussi
`_propagate_analytic_from_sale_order` (logique du point #6, toujours en
attente d'arbitrage métier). Vérifié : le code est **strictement
identique** à l'automatisation Studio `MTN : Propagation...` encore
active — la réactivation ne fait donc que dupliquer un calcul déjà fait
(idempotent, même résultat), elle **ne tranche pas** la question
d'arbitrage SO-vs-PO du #6, qui reste ouverte. Pas de risque de double
écriture incohérente, juste du travail redondant jusqu'à ce que les
automatisations Studio d'origine soient désactivées.

---

## Tableau officiel de suivi (réunion du 20/07/2026)

| # | Testeur | Anomalie | Décision | Responsable | Statut ici |
|---|---|---|---|---|---|
| 1 | VALLEM | Gamme/Série non filtrées | Bug confirmé | JBS | **Fait** — filtre domaine ajouté |
| 2 | VALLEM | Commercial auto (régression) | Bug confirmé | JBS/DAVSOR | **Fait** — champ Employé recréé (contact + Affaire + devis) |
| 3 | VALLEM | Mode de règlement (régression) | Bug confirmé | JBS/DAVSOR | **Fait** — champ recréé sur l'Affaire |
| 4 | VALLEM | Chatter affaire pas à droite | Pas un bug — confirmé OK | — | Clos (comportement responsive standard) |
| 5 | VALLEM | "Projet" devrait être "Compte analytique" | Standby (fusion en cours) | David/JBS | Mis en pause, ne pas traiter isolément |
| 6 | VALLEM | Champ BE doit rester vide | Clôturé conforme | — | Clos, aucune action |
| 7 | VALLEM | Préférence affichage Contact | AC — amélioration non prioritaire | JBS | Différé, à chiffrer plus tard |
| 8 | VALLEM | Dashboard Ventes FMA a sauté | Bug confirmé — en cours d'investigation | JBS/Alexis | En cours — voir détail #4/#8 |
| 9 | ELOGAU | Date effective manquante | Clarifié — pas un bug | — | Clos |
| 10 | ELOGAU | Séquence opération manquante | Bug corrigé — validé en réunion | JBS | **Fait** |
| 11 | ELOGAU | Onglet Divers : projet pas auto | À préciser — pas confirmé | JBS | **Rouvert** — à retester sur affaires post-migration |
| 12 | ELOGAU | Achats : Projet du SO, compte analytique, Is XML Created, commentaires | Bug confirmé — partiellement corrigé | JBS | **Fait** (Is XML Created + commentaires + creation time/SFTP sur la fiche) |
| 13 | ELOGAU | Ordre d'achat vitrage : champs manquants, Contrat cadre en trop | Bug confirmé — actions définies | JBS/David | **Fait** (champs conditionnés catégorie "Remplissage", Contrat cadre masqué) ; répartition analytique en standby (David) |
| 14 | MATANG | Droit d'intégrer des affaires | Bug corrigé — à valider | JBS | **Fait**, confirmé par test direct |
| 15 | EMIDAV | Congé 1 jour retire toute la semaine | Bug confirmé — à corriger | JBS | **Fait** — recalcul immédiat + cron élargi |
| 16 | EMIDAV | Niveau de complexité à maintenir | Corrigé — validé en réunion | JBS | **Fait** ; refonte propre post-v19 prévue (Logical/Tech Design) |
| 17 | EMIDAV | PO liés à l'OF plus accessibles | Bug confirmé — à corriger | **David** | Pas d'action JBS, David reprend avec Jean |
| 18 | EMIDAV | Pas d'accès à "Capacité par poste" | Bug confirmé — à corriger | JBS | Erreur analysée, rien trouvé côté serveur — **hypothèse cache navigateur**, à retester après vidage de cache |
| 19 | EMIDAV | Heures OT non modifiables sans fiche de temps | Pas un bug — standard v19 | — | Clos, traiter à la source (process) |
| 20 | EMIDAV | Capacité par poste 80,1h/3 ressources | Bug confirmé — correctif possible | JBS | **Fait** (durée min/max Integer→Float) ; recalcul jours planifiés après réplanification à surveiller |
| 21 | EMIDAV | Filtres/exports à conserver | Conforme, rien à faire | — | Clos |
| 22 | EMIDAV | Code-barres : transfert impossible | Demande confirmée (redéveloppement) | JBS | **En attente** — confirmation Emilien/David sur le champ backend avant de toucher au module code-barres |
| 23 | EMIDAV | Facture brouillon via code-barres | Demande confirmée (redéveloppement) | **David** | Pas d'action JBS |
| 24 | EMIDAV | Module Atelier : composants manquants | AC — non prioritaire, à surveiller | JBS | Différé, point de vigilance post-bascule |
| 25 | CLEGIS | Champ Référence non renseigné | Clarifié — fonctionnement confirmé | — | **À vérifier** sur le cas précis (lien commande à transmettre) |
| 26 | CLEGIS | Remise fournisseur n'apparaît pas | Partiellement confirmé | JBS | **Fait** (champ exposé via #13) ; auto-application du taux en standby |
| 27 | CLEGIS | Analytique par ligne non renseigné à l'export | Standby | **David** | Pas d'action JBS |
| 28 | CLEGIS | 2 onglets livraison (LRE-Préfabrication) | Bug confirmé — à corriger | JBS | Picking type candidat identifié ("Collecter les composants") ; **mis de côté** (écran exact non localisé, à la demande de l'utilisateur) |
| 29 | EMIDAV | Renvoi manuel XML SFTP bloqué | Nouvelle demande confirmée | **David** | Pas d'action JBS |

---

## Nouveaux correctifs appliqués suite au tableau du 20/07/2026

### #11 — Onglet Divers, réouverture

Ma clôture précédente (« c'était bon ») était prématurée : la décision
officielle de réunion est **« À préciser — pas confirmé »**, sans décision
ferme. **Action** : retester spécifiquement sur des affaires/commandes
créées **après la migration** (le testeur n'a confirmé que sur d'anciennes
commandes) — point rouvert, pas de correctif de code pour l'instant.

### #12 — Achats : Is XML Created, commentaires, creation time/SFTP — CORRIGÉ

Trois champs déjà déclarés en code mais visibles seulement en liste (pas
sur la fiche) ont été ajoutés au formulaire de commande d'achat :
`is_xml_created`, `xml_creation_time`, `sftp_synced_time`
(`purchase_order_export/views/purchase_order_views.xml`, module →
19.0.0.6.1). "Commentaire livraison"/"Commentaire interne"
(`x_studio_commentaire_livraison_vitrage_`/`x_studio_commentaire_interne_`)
traités avec le point #13 ci-dessous puisqu'ils sont spécifiques au
vitrage.

### #13 — Vitrage : champs conditionnés + Contrat cadre masqué — CORRIGÉ

Nouveau champ calculé `x_is_glazing_order` (Boolean, stocké) sur
`purchase.order`, vrai si au moins une ligne a un produit de catégorie
"Remplissage" (`custom/models/purchase_order.py`). Utilisé pour
n'afficher remise, commentaires et dimensions **que sur les commandes
vitrage** plutôt que sur tous les achats :
- En-tête : `x_studio_remise`, `x_studio_remise_1`,
  `x_studio_commentaire_livraison_vitrage_`,
  `x_studio_commentaire_interne_` (`invisible="not x_is_glazing_order"`).
- Lignes : `x_studio_posit` (renommé "Repère" en vue), `x_studio_hauteur`,
  `x_studio_largeur` (`column_invisible="not parent.x_is_glazing_order"`).
- "Contrat cadre" (`requisition_id`, module `purchase_requisition`,
  confirmé inutile) : masqué (`invisible="1"`) sur toutes les commandes.

Nouveau fichier `custom/views/purchase_order_views.xml`, dépendance
`purchase_requisition` ajoutée au manifeste (`custom` → 19.0.1.0.15).
Répartition analytique automatique : **en standby**, David travaille sur
la logique de reprise depuis le Projet du SO séparément.

### #18 — Accès "Capacité par poste" (Emilien) — hypothèse cache navigateur

Message d'erreur obtenu et analysé en direct : `OwlError` /
`this.child.mount is not a function` — exactement la même signature que le
bug Owl v19 déjà documenté dans `STUDIO_AUDIT.md`. Vérifications faites :
- Le menu pointe bien vers l'action versionnée
  (`fma_studio_models.action_x_capacite_par_poste`), pas vers l'ancienne
  action Studio — le mécanisme de repointage (`ir_ui_menu.py`) fonctionne
  correctement pour ce modèle.
- L'action et sa vue liste sont correctement configurées.
- **Avec le contexte exact d'Emilien** (`with_user`) : droits OK sur les 3
  modèles utilisés, lecture des 9 enregistrements OK, `get_view('list')`
  OK, `web_search_read` OK. **Rien ne reproduit le crash côté serveur.**

**Hypothèse retenue** : cache navigateur obsolète (bundle JS `b039f53`
antérieur à un redéploiement récent — l'environnement affiche une bannière
"base neutralisée pour les tests", donc redéployé fréquemment). **Action**
: demander à Emilien un rechargement forcé (Ctrl+Maj+R / vider le cache)
avant de creuser plus loin. Si le problème persiste après cache vidé, un
test F12 en direct avec l'onglet Network ouvert sera nécessaire.

### #22 — Code-barres : ajouter "Numéro de BL" à l'écran de réception

**En attente** : `stock_barcode` (Enterprise) est bien installé, mais
c'est un module à base de composants JS/Owl (pas de vues XML classiques)
— ajouter un champ demande une vraie surcharge JS d'un outil utilisé
quotidiennement par les opérateurs d'entrepôt. Mis en attente d'une
confirmation Emilien/David sur le champ backend cible (`origin` existant
vs nouveau champ dédié) avant de développer, pour ne pas risquer de
casser un outil critique sur une hypothèse non confirmée.

### #25 — CLEGIS, champ Référence — besoin du lien de la commande

Décision : "clarifié, fonctionnement confirmé" (le champ se renseigne par
défaut avec les initiales de l'utilisateur connecté, modifiable
manuellement). Un lien vers la commande concernée a été transmis en
réunion pour vérification ciblée, mais je ne l'ai pas — **toujours en
attente** de ce lien pour une vérification directe sur ce cas précis.

### #28 — 2 onglets livraison (LRE-Préfabrication) — mis de côté

**Investigation live faite** : candidat solide identifié —
`stock.picking.type` **"Collecter les composants"** (LA REGRIPPIERE,
id=28, 8 388 transferts ; LA REMAUDIERE, id=34, 1 748 transferts), code
`internal`. "LRE" = LA REGRIPPIERE. Vérifié : `sale_kpi_delivery` (calcul
de KPI facturation) ne semble pas inclure ces transferts (basé sur
`sale_line_id`, absent sur ces mouvements internes). **Écran exact où
apparaissent "2 onglets" non identifié** dans le code (probablement un
écran standard Odoo Inventaire, sans personnalisation FMA trouvée) — une
capture d'écran aurait été nécessaire pour localiser précisément quoi
filtrer. **Mis de côté à la demande de l'utilisateur** plutôt que de
deviner l'écran.

---

## ⚠️ Correction méthodologique : l'hypothèse "groupe manquant" était fausse

Sur les points #1 (MATANG) et #4 (dashboard Nolhan), le diagnostic initial
concluait à une appartenance manquante au groupe "Utilisateur interne"
(`base.group_user`), vérifiée via `env.ref('base.group_user') in
user.group_ids`. Un contrôle élargi à **tous** les utilisateurs actifs a
montré que **36 utilisateurs sur 37, y compris le compte Administrator
lui-même**, échouent à ce test — ce qui est absurde pour un compte admin
qui fonctionne sans aucun problème partout.

Vérification avec la bonne méthode (`user.has_group('base.group_user')`,
celle qu'Odoo utilise réellement pour ses contrôles d'accès) : **`True`
pour Admin, Angibault, Nolhan et Valentin Lemonnier sans exception**. Le
champ `group_ids` brut ne reflète donc pas l'appartenance effective en
Odoo 19 (implication de groupes calculée différemment) — c'était un faux
signal depuis le départ.

**Conséquence** : le correctif appliqué à Angibault (ajout explicite au
groupe) n'a très probablement rien changé fonctionnellement (il avait
déjà l'accès effectif). Les vrais blocages de MATANG (#1) et de Nolhan
(#4 dashboard) restent donc **non expliqués** — un test en cours via
impersonation ("Se connecter en tant que", plus fiable que la déduction
shell) doit trancher.

---

## Vue d'ensemble — lot initial (VALLEM/ELOGAU/MATANG)

| # | Anomalie (testeur) | Statut après retours Nolhan | Priorité |
|---|---|---|---|
| 1 | Droit création "Affaire" (MATANG) | **Résolu, confirmé en test direct (17/07)** — la création d'une Affaire fonctionne maintenant en se connectant avec son compte. Le correctif (ajout au groupe "Utilisateur interne") a probablement réglé un problème de **visibilité de menu** (mécanisme distinct de `has_group()`, qui ne montrait aucune différence) | **Fait — confirmation finale par Mathieu lui-même recommandée** |
| 2 | Pas de Gamme ni de Série (VALLEM) | Champs ajoutés en vue (fait), **mais** Nolhan signale que la liste déroulante proposée est incorrecte — nouveau sous-bug | **P1** |
| 3 | Chronologie/chatter Affaire (VALLEM) | Chatter rétabli (fait). Position "à droite" expliquée : dépend de la largeur d'écran (seuil ≥1920px), pas un bug, pas un réglage utilisateur | **Fermé (code)** |
| 4 | Tableau de bord Ventes FMA cassé (VALLEM) | Probable écart de snapshot pré-prod/prod (données de config, pas de code) — **mis de côté**, à retester avec un snapshot plus récent | **Différé** |
| 5 | Projet non auto-rempli en fabrication (ELOGAU) | Retour Nolhan ambigu ("sur les commandes anciennes ça marche") — à reclarifier | **P2** |
| 6 | Propagation analytique achat/vitrage (ELOGAU) | Bug confirmé, correctif en attente d'arbitrage métier (source SO vs PO) | **P1** |
| 7 | Champs manquants ligne achat (ELOGAU) | Nolhan confirme : doivent être en **en-tête**, pas en ligne — mais "Projet du SO" vide et "Is XML Created" absent sur son test | **P1** (nouveau bug) |
| 8 | Champs vitrage manquants (ELOGAU) | hauteur/largeur sécurisés en Python (fait, type Integer confirmé) ; reste : exposition en vue (attente arbitrage) | **P1** |
| 9 | Mode de règlement non auto-rempli (VALLEM) | Nolhan précise : c'est "Condition de paiement" (champ standard) qui doit se récupérer sur le client, **sur une Affaire** | **P2** |
| 10 | Commercial non auto-affecté (VALLEM) | Nolhan + retest Valentin : **fonctionne en réalité** — probable faux positif du test initial | **Probablement fermé** |
| 11 | Séquence opération invisible (ELOGAU) | **Corrigé** (mrp_capacity_planning 19.0.1.0.6) — toujours visible, en lecture seule hors brouillon | **Fait** |
| 12 | Champ "Dates effective" manquant (ELOGAU) | Nolhan précise : date à laquelle la livraison est totalement effectuée — reste à trancher auto vs manuel | **P2** |
| 13 | Workflow BE / Chef de projet (VALLEM) | **Fermé par Nolhan** : comportement confirmé correct en v19 | **Fermé** |
| 14 | "Projet" vs "compte analytique" (VALLEM) | Nolhan confirme : sur l'**Affaire**, le champ doit s'appeler "Compte analytique" — **champ réellement absent** de `x_affaire` | **P1** (nouveau) |
| 15 | Préférence module Contact (VALLEM) | Devient une vraie demande : badge visuel Client/Chantier/Contact sur la kanban | **P2** (nouvelle feature) |

## Vue d'ensemble — nouveau lot EMIDAV (16-17/07/2026)

| # | Anomalie | Cause identifiée | Priorité |
|---|---|---|---|
| 16 | Congé 1 jour → capacité retirée sur toute la semaine | Pas de bug de calcul trouvé ; modèle/vue Gantt **hebdomadaire uniquement**, effet visuel trompeur (tout le bloc-semaine passe en rouge) | **P2** |
| 17 | Champ "niveau de complexité" sur OF à maintenir | **Corrigé** — champ ajouté à la vue formulaire OF (`custom` → 19.0.1.0.11) | **Fait** |
| 18 | PO liés à la commande plus accessibles via l'OF | Corrigé récemment (commits 13/07) **mais uniquement dans le popup de replanification**, pas ailleurs sur la fiche OF | **P2** |
| 19 | Pas d'accès à "Capacité par poste" | Droits corrects dans le module (`base.group_user` = read/write/create) — cause externe au module probable | **P2** |
| 20 | Modification heures prévues (OT) plus faisable en ligne | Aucun code trouvé qui bloque `duration_expected` — cause non identifiée dans le repo | **P2** |
| 21 | Capacité par poste 80,1H/3 ressources → 1 seule utilisée | Confirmé : la division du nombre de ressources ne fait que raccourcir la durée planifiée, **aucune réservation multi-ressources réelle** — vrai en v19 ET v17, pas une régression | **P2** |
| 22 | Filtres personnalisés / exports Excel à conserver | Hors périmètre code (`ir.filters`/`ir.exports` sont des données utilisateur, pas versionnées) | **Hors dev** |
| 23 | Accès mouvement transfert code-barres impossible | `stock_barcode` absent de tout le repo — pas de personnalisation FMA en cause | **P2** |
| 24 | Facture brouillon sur réception | Comportement standard Odoo confirmé (portage fidèle, jamais d'auto-validation) — à clarifier si c'est vraiment ça qui est attendu | **P2** |
| 25 | Atelier : composants manquants sous étiquette "Affaire" peu lisible | Écran non localisé dans `fma_atelier` — clarification nécessaire | **P2** |

---

## Corrections déjà appliquées en code (commit `387315d` + suite)

| # | Correction | Module (version) |
|---|---|---|
| 2 | Gamme + Série ajoutés à la vue devis | `fma_sale_order_custom` → 19.0.1.0.4 |
| 3 | Chatter réactivé sur `x_affaire` (`mail.thread`/`mail.activity.mixin` + `<chatter/>`) | `fma_studio_models` → 19.0.1.0.8 |
| 8 | `x_studio_hauteur`/`x_studio_largeur` déclarés en Python (type `Integer` confirmé en base) | `custom` → 19.0.1.0.10 |
| 11 | Séquence d'opération toujours visible (lecture seule hors brouillon) | `mrp_capacity_planning` → 19.0.1.0.6 |

### 26. Bug systémique découvert en test direct : listes déroulantes illisibles ("x_affaire_stage,1")

**Découvert le 17/07/2026** en testant #1 (MATANG) : le champ "Étape" sur
l'Affaire affichait des valeurs du type `x_affaire_stage,1` au lieu du nom
réel de l'étape.

**Cause** : aucun des **20 modèles** portés depuis Studio dans
`fma_studio_models` ne déclarait `_rec_name = "x_name"`. Ces modèles
utilisent tous `x_name` (et non `name`) comme champ de nom — convention
systématique de Studio — mais sans `_rec_name` explicite, Odoo ne sait pas
quel champ utiliser pour l'affichage et retombe sur le format technique
`modèle,id`. Ce n'était pas un problème isolé à l'étape d'affaire : ça
affectait potentiellement **toutes les listes déroulantes et tous les
champs liés référençant un `x_affaire`, `x_gamme_mtn`, `x_serie_mtn`,
`x_capacite_par_poste`, `x_reglements`, etc.** partout dans l'application
(devis, commandes d'achat, fabrication...).

**Corrigé** : `_rec_name = "x_name"` ajouté aux 20 classes concernées
(`fma_studio_models` → 19.0.1.0.9). Aucun risque de perte de données
(changement d'affichage uniquement, pas de migration de schéma).

**Impact potentiel sur d'autres points de ce rapport** : ce bug pourrait
expliquer une partie de la confusion "Projet"/"Affaire"/noms illisibles
remontée ailleurs (#5, #14) — à revérifier une fois ce correctif déployé,
certains points pourraient se résoudre d'eux-mêmes.

### 35. Bug systémique découvert en réunion : valeurs affichées en dictionnaire de traduction brut

**Découvert le 17/07/2026** en retestant #2 (Gamme/Série) : la liste
déroulante de Gamme affichait `{'en_US': 'Forster', 'fr_FR': 'Forster'}`
au lieu de `Forster`.

**Cause** : la colonne `x_name` de **13 des 20 modèles** portés depuis
Studio est stockée en base au format `jsonb` (dictionnaire de traduction
par langue — comportement par défaut de Studio pour les champs texte),
mais notre code Python déclarait ces champs comme `Char` simple, sans
`translate=True`. Résultat : Odoo lit la valeur brute au lieu d'en
extraire la traduction courante.

**Modèles concernés** (colonne `x_name` en jsonb, confirmé en base) :
`x_affaire_stage`, `x_capacite_par_poste`, `x_delai_entre_operatio` (+ sa
ligne), `x_gamme_mtn`, `x_serie_mtn`, `x_reglements`, toute la famille
`x_remise` (7 modèles), `x_purchase_order_line_35a7b`,
`x_account_move_line_803a2`. **Non concernés** (déjà en `character
varying`, aucune action) : `x_affaire` lui-même (4059 enregistrements),
et tous les modèles `_tag`.

**Corrigé** : `translate=True` ajouté aux 16 champs concernés
(`fma_studio_models` → 19.0.1.0.10). Aucune migration de données requise
— la donnée jsonb existante est déjà correcte, seule la déclaration Python
était incomplète.

**Point de vigilance** : `x_affaire_stage` étant concerné, l'étape
d'affaire (déjà corrigée pour le `_rec_name` au point #26) aurait affiché
le même type de dictionnaire brut sans ce correctif complémentaire — les
deux bugs se cumulaient sur cet écran précis.

Point de vigilance sur #2 : les champs sont bien visibles maintenant, mais
Nolhan signale que **la liste de choix proposée pour la Série n'est pas
la bonne** — probablement un filtre manquant (la Série devrait sans doute
être filtrée selon la Gamme sélectionnée, via le champ
`x_studio_gamme_de_la_srie` déjà présent sur `x_serie_mtn`). Correctif à
qualifier avant de coder (voir #2 ci-dessous).

---

## Détail par point — lot initial

### 1. Droit de création d'"Affaire" (MATANG) — RÉSOLU

**Confirmé en test direct le 17/07/2026** : en se connectant avec le compte
de Mathieu Angibault (mot de passe temporaire défini par un admin, faute
de fonctionnalité d'impersonation native dans cette instance Odoo) et en
reproduisant le chemin Ventes > Affaire > Nouveau > Enregistrer, la
création fonctionne **sans blocage**.

**Nuance sur le diagnostic** : le test `has_group('base.group_user')`
(voir encadré méthodologique) montrait `True` pour tout le monde, groupe
ajouté ou non — ce qui avait fait conclure que le correctif du 16/07
(ajout explicite au groupe "Utilisateur interne") n'avait probablement
rien changé. Le fait que ça fonctionne maintenant suggère que
`has_group()` n'était pas le bon test : la **visibilité des menus** dans
Odoo peut dépendre d'une vérification différente, basée directement sur
la table de relation `groups_id` plutôt que sur la résolution transitive
utilisée par `has_group()`. Le correctif a donc probablement bien réglé
le vrai problème (menu "Affaire" invisible), via un mécanisme différent de
celui que j'avais vérifié.

**Reste à faire** :
- Demander à Mathieu Angibault de confirmer lui-même, avec son propre mot
  de passe (celui défini temporairement pour le test doit être changé).
- Supprimer l'enregistrement de test `x_affaire` id=4093
  ("TEST_VERIF_A_SUPPRIMER") créé lors des vérifications du 16/07.
- Vérifier si "intégrer une affaire" désignait bien cette création
  manuelle standard, ou une action plus spécifique (import, bouton dédié)
  — à confirmer avec Mathieu si un doute persiste.

### 2. Gamme/Série — corrigé en vue, nouveau sous-bug sur la liste

**Fait** : champs ajoutés à `fma_sale_order_custom/views/sale_order_views.xml`.

**Nouveau constat (Nolhan)** : "les champs étaient bien visibles mais la
liste n'est pas bonne". Hypothèse la plus probable : la liste déroulante
de `x_studio_srie` (Série) devrait être filtrée par la Gamme sélectionnée
(relation déjà présente : `x_serie_mtn.x_studio_gamme_de_la_srie`), mais
aucun domaine n'est actuellement appliqué sur le champ ajouté en vue — la
liste montre donc toutes les séries, pas seulement celles de la bonne
gamme.

**Avant de corriger** : confirmer avec Nolhan/VALLEM que c'est bien ce
comportement attendu (domaine dépendant), et pas autre chose (ex. la liste
propose des enregistrements de test/vides, ou l'ordre est incorrect).

### 3. Chronologie d'affaire — correction complète après captures d'écran (20/07)

**Erreur d'interprétation initiale corrigée** : "chronologie" ne
désignait pas le chatter (fil de discussion Odoo) mais la **section de
champs dates** déjà existante sur le **devis** (`sale.order`) — "Demande
reçue le", "Devis fait le", "Devis validé le", "ARC du", "BPE du"...
(groupe `<group string="Chronologie">`, `custom/views/sale_order_views.xml`).
Le chatter ajouté sur `x_affaire` (point ci-dessus, toujours légitime en
soi) ne répondait donc **pas** à la vraie demande de VALLEM.

**Cause racine (confirmée par capture d'écran prod vs pré-prod)** : ce
groupe "Chronologie", ainsi que "Informations principales" et
"Informations supplémentaires", étaient insérés via
`xpath expr="//sheet/notebook" position="before"` — c'est-à-dire **après**
le groupe natif `sale_header` (qui contient nativement `partner_details`
et `order_details` en 2 colonnes), mais **en dehors** de lui. Résultat :
chacun de nos 3 groupes s'empilait en pleine largeur au lieu de rejoindre
la grille à 2 colonnes d'Odoo — d'où "tout sur la même colonne" en
pré-prod, contre 2 colonnes distinctes en prod.

**Corrigé** : xpath changé pour insérer nos 3 groupes **à l'intérieur**
de `sale_header` (`position="inside"` sur `//group[@name='sale_header']`
au lieu de `//sheet/notebook` `position="before"`) — ils rejoignent ainsi
automatiquement la grille à 2 colonnes native (`custom` → 19.0.1.0.14).

**Point annexe conservé** : la position du chatter natif d'Odoo (côté vs
bas) reste, elle, une bascule responsive selon la largeur de fenêtre
(`form_renderer.js`, seuil XXL ≈1920px) — ceci concerne le chatter/fil de
discussion en tant que tel (par ex. sur `x_affaire`), pas la section
"Chronologie" du devis qui est désormais réglée par le xpath ci-dessus.

**Affinage #1 (capture d'écran du 20/07)** : agencement voulu — Chronologie
sur la 2e colonne, en 1ère ligne, avec Informations principales/
supplémentaires sur la 2e ligne (pleine largeur chacune). Corrigé en
ajoutant un groupe vide `fma_chronologie_filler` avant Chronologie pour la
décaler sur la 2e colonne (`custom` → 19.0.1.0.16).

**Affinage #2 (capture d'écran du 20/07)** : gros espace vide au-dessus de
Chronologie. Cause identifiée par inspection directe de la vue résolue
(`env['sale.order'].get_view(view_type='form')`) : tous les champs
personnalisés (Gamme, Série, Commercial...) atterrissent en réalité dans
`partner_details` (colonne 1, très haute), alors que `order_details`
(colonne 2) reste courte. Chronologie, ajoutée comme *nouvelle ligne* de
la grille de `sale_header`, attendait donc la fin de la colonne 1 (la plus
haute) avant de s'afficher. **Corrigé** : Chronologie déplacée à
l'intérieur de `order_details` (`position="inside"` sur
`//group[@name='order_details']`), supprimant le filler — elle continue
ainsi immédiatement le contenu (court) de cette colonne (`custom` →
19.0.1.0.17). Confirmé "beaucoup mieux" par le métier.

**Affinage #3 (capture d'écran du 20/07)** : une fois bien positionnée
verticalement, Chronologie restait étroite et collée à droite au lieu de
prendre 50% de la largeur de la ligne (comme Informations principales/
supplémentaires). **Cause racine** (trouvée en lisant le compilateur de
vue d'Odoo, `web/static/src/views/form/form_compiler.js`, fonction
`compileGroup`) : dès qu'un groupe contient un enfant `<group>`, Odoo le
traite comme un groupe "externe" (grille Bootstrap à colonnes) plutôt que
"interne" (grille 2 colonnes label/valeur). En imbriquant `<group
string="Chronologie">` À L'INTÉRIEUR de `order_details`, ce dernier
basculait donc en groupe externe, et Chronologie n'héritait plus que de
la moitié de la colonne d'`order_details` (donc un quart de la page) —
d'où l'aspect étroit/collé à droite. Cela cassait aussi silencieusement
l'affichage du libellé de certains champs natifs d'`order_details` (ex.
"Conditions de paiement"). **Corrigé** : suppression de la balise
`<group>` intermédiaire — le séparateur "Chronologie" et les paires
label/champ sont désormais des enfants directs d'`order_details`, qui
reste ainsi un groupe interne standard ; Chronologie prolonge alors
naturellement la grille 2 colonnes existante sur toute la largeur de la
colonne, comme Informations principales/supplémentaires (`custom` →
19.0.1.0.18). **À valider par le métier via un nouveau screenshot avant
commit/push.**

### 4. Dashboard Ventes FMA (Nolhan) — MIS DE CÔTÉ (probable écart de snapshot)

Fonctionne avec le compte admin, données intactes des deux côtés
(FMA/F2M). L'utilisateur réellement bloqué est **Nolhan Pavin**
(`nolhan.pavin@janneau.com`, id=69), pas Valentin Lemonnier comme supposé
au départ. Vérifications de droits faites (groupes, accès aux modèles
sources, `has_group`) : **rien ne l'explique techniquement**, y compris
sur le dashboard "Sales" (id=12) identifié en réunion comme le vrai
coupable.

**Découverte du 20/07** (captures d'écran prod vs pré-prod) : le contenu
affiché diffère complètement entre les deux environnements pour "Ventes
FMA" — pré-prod montre un dashboard générique, prod un rapport détaillé
("Devis réalisés, prise de commandes & taux de transformation 2026").
Recherche en base : le contenu détaillé **existe bel et bien** en
pré-prod (`spreadsheet.dashboard` id=64 "Ventes FMA (copie)", groupe
Sales), mais il existe aussi un **groupe de dashboards vide** nommé
"Ventes FMA 2025" (id=12 dans `spreadsheet.dashboard.group`, 0 dashboard
dedans) qui prête à confusion.

**Conclusion** : les dashboards Spreadsheet sont des données pures (non
versionnées dans le code, comme les filtres/exports personnalisés) —
cet écart est très probablement dû à la pré-prod (base de test, instantané
d'un moment donné) qui n'est pas synchronisée avec les dernières
modifications faites en production. **Pas un bug de code** à corriger
dans ce dépôt.

**Décision (20/07)** : point mis de côté, à retester une fois la base de
pré-prod rafraîchie avec un instantané plus récent de la production.

**Test direct effectué (21/07)** : backup pré-prod du jour même (21/07)
restauré en local, connexion réelle avec le compte de Nolhan (mot de passe
temporaire) via navigateur headless. **Le symptôme est confirmé, avec un
instantané frais** — donc pas (ou plus uniquement) un problème de
désynchronisation d'instantané :

- Cliquer sur **"Ventes FMA"** dans la sidebar (`spreadsheet.dashboard`
  id=12, groupe Ventes) affiche bien le dashboard **générique** (tuiles
  KPI Devis/Commandes/Revenu + graphique "Ventes mensuelles"), pas le
  rapport détaillé.
- Le rapport détaillé **"Devis réalisés, prise de commandes & taux de
  transformation"** existe et fonctionne, mais sous le nom **"Ventes FMA
  (2025)"** (id=64 — anciennement "Ventes FMA (copie)", renommé depuis).
  Le même rapport existe côté F2M sous "Ventes F2M" (id=53, celui-là
  correctement nommé sans suffixe) et "Ventes F2M (2025)" (id=66).
- Aucune erreur console navigateur pendant le chargement (hors "Loading..."
  normal des cellules spreadsheet asynchrones).

**Conclusion confirmée** : ce n'est **pas un bug de code**. C'est un pur
problème de **nommage/organisation des dashboards** (donnée, non
versionnée) — le dashboard que Nolhan cherche intuitivement ("Ventes
FMA") n'est pas celui qui contient le contenu utile ; celui-ci est rangé
sous "Ventes FMA (2025)". Contrairement à F2M où le nommage est cohérent
(rapport détaillé = nom simple "Ventes F2M"), côté FMA le nom simple
pointe vers un dashboard générique et le rapport détaillé est sous un nom
au suffixe année. **Action proposée** : renommer/réorganiser les
dashboards Spreadsheet directement en production (renommer "Ventes FMA"
actuel en autre chose, ou faire de "Ventes FMA (2025)" le dashboard
"Ventes FMA" par défaut) — action fonctionnelle pure, aucun correctif de
code requis dans ce dépôt.

### 5. Projet non auto-rempli en fabrication, onglet "Divers" (ELOGAU)

**Constat initial** : le champ existant (`x_studio_mtn_mrp_sale_order`,
pointe vers le devis, pas un projet) n'apparaît dans aucune vue.

**Retour Nolhan, ambigu** : "Bon sur les commandes anciennes commandes le
Projet ce renseigne bien" — fait référence aux **commandes** (d'achat ?),
pas clairement à l'onglet Divers de l'OF. Possible confusion entre deux
sujets différents (le "Projet" sur les commandes d'achat, cf. point #7 ;
et le champ devis sur l'OF, sujet initial d'ELOGAU).

**Décision (réunion du 20/07)** : confirmé bon par le métier — "c'était
bon". Aucune action requise, point fermé.

### 6. Répartition analytique qui ne se propage pas (ELOGAU) — CORRIGÉ

Bug confirmé (`fma_custom/models/purchase_order.py:38-51`) : la méthode
écrasait les lignes de la commande d'achat depuis le devis à *chaque
sauvegarde*, sans jamais lire une saisie manuelle sur la commande
elle-même. Remonté à nouveau en retour de test T-12 (« NOK, pas de
répartition analytique sur les commandes »).

**Correctif appliqué sans attendre l'arbitrage métier initialement
demandé** (quelle source doit primer) : même règle par défaut que pour
"Projet du SO" — ne jamais écraser une ligne qui a déjà une répartition
analytique (saisie manuelle ou propagation précédente), ne renseigner que
les lignes encore vides (`fma_custom` → 19.0.1.0.5). Si le métier veut
une règle de priorité différente (ex. le devis prime toujours), le
tranchera ultérieurement — pas de perte de données possible avec cette
règle par défaut, elle est donc sans risque en attendant.

### 7. Champs manquants sur les lignes de commande d'achat (ELOGAU)

**Confirmé par Nolhan** : "Projet du SO" et "Is XML Created" doivent bien
être en en-tête (pas dupliqués par ligne) — simplifie le correctif prévu.

**Nouveau problème signalé** : sur la commande testée par Nolhan,
"Projet du SO" est **vide** et "Is XML Created" **n'apparaît pas du tout**
(alors que le champ existe en en-tête, `purchase_order_export/models/purchase_order.py:24`).
Cause possible : la commande testée n'a pas de devis source (donc rien à
propager pour "Projet du SO" — comportement normal dans ce cas précis), ou
le champ "Is XML Created" n'est simplement pas présent sur la vue
formulaire consultée. **Point positif noté par Nolhan** : la répartition
analytique, elle, apparaît désormais correctement.

**Action** : vérifier (a) si la commande testée a bien un devis source
attaché (sinon "Projet du SO" vide est normal), (b) ajouter "Is XML
Created" à la vue formulaire de la commande d'achat s'il n'y est pas.

### 8. Champs vitrage manquants (ELOGAU)

hauteur/largeur sécurisés en Python (fait). Reste : exposition en vue de
remise/commentaire livraison/dimensions, décision sur "Contrat cadre",
et règle de propagation analytique — **toujours en attente d'arbitrage
métier** (question posée, pas de retour spécifique de Nolhan sur ce point
au-delà du #7).

### 9. Mode de règlement non auto-rempli (VALLEM)

**Précisé par Nolhan** : "Quand on sélectionne le client dans une affaire
ça doit récupérer le champ 'Condition de paiement' présent dans la fiche
client." Deux points à clarifier avant de coder :
- "Condition de paiement" est le nom du champ **standard** Odoo
  (`payment_term_id`), distinct des 4 champs "mode de règlement" custom
  déjà identifiés — probablement plus simple à traiter que prévu.
- "une affaire" désigne-t-il le modèle `x_affaire` (qui n'a aujourd'hui
  **aucun** champ de ce type) ou le devis/la commande (`sale.order`, où le
  champ standard existe déjà et se propage normalement via le mécanisme
  natif d'Odoo) ? Cette distinction change complètement l'ampleur du
  correctif (champ à créer sur `x_affaire` vs vérification d'un
  comportement qui existe peut-être déjà nativement sur le devis).

**Action** : redemander confirmation sur l'écran exact avant de développer.

### 10. Commercial non auto-affecté (VALLEM) — probablement fermé

Nolhan + retest avec Valentin Lemonnier confirment que l'auto-remplissage
du commercial **fonctionne** en pratique. Vérification code : l'onchange
custom (`custom/models/sale_order.py:69-71`) appelle correctement `super()`,
donc ne bloque pas le mécanisme standard d'Odoo. **Conclusion probable** :
faux positif du test initial (client testé sans commercial configuré sur
sa fiche). À confirmer avec VALLEM sur quel client précis le problème avait
été observé, sinon considérer comme fermé.

### 11. Séquence d'opération invisible (ELOGAU) — CORRIGÉ

Confirmé par Nolhan : en production, la colonne reste **toujours visible**
et triée chronologiquement. Corrigé dans `mrp_capacity_planning` (voir
tableau des corrections ci-dessus) : la poignée de tri reste en brouillon
uniquement, la valeur s'affiche en lecture seule ensuite.

### 12. Champ "Dates effective" manquant (ELOGAU)

**Précisé par Nolhan** : "dates effectives c'est la date à laquelle la
livraison est totalement faite." Reste à trancher : ce champ doit-il être
**calculé automatiquement** (ex. depuis la dernière réception/livraison
liée à l'affaire) ou **saisi manuellement** par un utilisateur ? Cette
décision change l'ampleur du développement (champ simple vs calcul lié aux
`stock.picking`).

### 13. Workflow BE / Chef de projet (VALLEM) — FERMÉ

Nolhan confirme explicitement : "JE CLOS CETTE LIGNE, c'est ok en V19 le
fait que le chef de projet ne se remplisse pas tant que le projet n'est
pas validé." Aucune action requise.

### 14. "Projet" vs "compte analytique" (VALLEM) — nouveau champ à ajouter

**Précisé par Nolhan** : "En production sur l'affaire, le champ 'Projet'
s'appelle 'Compte analytique'." Vérifié dans le code : `x_affaire`
(`fma_studio_models/models/x_affaire.py`) n'a **aucun champ analytique**
actuellement (18 champs déclarés : dates, contact, étape, responsable,
valeur, notes... rien sur un compte analytique ou un "projet"). Ce n'est
donc pas un problème d'étiquette à corriger, mais un **champ réellement
absent** du modèle porté.

**Décision (réunion du 20/07, David)** : **point mis en pause**, à ne pas
traiter isolément — à terme les champs "Projet" / "Compte analytique" /
"Projet MTN" vont être fusionnés et le nom "Projet MTN" va probablement
changer. Pas de développement tant que cette fusion n'est pas cadrée.

### 15. Contact — nouvelle demande produit

Le point initial "préférence pour l'ancien module" devient une vraie
demande : **"Les métiers aimeraient pouvoir voir d'un seul coup d'œil s'il
s'agit d'un client / d'une adresse chantier / ou d'un contact. Voir si
c'est possible de le spécifier directement dans la vue Kanban."**

**Analyse technique préalable** : aucune personnalisation FMA ne touche
la vue kanban des contacts aujourd'hui (vérifié). Pour implémenter un
badge visuel, il faut d'abord identifier **comment "adresse chantier" est
distinguée dans les données** (champ `type` standard de res.partner :
`contact`/`invoice`/`delivery`/`other` ? Un champ custom dédié ? Un des
7 champs "Affaire" candidats déjà recensés sur `stock.picking` dans
STUDIO_AUDIT.md ?). Sans cette clarification, impossible de coder le
badge de façon fiable.

**Décision (réunion du 20/07)** : confirmé comme un changement d'ergonomie
du standard Odoo 19, sans rapport avec la migration. **Amélioration à
chiffrer plus tard, non bloquante pour le démarrage** — pas de
développement dans le cadre de ce chantier de correction.

---

## Détail par point — nouveau lot EMIDAV (16-17/07/2026)

### 16. Congé d'1 jour — capacité affichée réellement fausse — CORRIGÉ

**Confirmé en réunion du 20/07** : ce n'est pas qu'un problème visuel, le
nombre d'heures affiché est réellement faux. Investigation live confirmée
sur un cas concret : congé Jessica PETIT du 19/06/2026 (~5h10,
"Compensatory Days") — calcul rejoué manuellement = **5.0h** (correct),
valeur **stockée** en base = **0.0h** (fausse).

**Cause racine confirmée** : `mrp.capacity.week._compute_absences()` est un
champ calculé stocké dont le `@api.depends` ne peut pas référencer les
congés (`hr.leave`) directement — limite structurelle d'Odoo (un champ
calculé ne peut dépendre que de champs, pas du résultat d'une recherche
`search()`). Un cron quotidien (`cron_recompute_absences`) compensait
partiellement, mais avec un filtre `week_date >= aujourd'hui` : toute
semaine déjà passée au moment de la saisie du congé n'était **plus jamais
recalculée**, et même les semaines courantes/futures avaient jusqu'à 24h
de retard avant mise à jour.

**Corrigé** (`mrp_capacity_planning` → 19.0.1.0.7) :
- Nouveau fichier `models/hr_leave.py` : `create`/`write`/`unlink` sur
  `hr.leave` déclenchent désormais **immédiatement** le recalcul des
  `mrp.capacity.week` concernées (au lieu d'attendre le cron du lendemain).
- Cron élargi pour couvrir aussi les 30 derniers jours (`week_date >=
  aujourd'hui - 30 jours` au lieu de `>= aujourd'hui` strictement), en
  filet de sécurité complémentaire.

### 17. Champ "niveau de complexité" sur l'OF — prêt à corriger

**Constat** : `x_studio_niveau_de_complexite` (`custom/models/mrp_production.py:16`,
type `Text`) est déjà déclaré en Python et sécurisé (aucun risque de perte
de données), mais **absent de toute vue**. Exactement le même schéma que
Gamme/Série (#2) : champ porté, jamais exposé à l'écran.

**Correctif** : ajouter le champ à la vue formulaire de `mrp.production` —
petit effort, aucune ambiguïté, peut être fait immédiatement.

### 18. PO liés à la commande plus accessibles via l'OF

**Constat** : deux commits récents (13/07/2026, `4f769eb` et `e52cf65`)
corrigent déjà la recherche des PO liés, **mais uniquement dans le popup
de replanification** (`mrp_capacity_planning`, méthode
`_build_replan_preview_payload`). Aucune trace d'un bouton statistique
"Achats" équivalent sur la fiche standard de l'OF en dehors de ce popup.

**Action** : clarifier avec Emilien s'il parle bien du popup de
replanification (dans ce cas probablement déjà réglé, à confirmer) ou
d'un autre endroit de la fiche OF où il s'attendait à voir les PO liés
(ex. un smart-button "Achats" en haut du formulaire, qui n'existe pas
dans ce repo).

### 19. Pas d'accès à "Capacité par poste"

**Constat** : les droits (`ir.model.access.csv`) sur `x_capacite_par_poste`
sont corrects pour "Utilisateur interne" (lecture/écriture/création), sans
restriction de groupe sur le menu. Rien dans le module ne bloque un profil
fabrication standard.

**Action** : même traitement que #1/#4 — vérifier directement via
impersonation sur le compte d'Emilien Davoine plutôt que de continuer à
déduire depuis les droits (l'expérience MATANG/Nolhan montre que cette
déduction peut être trompeuse).

### 20. Heures prévues non modifiables en ligne dans l'OT

**Constat** : aucune surcharge trouvée qui rendrait `duration_expected`
readonly dans l'onglet Ordres de travail — la vue standard v19 le permet
nativement (readonly seulement si `state in ['cancel', 'done']`). Le seul
changement apporté par FMA dans ce fichier concerne le champ `sequence`
(point #11), pas les heures.

**Action** : reproduire précisément le cas (quel OF, quel état) pour
identifier la cause réelle — rien dans le code ne l'explique.

### 21. Capacité par poste : division par ressources non fonctionnelle

**Constat** : confirmé que `x_studio_nbre_ressources` sert uniquement à
raccourcir la durée du planning macro (`_get_effective_duration_hours`),
sans jamais créer de réservation multi-ressources réelle
(`mrp.capacity.resource`). Le comportement "une seule ressource utilisée"
est donc cohérent avec la conception actuelle du module — **et le
problème existe aussi en v17**, donc ce n'est pas une régression de la
migration mais une limite structurelle pré-existante.

**Décision réunion du 20/07** : "Non lié à la migration v19 (même
comportement en v17), mais correctif ponctuel possible." Un souci concret
associé a été identifié et **corrigé** : les champs "Durée mini/maxi"
(`x_studio_dure_min`/`x_studio_dure_max`, `x_capacite_par_poste`) étaient
de type **Entier**, donc un seuil comme "80,1h" était tronqué à 80,
faussant le comparateur `>80h` de `_get_effective_duration_hours`. Passés
en type **Décimal** (`fma_studio_models` → 19.0.1.0.13), aucune migration
de données nécessaire (conversion entier → décimal sans perte).

**Point restant, à surveiller (pas de correctif immédiat)** : "après
réplanification, le nombre de jours planifiés ne se recalcule pas
toujours correctement" quand les heures augmentent — cas intermittent
signalé en réunion, responsable JBS, à creuser séparément si le problème
se reproduit avec un exemple précis (quel OF, quelle réplanification).

### 22. Filtres personnalisés / modèles d'export Excel à conserver

**Constat** : `ir.filters` et `ir.exports` sont des enregistrements créés
par les utilisateurs directement en base (pas de fichiers de données
versionnés dans le code) — hors périmètre du portage Studio→code.

**Action** : à vérifier/sauvegarder directement en base (staging → prod),
pas un sujet de développement.

### 23. Accès au mouvement transfert via code-barres impossible

**Constat** : aucune trace de `stock_barcode` dans tout le repo (ni
dépendance, ni surcharge). Si ce module Enterprise est installé
indépendamment, le blocage ne vient d'aucune personnalisation FMA.

**Action** : vérifier si le module `stock_barcode` est bien installé sur
l'instance et si un droit/licence spécifique est en cause — hors code FMA.

### 24. Facture brouillon sur réception

**Constat** : le bouton "Création Facture Fournisseur en masse"
(`fma_custom/models/stock_picking.py::action_create_supplier_invoices`)
délègue à la méthode standard Odoo `purchase.order.action_create_invoice()`,
qui crée **systématiquement** la facture en brouillon (jamais d'auto-post).
C'est un portage fidèle du comportement Studio d'origine, documenté dans
TEST_PLAN.md §12 — pas une régression.

**Action** : clarifier avec Emilien s'il attendait une validation
automatique de la facture (auto-post) — cette attente n'a jamais existé
ni côté Studio ni côté code, ce serait donc une nouvelle demande, pas un
bug.

### 25. Atelier : composants manquants sous étiquette "Affaire" (T-24) — CLOS, PAS UN BUG

**Écran identifié le 24/07/2026** grâce à une capture d'écran fournie
par le métier : il s'agit du **Shop Floor** d'Odoo Manufacturing
(module Enterprise `mrp_workorder`), vue tablette par poste de travail
("Débit FMA", "Usinage FMA"...), quasiment pas personnalisée côté FMA
(seul `fma_shopfloor_active_css` y touche, uniquement du CSS de
surlignage des cartes actives — aucun template QWeb ni composant Owl
hérité).

**Analyse des deux éléments signalés** :
- La ligne `[A26-02-00872] FOURNEL` sous chaque carte **n'est pas un
  champ "Affaire"** : c'est l'affichage standard Odoo du produit fini
  de l'OF (`product.product._compute_display_name`, mécanisme core
  `[default_code] name`). "FOURNEL" est le **nom du produit fabriqué**
  (convention FMA de nommer le produit d'après le client), pas une
  fonctionnalité Affaire — aucun champ `x_affaire` n'est référencé dans
  ce chemin de code (`mrp.workorder`/`mrp.production`/`product.product`
  ne pointent jamais vers `x_affaire` dans ce repo).
- Le texte barré + fraction type `64/64.8 ML` est aussi 100% standard :
  il indique un composant **déjà marqué consommé** (`picked`) avec sa
  quantité réservée/à consommer, pas une pénurie. Le bouton bascule
  consommé/non-consommé, d'où l'icône qui ressemble à un "undo".

**Conclusion** : sans rapport avec le bug `_rec_name` déjà corrigé sur
les modèles Studio (`fma_studio_models`) — ce chemin de code ne les
traverse jamais. Le testeur confondait probablement le nom du produit
fini avec une étiquette "Affaire". **Aucun correctif de code
nécessaire.**

**Si le métier souhaite malgré tout une vraie identification
client/affaire sur les cartes Shop Floor** (ex. afficher explicitement
`production_id.sale_id`/l'Affaire liée plutôt que compter sur le nom du
produit) : ce serait une **nouvelle demande d'évolution**, nécessitant
un héritage QWeb + JS Owl du template `mrp_workorder.MrpDisplayRecord`
(actuellement inexistant dans ce repo) — à chiffrer séparément, pas un
bug à corriger.

---

## Nouvelles anomalies non attribuées (17/07/2026, probablement ELOGAU — à confirmer)

8 points remontés en fin de fichier CSV sans testeur/date renseignés,
thématique achats/vitrage cohérente avec ELOGAU. **Attribution à
confirmer avant de les intégrer formellement au suivi.**

### 27. Pas d'onglet vitrage (pas de visu largeur/hauteur)

Rejoint directement #13 : confirme que même si `x_studio_hauteur`/
`x_studio_largeur` sont maintenant sécurisés en Python, l'absence d'un
**onglet dédié vitrage** (pas juste des champs épars) semble être ce qui
est réellement attendu. Précise la question ouverte sur l'emplacement
(#8/#13) : la réponse est probablement "un onglet dédié", pas juste
quelques champs ajoutés au formulaire général.

### 28. Délais de réception de bon de commande mal estimés

**Bug de code réel localisé, mais correctif impossible sans info
externe.** Aucune surcharge FMA du calcul standard de `date_planned` sur
`purchase.order` n'existe — le calcul reste 100% standard Odoo. En
revanche, `sqlite_connector/models/sqlite_connector.py:516` initialise
`delai = 0` avant une boucle d'import ("AllArticles") et **ne le réaffecte
jamais** à l'intérieur de cette boucle avant de l'utiliser pour créer les
`product.supplierinfo` (ligne 675, `'delay': delai`). Résultat : tout
fournisseur importé via ce flux précis se retrouve avec un délai figé à
**0 jour**, ce qui sous-estimerait mécaniquement `date_planned` sur les PO
utilisant ces produits.

**Pourquoi je n'ai pas corrigé directement** : la requête SQL de ce flux
(`select ... from AllArticles`) ne remonte **aucune colonne de délai** —
il n'y a donc rien de correct à réaffecter à `delai` avec les informations
disponibles dans ce fichier. Un autre flux du même fichier ("Glass",
ligne 965) gère ça différemment avec une règle métier (14 ou 21 jours
selon le type), et un troisième (ligne 1110) lit `delai = ligne[9]` depuis
une autre source. Il faut soit le schéma de la base SQLite source (quelle
colonne d'`AllArticles` contient le délai fournisseur réel ?), soit une
règle métier de valeur par défaut à appliquer faute de mieux.

**Action** : fournir le schéma source ou la règle métier attendue avant
de corriger — sinon risque d'introduire une valeur inventée.

---

## Session du 22-23/07/2026 — nouveaux tickets T-36 à T-41

Nouvelle vague de retours métier (Clément Rolland, CLEGIS, Adrien Mathie,
Stéphanie Aubain). Numérotation `T-XX` reprise telle quelle du tableau de
suivi transmis (distincte des deux numérotations précédentes de ce
document — sections "Détail par point" #1-34 et tableau officiel du
20/07 #1-29).

### T-36 — Éco-contribution à 0,14 au lieu de 0,3 sur l'intégration d'affaire — CORRIGÉ

Confirmé par Clément Rolland et David : Logikal et la fiche article Odoo
affichent bien 0,14, mais l'intégration d'une affaire écrasait cette
valeur à 0,3. **Déjà corrigé** (commit `e34f850`,
`sqlite_connector/models/sqlite_connector.py:1244`) : `price = 0.03` →
`price = 0.14` sur la branche de calcul `ECO-CONTRIBUTION`. Problème
présent aussi en prod avant correctif, corrigé dans les deux
environnements. **Fait**, à valider par le métier.

### T-37 — Description absente sur les lignes d'articles (commande d'achat vitrage) — clarification requise

Vérifié : aucun champ n'est masqué ni vidé côté FMA
(`custom/views/purchase_order_views.xml`, `custom/models/purchase_order.py`
— aucune écriture sur le champ standard `name`). En Odoo 19 standard, le
widget de ligne de commande d'achat (`product_label_section_and_note_field_o2m`)
**fusionne** la description (`name`) dans la cellule produit (texte en
italique sous le nom) dès que les deux champs sont présents — elle
n'apparaît donc que si le produit a une `description_purchase`
renseignée sur sa fiche. Rejoint la demande déjà notée aux points #13/#27
("onglet vitrage dédié" plutôt que champs épars), jamais tranchée.

**Deux hypothèses à distinguer avec CLEGIS/ELOGAU (capture d'écran
utile)** :
1. La description est vide car non renseignée sur la fiche produit
   Remplissage → donnée à corriger en base, pas un bug de code.
2. Le métier attend une colonne "Description" séparée, toujours visible
   (pas fusionnée sous le nom produit) → nécessite une vraie
   modification de vue, à chiffrer une fois confirmé.

**Action** : redemander confirmation avant de coder quoi que ce soit.

### T-38 — Export facture fournisseur : erreur RPC bloquante — CORRIGÉ

**Bug de code confirmé et corrigé.** Cause exacte : un bloc de logging
de debug non nettoyé dans
`fma_invoice_supplier_export/models/account_move.py:47`,
`action_create_supplier_journal_items_file()`, appelait
`self.mapped("is_file_txt_created")` — un typo sur le champ réellement
déclaré (`is_txt_created`, ligne 20 du même fichier).
`is_file_txt_created` n'existe nulle part dans le modèle
`account.move`, d'où le `KeyError` systématique dès qu'on cliquait sur
l'action, exactement reproduit par le traceback fourni par Adrien
Mathie (`BILL/2026/06/0012`).

**Corrigé** (`fma_invoice_supplier_export` → 19.0.1.0.2) : suppression du
bloc de logging de debug fautif. Aucun impact fonctionnel — ces deux
lignes ne faisaient que journaliser avant de planter, la logique métier
qui suit (génération et attachement du CSV) était saine et n'a pas été
touchée.

**Point annexe non bloquant, laissé en l'état** : le même fichier
contient encore une quinzaine de `_logger.warning`/`_logger.info` de
debug dans `_get_file_supplier_content` (lignes ~98-211) — bruyants
dans les logs mais sans risque de plantage, à nettoyer dans un second
temps si souhaité, hors urgence de ce ticket.

### T-39/T-40/T-41 — Module Assistance (Stéphanie Aubain) — pas de code FMA en cause

Vérification faite : **aucun module `fma_helpdesk`** n'existe dans ce
dépôt. Le module Assistance repose entièrement sur `helpdesk`
(Enterprise standard), dépendance ajoutée dans `custom/__manifest__.py`.
Seule trace FMA sur `helpdesk.ticket` : 2 champs Studio portés
(`custom/models/misc_studio_fields.py:10-14`,
`x_studio_datetime_field_4k_1j9c640h6` et `x_studio_intervention`) —
rien d'autre, ni vue, ni sécurité (`ir.model.access.csv`/`ir.rule`)
spécifique FMA sur ce modèle dans tout le repo.

**Conséquence directe : les 3 points suivants sont des vérifications de
configuration en base/production, pas des correctifs de code.**

- **T-39 — Carte "Équipe SAV" ouvre la création au lieu de la liste** :
  le comportement de clic sur la carte kanban `helpdesk.team` est
  entièrement porté par le module Enterprise standard. Deux pistes à
  vérifier directement en base/prod : (a) une vue kanban `helpdesk.team`
  modifiée via Studio directement en base, jamais exportée dans un
  module (déjà rencontré pour d'autres écrans, cf. `STUDIO_AUDIT.md`) ;
  (b) le kanban standard peut rediriger vers le formulaire de création
  quand le compteur de tickets ouverts de l'équipe est à 0 — donc
  potentiellement pas un bug mais un effet de bord du volume réel de
  tickets ouverts de l'équipe SAV.
- **T-40 — Champ "Type" absent sur le ticket** : `ticket_type_id`
  (Enterprise) est un champ standard dont l'affichage se pilote par un
  réglage par équipe (Assistance > Configuration > Équipes > case
  "Type de ticket"). Jamais masqué par une vue FMA. **Action** :
  vérifier ce réglage sur l'équipe de Stéphanie Aubain.
- **T-41 — Erreur d'accès (note/activité/pièce jointe)** : aucune ACL
  FMA en cause. À vérifier en base/prod : (a) appartenance de Stéphanie
  Aubain à un groupe Helpdesk (Réglages > Utilisateurs) ; (b) réglage
  `privacy_visibility` de l'équipe concernée — si limité aux
  "tickets suivis uniquement" et qu'elle n'est ni membre ni follower du
  ticket, l'ACL de `mail.message`/`ir.attachment` (qui suit celle du
  ticket parent) peut bloquer l'ajout de notes/activités/pièces
  jointes ; (c) présence dans `member_ids` de l'équipe SAV.

---

## Résumé — corrections encore ouvertes après retour métier du 24/07/2026

**Mise à jour 24/07/2026** : le métier a fait ses retours sur le compte
rendu du 24/07. Six tickets auparavant listés comme ouverts sont
**validés / clos** et retirés du suivi actif :

- **T-02 — Commercial auto-affecté** : validé par le métier.
- **T-03 — Mode de règlement / condition de paiement** : validé par le
  métier.
- **T-27 — Analytique par ligne non renseigné à l'export** : clos côté
  métier (sujet traité séparément par David, plus dans ce suivi).
- **T-32 — Valeurs affichées en dictionnaire de traduction brut** :
  validé par le métier.
- **T-34 — Numéros de commandes non générés (séquence `purchase.order`)** :
  validé par le métier (vérification en production confirmée faite).
- **T-35 — Export Comalu, lignes `default_code='affaire'` exclues** :
  arbitrage tranché par le métier, clos.

**Reste actif — 22 tickets**, consolidés ci-dessous par nature d'action
plutôt que par ordre chronologique : T-05, T-08, T-11, T-12, T-13, T-14,
T-17, T-22, T-23, T-25, T-26, T-28, T-29, T-30, T-31, T-33, T-36, T-37,
T-38, T-39, T-40, T-41.

### 🔴 P0 — Bloquant, action immédiate
- **T-12 / #7-#29 — "Projet du SO"** : correctif déployé (`476c639`) ;
  **rattrapage des commandes existantes à rejouer en production** (93
  commandes corrigées en local, même script à exécuter côté prod).
- **T-12 / #6 — Répartition analytique écrasée sur les commandes
  d'achat** : retour NOK distinct reçu sur le même ticket (bug séparé de
  "Projet du SO" ci-dessus, voir détail #6) ; correctif déployé
  (`fma_custom` → 19.0.1.0.5), à retester. Aucun rattrapage possible sur
  les données déjà écrasées (perdues), seules les prochaines sauvegardes
  sont protégées.
- **T-30 — `fma_custom/models` jamais chargé** : correctif déployé
  (`476c639`) ; vérifier après déploiement prod que les actions "Fichier
  clients Iziqo" et "Création Facture Fournisseur en masse" fonctionnent
  réellement en conditions réelles (lié à T-23).

### 🟠 Décisions d'arbitrage métier (bloquent un correctif à moitié fait)
- **T-05 / #5-#14 — "Projet" vs "Compte analytique" sur l'Affaire** :
  suspendu tant que la fusion Projet/Compte analytique/Projet MTN n'est
  pas cadrée (David).
- **T-37 — Description absente lignes vitrage** : donnée produit
  manquante ou vraie demande de colonne dédiée ? (capture d'écran utile)
- **T-33 / #28 — Délai fournisseur figé à 0** (`sqlite_connector.py:516`) :
  besoin du schéma source `AllArticles` ou d'une règle métier par défaut.
- **T-22 — Code-barres, ajout Numéro de BL** : confirmation du champ
  backend cible avant surcharge JS de `stock_barcode`.

### 🟡 Vérifications en base/production (pas de code)
- **T-08 — Dashboard "Ventes FMA"** : renommer/réorganiser les
  dashboards Spreadsheet (le rapport détaillé est sous "Ventes FMA
  (2025)").
- **T-25 — CLEGIS, champ Référence** : lien de la commande concernée
  toujours pas transmis.
- **T-28 / #33 — 2 onglets livraison LRE-Préfabrication** : capture
  d'écran nécessaire, aucune duplication trouvée en base ni en code.
- **T-40 — Champ "Type" absent sur ticket Assistance** : activer le
  réglage "Type de ticket" sur l'équipe concernée.
- **T-39 — Carte "Équipe SAV"** : vérifier vue kanban Studio en base et
  volume réel de tickets ouverts.
- **T-41 — Accès Stéphanie Aubain** : vérifier groupe Helpdesk et
  visibilité d'équipe (`privacy_visibility`/`member_ids`).

### 🟢 Bugs confirmés restant à traiter (responsable externe à JBS)
- **T-17 — PO liés à l'OF pas accessibles hors popup replanification**
  (David, avec Jean).
- **T-23 — Facture brouillon sur réception (Création Facture Fournisseur
  en masse)** (David) — à retester maintenant que `fma_custom/models`
  est chargé (T-30), pour clarifier s'il s'agit d'une vraie demande.
- **T-29 — Renvoi manuel XML SFTP bloqué** (David).

### ✅ Corrigé, en attente de validation métier
- **T-11 — Onglet Divers, Projet pas auto** : à retester spécifiquement
  sur affaires/commandes créées après la migration.
- **T-13 / T-26 — Champs vitrage + remise fournisseur** : champs
  conditionnés à la catégorie Remplissage, Contrat cadre masqué, remise
  exposée. Bug d'écrasement de la répartition analytique corrigé (voir
  T-12/#6) ; la logique de reprise automatique depuis "Projet du SO" que
  David développe séparément reste, elle, en standby.
- **T-31 — `_rec_name` sur les 20 modèles Studio** : listes déroulantes
  affichent désormais le nom lisible au lieu du format technique.
- **T-36 — Éco-contribution 0,14** : corrigé (`e34f850`).
- **T-38 — Export facture fournisseur, KeyError bloquant** : corrigé
  (`fma_invoice_supplier_export` → 19.0.1.0.2), typo de debug supprimé.

### ⏳ En attente de confirmation testeur (probablement déjà bons)
- **T-14 — Droit création Affaire (Mathieu Angibault)** : confirmation
  finale avec son propre mot de passe + suppression `x_affaire` id=4093
  (déjà absent du backup, rien à faire).

### 29. Projet du SO non renseigné dans les commandes

Rejoint directement #7 (retour Nolhan : "Projet du SO" vide sur son test).
Le fait que ce soit remonté une seconde fois, indépendamment, suggère que
ce n'est **pas un cas isolé** (commande sans devis source) mais un
problème plus systématique. Reste la même question qu'au #7 : les
commandes concernées ont-elles bien un devis d'origine renseigné ?

### 30. Numéros de commandes non générés

**Aucun bug de code trouvé.** Deux mécanismes distincts vérifiés :
- La séquence standard Odoo pour `purchase.order.name` : aucune
  redéfinition dans ce repo, reste le séquenceur standard du module
  `purchase` — la cause, si réelle, serait une question de **configuration
  en base** (`ir.sequence`, ex. `number_next` épuisé ou mal paramétré), pas
  de code.
- `x_studio_rfrence` (référence custom générée par
  `fma_custom/models/purchase_order.py::_compute_studio_reference`) :
  logique saine, sans risque d'échec silencieux identifié (pas de
  division, pas de try/except qui avalerait une erreur).

**Action** : vérifier en direct sur staging (Réglages > Technique >
Séquences) l'état de la séquence `purchase.order`, plutôt qu'un correctif
de code.

### 31. Remises Fournisseur n'apparaît pas

Rejoint #13 : `x_studio_remise`/`x_studio_remise_1` existent déjà en code
mais ne sont affichés dans aucune vue — confirmation supplémentaire du
même point déjà identifié.

### 32. Analytique par ligne non renseigné

Rejoint #7/#13 : le compte analytique par ligne (`analytic_distribution`,
champ standard Odoo) n'est effectivement rendu visible nulle part dans les
personnalisations FMA sur `purchase.order.line` — cohérent avec ce qui
était déjà noté.

### 33. 2 onglets livraison dont "LRE-Préfabrication"

**Aucune duplication d'onglet trouvée dans le code.** Recherche exhaustive
des onglets ajoutés sur `purchase.order`/`mrp.production`/`stock.picking`
par tous les modules FMA (`fma_laquage_subcontracting`, `purchase_order_export`,
`custom_delivery`, `custom`) : aucun onglet nommé "Livraison"/"Delivery"/
"LRE-Préfabrication" n'existe. "LRE" apparaît uniquement comme **nom
d'emplacement de stock en base** (ex. `LRE/Pré-fabrication`, cf.
`stock_picking_report_multi_loc` et `sqlite_connector`), pas comme onglet
de vue. Point notable : `custom_delivery/views/delivery_change.xml` et
`delivery.xml` sont deux templates de **rapport PDF** de bon de livraison
quasiment identiques (doublon fonctionnel entre deux templates, mais pas
un onglet de formulaire).

**Hypothèse la plus probable** : un onglet Studio existant en base mais
jamais versionné dans ce repo (comme d'autres cas déjà rencontrés dans ce
portage) — à vérifier directement sur le document concerné en staging.

### 34. Export PO Comalu : lignes XML manquantes

**Piste technique solide.** Le format d'export "Comalu" correspond au
type `xml` (`purchase_order_export/data/purchase_order_export.xml`,
template `purchase_order_sftp_export_template`). Ce template applique un
filtre explicite sur les lignes de la commande :

```xml
&lt;t t-set="filtered_lines" t-value="po.order_line.filtered(lambda line: line.product_id.default_code != 'affaire')"/&gt;
```

Toute ligne dont le produit a pour référence interne (`default_code`)
exactement `"affaire"` est **exclue silencieusement** du XML généré (même
filtre présent à l'identique dans le template TIV). Si une commande Comalu
contient des lignes utilisant un produit générique/placeholder avec cette
référence, elles disparaîtront du fichier sans erreur ni log.

**Action** : vérifier sur la commande Comalu concernée si les lignes
manquantes correspondent bien à des produits avec `default_code =
"affaire"`. Si oui, décider avec le métier si ce filtre est toujours
pertinent (il exclut peut-être délibérément des lignes internes de type
"ligne d'affaire" qui ne devraient jamais partir chez un fournisseur) ou
s'il faut l'ajuster.

---

## Session du 21/07/2026 — reprise de tous les points non résolus

Avec l'environnement local restauré (backup pré-prod du jour même) et un
accès direct en base + navigateur, reprise systématique de chaque point
encore ouvert pour tenter d'y apporter une réponse concrète plutôt
qu'une hypothèse.

### #2 — domaine Gamme→Série : déjà corrigé, plan pas à jour

Vérifié dans le code : le domaine `[('x_studio_gamme_de_la_srie', '=',
x_studio_gamme)]` est déjà présent sur `x_studio_srie`
(`fma_sale_order_custom/views/sale_order_views.xml`, commit `c4c77e9`,
antérieur à cette session). Le commentaire du fichier confirme une
validation métier du 17/07. **Rien à faire, juste une mise à jour de ce
document.**

### #7 / #29 — "Projet du SO" jamais propagé — CORRIGÉ

Confirmé en base sur données réelles (pas une hypothèse) : sur 169
commandes d'achat liées à un devis ayant lui-même un projet renseigné,
**81 (48%)** avaient "Projet du SO" vide sur la commande. Cause : ce
champ n'était écrit **nulle part** — ni par le code porté, ni par les
automatisations Studio actives (qui le *lisent* pour calculer référence
et responsable, mais ne l'*écrivent* jamais).

**Corrigé** (`custom` → 19.0.1.0.18, `custom/models/purchase_order.py`) :
propagation automatique à la création/écriture de la commande, depuis
`sale_order.x_studio_projet`, uniquement si le champ est encore vide (ne
touche jamais une saisie manuelle existante). Testé en direct sur un cas
réel (`P27214`) : propagation confirmée après un simple `write()`.
Rattrapage ponctuel exécuté sur la base de test locale : 93 commandes
existantes corrigées. **Un rattrapage identique sera à rejouer en
production après déploiement du correctif.**

### #18 — smart-button "Achats" sur l'OF : existe déjà nativement

Le bouton statistique existe bel et bien, mais côté **Odoo standard**
(module `purchase_mrp`, action `action_view_purchase_orders`, installé) —
l'investigation précédente n'avait cherché que dans les modules FMA. Pas
de correctif nécessaire. Seule limite connue : comme le filet de
sécurité déjà codé dans le popup de replanification, ce bouton ne
remonte pas les PO créés manuellement hors chaîne d'approvisionnement.

### #19 — accès "Capacité par poste" (Emilien) — hypothèse cache confirmée

Test direct avec le vrai compte d'Emilien Davoine (mot de passe
temporaire) dans un navigateur **entièrement neuf** (aucun cache, aucun
cookie — le scénario le plus extrême possible) : l'écran se charge
parfaitement, 9 postes affichés, aucune `OwlError`, aucune erreur
console. **Confirme définitivement l'hypothèse de cache navigateur
obsolète** — ce n'est pas un bug de code ni de droits.

### #20 — heures OT non modifiables en ligne — toujours sans explication

Testé en direct (pas juste lu le code) sur un OT réel en état "Prêt" :
écriture ORM de `duration_expected` réussie sans blocage, vue résolue
pour le compte réel d'Emilien confirmée non-readonly dans cet état.
Confirme le diagnostic du plan mais ne le résout pas — **reste
nécessaire un OF + état précis pour reproduire**, rien dans les données
ou le code ne bloque ce champ dans le cas général.

### #25 — Atelier, composants manquants — non localisé mais piste probable

Toujours pas d'écran identifié précisément (le wizard
`mrp_add_component_need_wizard` sert à *ajouter* un besoin, pas à en
lister les manquants). Mais le symptôme décrit ("étiquette Affaire peu
lisible") correspond exactement au bug systémique `_rec_name` déjà
corrigé au point #26 — probablement déjà résolu par ce correctif
existant, même sans avoir localisé l'écran exact.

### #30 — séquence purchase.order — CORRIGÉ (donnée)

Vérifié en base : `ir_sequence` pour `purchase.order` avait
`number_next = 1` alors que 27 214 commandes existent déjà (dernière :
`P27214`). Le prochain achat aurait donc été numéroté `P1`. **Corrigé
dans la base de test locale** (`number_next` → 27215). Pas un bug de
code — **la même vérification (Réglages > Technique > Séquences) est à
faire en production**, où le même problème est susceptible d'exister.

### #33 — 2 onglets livraison / LRE-Préfabrication — non confirmé

Vérifié en base : deux versions historiques des vues Studio
`stock.picking` (form/tree) existent, mais une seule est active de
chaque côté — pas de duplication réelle trouvée. Confirme la conclusion
déjà posée dans ce plan plutôt que de la contredire. Toujours besoin
d'une capture d'écran pour trancher.

### #34 — export Comalu, lignes manquantes — mécanisme confirmé sur données réelles

Vérifié en base : plusieurs commandes réelles (ex. `P05545`, 55 lignes)
contiennent effectivement une ligne avec `default_code = 'affaire'`, qui
serait silencieusement exclue du XML généré. Le mécanisme suspecté n'est
donc pas hypothétique — reste la décision métier (filtre volontaire ou
à ajuster) posée dans la section dédiée plus haut.

### Nettoyage — enregistrement test x_affaire id=4093

Déjà absent du backup du jour (vérifié par id et par nom) — nettoyage
déjà fait côté pré-prod avant cette restauration, rien à faire.

### Résumé des fichiers modifiés dans ce dépôt (session du 21/07)

| Fichier | Changement |
|---|---|
| `fma_custom/__init__.py` | Ajout de `from . import models` (bug critique, voir section dédiée en tête de ce document) |
| `fma_custom/__manifest__.py` | Version → 19.0.1.0.4 |
| `custom/models/purchase_order.py` | Propagation automatique de "Projet du SO" (#7/#29) |
| `custom/__manifest__.py` | Version → 19.0.1.0.18 |

---

## Prochaines étapes proposées

1. **Résolu** : #1 (MATANG) confirmé fonctionnel en test direct le 17/07.
2. **Testé en direct le 21/07** : #4 (dashboard Nolhan) — mot de passe
   temporaire + reproduction navigateur sur backup pré-prod du jour même.
   Confirmé : pas un bug de code, problème de nommage des dashboards
   Spreadsheet ("Ventes FMA" = générique, "Ventes FMA (2025)" = rapport
   détaillé recherché). Action restante : renommage/réorganisation
   fonctionnelle en production, hors périmètre de ce dépôt.
3. **Corrigés en code (commits `387315d` et `9910eab`)** : #2 (Gamme/Série
   en vue), #3 (chatter), #8 (hauteur/largeur Python), #11/séquence
   (toujours visible), #17 (complexité OF), #26 (`_rec_name` sur les 20
   modèles Studio — bug systémique découvert en testant #1).
4. **Clarifications à redemander en priorité** (impactent des correctifs
   déjà à moitié faits) : #2 (domaine Gamme→Série), #7/#29 (Projet du SO
   vide/Is XML Created, remonté deux fois), #9 (quel écran pour Condition
   de paiement), #14 (spécification exacte du champ Compte analytique sur
   l'Affaire — capture d'écran demandée, pas encore reçue en image
   exploitable).
5. **Probablement clos, à confirmer simplement** : #10 (commercial auto),
   #13 (déjà fermé par Nolhan).
6. **Pistes techniques trouvées, actions précises identifiées** : #28
   (délai fournisseur figé à 0 dans `sqlite_connector.py` — besoin du
   schéma source ou d'une règle métier avant correctif), #34 (export
   Comalu — vérifier si les lignes manquantes ont `default_code =
   "affaire"`).
7. **Nécessitent une vérification en base plutôt qu'un correctif de
   code** : #30 (séquence `ir.sequence` de `purchase.order`), #33 (onglet
   Studio "LRE-Préfabrication" non versionné).
8. **Nécessitent une discussion de fond plus large** : #21 (répartition
   multi-ressources), #15 (badge kanban contacts — nouvelle feature).
9. **Nettoyage à faire avant tout déploiement** : supprimer l'enregistrement
   test `x_affaire` id=4093 créé lors des vérifications du 16/07.
10. **Attribution à confirmer** : les points #27-34 n'ont pas de
    testeur/date renseignés dans le CSV — probablement ELOGAU vu la
    thématique, à confirmer.

---

## Ce qu'il reste à obtenir du métier (état au 21/07/2026)

Tout ce qui pouvait être vérifié ou corrigé sans input métier
supplémentaire l'a été (voir section "Session du 21/07" ci-dessus). Ce
qui suit **ne peut pas avancer sans une réponse humaine**.

Numérotation : les `#` renvoient aux sections "Détail par point" de ce
document (pas au tableau officiel du 20/07, qui a sa propre numérotation
1-29 sans rapport) — le titre à côté de chaque numéro permet de
retrouver directement la bonne section avec Ctrl+F.

### Décisions d'arbitrage (bloquent un correctif déjà à moitié fait)
- **#6 — Répartition analytique qui ne se propage pas (achat/vitrage)** :
  quand le devis et la commande d'achat ont chacun une répartition
  analytique, laquelle doit gagner ? (Responsable pressenti : David)
- **#5/#14 — "Projet" vs "Compte analytique" sur l'Affaire** : tant que
  le périmètre de la fusion Projet/Compte analytique/Projet MTN n'est
  pas cadré, aucun développement sur `x_affaire` (Responsable
  pressenti : David)
- **#34 — Export PO Comalu, lignes XML manquantes** : le filtre qui
  exclut les lignes `default_code = "affaire"` est-il volontaire
  (lignes internes à ne jamais envoyer à un fournisseur) ou faut-il
  l'ajuster ? Confirmé sur données réelles que ça touche de vraies
  commandes (ex. `P05545`, 55 lignes).

### Précisions d'écran à redemander (empêchent de coder juste)
- **#9 — Mode de règlement non auto-rempli** : "Condition de paiement"
  doit se récupérer sur le client — sur l'écran **Affaire** (`x_affaire`,
  aucun champ de ce type aujourd'hui) ou sur le **devis** (`sale.order`,
  où le mécanisme standard Odoo fonctionne déjà) ?
- **#25 — CLEGIS, champ Référence non renseigné** : le lien vers la
  commande précise évoquée en réunion du 20/07 n'a jamais été transmis.
- **#25 — Atelier, composants manquants sous étiquette "Affaire"**
  (EMIDAV, lot séparé du précédent malgré le même numéro) : nom exact
  du menu/écran concerné (aucune trace dans `fma_atelier`).
- **#33 — 2 onglets livraison dont "LRE-Préfabrication"** : capture
  d'écran nécessaire — vérifié en base, une seule vue Studio active de
  chaque côté sur `stock.picking`, pas de duplication trouvée sans voir
  l'écran exact.
- **#28 — Délais de réception de bon de commande mal estimés** : schéma
  de la base SQLite source (`AllArticles`) — quelle colonne contient le
  délai fournisseur réel ? Ou à défaut, une règle métier de valeur par
  défaut.
- **#22/#23 — Code-barres (transfert et facture brouillon)** :
  confirmation d'Emilien/David sur le champ backend cible avant toute
  surcharge JS de `stock_barcode`.

### Confirmations simples (probablement déjà bons, à valider par le
testeur concerné)
- **#1 — Droit de création d'"Affaire" (MATANG)** : Mathieu Angibault
  confirme avec **son propre** mot de passe (celui utilisé pour le test
  était temporaire).
- **#10 — Commercial non auto-affecté** : confirmer avec VALLEM sur
  quel client précis le problème avait été observé, sinon considérer
  clos.
- **#20 — Heures prévues (OT) non modifiables en ligne** : donner un OF
  + état précis (testé en direct aujourd'hui, rien ne bloque dans le
  cas général).

### Actions de configuration en production (pas du code)
- **#4 — Dashboard Ventes FMA cassé (Nolhan)** : renommer/réorganiser
  les dashboards Spreadsheet — "Ventes FMA" pointe vers le générique, le
  rapport détaillé recherché est sous "Ventes FMA (2025)".
- **#30 — Numéros de commandes non générés** : vérifier la séquence
  `purchase.order` dans Réglages > Technique > Séquences (`number_next`
  était à 1 pour 27 214 commandes déjà créées dans le backup du jour —
  à vérifier si le même problème existe en production).

### À rejouer en production une fois le commit `476c639` déployé
- **#7/#29 — Projet du SO non renseigné** : rattrapage ponctuel sur les
  commandes existantes qui ont un devis source avec un projet renseigné
  (même script que celui exécuté en local aujourd'hui).
- **#24 — Facture brouillon sur réception** : retester "Fichier clients
  Iziqo" et "Création Facture Fournisseur en masse" en conditions
  réelles — ces deux actions n'avaient jamais pu être validées avant
  aujourd'hui puisqu'elles plantaient systématiquement
  (`fma_custom/__init__.py`, voir découverte critique en tête de
  document).
