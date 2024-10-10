from datetime import timedelta
import logging
from odoo import api, fields, models
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(selection_add=[
        ('validated', 'Validated')
    ])
    
    date_bpe = fields.Date(string="Date BPE") 

    # Init date validation devis
    def action_validation(self):
        for order in self:
            order.state = 'validated'
            order.x_studio_date_de_la_commande = fields.Datetime.today()
            order.so_date_devis_valide = fields.Datetime.today()
            
    # Init date BPE lors de la confirmation du devis
    def action_confirm(self):
        for order in self:
            order.so_date_bpe = fields.Datetime.today()
        return super(SaleOrder, self).action_confirm()
    
    # Init date bon pour fab
    def action_confirm(self):
        for order in self:
            order.so_date_bon_pour_fab = fields.Datetime.today()
        return super(SaleOrder, self).action_confirm()

    # Init date fin de production réel
    def button_mark_done(self):
        for order in self:
            order.so_date_de_fin_de_production_reel = fields.Date.today()
        return super(SaleOrder, self).button_mark_done()
        
    # Init date de modification devis
    def action_quotation_send(self):
        for order in self:
            order.so_date_de_modification_devis = fields.Date.today()
        return super(SaleOrder, self).action_quotation_send()

    @api.model
    def create(self, vals):
        # Ajouter la date d'aujourd'hui au champ so_date_du_devis
        for order in self:
            order.so_date_du_devis = fields.Date.today()
    
        # Si un partner_id est présent, mettre à jour le mode de règlement
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            vals['x_studio_mode_de_rglement_1'] = partner.x_studio_mode_de_rglement_1
    
        return super(SaleOrder, self).create(vals)

    # Init date de livraison prévue
    @api.depends('so_date_bpe', 'so_delai_confirme_en_semaine')
    def _compute_so_date_de_livraison_prevu(self):
        for order in self:
            if order.so_date_bpe and order.so_delai_confirme_en_semaine:
                # Ajouter le délai confirmé (en semaines) à la date BPE
                order.so_date_de_livraison_prevu = order.so_date_bpe + timedelta(weeks=order.so_delai_confirme_en_semaine)
            else:
                # S'il manque une des valeurs, on ne fait pas le calcul
                order.so_date_de_livraison_prevu = False

    # Calcul des marges et coûts pour le devis
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

    # Calcul des marges et coûts pour BE
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

    # Calcul des marges et coûts pour le réel
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

    # Méthode write fusionnée
    def write(self, vals):
        _logger.info("Appel de write avec vals: %s", vals)
        
        # Si partner_id est modifié, mettre à jour le champ x_studio_mode_de_rglement_1
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            vals['x_studio_mode_de_rglement_1'] = partner.x_studio_mode_de_rglement_1

        # Appel de la méthode write parente
        res = super(SaleOrder, self).write(vals)
        _logger.info("Devis mis à jour: %s", self.id)
        
        # Mise à jour de l'entrepôt si les tags sont modifiés
        if 'tag_ids' in vals:
            _logger.info("Appel de _update_warehouse après mise à jour")
            self._update_warehouse()
        
        return res

    # Méthode create : mise à jour du mode de règlement
    @api.model_create_multi
    def create(self, vals_list):
        fma_tag = self.env['crm.tag'].search([('name', '=', 'FMA')], limit=1)
        f2m_tag = self.env['crm.tag'].search([('name', '=', 'F2M')], limit=1)
        for vals in vals_list:
            vals['so_date_du_devis'] = fields.Date.today()
            if 'partner_id' in vals:
                partner = self.env['res.partner'].browse(vals['partner_id'])
                vals['x_studio_mode_de_rglement_1'] = partner.x_studio_mode_de_rglement_1

            if 'tag_ids' in vals:
                tag_updates = vals.get('tag_ids', [])
                if tag_updates and fma_tag.id in tag_updates[0][2]:
                    warehouse_regripiere = self.env['stock.warehouse'].search([('name', '=', 'LA REGRIPPIERE')], limit=1)
                    if warehouse_regripiere:
                        vals['warehouse_id'] = warehouse_regripiere.id
                if tag_updates and f2m_tag.id in tag_updates[0][2]:
                    warehouse_remaudiere = self.env['stock.warehouse'].search([('name', '=', 'LA REMAUDIERE')], limit=1)
                    if warehouse_remaudiere:
                        vals['warehouse_id'] = warehouse_remaudiere.id

        return super(SaleOrder, self).create(vals_list)

    # Mise à jour de l'entrepôt en fonction des tags
    def _update_warehouse(self):
        _logger.info("Début de _update_warehouse pour le devis: %s", self.id)
        fma_tag = self.env['crm.tag'].search([('name', '=', 'FMA')], limit=1)
        f2m_tag = self.env['crm.tag'].search([('name', '=', 'F2M')], limit=1)
        for order in self:
            _logger.info("Tags actuels: %s", order.tag_ids)
            if fma_tag in order.tag_ids:
                warehouse_regripiere = self.env['stock.warehouse'].search([('name', '=', 'LA REGRIPPIERE')], limit=1)
                if warehouse_regripiere:
                    order.warehouse_id = warehouse_regripiere.id
            else:
                warehouse_remaudiere = self.env['stock.warehouse'].search([('name', '=', 'LA REMAUDIERE')], limit=1)
                if warehouse_remaudiere:
                    order.warehouse_id = warehouse_remaudiere.id
