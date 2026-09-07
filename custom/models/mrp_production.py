from odoo import models, fields, api
from datetime import datetime


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # --- Champs migrés depuis Odoo Studio ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # x_studio_mtn_mrp_sale_order était déjà utilisé (non déclaré) par le
    # portage Phase 1 (fma_custom/models/mrp_production.py).
    # 1 champ exclu : x_studio_atelier (sélection, valeurs non vérifiées).
    x_studio_date_de_fin = fields.Date(string="Date de fin")
    x_studio_date_field_wIHQY = fields.Date(string="New Date")
    x_studio_mtn_mrp_sale_order = fields.Many2one("sale.order", string="mtn mrp sale order")
    x_studio_niveau_de_complexite = fields.Text(string="NIVEAUX DE COMPLEXITE")
    # Projet de la vente : le projet porte par la commande a l'origine de l'OF.
    # Calcule et stocke, la ou il n'etait qu'un champ Studio saisissable qui
    # restait vide. Stocke, parce que c'est sur lui qu'on filtre et qu'on
    # regroupe les OF par affaire.
    x_studio_projet_de_la_vente = fields.Many2one(
        "project.project",
        string="Projet de la vente",
        compute="_compute_x_studio_projet_de_la_vente",
        store=True,
        readonly=True,
        index="btree_not_null",
    )
    x_studio_projet_so = fields.Many2one("project.project", string="Projet SO")
    x_studio_text_field_7bi_1jnoud87m = fields.Text(string="Nouveau Texte multiligne")

    def button_mark_done(self):
        # Appel de la méthode d'origine pour valider l'ordre de production
        res = super(MrpProduction, self).button_mark_done()

        # Vérifiez si l'ordre de production a une référence vers un devis
        if self.origin:
            # Recherche du devis correspondant en fonction de l'origine (nom de l'ordre de vente)
            sale_order = self.env["sale.order"].search(
                [("name", "=", self.origin)], limit=1
            )
            if sale_order:
                # Mettez à jour le champ de date avec la date actuelle
                sale_order.write({"so_date_de_fin_de_production_reel": datetime.now()})

        return res

    def _fma_commande_de_la_vente(self):
        """Commande a l'origine de l'OF.

        Deux chemins, dans cet ordre : le lien natif quand l'OF vient d'une
        ligne de commande, et sinon x_studio_mtn_mrp_sale_order, que
        fma_custom renseigne en remontant les mouvements — c'est la reprise en
        code de la regle d'automatisation Studio, avec ses replis v19
        (production_group_id, stock.move.sale_line_id...).

        Meme resolution que fma_mrp_ordonnancement : deux facons differentes de
        retrouver la commande d'un OF finiraient par ne plus dire la meme
        chose.
        """
        self.ensure_one()
        commande = self.sale_line_id.order_id if "sale_line_id" in self._fields else False
        if not commande and "x_studio_mtn_mrp_sale_order" in self._fields:
            commande = self.x_studio_mtn_mrp_sale_order
        return commande[:1] if commande else self.env["sale.order"]

    @api.depends("sale_line_id.order_id", "x_studio_mtn_mrp_sale_order")
    def _compute_x_studio_projet_de_la_vente(self):
        """Projet de la commande, recopie sur l'OF.

        La dependance ne descend pas jusqu'a x_studio_projet : ce champ est
        declare par fma_sale_order_custom, qui depend de custom. Le nommer ici
        ferait echouer le chargement partout ou ce module n'est pas installe.
        Il est donc lu au moment du calcul, si le registre le connait.
        """
        for production in self:
            commande = production._fma_commande_de_la_vente()
            production.x_studio_projet_de_la_vente = (
                commande.x_studio_projet
                if commande and "x_studio_projet" in commande._fields
                else False
            )
