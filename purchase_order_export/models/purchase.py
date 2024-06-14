# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
import base64
import ftplib
import io

from odoo import fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_generated = fields.Boolean(default=False)
    xml_file_generation_time = fields.Datetime()
    last_sync = fields.Datetime()

    def action_export_order(self):
        """Attach the purchase order XML template."""
        for po in self:
            if po.state in ['done', 'cancel']:
                raise ValidationError("Purchase order state should not be in 'Cancelled' or 'Done' state.")

            try:
                xml_content = self.env['ir.qweb']._render(
                    'purchase_order_export.purchase_order_export_template',
                    {'po': po}
                )
                attachment = self.env['ir.attachment'].create({
                    'name': 'Purchase Order for Export-%s.xml' % po.name,
                    'type': 'binary',
                    'datas': base64.b64encode(xml_content.encode('utf-8')),
                    'res_model': 'purchase.order',
                    'res_id': po.id,
                    'mimetype': 'text/xml',
                    'is_ftp_export_po': True
                })
                po.write({
                    'xml_file_generation_time': fields.Datetime.now(),
                    'is_generated': True
                })

            except Exception as e:
                po.write({'is_generated': False})
                _logger.exception("Failed to export purchase order %s: %s", po.name, e)

    def _sync_file(self, attachment):
        try:
            attachment_content = base64.b64decode(attachment.datas)
            get_param = self.env['ir.config_parameter'].sudo().get_param
            ftp_server_host = get_param('purchase_order_export.ftp_server_host')
            ftp_server_username = get_param('purchase_order_export.ftp_server_username')
            ftp_server_password = get_param('purchase_order_export.ftp_server_password')
            ftp_server_file_path = get_param('purchase_order_export.ftp_server_file_path')
            if not ftp_server_host or not ftp_server_username or not ftp_server_password or not ftp_server_file_path:
                _logger.exception("Missing FTP server credentials.")
                return

            with ftplib.FTP(ftp_server_host, ftp_server_username, ftp_server_password) as session:
                session.cwd(ftp_server_file_path)
                session.storbinary('STOR ' + attachment.name, io.BytesIO(attachment_content))

        except Exception as e:
            _logger.exception("File upload failed for %s: %s", attachment.name, e)

    def action_sync_to_server(self):
        """Sync the unsynced POs to the FTP server."""
        purchase_orders = self.env['purchase.order'].search([('is_generated', '=', True)])
        for order in purchase_orders:
            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', 'purchase.order'),
                ('res_id', '=', order.id),
                ('is_ftp_export_po', '=', True)
            ], limit=1)
            if attachment:
                self._sync_file(attachment)
                order.write({'last_sync': fields.Datetime.now()})
