# Synchronisation des clients vers IziQo — spécification

Le module `fma_iziqo_sync` a été retiré du dépôt le 2 septembre 2026 sans
jamais avoir été mis en production. Il n'existait que sur `Staging_19`, et
aucun autre module n'en dépendait.

Ce document conserve ce qu'il faisait, pour que la connaissance ne parte pas
avec le code. Il est aussi la référence si la synchronisation est reprise —
notamment dans le cadre d'un déploiement chez une autre société du groupe.

## Ce que le module faisait

Il poussait une fiche client Odoo vers l'API REST d'IziQo dès sa création ou
sa modification, sans attendre l'export quotidien. `POST` à la création,
`PATCH` à la modification. Seules les sociétés portant un SIRET étaient
concernées.

## Points de conception à retenir

Quatre choix méritent d'être repris tels quels dans toute réimplémentation.

**L'envoi a lieu après le commit de la transaction.** L'utilisateur qui
enregistre une fiche n'attend jamais l'API et n'est jamais bloqué si elle
répond mal. C'est la différence entre une synchronisation qui gêne la saisie
et une qui se fait oublier.

**Une file d'attente persistante**, modèle `iziqo.sync.job`, avec un nombre
maximal de tentatives et un journal des envois. Un échec réseau ne perd pas
la mise à jour : elle reste en file.

**Un cron de rattrapage** reprend les envois en échec. Sans lui, une coupure
d'API laisse des fiches désynchronisées sans que personne ne le sache.

**Un bouton « Synchroniser avec IziQo »** sur la fiche client, pour traiter
les clients historiques un par un sans attendre une reprise de masse.

## Paramétrage prévu

Tout était réglable dans les Paramètres, sans redéploiement :

| Réglage | Rôle |
|---|---|
| URL de l'API | point d'entrée IziQo |
| Type d'authentification | clé d'API ou identifiant / mot de passe |
| En-tête de la clé | nom de l'en-tête HTTP portant la clé |
| Champ identifiant | quelle donnée Odoo sert de clé de rapprochement |
| Périmètre | quels clients sont concernés |
| Temps réel | envoi immédiat ou différé au cron seul |
| Délai d'expiration | secondes avant abandon d'un appel |
| Tentatives maximales | avant abandon définitif d'un envoi |
| Rétention du journal | jours de conservation des envois |

## Pourquoi il a été retiré

Le module n'a jamais été déployé. Le maintenir sur une branche de
développement sans le livrer créait un écart permanent entre les
environnements, et faisait croire à une intégration en service alors qu'elle
ne l'était pas.

Le code reste accessible dans l'historique Git jusqu'au commit précédant sa
suppression.
