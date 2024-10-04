# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sftp_host_invoice_status = fields.Char(config_parameter='fma_invoice_status.sftp_host_invoice_status')
    sftp_username_invoice_status = fields.Char(config_parameter='fma_invoice_status.sftp_username_invoice_status')
    sftp_password_invoice_status = fields.Char(config_parameter='fma_invoice_status.sftp_password_invoice_status')
    sftp_file_path_invoice_status = fields.Char(config_parameter='fma_invoice_status.sftp_file_path_invoice_status')
