import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking" 

    def __init__(self, env, ids, prefetch_ids):
        super(StockPicking, self).__init__(env, ids, prefetch_ids)

    # Champ sale_id (s'il n'existe pas déjà)
    sale_id = fields.Many2one(
        "sale.order",
        string="Commande de Vente",
        help="Référence à la commande de vente associée",
    )  

    # Forcer le recalcul après la modification des mouvements
    def write(self, vals):
        res = super(StockPicking, self).write(vals)
        if "move_ids_without_package" in vals:  # Si les mouvements sont modifiés
            # self._compute_reliquat_qty()  # Recalcul du reliquat (commenté car non défini)
            _logger.warning(
                "Appel à '_compute_reliquat_qty' commenté car la méthode n'est pas définie."
            )
        if "scheduled_date" in vals:  # Mise à jour de la date de livraison si modifiée
            for picking in self:
                if picking.sale_id:
                    picking.sale_id.so_date_de_livraison_prevu = picking.scheduled_date
        return res

    # Champs détail colisage
    so_carton_qty = fields.Integer(string="Qté")
    so_botte_qty = fields.Integer(string="Qté")
    so_botte_length = fields.Float(string="Longueur (en mm)")
    so_poids_total = fields.Float(string="Poids (en kg)")

    # Ajout du champ one2many pour les lignes de colisage
    colisage_line_ids = fields.One2many(
        "picking.colisage.line", "picking_id", string="Lignes de Colisage"
    )

    palette_line_ids = fields.One2many(
        "picking.palette.line", "picking_id", string="Lignes de Palettes"
    )


class PickingColisageLine(models.Model):
    _name = "picking.colisage.line"
    _description = "Ligne de Colisage"
    _inherit = [
        "mail.thread"
    ]  # Inhérence au modèle de suivi Odoo pour l'historique des modifications
    _log_access = True  # Active l'historique des accès (qui a modifié et quand)

    picking_id = fields.Many2one("stock.picking", string="Colisage", ondelete="cascade")
    so_repere = fields.Char(string="Réf./Repère", track_visibility="onchange")
    so_designation = fields.Char(string="Désignation", track_visibility="onchange")
    so_largeur = fields.Float(string="Largeur", track_visibility="onchange")
    so_hauteur = fields.Float(string="Hauteur", track_visibility="onchange")
    so_qte_commandee = fields.Integer(
        string="Qté Commandée", track_visibility="onchange"
    )
    so_qte_livree = fields.Integer(string="Qté Livrée", track_visibility="onchange")

    # Contrainte SQL pour garantir l'unicité du champ 'so_repere'
    # _sql_constraints = [
    #     ('so_repere_unique', 'UNIQUE(so_repere)', 'La référence doit être unique !'),
    # ]

    @api.model
    def create(self, vals):
        """Permet de suivre les créations d'enregistrements dans le fil de discussion Odoo"""
        res = super(PickingColisageLine, self).create(vals)
        message = "Ligne de colisage créée : %s" % res.so_repere
        res.picking_id.message_post(body=message)
        return res

    def write(self, vals):
        """Permet de suivre les modifications dans le fil de discussion Odoo"""
        _logger.warning(
            "**********fonction write appelée dans PickingColisageLine *********"
        )  # Log d'avertissement
        res = super(PickingColisageLine, self).write(vals)
        message = "Ligne de colisage mise à jour."
        self.picking_id.message_post(body=message)
        return res


class PickingPaletteLine(models.Model):
    _name = "picking.palette.line"
    _description = "Ligne de Palette"
    _inherit = [
        "mail.thread"
    ]  # Permet le suivi des modifications dans le fil de discussion Odoo
    _log_access = True  # Active l'historique des accès

    picking_id = fields.Many2one("stock.picking", string="Palette", ondelete="cascade")
    qty = fields.Integer(string="Quantité", track_visibility="onchange")
    length = fields.Float(string="Longueur (mm)", track_visibility="onchange")
    depth = fields.Float(string="Profondeur (mm)", track_visibility="onchange")
    height = fields.Float(string="Hauteur (mm)", track_visibility="onchange")

    @api.model
    def create(self, vals):
        """Suivi des créations dans le fil de discussion Odoo"""
        res = super(PickingPaletteLine, self).create(vals)
        message = "Ligne de palette créée : %s palettes ajoutées." % res.qty
        res.picking_id.message_post(body=message)
        return res

    def write(self, vals):
        """Suivi des modifications dans le fil de discussion Odoo"""
        _logger.warning(
            "********** Fonction write appelée dans PickingPaletteLine *********"
        )  # Log d'avertissement
        res = super(PickingPaletteLine, self).write(vals)
        message = "Ligne de palette mise à jour."
        self.picking_id.message_post(body=message)
        return res
