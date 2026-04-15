# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class MrpBulkResequenceWizard(models.TransientModel):
    _name = "mrp.bulk.resequence.wizard"
    _description = "Assistant de réordonnancement FMA"

    production_ids = fields.Many2many("mrp.production", string="OF")
    operation_order_text = fields.Text(
        string="Ordre appliqué",
        readonly=True,
        default=lambda self: "Débit FMA\nCU (Banc) FMA\nUsinage FMA\nMontage FMA\nVitrage FMA\nEmballage FMA",
    )
    skip_started_info = fields.Char(
        string="Règle",
        readonly=True,
        default="Seuls les OF non lancés sont modifiés. Les OF déjà démarrés ou terminés sont ignorés.",
    )

    def action_apply(self):
        self.ensure_one()
        if not self.production_ids:
            raise UserError(_("Aucun OF sélectionné."))
        return self.production_ids.action_bulk_resequence_fma()
