# -*- coding: utf-8 -*-
"""Declaration de fabrication au scan, ordre par ordre.

Le lot a deja scinde les assemblages : un ordre = une menuiserie = un numero
de serie. Declarer au scan revient donc a terminer UN ordre, en entier, avec
le numero qu'il porte deja — sans reliquat, sans ecran des numeros de serie.

Tout passe par les methodes standard (button_start, button_finish,
button_mark_done). Si Odoo refuse — composant suivi sans numero, controle
qualite en attente, operateur non identifie —, le refus est affiche au poste
et note dans le fil de l'ordre. Rien n'est force.
"""
import logging

from odoo import _, models
from odoo.exceptions import UserError

from .stock_lot import fma_message

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # ------------------------------------------------------------------
    # Etiquettes
    # ------------------------------------------------------------------
    def _fma_ordre_etiquettes(self):
        """Dans l'ordre de la liste de quincaillerie : ligne de lot, puis
        rang de l'ordre. Le paquet d'etiquettes se pose ainsi sur les
        casiers sans avoir a chercher."""
        return self.sorted(lambda mo: (
            mo.lot_fabrication_id.id or 0,
            mo.lot_line_id.sequence or 0,
            mo.lot_line_id.id or 0,
            mo.id,
        ))

    def _fma_etiquettes(self):
        """Une etiquette par menuiserie. Un ordre sans numero de serie —
        article non suivi — recoit une etiquette a son propre numero : le
        poste de scan sait aussi le lire."""
        etiquettes = []
        for ordre in self._fma_ordre_etiquettes():
            if ordre.state == "cancel":
                continue
            if ordre.lot_producing_ids:
                for serie in ordre.lot_producing_ids:
                    etiquettes.append(serie._fma_etiquette_vals(ordre))
                continue
            commande = ordre.lot_sale_order_id
            produit = ordre.product_id
            Serie = self.env["stock.lot"]
            etiquettes.append({
                "serie": ordre.name,
                "casier": "",
                "repere": (produit.default_code or "").rpartition("_")[2]
                or produit.default_code or "",
                "designation": (produit.display_name or "")[:90],
                "dimensions": "",
                "affaire": "",
                "commande": commande.name or ordre.origin or "",
                "client": commande.partner_id.display_name or "",
                "chantier": "",
                "lot": ordre.lot_fabrication_id.display_name or "",
                "of": ordre.name,
                "societe": ordre.company_id.name,
                "sav_url": "",
                "barcode_src": Serie._fma_image(
                    "Code128", ordre.name, width=900, height=140, quiet=1),
                "qr_src": "",
            })
        return etiquettes

    def action_fma_imprimer_etiquettes(self):
        return self.env.ref(
            "fma_etiquette_scan.action_report_etiquette_of"
        ).report_action(self._fma_ordre_etiquettes(), config=False)

    # ------------------------------------------------------------------
    # Declaration
    # ------------------------------------------------------------------
    def _fma_prochaine_operation(self):
        """La premiere operation qui reste a faire, dans l'ordre de la
        gamme."""
        self.ensure_one()
        return self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel"))[:1]

    def _fma_refus(self, erreur, geste):
        """Odoo a refuse : on le dit au poste, et on le note sur l'ordre.

        La note est posee APRES le retour au point de sauvegarde, elle ne
        disparait donc pas avec ce qui a ete annule.
        """
        self.ensure_one()
        texte = str(erreur.args[0]) if erreur.args else str(erreur)
        try:
            self.message_post(body=_(
                "Scan atelier — %(geste)s refusé : %(erreur)s",
                geste=geste, erreur=texte))
        except Exception:  # noqa: BLE001 — la note ne doit jamais bloquer
            _logger.exception("Note de refus sur %s", self.display_name)
        return fma_message("danger", _(
            "%(of)s : %(erreur)s", of=self.name, erreur=texte))

    def _fma_declarable(self):
        """Un message si l'ordre ne peut pas etre declare, sinon rien."""
        self.ensure_one()
        if self.state == "done":
            return fma_message("info", _(
                "%(of)s est déjà terminé.", of=self.name))
        if self.state == "cancel":
            return fma_message("danger", _(
                "%(of)s est annulé.", of=self.name))
        if self.state == "draft":
            return fma_message("danger", _(
                "%(of)s est encore en brouillon : confirmez-le d'abord.",
                of=self.name))
        return None

    def fma_scan_pointer_operation(self):
        """Fait avancer la gamme d'un cran.

        Premier scan : l'operation suivante demarre, le chronometre standard
        tourne. Second scan : elle se termine, avec la duree reellement
        ecoulee. C'est un pointage, pas une saisie de temps.
        """
        self.ensure_one()
        blocage = self._fma_declarable()
        if blocage:
            return blocage
        operation = self._fma_prochaine_operation()
        if not operation:
            return fma_message("info", _(
                "%(of)s : toutes les opérations sont terminées. Déclarez "
                "la menuiserie terminée.", of=self.name))
        try:
            with self.env.cr.savepoint():
                if operation.state == "progress":
                    operation.button_finish()
                    suivante = self._fma_prochaine_operation()
                    return fma_message("success", _(
                        "%(op)s terminée (%(duree)d min)%(suite)s",
                        op=operation.name,
                        duree=round(operation.duration),
                        suite=_(" — reste : %s", suivante.name)
                        if suivante else _(" — gamme terminée")))
                operation.button_start()
                return fma_message("success", _(
                    "%(op)s démarrée sur %(of)s.",
                    op=operation.name, of=self.name))
        except UserError as erreur:
            return self._fma_refus(erreur, _("pointage de l'opération"))

    def fma_scan_terminer(self):
        """Declare la menuiserie terminee.

        Les operations restantes sont soldees par la methode standard
        « marquer comme fait » : une operation chronometree garde son temps
        reel, une operation jamais demarree prend sa duree prevue. Puis
        l'ordre est cloture avec le numero de serie qu'il porte deja.
        """
        self.ensure_one()
        blocage = self._fma_declarable()
        if blocage:
            return blocage
        if self.product_tracking == "serial" and not self.lot_producing_ids:
            return fma_message("danger", _(
                "%(of)s n'a pas de numéro de série : relancez « Compléter "
                "les OF » sur le lot.", of=self.name))
        try:
            with self.env.cr.savepoint():
                self.workorder_ids.filtered(
                    lambda w: w.state not in ("done", "cancel")
                ).action_mark_as_done()
                self.qty_producing = self.product_qty
                self._set_qty_producing()
                retour = self.button_mark_done()
                if self.state != "done":
                    # Odoo n'a pas refuse : il demande une confirmation dans
                    # un assistant (ecart de consommation, reliquat). Au
                    # poste de scan personne ne la donnera : on annule et on
                    # renvoie vers l'ordre.
                    nom = (retour.get("name") if isinstance(retour, dict)
                           else "") or _("confirmation")
                    raise UserError(_(
                        "Odoo demande une validation manuelle (%(nom)s). "
                        "Ouvrez l'ordre pour la donner.", nom=nom))
        except UserError as erreur:
            return self._fma_refus(erreur, _("déclaration de fin"))
        serie = self.lot_producing_ids[:1].name or self.name
        return fma_message("success", _(
            "Menuiserie %(serie)s déclarée terminée (%(of)s).",
            serie=serie, of=self.name))
