from odoo import api, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _remove_all_followers(self):
        for order in self:
            partners = order.message_partner_ids
            if partners:
                order.message_unsubscribe(partner_ids=partners.ids)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._remove_all_followers()
        return orders

    def write(self, vals):
        res = super().write(vals)
        self._remove_all_followers()
        return res
