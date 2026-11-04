# FMA — Documentation fonctionnelle utilisateurs

*Périmètre : base **Staging** (branche `Staging_202608`), Odoo 19.*
*Ce document décrit ce que les développements spécifiques FMA ajoutent à Odoo standard : à quoi ça sert, où le trouver, comment s'en servir.*

---

## 1. À qui s'adresse ce document

| Vous êtes… | Lisez en priorité |
|---|---|
| Commercial / deviseur | §4 Chantiers & devis, §5 Chiffrage, §6 Lots |
| Bureau d'études | §5 Chiffrage, §6 Lots, §7 Production |
| Planificateur / responsable atelier | §7 Production, §8 Laquage |
| Achats / approvisionnement | §9 Achats |
| Logistique / expédition | §10 Livraison |
| ADV / comptabilité | §11 Facturation & finance |
| Direction | §12 Pilotage |

Odoo standard n'est pas redocumenté ici. Seules les **spécificités FMA** le sont.

---

## 2. Vue d'ensemble

FMA fabrique des menuiseries. La chaîne va du chiffrage réalisé dans un logiciel métier (LOGIKAL / TechDesign) jusqu'à la livraison et la facturation, en passant par la mise en lot et la production en atelier.

```
CHANTIER (projet)
   │
   ├── Devis / Tranche 1 ──┐
   ├── Devis / Tranche 2    │  Import Pricer (fichier LOGIKAL ou TechDesign)
   └── Devis / Tranche N ──┘         │
                                     ▼
                          Lignes de devis = menuiseries
                                     │
                             Mise en lot (wizard)
                                     ▼
                    LOT-2026-0001  (max 10 menuiseries)
                                     │
                    ┌────────────────┴─────────────────┐
                    ▼                                  ▼
            OF DÉBIT (1 par lot)              OF ASSEMBLAGE (1 par menuiserie)
            optimisation de coupe             déclaration de fabrication
            appros matière                    consomme l'« Ensemble débité »
                    │                                  │
                    ▼                                  ▼
            Achats rattachés au lot          Laquage F2M (si tagué)
                                                       │
                                                       ▼
                                          Colisage → BL → Facture
```

Les deux niveaux d'OF sont liés par la **référence de lot**, pas par le chaînage parent/enfant natif d'Odoo.

---

## 3. Référentiels et paramétrage

À faire une fois, puis à maintenir.

### 3.1 Ateliers
`Fabrication > Configuration > Ateliers`

Notion métier FMA, indépendante des entrepôts et emplacements : **Atelier ALU**, **Atelier BOIS**. L'atelier est porté par l'ordre de fabrication (`atelier_id`) et sert de filtre/regroupement partout dans la production. Les OF de lot héritent de l'atelier de la commande.

### 3.2 Familles produits
`Inventaire > Familles produits` — Familles / Sous-familles / Sous-sous-familles + Triplets.

Le triplet Famille / Sous-famille / Sous-sous-famille crée automatiquement les catégories comptables associées. C'est ce qui structure le catalogue et la ventilation comptable.

### 3.3 Lots de fabrication
`Fabrication > Configuration > Paramètres > Lots de fabrication`

| Paramètre | Rôle |
|---|---|
| **Menuiseries max par lot** | Défaut 10 — contrainte de l'optimisation du débit. `0` désactive le plafond. |
| **Article débité par défaut** | Pré-rempli avec `DEB-LOT`. Surchargeable lot par lot. |

Prérequis : l'article débité doit avoir une **nomenclature** (profilés, renforts) si le besoin matière n'est pas saisi lot par lot ; les menuiseries vendues doivent avoir une **nomenclature d'assemblage**, sinon l'OF d'assemblage est créé sans composants.

### 3.4 Capacité et postes
`Fabrication > Macro Planning`

