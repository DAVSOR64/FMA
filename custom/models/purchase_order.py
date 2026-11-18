# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # Détecte une commande "vitrage" pour n'afficher les champs dédiés
    # (dimensions des lignes) que sur ce type de commande, plutôt que sur
    # tous les achats. Catégorie réelle : "02_REMPLISSAGE" (chemin complet
    # "All / 02_REMPLISSAGE"), cohérente avec le nom déjà utilisé par le
    # moteur "Calcul PRI" (fma_custom/models/sale_order.py:20).
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

    def _fma_commandes_source(self):
        """Commande(s) client a l'origine de l'achat.

        Trois chemins, du plus direct au plus large : les lignes de vente
        liees (achat a la commande), la « Commande client » posee sur l'achat
        (fma_custom : achats nes d'un OF ou d'un lot, ou rattaches a la main),
        puis l'origine du bon quand elle cite un numero de commande.
        """
        self.ensure_one()
        commandes = self.env["sale.order"]
        if self.sale_order_count:
            commandes = self._get_sale_orders()
        if not commandes and "fma_sale_order_id" in self._fields:
            commandes = self.fma_sale_order_id
        if not commandes and "fma_sale_order_id" in self.order_line._fields:
            commandes = self.order_line.fma_sale_order_id
        if not commandes and self.origin:
            jetons = [j for j in self.origin.replace(",", " ").split() if len(j) > 1]
            if jetons:
                commandes = commandes.search([("name", "in", jetons)])
        return commandes

    def _sync_projet_du_so_from_sale_order(self):
        # Le « Projet » de l'achat (x_studio_projet_du_so) reprend celui de la
        # commande client. Il ne se remplissait plus : la regle lisait le
        # champ Studio x_studio_projet du devis, alors que le projet du devis
        # vit desormais dans project_id (le champ « Projet » du bloc Affaire).
        # On lit donc project_id d'abord, l'ancien champ ensuite. Et la
        # commande se cherche par tous les liens connus, pas seulement les
        # lignes de vente : un achat ne d'un OF ou d'un lot n'en a pas.
        # Ne touche jamais une valeur deja saisie.
        for po in self:
            if po.x_studio_projet_du_so:
                continue
            projet = self.env["project.project"]
            for commande in po._fma_commandes_source():
                projet = commande.project_id if "project_id" in commande._fields else projet
                if not projet and "x_studio_projet" in commande._fields:
                    projet = commande.x_studio_projet
                if projet:
                    break
            if projet:
                po.x_studio_projet_du_so = projet

    # --- Champs migrés depuis Odoo Studio ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # x_studio_rfrence, x_studio_many2one_field_LCOZX et x_studio_projet_du_so
    # étaient déjà utilisés (non déclarés) dans fma_custom/models/purchase_order.py
    # (automatisations Studio portées) et dans les gabarits d'export
    # purchase_order_export -- ils fonctionnaient uniquement via le
    # mécanisme Studio.
    # Champs volontairement exclus de ce portage :
    # - 10 champs "related_field_*" (cible "related=" non vérifiable).
    # - x_studio_test : champ non stocké et manifestement de test.
    x_studio_affaire = fields.Char(string="Affaire (texte)", readonly=True)
    x_studio_affaire_1 = fields.Char(string="Affaire (texte bis)", readonly=True)
    x_studio_boolean_field_qj_1ih5s6309 = fields.Boolean(string="Nouveau Case à cocher")
    x_studio_commentaire_interne_ = fields.Char(string="Commentaire Interne :")
    x_studio_commentaire_livraison_vitrage_ = fields.Char(string="Commentaire Livraison :")
    x_studio_many2one_field_25XKn = fields.Many2one("x_affaire", string="Affaire (25XKn)")
    x_studio_many2one_field_8k2_1ilmpvkuh = fields.Many2one("x_affaire", string="Nouveau Many2One")
    x_studio_many2one_field_d15iY = fields.Many2one("res.partner", string="Contact")
    x_studio_many2one_field_LCOZX = fields.Many2one("x_affaire", string="Affaire")
    # Libelle « Projet » a l'ecran ; le nom technique reste celui de Studio.
    x_studio_projet_du_so = fields.Many2one("project.project", string="Projet")
    x_studio_remise = fields.Many2one("x_remises_affaire", string="Remise")
    x_studio_remise_1 = fields.Many2one("x_remise_chantier", string="remise")
    x_studio_rfrence = fields.Char(string="Référence ", readonly=True)
