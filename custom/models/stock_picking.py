from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # --- Champs migrés depuis Odoo Studio ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # Champs volontairement exclus de ce portage :
    # - 10 champs "related_field_*" (cible "related=" non vérifiable).
    # - x_studio_statut_de_la_commande : sélection, valeurs non vérifiées.
    # - x_studio_mtn_projet_mo : many2one vers "stock.reference", modèle
    #   dont l'existence n'a pas pu être confirmée en base -- à vérifier
    #   avant de le porter, une relation vers un modèle inexistant ferait
    #   échouer l'installation du module.
    #
    # Point notable : 7 champs différents (x_studio_affaire +
    # x_studio_many2one_field_J9w45/Luqxc/Vc214/fQVOa/oYral/uBzGv +
    # x_studio_many2many_field_JTFem), tous étiquetés "Affaire" et tous liés
    # à x_affaire, jamais renommés -- signe probable d'essais répétés côté
    # Studio. Portés tels quels (fidélité du schéma) ; lequel est réellement
    # utilisé reste à clarifier.
    x_studio_affaire = fields.Char(string="Affaire", readonly=True)
    x_studio_many2many_field_JTFem = fields.Many2many("x_affaire", string="Affaire")
    x_studio_many2one_field_fQVOa = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_J9w45 = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_Luqxc = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_oYral = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_uBzGv = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_Vc214 = fields.Many2one("x_affaire", string="Affaire")
    x_studio_n_bl = fields.Char(string="N° BL")
    # Projet de la vente, le meme que sur l'ordre de fabrication
    # (mrp.production.x_studio_projet_de_la_vente) : c'est le projet porte par
    # la commande a l'origine du transfert. Meme nom technique d'un modele a
    # l'autre, pour que le metier et les rapports parlent du meme champ.
    #
    # Stocke, sans quoi la colonne ne serait ni filtrable, ni groupable, ni
    # triable — or c'est pour trier les livraisons par affaire qu'on l'affiche.
    x_studio_projet_de_la_vente = fields.Many2one(
        "project.project",
        string="Projet de la vente",
        compute="_compute_x_studio_projet_de_la_vente",
        store=True,
        readonly=True,
        index="btree_not_null",
    )

    x_studio_projet_du_mo = fields.Many2one("project.project", string="Projet du MO", readonly=True)
    x_studio_projet_du_so = fields.Many2one("project.project", string="projet du SO")
    x_studio_projet_du_so_1 = fields.Many2one("project.project", string="Projet du SO", readonly=True)
    x_studio_projet_mo = fields.Many2one("project.project", string="Projet MO")
    x_studio_ref_client = fields.Char(string="Ref Client", readonly=True)
    x_studio_semaine_livraison_initiale = fields.Integer(string="Semaine Livraison initiale", readonly=True)
    x_studio_semaine_livraison_prevue = fields.Integer(string="Semaine Livraison prevue", readonly=True)

    so_retard_motif_level1_id = fields.Many2one(
        "sale.delay.category",
        string="Motif",
    )

    so_retard_motif_level2_id = fields.Many2one(
        "sale.delay.reason",
        string="Désignation",
        domain="[('category_id', '=', so_retard_motif_level1_id)]",
    )

    @api.onchange("so_retard_motif_level1_id")
    def _onchange_so_retard_motif_level1_id(self):
        # Si on change le Motif (catégorie), on reset la Désignation
        self.so_retard_motif_level2_id = False

    def _get_fields_stock_barcode(self):
        # Expose "N° BL" (x_studio_n_bl) sur l'écran code-barres -- le point
        # de personnalisation prévu par Odoo pour y ajouter un champ
        # (docstring de la méthode d'origine : "to be overridden in order
        # to inject new fields to the client action").
        return super()._get_fields_stock_barcode() + ["x_studio_n_bl"]

    @api.depends("sale_id")
    def _compute_x_studio_projet_de_la_vente(self):
        """Projet de la commande a l'origine du transfert.

        La dependance ne porte que sur sale_id, et non sur
        sale_id.x_studio_projet : ce dernier est declare par
        fma_sale_order_custom, qui depend de custom. Le nommer ici ferait
        echouer le chargement partout ou ce module n'est pas installe — c'est
        le meme piege que x_studio_date_de_relance_1 sur le devis.

        Consequence assumee : changer le projet d'une commande deja livree ne
        recalcule pas ses transferts. Le projet est renseigne avant la
        livraison, le cas est marginal, et une simple reouverture de la
        commande suffit a le rattraper.
        """
        for picking in self:
            commande = picking.sale_id
            picking.x_studio_projet_de_la_vente = (
                commande.x_studio_projet
                if commande and "x_studio_projet" in commande._fields
                else False
            )
