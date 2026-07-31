# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class AccountMoveSendWizard(models.TransientModel):
    _inherit = "account.move.send.wizard"

    def action_send_and_print(self, allow_fallback_pdf=False):
        # Update the context to not show invoice button
        return super(
            AccountMoveSendWizard, self.with_context(show_view_invoice_button=False)
        ).action_send_and_print(allow_fallback_pdf=allow_fallback_pdf)
