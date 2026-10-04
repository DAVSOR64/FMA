# FMA — Étiquettes, scan atelier et SAV par menuiserie

Module `fma_etiquette_scan` (Odoo 19). Il s'appuie sur ce que
`fma_lot_fabrication` produit déjà : **un ordre de fabrication et un numéro
de série par menuiserie**, posés dès « Générer les OF ». Ce numéro est aussi
celui du casier que le magasin garnit.

Tout le module tient dans une phrase : **une étiquette = une menuiserie = un
numéro de série = un ordre de fabrication**.

## Ce que le module apporte

| Besoin | Réponse |
|---|---|
| Étiqueter chaque menuiserie / casier | Étiquette 100 × 150 mm : repère, n° de casier, affaire, commande, client, chantier, lot, OF, désignation, dimensions, Code128 du numéro de série, QR code SAV |
| Déclarer la fabrication sans clavier | Poste de scan : une étiquette lue = une menuiserie pointée ou terminée |
| Savoir où en est une menuiserie | Mode « Localiser » : état de l'OF, opération en cours, emplacement du casier, livraison |
| Suivre le SAV à la menuiserie | Ticket d'assistance rattaché au numéro de série, à l'OF, au lot et à la commande ; QR code sur l'étiquette |

## Menus

Sous **Fabrication > Opérations** :

- **Déclaration de fabrication (scan)**
- **Localiser une menuiserie**
- **SAV par étiquette**
- **Menuiseries (numéros de série)** — la liste de toutes les menuiseries
  numérotées, avec état, opération en cours, livraison, nombre de tickets
- **Tickets SAV par menuiserie**

Boutons ajoutés :

- sur le **lot de fabrication** : « Imprimer les étiquettes », « Déclarer au
  scan », et un compteur « x / y terminées » ;
- sur l'**ordre de fabrication** : « Étiquette menuiserie » ;
- sur le **numéro de série** : « Tickets SAV », « Ordre de fabrication »,
  bloc « Menuiserie », « Historique de la menuiserie », « Imprimer
  l'étiquette », « Créer un ticket SAV » ;
- sur le **ticket** : onglet « Menuiserie » et boutons vers la menuiserie,
  l'OF, le lot, la commande.

## Flux

### 1. Imprimer

Depuis le lot, après « Générer les OF » : « Imprimer les étiquettes ». Le PDF
porte une étiquette par menuiserie, **dans l'ordre de la liste de
quincaillerie** (ligne de lot, puis rang). Le paquet se pose sur les casiers
sans chercher.

La même étiquette s'imprime depuis un OF (menu Imprimer ou bouton) et depuis
un numéro de série. Il n'y a volontairement qu'**un seul modèle** : le casier
et la menuiserie portent le même numéro, deux étiquettes différentes
laisseraient croire à deux objets. Pour étiqueter le casier ET la menuiserie,
imprimer deux exemplaires.

Les codes sont embarqués dans le PDF (pas d'appel réseau à l'impression).

### 2. Déclarer

Le poste de scan est un formulaire. La douchette USB (ou le PDA) en mode
clavier « tape » le code puis Entrée ; le champ se vide, prêt pour le
suivant. Le code est aussi capté quand le curseur n'est dans aucun champ.

Réglage « Au scan » :

- **Afficher, je valide au bouton** (défaut) : le scan montre la menuiserie,
  son état, ses opérations ; on clique « Démarrer / terminer l'opération » ou
  « Déclarer la menuiserie terminée ».
- **Pointer l'opération** : 1er scan = l'opération suivante démarre (le
  chronomètre standard tourne) ; 2e scan = elle se termine avec son temps
  réel. Aucun clic.
- **Déclarer la menuiserie terminée** : un scan clôture l'OF. Aucun clic.

« Terminée » fait exactement ceci, avec les méthodes standard :

1. les opérations restantes sont soldées (`action_mark_as_done`) — une
   opération chronométrée garde son temps réel, une opération jamais
   démarrée prend sa **durée prévue** ;
2. l'OF est clôturé (`button_mark_done`) avec le numéro de série qu'il porte
   déjà : composants consommés, menuiserie en stock sous son numéro.

Si Odoo refuse (composant suivi sans lot, contrôle qualité en attente,
opérateur non identifié, écart de consommation à confirmer…), **rien n'est
forcé** : tout est annulé, le message s'affiche en rouge au poste et une
note est posée dans le fil de l'OF.

Le poste affiche l'avancement du lot : « 3 / 8 menuiseries terminées ».

Codes acceptés : le Code128 (numéro de série), le QR code (lien SAV), le
numéro d'un OF. Une douchette réglée en QWERTY sur un poste AZERTY est
reconnue (les caractères sont retraduits) — mais mieux vaut régler la
douchette.

### 3. Localiser

Scan → état de l'OF, opération en cours, emplacement du casier, livraison
prévue ou faite, historique. On peut saisir un emplacement libre (« Travée
B ») et « Ranger ici » : il est noté sur la menuiserie. Ce n'est **pas** un
emplacement de stock Odoo, seulement une indication.

