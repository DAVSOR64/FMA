# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sftp_host_invoice_export = fields.Char(config_parameter='fma_invoice_export.sftp_host_invoice_export')
    sftp_username_invoice_export = fields.Char(config_parameter='fma_invoice_export.sftp_username_invoice_export')
    sftp_server_password_invoice_export = fields.Char(config_parameter='fma_invoice_export.sftp_server_password_invoice_export')
    sftp_server_file_path_invoice_export = fields.Char(config_parameter='fma_invoice_export.sftp_server_file_path_invoice_export')