* **Ressources & Postes** — affectation d'un employé à un poste de travail, avec le **calendrier de travail choisi ici** (il peut différer du calendrier RH de l'employé : un salarié à 35 h affecté à un poste 39 h). Modifiable à tout moment, les semaines futures se recalculent.
* **Lier Rôles → Postes** — correspondance entre les rôles de planification et les postes de charge.
* **Générer les semaines** — matérialise les semaines de capacité.
* **Capacité par poste** et **Délai entre opérations** (`Fabrication >`) — référentiels de paramétrage de la charge et des délais inter-opérations.

### 3.5 Motifs de retard
`Ventes > Configuration > Motifs de retard` (catégories) et **Désignations**.

Alimentent le couple *Motif / Désignation* saisi sur la commande en cas de retard de livraison ; le libellé consolidé apparaît dans le mail de retard.

### 3.6 Sous-traitants laquage
`Fabrication > Configuration > Laquage > Sous-traitants laquage`

Fournisseurs cochés « fournisseur de laquage », avec leurs créneaux.

---

## 4. Chantiers, devis et tranches

### 4.1 Le chantier
`Ventes > Chantiers`

Le chantier est un **projet** Odoo. Il porte :

* le **code affaire** (`A24-04-01435`) — le numéro du premier devis du chantier, sans suffixe de tranche ;
* le **montant chiffré** du chantier ;
* les **commandes du chantier** (toutes tranches confondues) ;
* les cumuls : vendu, facturé, reste à vendre.

Points importants :

* le **montant vendu** compte les commandes confirmées **et** les devis à l'état *Validé* ;
* le **reste à vendre** est neutralisé tant qu'aucun chiffrage n'est renseigné ;
* on ne se sert pas du budget natif : il mesure un réalisé comptable, alors que le besoin porte sur le vendu (une commande confirmée non facturée ne produit aucune écriture) ;
* tout projet est sélectionnable comme chantier depuis un devis.

### 4.2 Le devis et ses états

Un état supplémentaire s'intercale dans le cycle standard :

```
Devis → Devis envoyé → VALIDÉ → Bon de commande → Verrouillé
                                          └→ Annulé
```

L'état **Validé** matérialise le devis accepté mais pas encore transformé en commande ferme. Il compte déjà dans le vendu du chantier.

### 4.3 Vendeur, deviseur et commercial

C'est un point qui prête souvent à confusion :

| Champ | Qui | Remarque |
|---|---|---|
| **Deviseur** | Utilisateur Odoo qui établit le devis | C'est le champ « Vendeur » natif d'Odoo, simplement renommé. Filtres, droits et rapports standards continuent de fonctionner. |
| **Commercial** | Employé (fiche RH), sans licence Odoo | Champ dédié sur le devis et la facture. Filtré sur le département Commerce. |

Le **commercial est recopié du client à la création puis figé sur le document**. Il ne suit pas les changements ultérieurs de la fiche client : le commercial d'un document est celui qui était en place au moment du devis. Sur les factures antérieures à la bascule, l'impression retombe sur l'ancienne sélection.

### 4.4 Tranches

Une affaire se vend en plusieurs tranches. La référence de tranche est fabriquée à partir du code affaire du chantier, indépendamment de la façon dont le nom du projet a été saisi. Le renommage s'applique aussi à la création du devis. Quand le numéro ne peut pas changer, Odoo l'explique dans un message.

### 4.5 Fiche devis — organisation

La fiche a été réorganisée pour l'usage FMA :

* **frise de chronologie** en lecture seule en haut de la fiche ;
* onglets **« Livraison & accès »** et **« Chronologie »** ;
* horaires saisis en format heure ;
* champs métier : ARC, contact principal, date BPE, avancement, motif d'annulation.

### 4.6 Contrôles à la confirmation

Des règles bloquantes, héritées des automatisations Studio et désormais portées dans le code :

* **CGV et RIB obligatoires** — la confirmation d'un devis est refusée si le client n'a pas ses conditions générales et son RIB ;
* **Client bloqué** — un client en blocage empêche la confirmation ;
* un **encours client** est calculé à partir d'un fichier importé, et alerte à la confirmation et à la validation.

### 4.7 Communication avec le client

