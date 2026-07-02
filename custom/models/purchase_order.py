# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # --- Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02) ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # x_studio_rfrence, x_studio_many2one_field_LCOZX et x_studio_projet_du_so
    # étaient déjà utilisés (non déclarés) dans fma_custom/models/purchase_order.py
    # (portage Phase 1 des automatisations Studio) et dans les gabarits
    # d'export purchase_order_export -- ils fonctionnaient uniquement via le
    # mécanisme Studio.
    # 11 champs volontairement exclus de ce portage (voir STUDIO_AUDIT.md) :
    # - 10 champs "related_field_*" (cible "related=" non vérifiable).
    # - x_studio_test : champ non stocké et manifestement de test.
    x_studio_affaire = fields.Char(string="Affaire", readonly=True)
    x_studio_affaire_1 = fields.Char(string="Affaire", readonly=True)
    x_studio_boolean_field_qj_1ih5s6309 = fields.Boolean(string="Nouveau Case à cocher")
    x_studio_commentaire_interne_ = fields.Char(string="Commentaire Interne :")
    x_studio_commentaire_livraison_vitrage_ = fields.Char(string="Commentaire Livraison :")
    x_studio_many2one_field_25XKn = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_8k2_1ilmpvkuh = fields.Many2one("x_affaire", string="Nouveau Many2One")
    x_studio_many2one_field_d15iY = fields.Many2one("res.partner", string="Contact")
    x_studio_many2one_field_LCOZX = fields.Many2one("x_affaire", string="Affaire")
    x_studio_projet_du_so = fields.Many2one("project.project", string="projet du SO")
    x_studio_remise = fields.Many2one("x_remises_affaire", string="Remise")
    x_studio_remise_1 = fields.Many2one("x_remise_chantier", string="remise")
    x_studio_rfrence = fields.Char(string="Référence ", readonly=True)
