# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sftp_host_outstandings = fields.Char(config_parameter='fma_customer_outstanding.sftp_host_outstandings')
    sftp_username_outstandings = fields.Char(config_parameter='fma_customer_outstanding.sftp_username_outstandings')
    sftp_password_outstandings = fields.Char(config_parameter='fma_customer_outstanding.sftp_password_outstandings')
    sftp_file_path_outstandings = fields.Char(config_parameter='fma_customer_outstanding.sftp_file_path_outstandings')
