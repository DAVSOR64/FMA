from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    show_text_block = fields.Boolean(string="Show Text Block", compute='_compute_show_text_block')
    inv_show_affacturage = fields.Boolean(string="Show Affacturage", compute='_compute_show_affacturage')
    x_studio_delegation_fac = fields.Boolean(string="Délégation")
    x_studio_com_delegation_fac = fields.Char(string="Commentaire Délégation :")
    x_delegation_text = fields.Char(string="Texte de Délégation", compute='_compute_delegation_text')
    x_studio_imputation_2 = fields.Char(string="Imputation :")
    inv_delegation = fields.Boolean(string="Délégation")
    inv_commentaire_delegation = fields.Char(string="Commentaire Délégation :")
    inv_delegation_txt = fields.Char(string="Texte de Délégation", compute='_compute_delegation_txt')
    
    
    @api.depends('partner_id')
    def _compute_show_text_block(self):
        for record in self:
            record.show_text_block = record.partner_id.x_studio_affacturage

    @api.depends('partner_id')
    def _compute_show_affacturage(self):
        for record in self:
            record.inv_show_affacturage = record.partner_id.part_affacturage
    
    
    @api.model
    def _get_invoice_lines(self):
        lines = super(AccountMove, self)._get_invoice_lines()
        return lines.filtered(lambda l: l.product_id.name != 'Devis')

    @api.depends('x_studio_delegation_fac')
    def _compute_delegation_text(self):
        for record in self:
            #_logger.warning("**********delegation********* %s " % record.x_studio_delegation_fac )
            if record.x_studio_delegation_fac:
                record.x_delegation_text = record.x_studio_com_delegation_fac
            else:
                record.x_delegation_text = ""    
                                
    @api.depends('inv_delegation')
    def _compute_inv_delegation_txt(self):
        for record in self:
            #_logger.warning("**********delegation********* %s " % record.x_studio_delegation_fac )
            if record.inv_delegation:
                record.inv_delegation_text = record.inv_commentaire_delegation
            else:
                record.inv_delegation_text = ""
    

    def format_amount(self, amount):
        return '{:,.2f}'.format(amount).replace(',', ' ').replace('.', ',')
    def create(self, vals):
        if isinstance(vals, list):
            for val in vals:
                if 'invoice_origin' in val:
                    sale_order = self.env['sale.order'].search([('name', '=', val['invoice_origin'])], limit=1)
                    if sale_order:
                        val['inv_commande_client'] = sale_order.so_commande_client
                        # Récupération correcte des noms des tags
                        tags = sale_order.tag_ids.name
                        _logger.warning("**********Etiquettes trouvées********* %s", tags)
                        if  tags == 'FMA': 
                            val['inv_activite'] = 'ALU'
                        elif tags == 'F2M' :
                            val['inv_activite'] = 'ACIER'
        else:
            if 'invoice_origin' in vals:
                sale_order = self.env['sale.order'].search([('name', '=', vals['invoice_origin'])], limit=1)
                if sale_order:
                    vals['inv_commande_client'] = sale_order.so_commande_client
                    # Récupération correcte des noms des tags
                    tags = sale_order.tag_ids.name
                    _logger.warning("**********Etiquettes trouvées********* %s", tags)
                    if  tags == 'FMA': 
                        vals['inv_activite'] = 'ALU'
                    elif tags == 'F2M' :
                        vals['inv_activite'] = 'ACIER'
        
        return super(AccountMove, self).create(vals)


    #discount_rate = fields.Float(string='Discount Rate', compute='_compute_discount_rate', store=True)
    #amount_discount = fields.Monetary(string='Total Discount', compute='_compute_amount_discount', store=True)
    #amount_advance = fields.Monetary(string='Advance Payment', compute='_compute_amount_advance', store=True)

    #@api.depends('invoice_line_ids.sale_line_ids.discount', 'invoice_line_ids.sale_line_ids.price_subtotal')
    #def _compute_discount_rate(self):
    #    for move in self:
    #        total_discount = sum(line.sale_line_ids.price_subtotal * (line.sale_line_ids.discount / 100.0) for line in move.invoice_line_ids)
    #        if move.amount_untaxed:
    #            move.discount_rate = (total_discount / move.amount_untaxed) * 100
    #        else:
    #            move.discount_rate = 0.0

    #@api.depends('invoice_line_ids.sale_line_ids.discount', 'invoice_line_ids.sale_line_ids.price_subtotal')
    #def _compute_amount_discount(self):
    #    for move in self:
    #        move.amount_discount = sum(line.sale_line_ids.price_subtotal * (line.sale_line_ids.discount / 100.0) for line in move.invoice_line_ids)

    #@api.depends('invoice_line_ids.sale_line_ids.order_id.advance_payment')
    #def _compute_amount_advance(self):
    #    for move in self:
    #        move.amount_advance = sum(line.sale_line_ids.order_id.advance_payment for line in move.invoice_line_ids if line.sale_line_ids.order_id)
