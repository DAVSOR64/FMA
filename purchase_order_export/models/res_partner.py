# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    shipping_number = fields.Char()
    po_xml_export_sftp_path = fields.Char("File Path", help="SFTP server file path for the PO XML file.")
