import logging
from odoo import models, fields, api
_logger = logging.getLogger(__name__)


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
    so_date_de_reception_devis = fields.Date(string="Date de réception devis")
    so_date_du_devis = fields.Date(string="Date du devis")
    so_date_de_modification_devis = fields.Date(string="Date de modification devis")
    so_date_devis_valide = fields.Date(string="Date devis validé")
    so_date_ARC = fields.Date(string="Date ARC")
    so_date_ARC_valide = fields.Date(string="Date ARC Validé")
    so_date_de_fin_de_production_reel = fields.Date(string="Date de fin de production réel")
    so_date_de_livraison_prevu = fields.Date(string="Date de livraison prévu")
    so_statut_avancement = fields.Char(string="Statut Avancement")
    so_gamme = fields.Char(string="GAMME")

    #Onglet Analyse Financière
    so_achat_matiere_devis = fields.Monetary(string="Achat Matière (Devis)")
    so_achat_vitrage_devis = fields.Monetary(string="Achat Vitrage (Devis)")
    so_cout_mod_devis = fields.Monetary(string="Coût MOD (Devis)")
    so_mtt_facturer_devis = fields.Monetary(string="Montant à Facturer H.T. (Devis)")
    so_marge_brute_devis = fields.Monetary(string="Marge Brute en € (Devis)",compute='_compute_so_marge_brute_devis',store=True)
    so_prc_marge_brute_devis = fields.Float(string="Marge Brute en % (Devis)",compute='_compute_so_prc_marge_brute_devis',store=True)
    so_mcv_devis = fields.Monetary(string="M.C.V. en € (Devis)",compute='_compute_so_mcv_devis',store=True)
    so_prc_mcv_devis = fields.Float(string="M.C.V. en (Devis)",compute='_compute_so_prc_mcv_devis',store=True)

    so_achat_matiere_be = fields.Monetary(string="Achat Matière (B.E.)")
    so_achat_vitrage_be = fields.Monetary(string="Achat Vitrage (B.E.)")
    so_cout_mod_be = fields.Monetary(string="Coût MOD (B.E.)")
    so_mtt_facturer_be = fields.Monetary(string="Montant à Facturer H.T. (B.E.)")
    so_marge_brute_be = fields.Monetary(string="Marge Brute en € (B.E.)",compute='_compute_so_marge_brute_be',store=True)
    so_prc_marge_brute_be = fields.Float(string="Marge Brute en % (B.E.)",compute='_compute_so_prc_marge_brute_be',store=True)
    so_mcv_be = fields.Monetary(string="M.C.V. en € (B.E.)",compute='_compute_so_mcv_be',store=True)
    so_prc_mcv_be = fields.Float(string="M.C.V. en (B.E.)",compute='_compute_so_prc_mcv_be',store=True)

    so_achat_matiere_reel = fields.Monetary(string="Achat Matière (Réel)")
    so_achat_vitrage_reel = fields.Monetary(string="Achat Vitrage (Réel)")
    so_cout_mod_reel = fields.Monetary(string="Coût MOD (Réel)")
    so_mtt_facturer_reel = fields.Monetary(string="Montant à Facturer H.T. (Réel)")
    so_marge_brute_reel = fields.Monetary(string="Marge Brute en € (Réel)",compute='_compute_so_marge_brute_reel',store=True)
    so_prc_marge_brute_reel = fields.Float(string="Marge Brute en % (Réel)",compute='_compute_so_prc_marge_brute_reel',store=True)
    so_mcv_reel = fields.Monetary(string="M.C.V. en € (Réel)",compute='_compute_so_mcv_reel',store=True)
    so_prc_mcv_reel = fields.Float(string="M.C.V. en (Réel)",compute='_compute_so_prc_mcv_reel',store=True)
    
    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['x_studio_rfrence_affaire'] = self.x_studio_ref_affaire
        invoice_vals['x_studio_imputation_2'] = self.x_studio_imputation
        invoice_vals['x_studio_delegation_fac'] = self.x_studio_delegation
        invoice_vals['x_studio_com_delegation_fac'] = self.x_studio_com_delegation
        invoice_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        invoice_vals['x_studio_date_de_la_commande'] = self.x_studio_date_de_la_commande
        return invoice_vals

    #calcul DEVIS 
    @api.depends('so_mtt_facturer_devis', 'so_achat_vitrage_devis', 'so_achat_matiere_devis')
    def _compute_so_marge_brute_devis(self):
        for order in self:
            order.so_marge_brute_devis = order.so_mtt_facturer_devis - order.so_achat_vitrage_devis - order.so_achat_matiere_devis

    @api.depends('so_marge_brute_devis', 'so_mtt_facturer_devis')
    def _compute_so_prc_marge_brute_devis(self):
        for order in self:
            if order.so_mtt_facturer_devis:
                order.so_prc_marge_brute_devis = (order.so_marge_brute_devis / order.so_mtt_facturer_devis) * 100
            else:
                order.so_prc_marge_brute_devis = 0.0

    @api.depends('so_marge_brute_devis', 'so_cout_mod_devis')
    def _compute_so_mcv_devis(self):
        for order in self:
            order.so_mcv_devis = order.so_marge_brute_devis - order.so_cout_mod_devis

    @api.depends('so_mcv_devis', 'so_mtt_facturer_devis')
    def _compute_so_prc_mcv_devis(self):
        for order in self:
            if order.so_mtt_facturer_devis:
                order.so_prc_mcv_devis = (order.so_mcv_devis / order.so_mtt_facturer_devis) * 100
            else:
                order.so_prc_mcv_devis = 0.0

    #calcul BE
    @api.depends('so_mtt_facturer_be', 'so_achat_vitrage_be', 'so_achat_matiere_be')
    def _compute_so_marge_brute_be(self):
        for order in self:
            order.so_marge_brute_be = order.so_mtt_facturer_be - order.so_achat_vitrage_be - order.so_achat_matiere_be

    @api.depends('so_marge_brute_be', 'so_mtt_facturer_be')
    def _compute_so_prc_marge_brute_be(self):
        for order in self:
            if order.so_mtt_facturer_be:
                order.so_prc_marge_brute_be = (order.so_marge_brute_be / order.so_mtt_facturer_be) * 100
            else:
                order.so_prc_marge_brute_be = 0.0

    @api.depends('so_marge_brute_be', 'so_cout_mod_be')
    def _compute_so_mcv_be(self):
        for order in self:
            order.so_mcv_be = order.so_marge_brute_be - order.so_cout_mod_be

    @api.depends('so_mcv_be', 'so_mtt_facturer_be')
    def _compute_so_prc_mcv_be(self):
        for order in self:
            if order.so_mtt_facturer_be:
                order.so_prc_mcv_be = (order.so_mcv_be / order.so_mtt_facturer_be) * 100
            else:
                order.so_prc_mcv_be = 0.0

    #calcul REEL
    @api.depends('so_mtt_facturer_reel', 'so_achat_vitrage_reel', 'so_achat_matiere_reel')
    def _compute_so_marge_brute_reel(self):
        for order in self:
            order.so_marge_brute_reel = order.so_mtt_facturer_reel - order.so_achat_vitrage_reel - order.so_achat_matiere_reel

    @api.depends('so_marge_brute_reel', 'so_mtt_facturer_reel')
    def _compute_so_prc_marge_brute_reel(self):
        for order in self:
            if order.so_mtt_facturer_reel:
                order.so_prc_marge_brute_reel = (order.so_marge_brute_reel / order.so_mtt_facturer_reel) * 100
            else:
                order.so_prc_marge_brute_reel = 0.0

    @api.depends('so_marge_brute_reel', 'so_cout_mod_reel')
    def _compute_so_mcv_reel(self):
        for order in self:
            order.so_mcv_reel = order.so_marge_brute_reel - order.so_cout_mod_reel

    @api.depends('so_mcv_reel', 'so_mtt_facturer_reel')
    def _compute_so_prc_mcv_reel(self):
        for order in self:
            if order.so_mtt_facturer_reel:
                order.so_prc_mcv_reel = (order.so_mcv_reel / order.so_mtt_facturer_reel) * 100
            else:
                order.so_prc_mcv_reel = 0.0
    
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

    # Init date BPE lors de la confirmation du devis

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for order in self:
            order.write({'so_date_bpe': fields.Date.today()})
        return res

    # Init date du Devis lors de la création d'un numéro de commande

    def create(self, vals):
        if 'name' in vals:
            vals['so_date_du_devis'] = fields.Date.today()
        return super(SaleOrder, self).create(vals)

    # Init du WAREHOUSE en fonction du tag FMA ou F2M
    @api.model   
    def write(self, vals):
        _logger.info("Appel de write avec vals: %s", vals)
        res = super(SaleOrder, self).write(vals)
        _logger.info("Devis mis à jour: %s", self.id)
        
        # Appelez _update_warehouse ici
        if 'tag_ids' in vals:
            _logger.info("Appel de _update_warehouse après mise à jour")
            self._update_warehouse()
        return res

    def _update_warehouse(self):
        _logger.info("Début de _update_warehouse pour le devis: %s", self.id)
        for order in self:
            _logger.info("Tags actuels: %s", order.tag_ids.mapped('name'))

            # Cherche les entrepôts correspondant aux étiquettes spécifiques
            warehouse_regripiere = self.env['stock.warehouse'].search([('name', '=', 'LA REGRIPPIERE')], limit=1)
            warehouse_remaudiere = self.env['stock.warehouse'].search([('name', '=', 'LA REMAUDIERE')], limit=1)
            _logger.info("Entrepôt LA Regripière: %s, Entrepôt La Remaudière: %s", warehouse_regripiere, warehouse_remaudiere)

            # Met à jour l'entrepôt en fonction de l'étiquette
            if any(tag.name == 'FMA' for tag in order.tag_ids):
                if warehouse_regripiere:
                    _logger.info("Mise à jour de l'entrepôt vers LA Regripière")
                    order.write({'warehouse_id': warehouse_regripiere.id})
                else:
                    _logger.warning("Entrepôt LA Regripière non trouvé")
            elif any(tag.name == 'F2M' for tag in order.tag_ids):
                if warehouse_remaudiere:
                    _logger.info("Mise à jour de l'entrepôt vers La Remaudière")
                    order.write({'warehouse_id': warehouse_remaudiere.id})
                else:
                    _logger.warning("Entrepôt La Remaudière non trouvé")