* **Modèles de messages d'affaire** (`Ventes > Configuration`) — messages types publiés dans le fil de discussion du devis en un clic.
* **Motif / Désignation de retard** + nouvelle date de livraison — alimentent le mail de retard envoyé depuis le bon de livraison.

---

## 5. Le chiffrage : import Pricer

### 5.1 Principe

Le chiffrage est réalisé hors Odoo (LOGIKAL ou TechDesign). Le fichier produit est ensuite **déposé dans un devis Odoo existant**.

> **Le sens de l'import a changé.** Auparavant il fallait créer un devis dont le *nom* reproduisait exactement le nom du projet LOGIKAL, puis lancer l'export depuis le menu SQLite Connector. Aujourd'hui on crée l'entête du devis normalement dans Odoo (numéro généré par Odoo, bon client), puis on importe le fichier dedans. **Le client et la date saisis dans Odoo ne sont plus écrasés.**

### 5.2 Mode opératoire

1. Créer le devis dans Odoo : client, chantier, tranche, dates.
2. Sur le devis, cliquer sur **Import Pricer**.
3. Déposer le fichier de chiffrage et renseigner les options :

| Option | Effet |
|---|---|
| **Description** | Libellé de l'import dans le journal SQLite Connector. |
| **Remplacer les lignes existantes** | Supprime les lignes actuelles avant l'import. À utiliser pour réimporter un chiffrage corrigé. |
| **Créer les lots de fabrication** | Coché par défaut. Crée le lot décrit par le fichier, répartit les quantités du devis sur ce lot et enregistre les barres optimisées comme besoin matière. À décocher pour un chiffrage sans mise en lot. |

4. Valider : les lignes sont importées **dans ce devis-là**.

### 5.3 Garde-fous et traçabilité

* Un fichier chiffré **pour un autre devis est refusé** — l'import ne se trompe pas de cible.
* Le vitrage repris est celui de l'affaire en cours, jamais celui d'une autre affaire.
* L'article projet n'est posé qu'une seule fois.
* Chaque import crée un enregistrement consultable dans `SQLite Connector > Imports > SQL Imports`, avec ses **logs**.

### 5.4 Nomenclatures et gammes

