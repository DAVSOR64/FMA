from odoo import _, models
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_related_sale_order(self):
        self.ensure_one()

        if hasattr(self, "sale_id") and self.sale_id:
            return self.sale_id

        sale_orders = self.move_ids.sale_line_id.order_id
        sale_orders = sale_orders.filtered(lambda so: so)

        if len(sale_orders) == 1:
            return sale_orders

        if len(sale_orders) > 1:
            raise UserError("Plusieurs commandes clients liées à ce BL.")

        return False

    def action_open_delay_email(self):
        self.ensure_one()

        sale_order = self._get_related_sale_order()
        if not sale_order:
            raise UserError("Aucun SO lié.")

        contact = sale_order.main_contact_principal
        if not contact:
            raise UserError("Pas de contact principal.")

        if not contact.email:
            raise UserError("Contact sans email.")

        # >>> REMPLACE ICI PAR TON TEMPLATE <<<
        template = self.env.ref(
            "MON_MODULE.MON_XML_ID_TEMPLATE_RETARD",
            raise_if_not_found=False
        )

        if not template:
            raise UserError("Template email introuvable.")

        ctx = {
            "default_model": "stock.picking",
            "default_res_ids": [self.id],
            "default_use_template": True,
            "default_template_id": template.id,
            "default_composition_mode": "comment",
            "force_email": True,
            "default_partner_ids": [(6, 0, [contact.id])],
        }

        return {
            "type": "ir.actions.act_window",
            "name": "Information retard",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
