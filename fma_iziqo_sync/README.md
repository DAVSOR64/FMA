# Iziqo : synchronisation des clients et des commerciaux

Pousse les fiches Odoo vers la base de l'application Iziqo **dès leur création
ou leur modification**, en remplacement / complément de l'export manuel
« Fichier clients Iziqo » (`fma_custom`) et de l'export quotidien TXT/SFTP
(`fma_customer_export`).

Contrat : **API REST**. `POST {url}` à la création, `PATCH {url}/{identifiant}`
à la modification.

Deux ressources, deux collections, la même mécanique :

| Ressource | Modèle Odoo | Périmètre par défaut |
|---|---|---|
| Clients | `res.partner` | Sociétés **ayant un SIRET**, hors fournisseurs purs |
| Commerciaux | `hr.employee` | Employés du **département « Commerce »** |

Le payload client référence le commercial par `id_employe_commercial`, qui est
l'`odoo_id` du payload commercial : c'est la clé de jointure côté Iziqo.
**Chargez donc les commerciaux avant les clients.**

## Fonctionnement

1. `create()` / `write()` : si la fiche est dans le périmètre et qu'un champ
   suivi a changé, un job `iziqo.sync.job` est créé.
2. L'envoi HTTP est déclenché **après le commit** de la transaction, dans un
   curseur dédié : l'utilisateur qui enregistre n'attend jamais Iziqo et une
   erreur d'API ne fait jamais échouer l'enregistrement.
3. En cas d'échec, le job est relancé par le cron *Iziqo - Envoi des fiches
   clients en attente* (toutes les 10 min) avec un délai croissant
   (5 min, 15 min, 1 h, 4 h, 24 h) puis passe en état *En échec*.
4. Si le `POST` répond **409** (fiche déjà présente côté Iziqo, cas courant au
   chargement initial), le job bascule immédiatement en `PATCH`.

Une société sans SIRET est ignorée puis envoyée automatiquement dès que le
SIRET est renseigné. Modification d'une adresse de livraison ou de facturation
enfant : c'est la société parente qui est renvoyée, puisque c'est elle qui
porte les colonnes « … livraison » du payload.

## Configuration

*Paramètres > Iziqo*, en quatre blocs : **Connexion** (authentification
commune + test), **Clients**, **Commerciaux**, **Comportement**.

| Paramètre | Clé `ir.config_parameter` | Rôle |
|---|---|---|
| Authentification | `iziqo_sync.auth_type` | `none`, `bearer`, `apikey` (en-tête paramétrable), `basic` — commune aux deux collections |
| URL collection clients | `iziqo_sync.api_url` | **Vide = clients non synchronisés** |
| Identifiant client | `iziqo_sync.identifier_field` | `id` (défaut), `siret`, `ref` |
| Périmètre clients | `iziqo_sync.scope` | `customers_and_prospects` (défaut), `customers`, `flagged` |
| URL collection commerciaux | `iziqo_sync.employee_api_url` | **Vide = commerciaux non synchronisés** |
| Identifiant commercial | `iziqo_sync.employee_identifier_field` | `id` (défaut), `email`, `matricule` |
| Périmètre commerciaux | `iziqo_sync.employee_scope` | `department` (défaut), `all` |
| Département commercial | `iziqo_sync.employee_department` | Nom exact du département, `Commerce` par défaut |
| Envoi immédiat | `iziqo_sync.realtime` | Décoché : tout passe par le cron |
| Timeout / tentatives | `iziqo_sync.timeout`, `iziqo_sync.max_attempts` | 15 s et 5 tentatives |
| Conservation du journal | `iziqo_sync.keep_days` | Purge des envois réussis au-delà de 30 jours |

Le bouton **Tester l'accès à l'API** fait un `GET` sur chaque collection
configurée : en lecture seule, il ne crée rien dans Iziqo.

Le filtre des commerciaux porte sur le **nom** du département et non sur son
identifiant, qui diffère d'un environnement à l'autre — même raison que le
domaine de `res.partner.x_studio_commercial_1`.

## Payloads

Toutes les clés sont toujours présentes ; une valeur inconnue est une chaîne
vide, jamais `null`. `actif: false` correspond à une fiche archivée : c'est la
seule forme de suppression propagée.

**Client** — les clés reprennent les colonnes du fichier CSV Iziqo historique :
`operation`, `odoo_id`, `code_client`, `nom`, `telephone`, `email`, `siret`,
`tva`, `adresse`, `cp`, `ville`, `pays`, `code_pays`, `commercial`,
`id_employe_commercial`, `adresse_livraison`, `cp_livraison`,
`ville_livraison`, `pays_livraison`, `actif`, `date_modification`.

**Commercial** : `operation`, `odoo_id`, `nom`, `email`, `telephone`, `mobile`,
`fonction`, `departement`, `matricule`, `actif`, `date_modification`.

Pour ajouter un champ : surcharger `_iziqo_payload()` sur le modèle concerné.

## Fiches historiques

- **Bouton « Synchroniser avec Iziqo »** dans l'en-tête de la fiche client et
  de la fiche employé, ou action du menu ⚙️ sur une sélection de la liste.
  Envoi immédiat et **hors périmètre automatique** : une fiche qui ne remplit
  pas le `scope` est quand même envoyée (un commercial rattaché à un autre
  département, par exemple). Restent bloquants : l'exclusion manuelle et,
  pour un client, l'absence de SIRET.
- **Mettre tous les commerciaux / tous les clients en file** dans les réglages.
  Dans cet ordre, à cause de la clé de jointure. La notification indique
  combien de sociétés ont été écartées faute de SIRET.

## Ajouter une troisième ressource

1. Hériter du mixin : `_inherit = ["mon.modele", "iziqo.sync.mixin"]`.
2. Déclarer `_iziqo_url_param`, `_iziqo_identifier_param` et
   `_iziqo_tracked_fields`.
3. Implémenter `_iziqo_is_eligible()`, `_iziqo_payload()`,
   `_iziqo_identifier_candidates()` et `_iziqo_manual_targets()`.
4. Ajouter le modèle à `iziqo.sync.job._selection_res_model()`.

La file, le cron, les relances, le journal, l'envoi post-commit et le bouton
manuel sont fournis par le mixin.

## Supervision

*Paramètres > Synchronisation Iziqo > File d'attente et journal* : ressource,
fiche visée, état, tentatives, code HTTP, réponse d'Iziqo et payload envoyé,
avec boutons **Relancer**, **Annuler** et **Ouvrir la fiche**. Chaque fiche
affiche par ailleurs la date, le statut et l'erreur de son dernier envoi.

## Garde-fous

- Import de fichier ou action de masse touchant plus de 20 fiches : l'envoi
  immédiat est désactivé, le cron prend le relais (100 jobs par passage).
- Les jobs sont verrouillés (`FOR UPDATE SKIP LOCKED`) : pas de double envoi
  entre l'envoi post-commit et le cron.
- 5 échecs réseau consécutifs interrompent le lot en cours.
- URL vide = ressource totalement inerte, aucun job créé.
