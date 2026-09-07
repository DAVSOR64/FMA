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

    @api.depends("x_studio_mtn_mrp_sale_order")
    def _compute_x_studio_projet_de_la_vente(self):
        """Projet de la commande, recopie sur l'OF.

        La dependance ne cite QUE x_studio_mtn_mrp_sale_order, seul champ
        declare par custom lui-meme. Ni sale_line_id, ni x_studio_projet n'y
        figurent, et pour la meme raison de fond : custom est charge en 257e
        position sur 356, avant les modules qui les apportent — sale_line_id
        vient d'un module de liaison vente/fabrication, x_studio_projet de
        fma_sale_order_custom, qui depend de custom.

        Odoo resout les dependances au chargement de CHAQUE module, pas a la
        fin : nommer un champ pas encore declare fait echouer le demarrage.
        « Dependency field 'sale_line_id' not found in model mrp.production »,
        et la base entiere refuse de se lever. fma_mrp_ordonnancement peut se
        le permettre, lui, car il charge en 301e position.

        Les deux champs sont donc lus au moment du calcul, si le registre les
        connait alors. Consequence : l'OF rattache a une ligne de commande
        sans passer par x_studio_mtn_mrp_sale_order ne declenche pas de
        recalcul — mais fma_custom renseigne justement ce champ dans ce cas.
        """
        for production in self:
            commande = production._fma_commande_de_la_vente()
            projet = (
                commande.x_studio_projet
                if commande and "x_studio_projet" in commande._fields
                else False
            )
            # Ne JAMAIS effacer une valeur existante. Ce champ etait un champ
            # Studio saisi ou alimente par une automatisation avant d'etre
            # calcule : ecrire False quand la commande reste introuvable
            # detruirait cet historique, et le recalcul de masse le ferait sur
            # toute la base d'un coup. Un calcul qui ne trouve rien se tait.
            production.x_studio_projet_de_la_vente = (
                projet or production.x_studio_projet_de_la_vente
            )
