# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class AccountInvoiceSend(models.TransientModel):
    _inherit = 'account.invoice.send'

    def send_and_print_action(self):
        # Update the context to not show invoice button
        return super(AccountInvoiceSend, self.with_context(show_view_invoice_button=False)).send_and_print_action()
