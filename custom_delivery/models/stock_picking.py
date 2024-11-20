import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    

    def __init__(self, pool, cr):
        super(StockPicking, self).__init__(pool, cr)
        _logger.warning("Le modèle StockPicking est chargé avec succès")

    # Champ sale_id (s'il n'existe pas déjà)
    sale_id = fields.Many2one('sale.order', string="Commande de Vente", help="Référence à la commande de vente associée")
    
    so_acces_bl = fields.Char(string="Accès")
    so_horaire_ouverture_bl = fields.Float(string='Horaire ouverture', widget='float_time')
    so_horaire_fermeture_bl = fields.Float(string='Horaire fermeture', widget='float_time')


    # Forcer le recalcul après la modification des mouvements
    def write(self, vals):
        res = super(StockPicking, self).write(vals)
        if 'move_ids_without_package' in vals:  # Si les mouvements sont modifiés
            self._compute_reliquat_qty()  # Recalcul du reliquat
        if 'scheduled_date' in vals:  # Mise à jour de la date de livraison si modifiée
            for picking in self:
                if picking.sale_id:
                    picking.sale_id.so_date_de_livraison_prevu = picking.scheduled_date
        return res

    so_type_camion_bl = fields.Selection(
        [
            ('Fourgon 20m3 (150€ + 0.50€/km)','Fourgon 20m3 (150€ + 0.50€/km)'),
            ('GEODIS','GEODIS'),
            ('Porteur avec hayon (base)','Porteur avec hayon (base)'),
            ('Semi-remorque (base)','Semi-remorque (base)'),
            ('Semi-remorque avec hayon (base)','Semi-remorque avec hayon (base)'),
            ('Semi-remorque plateau (base)','Semi-remorque plateau (base)'),
            ('Semi-remorque chariot embarqué (650€)','Semi-remorque chariot embarqué (650€)'),
            ('Autre (sur devis)','Autre (sur devis)'),
        ],
        string="Type de camion (Hayon palette maxi 2400mm)",
    )

    # Champs détail colisage
    so_carton_qty = fields.Integer(string='Qté')
    so_botte_qty = fields.Integer(string='Qté')
    so_botte_length = fields.Float(string='Longueur (en m)')
    so_palette_qty = fields.Integer(string='Qté')
    so_palette_length = fields.Float(string='Longueur (en m)')
    so_palette_depth = fields.Float(string='Profondeur (en m)')
    so_palette_height = fields.Float(string='Hauteur (en m)')
    so_poids_total = fields.Float(string='Poids (en kg)')

    # Ajout du champ one2many pour les lignes de colisage
    colisage_line_ids = fields.One2many(
        'picking.colisage.line', 'picking_id', string="Lignes de Colisage"
    )

class PickingColisageLine(models.Model):
    _name = 'picking.colisage.line'
    _description = 'Ligne de Colisage'
    _inherit = ['mail.thread']  # Inhérence au modèle de suivi Odoo pour l'historique des modifications
    _log_access = True  # Active l'historique des accès (qui a modifié et quand)

    picking_id = fields.Many2one('stock.picking', string="Colisage", ondelete='cascade')
    so_repere = fields.Char(string="Réf./Repère", track_visibility='onchange')
    so_designation = fields.Char(string="Désignation", track_visibility='onchange')
    so_largeur = fields.Float(string="Largeur", track_visibility='onchange')
    so_hauteur = fields.Float(string="Hauteur", track_visibility='onchange')
    so_qte_commandee = fields.Integer(string="Qté Commandée", track_visibility='onchange')
    so_qte_livree = fields.Integer(string="Qté Livrée", track_visibility='onchange')

    # Contrainte SQL pour garantir l'unicité du champ 'so_repere'
    _sql_constraints = [
        ('so_repere_unique', 'UNIQUE(so_repere)', 'La référence doit être unique !'),
    ]

    @api.model
    def create(self, vals):
        """Permet de suivre les créations d'enregistrements dans le fil de discussion Odoo"""
        res = super(PickingColisageLine, self).create(vals)
        message = "Ligne de colisage créée : %s" % res.so_repere
        res.picking_id.message_post(body=message)
        return res

    def write(self, vals):
        """Permet de suivre les modifications dans le fil de discussion Odoo"""
        _logger.warning("**********fonction write appelée dans PickingColisageLine *********")  # Log d'avertissement
        res = super(PickingColisageLine, self).write(vals)
        message = "Ligne de colisage mise à jour."
        self.picking_id.message_post(body=message)
        return res
