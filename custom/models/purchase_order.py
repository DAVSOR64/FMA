# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # Détecte une commande "vitrage" pour n'afficher les champs dédiés
    # (remise, commentaires, dimensions) que sur ce type de commande, plutôt
    # que sur tous les achats -- retour métier ELOGAU, réunion du 20/07/2026 :
    # "afficher les champs vitrage uniquement quand la catégorie de produit
    # = Remplissage". Nom de catégorie initialement en dur ("Remplissage"),
    # confirmé faux par retour métier T-13 (David, 29/07, capture d'écran
    # article A26-03-01167) : la catégorie réelle est "02_REMPLISSAGE"
    # (chemin complet "All / 02_REMPLISSAGE"), cohérente avec le nom déjà
    # utilisé par le moteur "Calcul PRI" (fma_custom/models/sale_order.py:20).
    x_is_glazing_order = fields.Boolean(
        string="Commande vitrage", compute="_compute_x_is_glazing_order", store=True
    )

    @api.depends("order_line.product_id.categ_id")
    def _compute_x_is_glazing_order(self):
        for order in self:
            order.x_is_glazing_order = any(
                line.product_id.categ_id.name == "02_REMPLISSAGE" for line in order.order_line
            )

    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._sync_projet_du_so_from_sale_order()
        return orders

    def write(self, vals):
        res = super().write(vals)
        self._sync_projet_du_so_from_sale_order()
        return res

    def _sync_projet_du_so_from_sale_order(self):
        # "Projet du SO" (x_studio_projet_du_so) n'était alimenté par aucun
        # mécanisme -- ni les automatisations Studio encore actives en base
        # (base.automation "DSA Reference compute PO"/"...responsable...",
        # qui le lisent mais ne l'écrivent jamais), ni le portage Python
        # (fma_custom/models/purchase_order.py, jamais chargé : son
        # __init__.py n'importe pas le sous-package "models", cf. audit du
        # 21/07/2026 -- hors périmètre de ce correctif ciblé). Constaté en
        # test métier (Nolhan, #7/#29) et confirmé en base sur les données
        # réelles : ~48% des commandes liées à un devis "projet" concerné
        # restent vides. Ne touche jamais une valeur déjà saisie (manuelle
        # ou future automatisation), et n'agit que si le devis source a
        # lui-même un projet renseigné (champ x_studio_projet, module
        # fma_sale_order_custom, non garanti installé -- vérifié dynamiquement).
        for po in self:
            if po.x_studio_projet_du_so or not po.sale_order_count:
                continue
            sale_order = po._get_sale_orders()[:1]
            if (
                sale_order
                and "x_studio_projet" in sale_order._fields
                and sale_order.x_studio_projet
            ):
                po.x_studio_projet_du_so = sale_order.x_studio_projet

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
