# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpRecalcPlanifWizard(models.TransientModel):
    _name = "mrp.recalc.planif.wizard"
    _description = "Wizard recalcul planification"

    production_id = fields.Many2one("mrp.production", required=True, readonly=True)
    preview_html = fields.Html(string="Prévisualisation", sanitize=False, readonly=True)
    po_html = fields.Html(string="PO associées", sanitize=False, readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        production_id = self.env.context.get("default_production_id")
        if not production_id:
            return res

        production = self.env["mrp.production"].browse(production_id).exists()
        if not production:
            return res

        simulation = production._fma_build_planning_result()
        preview_html, po_html = self._build_preview_html(production, simulation)

        res["production_id"] = production.id
        res["preview_html"] = preview_html
        res["po_html"] = po_html
        return res

    def _build_preview_html(self, production, simulation):
        def fmt(value):
            return production._fma_format_date(value)

        preview_html = """
        <div style="width:100%%; max-width:1100px;">
            <table style="width:100%%; border-collapse:collapse; margin-bottom:18px;">
                <tr>
                    <td style="width:35%%; padding:10px; border:1px solid #d9d9d9; font-weight:600;">Date livraison</td>
                    <td style="padding:10px; border:1px solid #d9d9d9;">{delivery}</td>
                </tr>
                <tr>
                    <td style="padding:10px; border:1px solid #d9d9d9; font-weight:600;">Date fin OF saisie</td>
                    <td style="padding:10px; border:1px solid #d9d9d9;">{custom_finish}</td>
                </tr>
                <tr>
                    <td style="padding:10px; border:1px solid #d9d9d9; font-weight:600;">Nouvelle date début OF</td>
                    <td style="padding:10px; border:1px solid #d9d9d9;">{new_start}</td>
                </tr>
                <tr>
                    <td style="padding:10px; border:1px solid #d9d9d9; font-weight:600;">Nouvelle date fin OF</td>
                    <td style="padding:10px; border:1px solid #d9d9d9;">{new_finish}</td>
                </tr>
            </table>
        </div>
        """.format(
            delivery=fmt(simulation.get("delivery_dt")),
            custom_finish=fmt(simulation.get("custom_finish_dt")),
            new_start=fmt(simulation.get("new_start_dt")),
            new_finish=fmt(simulation.get("new_finish_dt")),
        )

        po_rows = ""
        for po in simulation.get("purchase_orders", []):
            planned_date = po.date_planned or po.date_order or False
            po_rows += """
                <tr>
                    <td style="padding:8px; border:1px solid #d9d9d9;">{name}</td>
                    <td style="padding:8px; border:1px solid #d9d9d9;">{partner}</td>
                    <td style="padding:8px; border:1px solid #d9d9d9;">{planned}</td>
                </tr>
            """.format(
                name=po.name or "",
                partner=po.partner_id.name or "",
                planned=fmt(planned_date) if planned_date else "",
            )

        if not po_rows:
            po_rows = """
                <tr>
                    <td colspan="3" style="padding:8px; border:1px solid #d9d9d9;">Aucun achat associé trouvé.</td>
                </tr>
            """

        po_html = """
        <div style="width:100%%; max-width:1100px;">
            <div style="font-weight:600; margin:10px 0 6px 0;">PO associées</div>
            <table style="width:100%%; border-collapse:collapse;">
                <thead>
                    <tr>
                        <th style="text-align:left; padding:8px; border:1px solid #d9d9d9;">PO</th>
                        <th style="text-align:left; padding:8px; border:1px solid #d9d9d9;">Fournisseur</th>
                        <th style="text-align:left; padding:8px; border:1px solid #d9d9d9;">Date prévue</th>
                    </tr>
                </thead>
                <tbody>{po_rows}</tbody>
            </table>
        </div>
        """.format(po_rows=po_rows)

        return preview_html, po_html

    def action_apply(self):
        self.ensure_one()

        if not self.production_id:
            raise UserError(_("Aucun ordre de fabrication lié au wizard."))

        simulation = self.production_id._fma_build_planning_result()
        self.production_id._fma_apply_simulation(simulation)

        return {"type": "ir.actions.act_window_close"}