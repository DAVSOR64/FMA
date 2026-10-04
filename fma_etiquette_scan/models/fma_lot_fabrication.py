# -*- coding: utf-8 -*-
"""Le lot : impression du paquet d'etiquettes et avancement a l'unite."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FmaLotFabrication(models.Model):
    _inherit = "fma.lot.fabrication"

    fma_unites_total = fields.Integer(
        string="Menuiseries à fabriquer", compute="_compute_fma_avancement")
    fma_unites_terminees = fields.Integer(
        string="Menuiseries terminées", compute="_compute_fma_avancement")
    fma_avancement = fields.Float(
        string="Avancement", compute="_compute_fma_avancement")
    fma_avancement_texte = fields.Char(
        string="Terminées", compute="_compute_fma_avancement")

    def _fma_assemblages(self):
        self.ensure_one()
        return self.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state != "cancel")

    @api.depends("production_ids.state", "production_ids.lot_production_type")
    def _compute_fma_avancement(self):
        """Un ordre par menuiserie : l'avancement du lot se compte en
        ordres termines, sans calcul de quantite."""
        for lot in self:
            ordres = lot._fma_assemblages()
            total = len(ordres)
            faits = len(ordres.filtered(lambda p: p.state == "done"))
            lot.fma_unites_total = total
            lot.fma_unites_terminees = faits
            lot.fma_avancement = 100.0 * faits / total if total else 0.0
            lot.fma_avancement_texte = "%s / %s" % (faits, total)

    def action_fma_imprimer_etiquettes(self):
        self.ensure_one()
        ordres = self._fma_assemblages()
        if not ordres:
            raise UserError(_(
                "Le lot %s n'a pas encore d'ordre d'assemblage : générez "
                "les OF, ce sont eux qui posent les numéros de série.",
                self.display_name))
        return ordres.action_fma_imprimer_etiquettes()

    def action_fma_poste_scan(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Déclaration de fabrication"),
            "res_model": "fma.poste.scan",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_mode": "declarer",
                "default_lot_fabrication_id": self.id,
            },
        }