### 4. SAV

Trois entrées, un même ticket :

- **QR code de l'étiquette**, lu au téléphone : page
  `/fma/sav/<jeton>`. Sans connexion, elle montre le numéro, la désignation,
  le repère, les dimensions — ni client ni commande — et un formulaire
  (objet, description, nom, e-mail ou téléphone). Connecté en interne, elle
  montre toute la fiche, l'historique et les tickets existants.
- **Poste de scan, mode SAV** : scan → tickets existants signalés → « Créer
  le ticket SAV » ouvre un ticket pré-rempli.
- **Fiche du numéro de série** : « Créer un ticket SAV ».

Le ticket porte la menuiserie (`fma_serial_id`) et, figés à la création,
l'OF, le lot et la commande. Sa description reprend la fiche complète.

Le jeton du lien est aléatoire (32 caractères), propre à chaque menuiserie :
connaître un numéro de série ne donne pas accès à la page d'une autre.
Paramètre système `fma_etiquette_scan.sav_public` : `1` (défaut) = page
accessible sans connexion ; `0` = connexion exigée.

## La contrainte à connaître : un OF par étiquette

L'article menuiserie est **suivi au numéro de série**. Dans Odoo, un numéro
de série désigne une unité, et une seule. Pour que chaque menuiserie ait son
identité **avant** d'être fabriquée — c'est ce qui permet au magasin de
préparer un casier numéroté —, le lot scinde chaque ordre en autant d'ordres
qu'il y a de menuiseries.

Conséquences :

- **Autant d'OF que de menuiseries.** Un lot de 8 menuiseries = 1 OF de débit
  + 8 OF d'assemblage. Chaque OF porte sa propre gamme : 8 menuiseries × 3
  opérations = 24 ordres de travail.
- **Le planning se lit au lot**, pas à l'OF. C'est le rôle des écrans
  d'ordonnancement et du lot (dates, replanification) : ils regroupent.
- **L'écran Atelier affiche une carte par menuiserie**, pas une carte par
  ligne de commande.

Ce que le scan apporte en échange :

- **Pas de reliquat.** Déclarer 1 menuiserie sur un OF de 5 crée, en
  standard, un OF de reliquat de 4 — et un nouveau numéro d'OF à chaque
  déclaration partielle. Ici chaque OF se termine en entier, d'un scan.
- **Pas d'écran des numéros de série.** Le numéro est déjà sur l'OF ;
  l'opérateur ne choisit rien, il ne peut pas se tromper de numéro.
- **Le nombre d'OF ne coûte rien à l'opérateur** : il ne les ouvre pas, il
  scanne. L'avancement du lot se compte en OF terminés.
- **Une traçabilité de bout en bout** : casier → fabrication → livraison →
  SAV, sur le même numéro.

L'alternative — un OF par ligne, numéros saisis à la déclaration — donne
moins d'OF, mais des reliquats, des casiers anonymes et aucun lien fiable
entre le casier préparé et la menuiserie déclarée.

## Limites

- **Opérateur.** Avec l'Atelier (`mrp_workorder`), démarrer une opération
  exige que l'utilisateur connecté soit lié à un employé. Sinon Odoo refuse,
  et le poste affiche le refus. Le temps est pointé au nom de l'utilisateur
  connecté au poste, pas d'un opérateur badgé : pour un pointage nominatif
  par opérateur, l'écran Atelier standard reste l'outil.
- **Durées.** « Déclarer terminée » sur des opérations jamais démarrées leur
  donne leur durée prévue. Pour des temps réels, pointer les opérations.
- **Contrôles qualité.** S'ils sont obligatoires sur une opération, Odoo
  refuse la clôture au scan : ils se font dans l'écran Atelier.
- **Livraison.** La date « livrée le » est exacte si le bon de livraison
  porte le numéro de série ; sinon le module indique la livraison prévue de
  la ligne de commande.
- **Accusé de réception.** Un ticket créé avec un e-mail peut déclencher le
  modèle de mail de l'étape « Nouveau » de l'équipe d'assistance : c'est le
  comportement standard, à régler sur l'équipe.
- **Formulaire public.** Protégé par le jeton, un contrôle CSRF et un champ
  piège ; pas de captcha.
- **Emplacement du casier** : texte libre, sans mouvement de stock.
- **Impression** : PDF 100 × 150 mm via le pilote de l'imprimante. Pas de
  ZPL direct ni d'impression automatique (IoT Box) dans cette version.
- **Articles non suivis** : un OF sans numéro de série reçoit une étiquette
  à son numéro d'OF, scannable, mais sans QR SAV.

## Droits

- Utilisateur Fabrication : poste de scan, étiquettes, création de tickets.
- Utilisateur Assistance : poste de scan (localiser, SAV), lecture des
  numéros de série, des OF et des lots.

## Tests

`tests/test_etiquette_scan.py` (post_install) : scission en un OF par
menuiserie, rendu des étiquettes, lecture des codes, déclaration au bouton
et automatique, pointage d'opération, refus d'Odoo sans plantage,
localisation, ticket SAV, page SAV publique et interne.
