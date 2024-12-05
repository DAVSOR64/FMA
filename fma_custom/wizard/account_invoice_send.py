# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class AccountMoveSend(models.TransientModel):
    _inherit = 'account.move.send'

    def action_send_and_print(self):
        # Update the context to not show invoice button
        return super(AccountMoveSend, self.with_context(show_view_invoice_button=False)).action_send_and_print()
