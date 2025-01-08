# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import base64
import io
import logging
import paramiko
import psycopg2

from odoo import SUPERUSER_ID, api, fields, models, registry
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_xml_created = fields.Boolean(default=False, readonly=True)
    xml_creation_time = fields.Datetime(readonly=True)
    sftp_synced_time = fields.Datetime("Send to SFTP", readonly=True)
    shipping_partner_id = fields.Many2one('res.partner')
    customer_delivery_address = fields.Char(compute='_get_default_customer_delivery_address', readonly=False)

    @api.depends('shipping_partner_id')
    def _get_default_customer_delivery_address(self):
        shipping_number_to_address = {
            '130172': 'LA REGRIPPIERE',
            '175269': 'LA REMAUDIERE'
        }
        for order in self:
            if order.shipping_partner_id:
                delivery_address = order.shipping_partner_id.shipping_number
                order.customer_delivery_address = shipping_number_to_address.get(delivery_address, '')

    def action_export_order(self):
        """Attach the purchase order XML template."""
        for po in self:
            if po.state in ['done', 'cancel']:
                raise ValidationError("Purchase order state should not be in 'Cancelled' or 'Done' state.")

            try:
                xml_content = self.env['ir.qweb']._render(
                    'purchase_order_export.purchase_order_sftp_export_template',
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

    def _sync_file(self, sftp_obj, attachment, order, sftp_server_file_path):
        attachment_content = base64.b64decode(attachment.datas)
        transport = None
        try:
            partner_path = getattr(order.partner_id, 'po_xml_export_sftp_path', '')
            if not partner_path:
                order.write({'sftp_synced_time': False})
                _logger.error(f"Missing File Path at the Vendor {order.partner_id.name} of {order.name}.")
                return
            partner_path = partner_path.strip('/')
            full_path = f"/{sftp_server_file_path.strip('/')}/{partner_path}" + '/'
            sftp_obj.chdir(full_path)
            with io.BytesIO(attachment_content) as file_obj:
                sftp_obj.putfo(file_obj, attachment.name)  # Upload file
                order.write({'sftp_synced_time': fields.Datetime.now()})

            self.log_request('SFTP Sync Success',
                f"File {attachment.name} uploaded successfully to {sftp_server_file_path}",
                f'Sync File {attachment.name}')

        except FileNotFoundError as e:
            _logger.error(f"SFTP Sync Error: Error locating the directory {full_path}. Exception: {e}")
        except paramiko.SSHException as ssh_error:
            _logger.error(f"SSH error while uploading file {attachment.name}: {ssh_error}")
        except IOError as io_error:
            _logger.error(f"I/O error during file upload for {attachment.name}: {io_error}")
        except Exception as e:
            order.write({'sftp_synced_time': False})
            _logger.error(f"Unexpected error while uploading file {attachment.name}: {e}")

    def cron_send_po_xml_to_sftp(self):
        """Sync the unsynced POs to the SFTP server."""
        purchase_orders = self.env['purchase.order'].search([('is_xml_created', '=', True)])
        attachment_model = self.env['ir.attachment']

        get_param = self.env['ir.config_parameter'].sudo().get_param
        sftp_server_host = get_param('purchase_order_export.sftp_host_po_xml_export')
        sftp_server_username = get_param('purchase_order_export.sftp_username_po_xml_export')
        sftp_server_password = get_param('purchase_order_export.sftp_password_po_xml_export')
        sftp_server_file_path = get_param('purchase_order_export.sftp_file_path_po_xml_export')
        if not all([sftp_server_host, sftp_server_username, sftp_server_password, sftp_server_file_path]):
            _logger.error("Missing one or more SFTP server credentials.")
            return

        try:
            transport = paramiko.Transport((sftp_server_host, 22))
            transport.connect(username=sftp_server_username, password=sftp_server_password)
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                for order in purchase_orders:
                    with self.env.cr.savepoint():
                        attachment = attachment_model.search([
                            ('res_model', '=', 'purchase.order'),
                            ('res_id', '=', order.id),
                            ('is_po_xml', '=', True)
                        ], limit=1)
                        if attachment:
                            self._sync_file(sftp, attachment, order, sftp_server_file_path)
                        else:
                            _logger.warning(f"No attachment found for Purchase Order {order.name}.")
        except Exception as e:
            order.write({'sftp_synced_time': False})
            _logger.error(f"Failed to sync Purchase Order {order.name} to SFTP server: {e}")
        finally:
            if transport:
                transport.close()

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
