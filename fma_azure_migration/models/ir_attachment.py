# -*- coding: utf-8 -*-
"""Migration des pieces jointes vers Azure, par paquets, sans surveillance.

LE PROBLEME QUE CE MODULE RESOUT N'EST PAS TECHNIQUE, IL EST HUMAIN. La
meme boucle, lancee depuis l'onglet Shell d'odoo.sh, marche parfaitement —
mais elle vit dans le websocket du navigateur : changer d'ecran la coupe. Sur
quarante gigaoctets a 1,3 Mo/s, cela represente huit heures passees a
regarder defiler des lignes sans rien pouvoir faire d'autre.

Ici, c'est le worker cron qui travaille. Le navigateur peut etre ferme, le
poste en veille, la session expiree : la migration avance.

TROIS BORNES A CHAQUE PASSAGE, et chacune pour une raison distincte :

* un NOMBRE de fichiers, pour que le paquet reste previsible ;
* une DUREE, parce qu'un cron trop long se fait interrompre par la
  plate-forme au milieu d'un lot ;
* une CROISSANCE MEMOIRE, parce que deplacer un fichier le fait passer
  entier par la memoire du processus — deux fois, octets puis base64 — et
  que le worker est un processus qui dure. Le passage s'arrete avant de
  gener les autres crons ; le suivant repart cinq minutes plus tard.

Ces trois bornes sont des parametres systeme : les regler ne demande pas de
redeploiement.

Quand il ne reste plus rien a deplacer, l'action planifiee SE DESACTIVE. Il
n'y a donc pas de cron oublie qui tourne a vide, et le module peut etre
desinstalle.
"""
import logging
import os
import time

from odoo import api, models

from odoo.addons.fs_attachment.models.ir_attachment import clean_fs

_logger = logging.getLogger(__name__)

#: Identifiant de l'action planifiee, qu'on desactive en fin de travail.
CRON_XMLID = "fma_azure_migration.ir_cron_fma_azure"

#: Reglages, et leur valeur par defaut. Parametres systeme pour pouvoir les
#: changer en production sans build : une migration se pilote pendant qu'elle
#: tourne, pas avant.
REGLAGES = {
    # 100 Ko. En dessous, l'ecriture coute plus que la place gagnee — et la
    # regle de la fiche de stockage renverrait de toute facon les petites
    # images vers la BASE, ce qui est l'inverse du but.
    "plancher": ("fma_azure.plancher", 102400),
    # 0 = pas de plafond. Sert a traiter les tailles par bandes.
    "plafond": ("fma_azure.plafond", 0),
    # Fichiers par passage.
    "limite": ("fma_azure.limite", 300),
    # Secondes par passage. Le cron passe toutes les 5 minutes : on s'arrete
    # bien avant, pour ne jamais chevaucher le passage suivant.
    "secondes": ("fma_azure.secondes", 240),
    # Commit (et nettoyage du filestore) tous les N fichiers.
    "lot": ("fma_azure.lot", 20),
    # Croissance memoire toleree sur UN passage, en Mo.
    "memoire": ("fma_azure.memoire_mo", 600),
}

#: Types que la fiche de stockage garde en base pour la rapidite des vues.
#: Les deplacer ne les enverrait pas sur Azure, il les enverrait en BASE.
TYPES_EN_BASE = ("application/javascript", "text/javascript", "text/css")


