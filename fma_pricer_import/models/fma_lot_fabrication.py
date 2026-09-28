# -*- coding: utf-8 -*-
"""Rattachement d'un lot Odoo au lot du pricer, et suivi des manques d'import."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FmaLotFabrication(models.Model):
    _inherit = "fma.lot.fabrication"

    pricer_lot_key = fields.Char(
        string="Cle du lot pricer",
        index=True,
        copy=False,
        help="Identifiant du lot chez le pricer (GUID de la phase LOGIKAL). "
        "Sert a retrouver le lot lors d'un reimport : redeposer le fichier "
        "d'un lot corrige met a jour ce lot-la et ne touche pas aux autres.",
    )
    import_issues = fields.Text(
        string="Manques a l'import",
        copy=False,
        readonly=True,
        help="Ce que le fichier du pricer decrivait et qui n'a pas pu etre "
        "repris dans Odoo, faute d'article ou de ligne de devis "
        "correspondante.",
    )
    import_incomplete = fields.Boolean(
        string="Import incomplet",
        compute="_compute_import_incomplete",
        store=True,
        help="Le lot a ete cree, mais une partie de ce que decrivait le "
        "fichier manque. Il ne peut pas etre confirme tant que le manque "
        "n'est pas leve ou assume.",
    )

    debit_length = fields.Float(
        string="Besoin debit (m)",
        compute="_compute_debit_lengths",
        store=True,
        digits="Product Unit of Measure",
        help="Metres lineaires de profiles necessaires aux menuiseries du lot.",
    )
    purchased_length = fields.Float(
        string="Barres achetees (m)",
        compute="_compute_debit_lengths",
        store=True,
        digits="Product Unit of Measure",
    )
    loss_rate = fields.Float(
        string="Chute (%)",
        compute="_compute_debit_lengths",
        store=True,
        digits=(5, 1),
        help="Ecart entre les barres sorties du stock a l'OF de debit et les "
        "metres qui entrent en en-cours. C'est la chute reelle du lot.",
    )

    @api.depends(
        "material_line_ids.debit_length", "material_line_ids.purchased_length"
    )
    def _compute_debit_lengths(self):
        for lot in self:
            besoin = sum(lot.material_line_ids.mapped("debit_length"))
            achete = sum(lot.material_line_ids.mapped("purchased_length"))
            lot.debit_length = besoin
            lot.purchased_length = achete
            lot.loss_rate = 100.0 * (achete - besoin) / achete if achete else 0.0

    @api.depends("import_issues")
    def _compute_import_incomplete(self):
        for lot in self:
            lot.import_incomplete = bool(lot.import_issues)

    def action_confirm(self):
        """Refuse de confirmer un lot dont l'import est incomplet.

        L'import, lui, ne bloque pas : un article introuvable n'invalide ni le
        lot ni son affectation. Mais confirmer un lot dont le besoin matiere
        est partiel reviendrait a lancer les achats avec des barres en moins —
        c'est la que le blocage a un sens.
        """
        blocked = self.filtered(
            lambda lot: lot.state == "draft" and lot.import_incomplete
        )
        if blocked:
            raise UserError(
                _(
                    "Ces lots ont ete importes de facon incomplete :\n\n"
                    "%(detail)s\n\n"
                    "Corrigez les articles manquants et redeposez le fichier "
                    "du lot, ou utilisez « Ignorer les manques » si le besoin "
                    "matiere a ete complete a la main.",
                    detail="\n\n".join(
                        "%s :\n%s" % (lot.display_name, lot.import_issues)
                        for lot in blocked
                    ),
                )
            )
        return super().action_confirm()

    def action_ignore_import_issues(self):
        """Assume les manques : le besoin matiere a ete complete a la main."""
        for lot in self:
            if not lot.import_issues:
                continue
            lot.message_post(
                body=_(
                    "Manques d'import assumes :<br/><pre>%s</pre>",
                    lot.import_issues,
                )
            )
            lot.import_issues = False
        return True
