from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_studio_ref_affaire = fields.Char(string="Affaire")
    x_studio_imputation = fields.Char(string="Numéro Commande Client")
    x_studio_delegation = fields.Boolean(string="Délégation")
    x_studio_com_delegation = fields.Char(string="Commentaire Délégation:")
    x_studio_mode_de_rglement_1 = fields.Selection(
        [
            ('ESPECES','ESPECES'),
            ('CHEQUE BANCAIRE','CHEQUE BANCAIRE'),
            ('VIREMENT BANCAIRE','VIREMENT BANCAIRE'),
            ('L.C.R. DIRECTE','L.C.R. DIRECTE'),
            ('L.C.R. A L ACCEPTATION','L.C.R. A L ACCEPTATION'),
            ('PRELEVEMENT','PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE','L.C.R. MAGNETIQUE'),
            ('BOR','BOR'),
            ('CARTE BANCAIRE','CARTE BANCAIRE'),
            ('CREDIT DOCUMENTAIRE','CREDIT DOCUMENTAIRE'),
        ],
        string="Mode de Règlement",
    )
    x_studio_date_de_la_commande = fields.Date(string="Date de la Commande")

    so_mode_reglement = fields.Selection(related='partner_id.part_mode_de_reglement', string="Mode de Règlement")
    so_commercial = fields.Selection(related='partner_id.part_commercial', string="Commercial")
    so_code_tiers = fields.Integer(related='partner_id.part_code_tiers', string="Code Tiers")
    so_commande_client = fields.Char(string="N° Commande Client")
    so_delegation = fields.Boolean(string="Délégation?")
    so_commmentaire_delegation = fields.Char(string="Commentaire Délégation")
    so_date_de_reception = fields.Date(string="Date de réception")
    so_date_de_modification = fields.Date(string="Date de modification")
    so_date_de_commande = fields.Date(string="Date de la commande")
    so_date_bpe = fields.Date(string="Date BPE")
    
    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['x_studio_rfrence_affaire'] = self.x_studio_ref_affaire
        invoice_vals['x_studio_imputation_2'] = self.x_studio_imputation
        invoice_vals['x_studio_delegation_fac'] = self.x_studio_delegation
        invoice_vals['x_studio_com_delegation_fac'] = self.x_studio_com_delegation
        invoice_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        invoice_vals['x_studio_date_de_la_commande'] = self.x_studio_date_de_la_commande
        return invoice_vals

    @api.model
    def create(self, vals):
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            vals['x_studio_mode_de_rglement_1'] = partner.x_studio_mode_de_rglement_1
        return super(SaleOrder, self).create(vals)

    def write(self, vals):
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            vals['x_studio_mode_de_rglement_1'] = partner.x_studio_mode_de_rglement_1
        return super(SaleOrder, self).write(vals)