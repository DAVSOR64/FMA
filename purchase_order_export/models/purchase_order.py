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
    customer_delivery_address = fields.Char(compute='_get_default_customer_delivery_address')

    @api.depends('shipping_partner_id')
    def _get_default_customer_delivery_address(self):
        for order in self:
            if order.shipping_partner_id:
                order.customer_delivery_address = order.shipping_partner_id.shipping_number
            else:
                order.customer_delivery_address = ''

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
                    'name': 'ZOR_%s.xml' % po.name,
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

    # Champs détail laquage
    so_carton_qty = fields.Integer(string='Qté')
    so_botte_qty = fields.Integer(string='Qté')
    so_botte_length = fields.Float(string='Longueur (en m)')
    so_palette_qty = fields.Integer(string='Qté')
    so_palette_length = fields.Float(string='Longueur (en m)')
    so_palette_depth = fields.Float(string='Profondeur (en m)')
    so_palette_height = fields.Float(string='Hauteur (en m)')
    so_poids_total = fields.Float(string='Poids (en kg)')

    # Ajout du champ One2many pour les lignes de laquage
    laquage_line_ids = fields.One2many(
        'purchase.order.laquage.line', 'order_id', string="Lignes de Laquage"
    )


class PurchaseOrderLaquageLine(models.Model):
    _name = 'purchase.order.laquage.line'
    _description = 'Ligne de Laquage'
    _inherit = ['mail.thread']  # Suivi pour l'historique des modifications
    _log_access = True  # Historique des accès

    # Relation avec la commande d'achat
    order_id = fields.Many2one(
        'purchase.order', string="Commande d'Achat", ondelete='cascade'
    )

    # Champs spécifiques pour les détails de laquage
    so_repere = fields.Char(string="Réf./Repère")
    so_designation = fields.Char(string="Désignation")
    so_largeur = fields.Float(string="Largeur")
    so_hauteur = fields.Float(string="Hauteur")
    so_qte_commandee = fields.Integer(string="Quantité")
    so_qte_livree = fields.Integer(string="Qté Livrée")
    so_reliquat = fields.Integer(string="Reliquat")
    so_poids_total = fields.Float(string="Poids Total")
    so_carton_qty = fields.Integer(string="Quantité de Cartons")
    so_botte_qty = fields.Integer(string="Nombre de Bottes")
    so_botte_length = fields.Float(string="Longueur de Botte")
    so_palette_qty = fields.Integer(string="Nombre de Palettes")
    so_palette_length = fields.Float(string="Longueur Palette")
    so_palette_depth = fields.Float(string="Profondeur Palette")
    so_palette_height = fields.Float(string="Hauteur Palette")

    # Contrainte SQL pour garantir l'unicité du champ 'so_repere'
    _sql_constraints = [
        ('so_repere_unique', 'UNIQUE(so_repere)', 'La référence doit être unique pour une ligne de laquage !'),
    ]

    @api.model
    def create(self, vals):
        """Log de création"""
        res = super(PurchaseOrderLaquageLine, self).create(vals)
        message = _("Ligne de laquage créée : %s") % res.so_repere
        res.order_id.message_post(body=message)
        return res

    def write(self, vals):
        """Log de modification"""
        _logger.warning("********** Fonction write appelée dans PurchaseOrderLaquageLine *********")
        res = super(PurchaseOrderLaquageLine, self).write(vals)
        message = _("Ligne de laquage mise à jour.")
        self.order_id.message_post(body=message)
        return res

