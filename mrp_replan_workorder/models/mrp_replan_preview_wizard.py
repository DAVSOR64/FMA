# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpReplanPreviewWizard(models.TransientModel):
    _name = "mrp.replan.preview.wizard"
    _description = "Assistant technique de compatibilité"

    name = fields.Char(default="Compatibilité")
