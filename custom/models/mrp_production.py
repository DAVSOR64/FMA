from odoo import models, fields, api
from datetime import datetime


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # --- Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02) ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # x_studio_mtn_mrp_sale_order était déjà utilisé (non déclaré) par le
    # portage Phase 1 (fma_custom/models/mrp_production.py).
    # 1 champ exclu : x_studio_atelier (sélection, valeurs non vérifiées).
    x_studio_date_de_fin = fields.Date(string="Date de fin")
    x_studio_date_field_wIHQY = fields.Date(string="New Date")
    x_studio_mtn_mrp_sale_order = fields.Many2one("sale.order", string="mtn mrp sale order")
    x_studio_niveau_de_complexite = fields.Text(string="NIVEAUX DE COMPLEXITE")
    x_studio_projet_de_la_vente = fields.Many2one("project.project", string="Projet de la vente", readonly=True)
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
