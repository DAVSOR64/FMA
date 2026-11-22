# FMA — Migration des pièces jointes vers Azure

**Module jetable.** Il vide le filestore vers le stockage Azure, par paquets,
dans le worker cron d'odoo.sh. Une fois le travail fait, l'action planifiée se
désactive seule et le module se désinstalle.

Il ne crée aucun champ, aucune vue, aucune donnée métier : une méthode sur
`ir.attachment` et une action planifiée, livrée **inactive**.

## Pourquoi un module plutôt que l'onglet Shell

La même boucle tourne très bien depuis le Shell d'odoo.sh — mais elle vit dans
le websocket du navigateur : changer d'écran la coupe. Sur 40 Go à 1,3 Mo/s,
cela fait huit heures à tenir un onglet ouvert. Ici, le navigateur n'a aucun
rôle.

## Mode d'emploi

1. **Avant tout**, sur le conteneur Azure : activer la **suppression réversible
   (soft delete)** et le **versioning**. Après la migration, la sauvegarde
   odoo.sh ne contient plus ces fichiers, et `autovacuum_gc` de la fiche de
   stockage supprime le blob d'une pièce jointe supprimée dans Odoo.

2. Vérifier que la fiche de stockage Azure porte bien
   **« Use as default for attachments »**. Sans elle, la migration s'arrête
   d'elle-même en le disant dans le journal.

3. Installer le module (*Apps → Mettre à jour la liste des applications*).

4. Facultatif : régler les bornes dans *Paramètres → Technique → Paramètres
   système*. Aucun redéploiement n'est nécessaire.

   | Paramètre | Défaut | Rôle |
   |---|---|---|
   | `fma_azure.plancher` | `102400` | taille minimale (100 Ko) |
   | `fma_azure.plafond` | `0` | taille maximale, `0` = aucune |
   | `fma_azure.limite` | `300` | fichiers par passage |
   | `fma_azure.secondes` | `240` | durée maximale d'un passage |
   | `fma_azure.lot` | `20` | commit tous les N fichiers |
   | `fma_azure.memoire_mo` | `600` | croissance mémoire tolérée par passage |

5. **Activer** l'action planifiée *« FMA - MIGRATION : pièces jointes vers
   Azure »* (*Paramètres → Technique → Actions planifiées*). Elle passe toutes
   les cinq minutes.

6. Suivre l'avancement dans *Paramètres → Technique → Journalisation*, en
   filtrant sur `fma_azure_migration`. Chaque passage écrit une ligne : nombre
   de fichiers, volume, débit, mémoire, et **ce qu'il reste**.

7. Quand le journal annonce « Plus aucune pièce jointe à déplacer », l'action
   est déjà désactivée. Désinstaller le module.

## Ce qui n'est jamais déplacé

- Les fichiers de moins de 100 Ko : la règle `force_db_for_default_attachment_rules`
  de la fiche de stockage les renverrait vers la **base**, soit l'inverse du but.
- Le JavaScript et le CSS, pour la même raison.
- Les pièces jointes de `ir.ui.view` — les paquets `/web/assets` et leurs
  fichiers compagnons. Ils sont régénérés à chaque reconstruction des actifs.

## Les garde-fous

- **Reprenable** : le périmètre est « ce qui n'est pas encore sur Azure ». Un
  passage interrompu ne laisse rien à rattraper.
- **Commit par lot**, et le filestore local n'est nettoyé qu'**après** le
  commit : on ne supprime jamais un fichier qui ne serait pas déjà enregistré
  comme étant sur Azure.
- **`FOR UPDATE NOWAIT`** : une pièce jointe qu'un utilisateur est en train de
  modifier est sautée, et reprise au passage suivant.
- **Trois bornes par passage** — nombre, durée, croissance mémoire — pour ne
  jamais gêner les autres crons ni se faire interrompre au milieu d'un lot.
