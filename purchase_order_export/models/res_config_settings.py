# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sftp_host_po_xml_export = fields.Char(config_parameter='purchase_order_export.sftp_host_po_xml_export')
    sftp_username_po_xml_export = fields.Char(config_parameter='purchase_order_export.sftp_username_po_xml_export')
    sftp_password_po_xml_export = fields.Char(config_parameter='purchase_order_export.sftp_password_po_xml_export')
    sftp_file_path_po_xml_export = fields.Char(config_parameter='purchase_order_export.sftp_file_path_po_xml_export')
