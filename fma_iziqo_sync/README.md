# Iziqo : synchronisation des clients et des commerciaux

Pousse les fiches Odoo vers la base de l'application Iziqo **dès leur création
ou leur modification**, en remplacement / complément de l'export manuel
« Fichier clients Iziqo » (`fma_custom`) et de l'export quotidien TXT/SFTP
(`fma_customer_export`).

Contrat : **API REST**. `POST {url}` à la création, `PATCH {url}/{odoo_id}`
à la modification. Iziqo compare l'identifiant de l'URL au `odoo_id` du payload
et **refuse en 400** s'ils diffèrent : l'identifiant de ressource est donc
toujours l'ID Odoo, des deux côtés.

Deux ressources, deux collections, la même mécanique :

| Ressource | Modèle Odoo | Collection Iziqo | Périmètre par défaut |
|---|---|---|---|
| Clients | `res.partner` | `…/iziqo-api-v2/customers` | Sociétés **ayant un SIRET**, hors fournisseurs purs |
| Commerciaux | `hr.employee` | `…/iziqo-api-v2/salespeople` | Employés du **département « Commerce »** ayant un **e-mail professionnel** |

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
   chargement initial), le job bascule immédiatement en `PATCH`. Mais Iziqo
   répond aussi 409 sur un conflit d'un autre ordre — e-mail déjà porté par un
   commercial, code déjà pris par un client : ce `PATCH` répond alors **404**,
   et le job passe aussitôt **en échec** avec le message du 409, sans épuiser
   ses cinq tentatives. Il redevient une création : une fois le conflit arbitré
   dans Iziqo, *Relancer* repart d'un `POST`.

Une société sans SIRET, un commercial sans e-mail professionnel : la fiche est
ignorée, puis envoyée automatiquement dès que la donnée manquante est
renseignée, les deux champs étant suivis. Modification d'une adresse de
livraison ou de facturation enfant : c'est la société parente qui est renvoyée,
puisque c'est elle qui porte les colonnes « … livraison » du payload.

## Configuration

*Paramètres > Iziqo*, en quatre blocs : **Connexion** (authentification
commune + test), **Clients**, **Commerciaux**, **Comportement**.

| Paramètre | Clé `ir.config_parameter` | Rôle |
|---|---|---|
| Authentification | `iziqo_sync.auth_type` | `none`, `bearer`, `apikey` (en-tête paramétrable), `basic` — commune aux deux collections |
| URL collection clients | `iziqo_sync.api_url` | **Vide = clients non synchronisés** |
| Identifiant client | `iziqo_sync.identifier_field` | `id` (défaut), `siret`, `ref` — **à laisser sur `id`** : Iziqo rejette les autres |
| Périmètre clients | `iziqo_sync.scope` | `customers_and_prospects` (défaut), `customers`, `flagged` |
| URL collection commerciaux | `iziqo_sync.employee_api_url` | **Vide = commerciaux non synchronisés** |
| Périmètre commerciaux | `iziqo_sync.employee_scope` | `department` (défaut), `all` |
| Département commercial | `iziqo_sync.employee_department` | Nom exact du département, `Commerce` par défaut |
| Envoi immédiat | `iziqo_sync.realtime` | Décoché : tout passe par le cron |
| Timeout / tentatives | `iziqo_sync.timeout`, `iziqo_sync.max_attempts` | 15 s et 5 tentatives |
| Conservation du journal | `iziqo_sync.keep_days` | Purge des envois réussis au-delà de 30 jours |

L'authentification doit être un **token Bearer** : c'est la seule que l'API
reconnaît, les autres modes répondent 401.

Le bouton **Tester l'accès à l'API** fait un `GET` sur les collections qui en
exposent un : en lecture seule, il ne crée rien dans Iziqo. La collection des
commerciaux n'en expose pas — un `GET` y répondrait 404 alors que la
configuration est bonne : elle est donc signalée comme renseignée mais non
interrogeable, et son premier envoi réel vaut test.

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

Côté commercial, Iziqo exige `odoo_id` (entier), `nom`, `email`, `actif` et
`date_modification` au format `AAAA-MM-JJ HH:MM:SS` : un `nom` ou un `email`
vide est refusé en 400, d'où leur place dans le périmètre. Il n'exploite que le
nom, l'e-mail, le téléphone et `actif` ; `mobile`, `fonction`, `departement` et
`matricule` sont acceptés sans être utilisés. La fiche est créée en **TCI** et
la promotion en **RRV** est un geste du fabricant dans Iziqo : une mise à jour
ne l'écrase jamais. Une `date_modification` antérieure au dernier envoi
appliqué est ignorée côté Iziqo (réponse 200, `updated: false`).

Pour ajouter un champ : surcharger `_iziqo_payload()` sur le modèle concerné.

## Fiches historiques

- **Bouton « Synchroniser avec Iziqo »** dans l'en-tête de la fiche client et
  de la fiche employé, ou action du menu ⚙️ sur une sélection de la liste.
  Envoi immédiat et **hors périmètre automatique** : une fiche qui ne remplit
  pas le `scope` est quand même envoyée (un commercial rattaché à un autre
  département, par exemple). Restent bloquants : l'exclusion manuelle et, faute
  de quoi Iziqo refuse la fiche, l'absence de SIRET pour un client ou
  d'e-mail professionnel pour un commercial.
- **Mettre tous les commerciaux / tous les clients en file** dans les réglages.
  Dans cet ordre, à cause de la clé de jointure. La notification indique
  combien de fiches ont été écartées faute de SIRET ou d'e-mail.

## Ajouter une troisième ressource

1. Hériter du mixin : `_inherit = ["mon.modele", "iziqo.sync.mixin"]`.
2. Déclarer `_iziqo_url_param`, `_iziqo_tracked_fields`, et
   `_iziqo_supports_get` si la collection répond au `GET` du test d'accès.
   `_iziqo_identifier_param` seulement si l'identifiant de ressource est
   configurable, ce que l'API n'accepte pas aujourd'hui.
3. Implémenter `_iziqo_is_eligible()`, `_iziqo_payload()` et
   `_iziqo_manual_targets()` — plus `_iziqo_identifier_candidates()` si
   l'identifiant est configurable.
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
- Chez un fabricant, Iziqo range le code d'un commercial (son ID Odoo) et les
  codes clients dans le même espace : si un code client vaut l'ID Odoo d'un
  commercial, la création part en 409 et le journal le dit. C'est un arbitrage
  Iziqo, pas un réglage Odoo.
- En v19, `department_id` et `job_title` appartiennent à `hr.version`, dont
  `hr.employee` hérite par délégation. Une modification faite depuis la fiche
  employé passe bien par `hr.employee.write()` et déclenche la synchro ; une
  modification faite sur la version elle-même (nouvelle version, flux contrat)
  ne la déclenche pas. Un commercial arrivé par ce chemin part au prochain
  changement d'un autre champ suivi, par le bouton de la fiche ou par *Mettre
  tous les commerciaux en file*.
