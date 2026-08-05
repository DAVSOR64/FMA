# FMA — Lots de fabrication

Relie le commerce (lignes de devis = menuiseries) à la production (ordres de
fabrication) via une notion de **lot de fabrication**.

## Le flux

```
Devis (Odoo)                     Lot                      Production
────────────                     ───                      ──────────
Import Pricer  ──►  Mise en lot  ──►  LOT-2026-0001  ──►  OF Débit  (1/lot)
(fma_pricer_import)   (wizard)         8 menuiseries       OF Assemblage (1/menuiserie)
                                                           Achats rattachés au lot
```

1. **Import Pricer** (module `fma_pricer_import`) : on crée l'entête du devis
   dans Odoo — numéro Odoo, bon client — puis on dépose le fichier de
   chiffrage. Les lignes sont importées dans **ce** devis.
2. **Mise en lot** : bouton sur le devis. Le wizard liste les lignes ; on
   saisit en face de chacune un **numéro de lot** et la **quantité** à y
   placer. À la validation, les lots sont créés ou complétés.
3. **Générer les OF** : bouton sur le lot. Crée 1 OF Débit (niveau lot) et
   N OF Assemblage (1 par menuiserie).
4. Les achats déclenchés par l'OF Débit remontent sur le lot
   (`Achats > Regrouper par lot de fabrication`).

## Le modèle de données

| Modèle | Rôle |
|---|---|
| `fma.lot.fabrication` | Le lot : état, date planifiée, article débité, OF, groupe d'appro |
| `fma.lot.fabrication.line` | **Liaison ligne de devis ↔ lot, avec quantité** |
| `fma.lot.material.line` | Besoin matière du lot (profilés, renforts) |

Le point structurant : le lot n'est **pas** un simple `Many2one` posé sur la
ligne de devis. Une ligne portant 5 menuiseries peut être répartie sur
plusieurs lots (3 dans le lot A, 2 dans le lot B). D'où la table de liaison
avec quantité, et les champs `qty_lot` / `qty_to_lot` sur la ligne de devis.

Les deux niveaux d'OF sont reliés par `lot_fabrication_id` — la référence de
lot — et non par le chaînage parent/enfant natif d'Odoo. Un OF porte en plus
`lot_production_type` (`debit` / `assemblage`).

## Traçabilité matière débit → assemblage

L'OF Débit produit un article intermédiaire (**Ensemble débité**, `DEB-LOT`)
que chaque OF Assemblage consomme, en plus des composants de sa nomenclature.
C'est ce qui matérialise le lien entre le débit — mutualisé sur le lot — et
l'assemblage, fait menuiserie par menuiserie.

L'article est paramétrable :
* par défaut sur la société (`Fabrication > Configuration > Paramètres`) ;
* surchargeable lot par lot via le champ *Article débité*.

## Paramétrage

`Fabrication > Configuration > Paramètres > Lots de fabrication` :

* **Menuiseries max par lot** — défaut 10, contrainte de l'optimisation du
  débit. `0` désactive le plafond.
* **Article débité par défaut** — pré-rempli avec `DEB-LOT`.

À faire à l'installation :

1. Créer la **nomenclature de l'article débité** (profilés, renforts) si le
   besoin matière n'est pas saisi lot par lot. Sans nomenclature, l'OF Débit
   prend les composants de l'onglet *Besoin matière* du lot.
2. Vérifier que les menuiseries vendues ont bien une **nomenclature
   d'assemblage**, sinon l'OF Assemblage est créé sans composants.

## États du lot

| État | Signification |
|---|---|
| Brouillon | Composition modifiable |
| Confirmé | Composition figée, OF pas encore générés |
| En production | OF générés — le bouton *Compléter les OF* rattrape les menuiseries ajoutées après coup |
| Terminé | Tous les OF non annulés sont terminés (bascule automatique) |
| Annulé | Annule aussi les OF non terminés |

La génération des OF est **idempotente** : relancer le bouton ne recrée pas
les OF existants.

## Écarts assumés avec les maquettes de cadrage

Les deux documents de cadrage décrivaient un lotissement **décidé dans
LOGIKAL puis importé** dans Odoo. L'implémentation retenue place le
lotissement **dans Odoo**, via le wizard de mise en lot :

* la composition des lots est saisie par l'opérateur dans Odoo, pas importée ;
* une ligne de devis peut être **répartie sur plusieurs lots** avec une
  quantité — cas qui n'apparaissait pas dans les maquettes ;
* le champ `logikal_ref` sur le lot reste disponible pour rapprocher un lot
  Odoo d'une optimisation LOGIKAL, si le besoin d'un import automatique
  revient plus tard.

Le reste suit le cadrage : deux niveaux d'OF, plafond de 10 menuiseries,
regroupement par référence de lot, appros au niveau du lot, expédition et
facturation libres (par lot ou à la commande).

## Reste à trancher

* **Composants débités** : l'OF Assemblage consomme 1 unité d'`Ensemble
  débité` par menuiserie. Si le flux réel demande une réservation par
  emplacement intermédiaire plutôt qu'un article générique, c'est
  `_add_debit_component` qu'il faut adapter.
* **Menuiserie modifiée après lotissement** : aucun blocage n'est posé
  aujourd'hui. À définir : bloquer la modification d'une ligne déjà lotie,
  ou remettre le lot en brouillon automatiquement.
* **Expédition par lot** : les OF d'assemblage tracent chaque menuiserie,
  mais aucun regroupement de livraison par lot n'est implémenté.
