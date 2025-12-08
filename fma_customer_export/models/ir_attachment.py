# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    is_customer_txt = fields.Boolean()
    is_synced_to_sftp = fields.Boolean()
