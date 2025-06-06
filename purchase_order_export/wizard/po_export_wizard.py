# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields

class PoExportWizard(models.TransientModel):
    _name = 'po.export.wizard'
    _description = 'Export Order Wizard'

    export_format = fields.Selection([
        ('xlsx', 'Excel'),
        ('xml', 'XML'),
        ('xml_v2', 'XML (Version 2)')
    ], string='Export Format', default='xlsx')

    def action_export(self):
        active_ids = self.env.context.get('active_ids', [])
        purchase_orders = self.env['purchase.order'].browse(active_ids)
        for po in purchase_orders:
            po.action_export_order(self.export_format)
