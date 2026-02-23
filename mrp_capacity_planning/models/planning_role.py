# -*- coding: utf-8 -*-
from odoo import fields, models


class PlanningRole(models.Model):
    """
    Extension du rôle Planning pour s'assurer que workcenter_id existe.
    Si le champ est déjà créé via Studio ou mrp_macro_planning, ce fichier
    ne fait qu'ajouter les méthodes utilitaires sans recréer le champ.
    """
    _inherit = 'planning.role'

    # Ce champ est déjà présent dans mrp_macro_planning — on le déclare ici
    # uniquement si ce n'est pas déjà fait (Odoo gère les doublons en _inherit)
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Poste de travail',
        help='Poste de travail MRP associé à ce rôle de planification',
        ondelete='set null',
    )
