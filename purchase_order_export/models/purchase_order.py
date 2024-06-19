# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import base64
import ftplib
import io
import logging
import psycopg2

from odoo import SUPERUSER_ID, api, fields, models, registry
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_xml_created = fields.Boolean(default=False, readonly=True)
    xml_creation_time = fields.Datetime(readonly=True)
    ftp_synced_time = fields.Datetime("Send to FTP", readonly=True)
    shipping_partner_id = fields.Many2one('res.partner')
    shipping_number = fields.Char(compute='_get_default_shipping_number', readonly=False)

    @api.depends('shipping_partner_id')
    def _get_default_shipping_number(self):
        address_to_shipping_number = {
            'LA REGRIPPIERE': '130172',
            'LA REMAUDIERE': '175269'
        }
        for order in self:
            if order.shipping_partner_id:
                delivery_address = order.shipping_partner_id.customer_delivery_address
                order.shipping_number = address_to_shipping_number.get(delivery_address, '')
            else:
                order.shipping_number = ''

    def action_export_order(self):
        """Attach the purchase order XML template."""
        for po in self:
            if po.state in ['done', 'cancel']:
                raise ValidationError("Purchase order state should not be in 'Cancelled' or 'Done' state.")

            try:
                xml_content = self.env['ir.qweb']._render(
                    'purchase_order_export.purchase_order_ftp_export_template',
                    {'po': po}
                )
                attachment = self.env['ir.attachment'].create({
                    'name': 'Purchase Order for Export-%s.xml' % po.name,
                    'type': 'binary',
                    'datas': base64.b64encode(xml_content.encode('utf-8')),
                    'res_model': 'purchase.order',
                    'res_id': po.id,
                    'mimetype': 'text/xml',
                    'is_po_xml': True
                })
                po.write({
                    'xml_creation_time': fields.Datetime.now(),
                    'is_xml_created': True
                })

            except Exception as e:
                po.write({'is_xml_created': False})
                _logger.exception("Failed to export purchase order %s: %s", po.name, e)

    def _sync_file(self, attachment):
        attachment_content = base64.b64decode(attachment.datas)
        get_param = self.env['ir.config_parameter'].sudo().get_param
        ftp_server_host = get_param('purchase_order_export.ftp_server_host')
        ftp_server_username = get_param('purchase_order_export.ftp_server_username')
        ftp_server_password = get_param('purchase_order_export.ftp_server_password')
        ftp_server_file_path = get_param('purchase_order_export.ftp_server_file_path')
        if not all([ftp_server_host, ftp_server_username, ftp_server_password, ftp_server_file_path]):
            _logger.error("Missing one or more FTP server credentials.")
            return

        with ftplib.FTP(ftp_server_host, ftp_server_username, ftp_server_password) as session:
            try:
                session.cwd(ftp_server_file_path)
                session.storbinary('STOR ' + attachment.name, io.BytesIO(attachment_content))
                self.log_request('FTP Sync Success', f"File {attachment.name} uploaded successfully to {ftp_server_file_path}", f'Sync File {attachment.name}')

            except ftplib.all_errors as ftp_error:
                _logger.error("FTP error while uploading file %s: %s", attachment.name, ftp_error)
            except Exception as upload_error:
                _logger.error("Unexpected error while uploading file %s: %s", attachment.name, upload_error)

    def cron_send_po_xml_to_ftp(self):
        """Sync the unsynced POs to the FTP server."""
        purchase_orders = self.env['purchase.order'].search([('is_xml_created', '=', True)])
        attachment_model = self.env['ir.attachment']
        for order in purchase_orders:
            try:
                with self.env.cr.savepoint():
                    attachment = attachment_model.search([
                        ('res_model', '=', 'purchase.order'),
                        ('res_id', '=', order.id),
                        ('is_po_xml', '=', True)
                    ], limit=1)
                    if attachment:
                        self._sync_file(attachment)
                        order.write({'ftp_synced_time': fields.Datetime.now()})
                    else:
                        _logger.warning(f"No attachment found for Purchase Order {order.name}.")
            except Exception as e:
                _logger.error(f"Failed to sync Purchase Order {order.name} to FTP: {e}")

    def log_request(self, operation, ref, path, level=None):
        db_name = self.env.cr.dbname
        try:
            db_registry = registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                IrLogging = env['ir.logging']
                IrLogging.sudo().create({'name': operation,
                    'type': 'server',
                    'dbname': db_name,
                    'level': level,
                    'message': ref,
                    'path': path,
                    'func': operation,
                    'line': 1
                })
        except psycopg2.Error:
            pass