* La **gamme se met à jour même quand les composants sont figés**.
* Le rapprochement entre les opérations du fichier et les **postes de charge** Odoo se fait par le **code du poste** (qui vaut la séquence de l'opération) ; le **site** du fichier départage les postes homonymes.
* Un outil permet de sortir la **nomenclature attendue** d'un export pricer, pour contrôle.

---

## 6. Les lots de fabrication

`Fabrication > Lots de fabrication`

### 6.1 À quoi sert un lot

Le lot regroupe des menuiseries qui seront **débitées ensemble** — c'est l'unité d'optimisation de coupe. Une barre optimisée dans un lot ne sert pas ailleurs.

Le point structurant : **une ligne de devis peut être répartie sur plusieurs lots**. Une ligne de 5 menuiseries peut aller 3 dans le lot A et 2 dans le lot B. Le lot n'est donc pas un simple champ posé sur la ligne : c'est une liaison ligne ↔ lot **avec une quantité**. Le devis affiche pour chaque ligne la quantité déjà lotie et la quantité restant à lotir.

### 6.2 Mise en lot

1. Sur le devis, bouton **Mise en lot**.
2. Le wizard liste les lignes. En face de chacune, saisir un **numéro de lot** et la **quantité** à y placer.
3. **Créer les lots** : les lots sont créés ou complétés.

Le lotissement se fait **dans Odoo**, pas dans LOGIKAL. Le champ *référence LOGIKAL* reste disponible sur le lot pour rapprocher un lot Odoo d'une optimisation LOGIKAL.

### 6.3 Générer les OF

Bouton **Générer les OF** sur le lot :

* **1 OF Débit** au niveau du lot — porte l'optimisation de coupe et les appros ;
* **N OF Assemblage**, un par menuiserie — c'est là qu'on déclare la fabrication.

Les OF sont **confirmés à la génération** et reprennent l'**atelier** et le **chantier** de la commande. La génération est **idempotente** : relancer le bouton ne recrée pas les OF existants. Le bouton **Compléter les OF** rattrape les menuiseries ajoutées après coup.

Sur l'OF de débit, la **fin de fabrication macro** est renseignée automatiquement.

### 6.4 Traçabilité matière débit → assemblage

L'OF Débit produit un article intermédiaire — l'**Ensemble débité** (`DEB-LOT`) — que chaque OF Assemblage consomme, en plus des composants de sa propre nomenclature. C'est ce qui matérialise le lien entre le débit, mutualisé sur le lot, et l'assemblage, fait menuiserie par menuiserie.

### 6.5 États du lot

| État | Signification |
|---|---|
| **Brouillon** | Composition modifiable |
| **Confirmé** | Composition figée, OF pas encore générés |
| **En production** | OF générés |
| **Terminé** | Tous les OF non annulés sont terminés (bascule automatique) |
| **Annulé** | Annule aussi les OF non terminés |

### 6.6 Lots et achats

Les achats déclenchés par l'OF Débit **remontent sur le lot** : `Achats > Regrouper par lot de fabrication`. Le lot vit sur la **ligne** d'achat, pas sur l'en-tête — un même bon de commande peut couvrir plusieurs lots (regroupement par fournisseur et par projet). Le champ reste modifiable à la main sur l'achat.

Le rattachement est déduit des mouvements de stock, avec repli sur la référence de lot présente dans l'origine du bon de commande.

### 6.7 Points ouverts

* Aucun blocage n'est posé aujourd'hui sur la **modification d'une menuiserie déjà lotie**.
* Il n'y a **pas de regroupement d'expédition par lot** : les OF d'assemblage tracent chaque menuiserie, l'expédition et la facturation restent libres (par lot ou à la commande).

---

## 7. La production

### 7.1 Le planning macro et la capacité

`Fabrication > Macro Planning`

| Écran | Ce qu'il montre |
|---|---|
| **Capacité vs Charge** | La capacité disponible par semaine, poste et atelier, face à la charge des OF. |
| **Charge par opérateur** | La même lecture, ressource par ressource. |
| **Planning Atelier (Gantt)** | Les ordres de travail positionnés dans le temps. |
| **Recalculer capacité et charge** | Relance le calcul après un changement d'affectation, de calendrier ou d'absence. |

La capacité d'une semaine part du **calendrier choisi sur l'affectation ressource → poste**, pondéré par un **taux d'allocation**, et tient compte des **congés**.

`Fabrication > Suivi Prod` donne la lecture hebdomadaire **Charge vs capacité** et la **Visu Atelier**.

### 7.2 Dates et replanification

* La **date de livraison** est pilotée par le **bon de livraison**, et par lui seul.
* Le lot porte une **date de fin de fabrication** ; on peut replanifier depuis cette date.
* La planification **chaîne le débit et l'assemblage** du lot.
* Sur l'OF, **« Fin de fab »** est la fin macro **forcée**, et elle est **modifiable**.
* Boutons **Replanifier l'OF** et **Replanification en lot** (`Recalcul batch OF non démarrés`) pour réordonnancer en masse ; un aperçu permet de contrôler avant d'appliquer.

La fiche OF est présentée en **deux colonnes** — *Fabrication* et *Planification* — sous les colonnes natives.

### 7.3 Besoin matière

Bouton **Ajouter un besoin** sur l'OF : ajoute un composant au besoin matière sans repasser par la nomenclature.

### 7.4 Atelier (Shop Floor)

Deux ajustements de l'écran atelier Odoo :

* les **ordres de travail actifs sont surlignés** par un indicateur de couleur ;
* les **listes de composants et de sous-produits sont masquées** sur les cartes d'OF, pour ne garder que ce dont l'opérateur a besoin.

---

## 8. Le laquage sous-traité (F2M)

`Fabrication > Configuration > Laquage`

### 8.1 Déclenchement

Un OF issu d'une commande client **taguée F2M** est automatiquement marqué **Laquage requis**. Le tag déclencheur est paramétrable sans toucher au code.

### 8.2 Cycle

```
Non concerné → À planifier → Planifié → Envoyé → Retourné
```

Boutons disponibles sur l'OF : **Planifier laquage**, **Envoyé laquage**, **Retour laquage**, **Replanifier laquage**.

À la planification, Odoo choisit un **créneau** chez un **sous-traitant laquage**, crée l'**achat de sous-traitance** correspondant et calcule le **coût de laquage**, reporté sur l'OF. Une alerte s'affiche sur l'OF quand une action laquage est attendue.

---

## 9. Les achats

### 9.1 Rattachements automatiques

À la création et à la modification d'un bon de commande d'achat :

* le **compte analytique** de la commande client (ou de l'OF) est propagé sur les lignes d'achat — sans jamais écraser une répartition analytique déjà saisie ;
* la **référence** interne est calculée ;
* le **responsable de l'achat** est aligné sur le responsable du projet ;
* le **lot de fabrication** est déduit (voir §6.6).

### 9.2 Documents et exports

* **Rapports PDF d'achat personnalisés** (`custom_purchase_documents`).
* **Export XML des commandes fournisseurs** — via l'écran `Export > Liste des commandes`, ou automatiquement par tâche planifiée avec dépôt sur SFTP.
* **Export TXT des fournisseurs** vers SFTP, quotidien pour les nouveaux fournisseurs.

---

## 10. La livraison

### 10.1 Colisage et palettes

Le bon de livraison porte les informations de **colisage** et de **palettes** : quantité, longueur, profondeur, hauteur par palette. Les lignes de palette sont suivies dans le fil de discussion du BL.

Le **bon de livraison imprimé** est adapté au besoin FMA.

### 10.2 Bon de préparation

Le rapport de préparation retire la colonne *destination*, ajoute **« Emplacements existants »** et affiche **tous les articles** — y compris ceux sans quantité réservée.

### 10.3 Mail de retard

Depuis le BL, envoi d'un mail de retard au client, alimenté par le **motif**, la **désignation** et la **nouvelle date de livraison** saisis sur la commande.

### 10.4 Taux de service

`Inventaire > Analyse > Taux de service %`

Pourcentage mensuel de livraisons faites **à la date prévue ou avant**, sur les expéditions terminées. Un motif de retard est saisissable sur le BL.

### 10.5 Traçabilité des mouvements

Sur les lignes de mouvement de stock : **type de mouvement** (entrée / sortie / autre), **emplacement suivi**, **quantité avant** et **quantité après** le mouvement. Un assistant (`Inventaire > Configuration > Recalculer qté avant/après`) recalcule l'historique existant.

---

## 11. Facturation et suivi financier

### 11.1 Facture client

* Bloc de texte conditionnel affiché sur la facture selon un indicateur porté par le contact.
* Le **commercial** figure sur la facture imprimée (avec repli sur l'ancienne sélection pour l'historique).

### 11.2 Encours client

Un fichier d'encours importé depuis un serveur FTP alimente un champ sur la fiche client (différence débit − crédit). Il permet de filtrer les clients concernés et déclenche des **alertes à la confirmation et à la validation** des commandes.

### 11.3 Statut de paiement des factures

Un fichier CSV déposé sur FTP met à jour le **statut** et la **date de paiement** des factures.

### 11.4 Règlements

Le mode de règlement est une chaîne unique portée par le référentiel des règlements, avec une vue formulaire dédiée.

### 11.5 Exports comptables

* **Export CSV des factures** avec le détail des écritures + dépôt du PDF sur FTP.
* **Export des factures fournisseurs**.
* **Export TXT des clients** vers SFTP, quotidien pour les nouveaux clients.

### 11.6 Suivi de marge (calcul PRI)

Un moteur recalcule, par affaire, les coûts réellement engagés :

| Indicateur | Contenu |
|---|---|
| Achat matière réel | Achats hors vitrage |
| Achat vitrage réel | Achats de la catégorie vitrage |
| Coût appro affaire / stock | Séparation appro dédiée / prise sur stock |
| Montant total appro | Cumul |
| Non livré non facturé / livré non facturé / livré facturé | Ventilation de l'appro selon l'avancement |

Disponible par **bouton** sur le document et par **tâche planifiée** pour le recalcul en masse. Un second bouton recalcule le *Restant HT (pivot)*.

---

## 12. Pilotage et intégrations

### 12.1 Écrans de pilotage

| Écran | Emplacement |
|---|---|
| **Commandes à facturer (+ Rien à facturer)** | `Ventes > Commandes` |
| **KPI Livraison — Facturation vs Livraison** | `Ventes > KPI Livraison` |
| **KPI Affaire (Vente / Appro / Stock)** | Vue de synthèse par affaire |
| **Taux de service** | `Inventaire > Analyse` |
| **Capacité vs Charge / Visu Atelier** | `Fabrication > Macro Planning` et `Suivi Prod` |

### 12.2 Export Power BI

Export automatique (tâche planifiée) des **clients, commandes, factures, achats, stock et production** vers un serveur SFTP, pour alimenter les rapports Power BI. Configuration dans l'écran dédié.

### 12.3 HubSpot

Les évènements Odoo sont poussés vers HubSpot par webhook. Le journal est consultable dans `Administration > Export HubSpot > Logs`.

### 12.4 Pièces jointes Excel

Génération de pièces jointes Excel sur les documents, avec bouton **Télécharger Excel**.

---

## 13. Rôles et bonnes pratiques

* **Ne pas renommer un devis pour faire correspondre un nom LOGIKAL** : ce n'est plus le mécanisme d'import.
* **Toujours créer le devis avant d'importer le chiffrage** — l'entête (client, dates) est la référence, l'import ne l'écrase pas.
* **Vérifier le lotissement avant de générer les OF** : la composition d'un lot est figée à la confirmation.
* **Ne pas modifier une menuiserie déjà lotie** sans repasser le lot en brouillon — aucun contrôle automatique ne le bloque aujourd'hui.
* **La date de livraison se pilote depuis le BL**, pas depuis la commande.
* **Le commercial d'un document ne se met pas à jour** si celui de la fiche client change : c'est voulu.

---

## 14. Glossaire

| Terme | Définition |
|---|---|
| **Affaire / Chantier** | Projet Odoo regroupant toutes les tranches et commandes d'un même chantier. Identifié par un code `A24-04-01435`. |
| **Tranche** | Découpage commercial d'une affaire ; un devis par tranche. |
| **Deviseur** | Utilisateur Odoo qui établit le devis (champ « Vendeur » natif renommé). |
| **Commercial** | Employé responsable commercial, figé sur le document à sa création. |
| **Pricer / LOGIKAL / TechDesign** | Logiciels de chiffrage métier ; produisent le fichier importé dans le devis. |
| **Lot de fabrication** | Regroupement de menuiseries débitées ensemble (max 10 par défaut). |
| **OF Débit** | Ordre de fabrication du lot : coupe des barres, appros. Un seul par lot. |
| **OF Assemblage** | Ordre de fabrication d'une menuiserie. Un par menuiserie du lot. |
| **Ensemble débité (`DEB-LOT`)** | Article intermédiaire produit par l'OF Débit et consommé par les OF Assemblage. |
| **Atelier** | Notion métier FMA (ALU / BOIS), portée par l'OF, indépendante des entrepôts. |
| **F2M** | Tag de commande déclenchant le laquage sous-traité. |
| **Fin de fab** | Date de fin de fabrication macro forcée, modifiable, portée par l'OF. |
| **BPE** | Bon pour exécution (date portée par le devis). |
| **ARC** | Accusé de réception de commande. |
| **PRI** | Prix de revient — moteur de recalcul des coûts réels par affaire. |