def memoire_mo():
    """La memoire occupee par le processus, en Mo. Zero si illisible."""
    try:
        with open("/proc/self/statm") as fichier:
            pages = int(fichier.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 1024.0 ** 2
    except Exception:  # noqa: BLE001 — une mesure ne doit jamais bloquer
        return 0.0


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    # ------------------------------------------------------------------
    # Reglages et perimetre
    # ------------------------------------------------------------------
    @api.model
    def _fma_azure_reglages(self):
        parametres = self.env["ir.config_parameter"].sudo()
        valeurs = {}
        for nom, (cle, defaut) in REGLAGES.items():
            brut = parametres.get_param(cle)
            try:
                valeurs[nom] = int(brut) if brut not in (None, False, "") \
                    else defaut
            except (TypeError, ValueError):
                _logger.warning(
                    "Migration Azure : parametre %s illisible (%r), valeur "
                    "par defaut %s", cle, brut, defaut)
                valeurs[nom] = defaut
        return valeurs

    @api.model
    def _fma_azure_domaine(self, code, reglages):
        """Ce qui reste a deplacer.

        Le « res_field = False OU res_field != False » est obligatoire : sans
        lui, Odoo ajoute d'office « res_field = False » et les pieces jointes
        de champs binaires sortent du lot sans qu'on le voie.

        Les paquets d'actifs web (ir.ui.view) sont ecartes par le MODELE : la
        regle de la fiche de stockage garde en base le JavaScript et le CSS,
        mais pas les fichiers qui les accompagnent — et ceux-la n'ont rien a
        gagner a partir sur Azure, puisqu'ils sont regeneres a chaque
        reconstruction des actifs.
        """
        domaine = [
            "|", ("store_fname", "=", False),
                 ("store_fname", "not like", "%s://" % code),
            ("file_size", ">", reglages["plancher"]),
            ("mimetype", "not in", list(TYPES_EN_BASE)),
            ("res_model", "!=", "ir.ui.view"),
            "|", ("res_field", "=", False), ("res_field", "!=", False),
        ]
        if reglages["plafond"]:
            domaine.append(("file_size", "<=", reglages["plafond"]))
        return domaine

    # ------------------------------------------------------------------
    # Journal : ce que le metier lit sans ouvrir les traces d'odoo.sh
    # ------------------------------------------------------------------
    @api.model
    def _fma_azure_journal(self, titre, message, niveau="INFO"):
        _logger.info("Migration Azure : %s — %s", titre, message)
        try:
            with self.env.registry.cursor() as cr:
                api.Environment(cr, self.env.uid, {})["ir.logging"].sudo(
                ).create({
                    "name": "fma_azure_migration",
                    "type": "server",
                    "dbname": self.env.cr.dbname,
                    "level": niveau,
                    "message": message,
                    "path": "migration Azure",
                    "func": titre,
                    "line": 1,
                })
        except Exception:  # noqa: BLE001 — le journal ne bloque jamais
            _logger.exception("Migration Azure : journal non ecrit")

    @api.model
    def _fma_azure_desactiver(self, raison):
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron and cron.sudo().active:
            cron.sudo().active = False
        self._fma_azure_journal("Action planifiee desactivee", raison)

    # ------------------------------------------------------------------
    # Le passage
    # ------------------------------------------------------------------
    @api.model
    def fma_migrer_vers_azure(self):
        """Deplace un paquet de pieces jointes vers le stockage par defaut.

        Appelee par l'action planifiee, toutes les cinq minutes. Chaque appel
        fait ce qu'il peut dans ses bornes, commite au fur et a mesure, et
        rend la main. Rien n'est jamais a rattraper : le perimetre est
        « ce qui n'est pas encore sur Azure », donc le travail deja fait
        n'est jamais refait.
        """
        debut = time.time()
        memoire_depart = memoire_mo()

        code = self.env["fs.storage"].sudo(
        ).get_default_storage_code_for_attachments()
        if not code:
            self._fma_azure_desactiver(
                "Aucun stockage par defaut : rien ne peut etre migre. Cochez "
                "« Use as default for attachments » sur la fiche Azure, puis "
                "reactivez l'action planifiee.")
            return False

        reglages = self._fma_azure_reglages()
        Att = self.with_context(prefetch_fields=False)
        # Du PLUS PETIT au plus gros : la memoire d'un passage suit la taille
        # des fichiers qu'il touche, et un passage court doit rester sans
        # risque. Les gros finiront par venir, par bandes.
        ids = Att.search(
            self._fma_azure_domaine(code, reglages),
            order="file_size", limit=reglages["limite"]).ids
        if not ids:
            self._fma_azure_desactiver(
                "Plus aucune piece jointe a deplacer dans le perimetre "
                "(plancher %s octets, plafond %s). Le module peut etre "
                "desinstalle." % (reglages["plancher"],
                                  reglages["plafond"] or "aucun"))
            return True

        tailles = dict(self._fma_azure_tailles(ids))
        a_nettoyer, deplaces, sautes, octets = [], 0, 0, 0
        arret = "paquet termine"

        for rang, aid in enumerate(ids, 1):
            try:
                with self.env.cr.savepoint():
                    # Personne d'autre ne doit tenir cette ligne : un fichier
                    # deplace sous les pieds d'un utilisateur en train
                    # d'ecrire dessus serait perdu pour lui. NOWAIT : on
                    # saute, on ne fait pas la queue — le passage suivant le
                    # reprendra.
                    self.env.cr.execute(
                        "SELECT id FROM ir_attachment WHERE id = %s "
                        "FOR UPDATE NOWAIT", (aid,), log_exceptions=False)
                    # Sans ce vidage, la premiere lecture de « datas »
                    # calculerait le champ pour TOUT le paquet, donc lirait
                    # des centaines de fichiers d'un coup.
                    self.env.clear()
                    chemin = Att.browse(aid)._move_attachment_to_store()
                    deplaces += 1
                    octets += tailles.get(aid, 0)
                    if chemin:
                        a_nettoyer.append(chemin)
            except Exception as erreur:  # noqa: BLE001 — un fichier ne bloque pas
                sautes += 1
                _logger.info(
                    "Migration Azure : piece jointe %s sautee (%s)",
                    aid, type(erreur).__name__)

            dernier = rang == len(ids)
            if rang % reglages["lot"] and not dernier:
                continue

            # Le commit D'ABORD : on ne supprime du filestore que ce qui est
            # deja enregistre comme etant sur Azure.
            self.env.cr.commit()
            clean_fs(a_nettoyer)
            a_nettoyer = []

            ecoule = time.time() - debut
            croissance = memoire_mo() - memoire_depart
            if dernier:
                break
            if ecoule > reglages["secondes"]:
                arret = "duree du passage atteinte (%.0f s)" % ecoule
                break
            if croissance > reglages["memoire"]:
                arret = "memoire du passage atteinte (+%.0f Mo)" % croissance
                break

        ecoule = max(time.time() - debut, 0.001)
        reste = Att.search_count(self._fma_azure_domaine(code, reglages))
        self._fma_azure_journal(
            "Passage termine : %s fichiers, %.2f Go" % (
                deplaces, octets / 1024.0 ** 3),
            "%s. %s deplaces, %s sautes, %.2f Go en %.0f s (%.2f Mo/s). "
            "Memoire : %.0f Mo (+%.0f). Reste %s fichiers dans le perimetre."
            % (arret, deplaces, sautes, octets / 1024.0 ** 3, ecoule,
               (octets / 1024.0 ** 2) / ecoule, memoire_mo(),
               memoire_mo() - memoire_depart, reste))
        return True

    @api.model
    def _fma_azure_tailles(self, ids):
        """[(id, taille)] en une requete : le volume dit l'avancement, et le
        lire apres le deplacement ne donnerait plus rien d'utilisable."""
        self.env.cr.execute(
            "SELECT id, COALESCE(file_size, 0) FROM ir_attachment "
            "WHERE id IN %s", (tuple(ids),))
        return self.env.cr.fetchall()
