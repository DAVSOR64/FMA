# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ftp_server_host = fields.Char(config_parameter='fma_invoice_status.ftp_server_host')
    ftp_server_username = fields.Char(config_parameter='fma_invoice_status.ftp_server_username')
    ftp_server_password = fields.Char(config_parameter='fma_invoice_status.ftp_server_password')
    ftp_server_file_path = fields.Char(config_parameter='fma_invoice_status.ftp_server_file_path')
