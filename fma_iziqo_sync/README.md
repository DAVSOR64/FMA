# Iziqo : synchronisation des clients

Pousse une fiche client Odoo (`res.partner`) vers la base clients de l'application
Iziqo **dès sa création ou sa modification**, en remplacement / complément de
l'export manuel « Fichier clients Iziqo » (`fma_custom`) et de l'export
quotidien TXT/SFTP (`fma_customer_export`).

Contrat : **API REST**. `POST {url}` à la création, `PATCH {url}/{identifiant}`
à la modification. Périmètre : **uniquement les sociétés ayant un SIRET**.

## Fonctionnement

1. `create()` / `write()` sur `res.partner` : si la fiche est dans le périmètre
   (société **avec SIRET**) et qu'un champ suivi a changé, un job
   `iziqo.sync.job` est créé. Une société sans SIRET est ignorée, puis
   envoyée automatiquement dès que le SIRET est renseigné (champ suivi).
2. L'envoi HTTP est déclenché **après le commit** de la transaction, dans un
   curseur dédié : l'utilisateur qui enregistre n'attend jamais Iziqo et une
   erreur d'API ne fait jamais échouer l'enregistrement.
3. En cas d'échec, le job est relancé par le cron *Iziqo - Envoi des fiches
   clients en attente* (toutes les 10 min) avec un délai croissant
   (5 min, 15 min, 1 h, 4 h, 24 h) puis passe en état *En échec*.
4. Si le `POST` répond **409** (client déjà présent côté Iziqo, cas courant au
   chargement initial), le job bascule immédiatement en `PATCH` sans attendre
   le cron.

Modification d'une adresse de livraison ou de facturation enfant : c'est la
société parente qui est renvoyée, puisque c'est elle qui porte les colonnes
« … livraison » du payload.

## Configuration

*Paramètres > Iziqo*

| Paramètre | Clé `ir.config_parameter` | Rôle |
|---|---|---|
| URL de la collection clients | `iziqo_sync.api_url` | `POST` à la création, `PATCH {url}/{identifiant}` à la modification. **Vide = synchronisation désactivée** (aucun job créé) |
| Identifiant de la ressource | `iziqo_sync.identifier_field` | `siret` (défaut), `ref` (code client) ou `id` Odoo, placé dans l'URL du `PATCH`. Repli sur le SIRET puis l'ID Odoo si la valeur est vide |
| Authentification | `iziqo_sync.auth_type` | `none`, `bearer`, `apikey` (en-tête paramétrable), `basic` |
| Périmètre | `iziqo_sync.scope` | `customers_and_prospects` (défaut), `customers`, `flagged` |
| Envoi immédiat | `iziqo_sync.realtime` | Décoché : tout passe par le cron |
| Timeout / tentatives | `iziqo_sync.timeout`, `iziqo_sync.max_attempts` | 15 s et 5 tentatives par défaut |
| Conservation du journal | `iziqo_sync.keep_days` | Purge des envois réussis au-delà de 30 jours (cron quotidien) |

Le bouton **Tester l'accès à l'API** fait un `GET` sur la collection : en
lecture seule, il ne crée rien dans Iziqo.

### Périmètres

Condition commune à tous les périmètres : **être une société et avoir un
SIRET** (`company_registry` en v19, avec repli sur les anciens champs `siret`
et `x_studio_siret`). C'est la clé de rapprochement côté Iziqo.

- `customers_and_prospects` (défaut) : sociétés qui ne sont pas des
  fournisseurs purs. C'est le seul périmètre qui envoie une fiche **dès sa
  création**, `customer_rank` ne passant à 1 qu'à la première vente.
- `customers` : `customer_rank > 0`, périmètre identique à l'export CSV
  historique.
- `flagged` : uniquement les sociétés dont la case **Iziqo**
  (`x_studio_iziqo_1`) est cochée.

Exclusion au cas par cas : case **Exclure de la synchro Iziqo** sur la fiche
(onglet *Ventes & Achats*).

## Payload

Les clés reprennent les colonnes du fichier CSV Iziqo historique pour que le
mapping côté Iziqo reste inchangé :

```json
{
  "operation": "create",
  "odoo_id": 4213,
  "code_client": "C0042",
  "nom": "MENUISERIE DUPONT",
  "telephone": "+33 2 40 00 00 00",
  "email": "contact@dupont.fr",
  "siret": "12345678900012",
  "tva": "FR12345678900",
  "adresse": "12 rue des Ateliers",
  "cp": "44000",
  "ville": "NANTES",
  "pays": "France",
  "code_pays": "FR",
  "commercial": "Pierre ROYER",
  "id_employe_commercial": "37",
  "adresse_livraison": "ZA du Chêne",
  "cp_livraison": "44300",
  "ville_livraison": "NANTES",
  "pays_livraison": "France",
  "actif": true,
  "date_modification": "2026-08-27 09:12:44"
}
```

Pour ajouter un champ : surcharger `res.partner._iziqo_payload()`. Pour changer
le périmètre : surcharger `res.partner._iziqo_is_eligible()`.

Une fiche archivée est envoyée comme une modification avec `"actif": false` ;
les suppressions ne sont pas propagées.

## Clients historiques

Deux façons de rattraper les fiches jamais synchronisées :

- **Bouton « Synchroniser avec Iziqo »** dans l'en-tête de la fiche client, ou
  action **Synchroniser vers Iziqo** du menu ⚙️ sur une sélection de la liste.
  Envoi immédiat, et **hors périmètre automatique** : une fiche qui ne remplit
  pas le `scope` configuré est quand même envoyée. Seules conditions : société,
  SIRET renseigné, fiche non exclue. Sans SIRET, le bouton refuse en nommant
  les fiches concernées.
- **Mettre tout le périmètre en file** dans les réglages : met en file toutes
  les sociétés du périmètre et laisse le cron envoyer. La notification indique
  combien de sociétés ont été écartées faute de SIRET.

## Supervision

*Paramètres > Synchronisation Iziqo > File d'attente et journal* : état,
nombre de tentatives, code HTTP, réponse d'Iziqo et payload envoyé, avec
boutons **Relancer** / **Annuler**. La fiche client affiche la date, le statut
et l'erreur du dernier envoi.

## Garde-fous

- Import de fichier ou action de masse touchant plus de 20 fiches : l'envoi
  immédiat est désactivé, le cron prend le relais (100 jobs par passage).
- Les jobs sont verrouillés (`FOR UPDATE SKIP LOCKED`) : pas de double envoi
  entre l'envoi post-commit et le cron.
- 5 échecs réseau consécutifs interrompent le lot en cours.
