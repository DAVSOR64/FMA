# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    date_bpe = fields.Date(string="Date BPE") 

    # Init date validation devis

    def action_validation(self):
        for order in self:
            order.state = 'validated'
            order.x_studio_date_de_la_commande = fields.datetime.today()
            order.so_date_devis_valide = fields.datetime.today()
            
    # Init date BPE lors de la confirmation du devis
    def action_confirm(self):
        for order in self:
            order.so_date_bpe = fields.datetime.today()
        return super().action_confirm()
        
    # Init date de modification devis
    def action_quotation_send(self):
        for order in self:
            order.so_date_de_modification_devis =fields.Date.today()

    # Init date de livraison prévu

    # Calcul de la date de livraison prévue
    @api.depends('so_date_bpe', 'so_delai_confirme_en_semaine')
    def _compute_so_date_de_livraison_prevu(self):
        for order in self:
            if order.so_date_bpe and order.so_delai_confirme_en_semaine:
                # Ajouter le délai confirmé (en semaines) à la date BPE
                order.so_date_de_livraison_prevu = order.so_date_bpe + timedelta(weeks=order.so_delai_confirme_en_semaine)
            else:
                # S'il manque une des valeurs, on ne fait pas le calcul
                order.so_date_de_livraison_prevu = False


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

    # Init date fin de production réel

    def do_finish(self):
        res = super(SaleOrder, self).do_finish()
        for order in self:
            order.write({'so_date_de_fin_de_production_reel': fields.Date.today()})
        return res

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