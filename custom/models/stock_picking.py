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

    def _fma_ordres_de_fabrication(self):
        """Ordres de fabrication auxquels ce transfert se rattache.

        Trois chemins, du plus direct au plus permissif, parce qu'un OF n'est
        pas relie de la meme facon a tous ses transferts.

        Les mouvements du transfert portent parfois l'OF directement :
        production_id pour l'entree du produit fini,
        raw_material_production_id pour la consommation des composants.

        Mais pas toujours, et c'est ce qui laissait le champ vide. Avec une
        fabrication en deux ou trois etapes, le transfert « Collecter les
        composants » deplace la matiere du stock vers la pre-fabrication : ses
        mouvements ne sont PAS ceux de l'OF, ils les alimentent. Le lien passe
        alors par le chainage — move_dest_ids vers l'aval, move_orig_ids vers
        l'amont pour le transfert des produits finis.

        En dernier recours, le document d'origine : Odoo y inscrit le nom de
        l'OF, comme le montre « LRE/LRE/04506 » sur ces transferts. Moins sur
        qu'une relation, mais c'est mieux qu'un champ vide.
        """
        self.ensure_one()
        Move = self.env["stock.move"]
        Production = self.env["mrp.production"]
        champs = [c for c in ("production_id", "raw_material_production_id")
                  if c in Move._fields]
        if not champs:
            return Production

        mouvements = self.move_ids
        for lien in ("move_dest_ids", "move_orig_ids"):
            if lien in Move._fields:
                mouvements |= self.move_ids.mapped(lien)

        productions = Production
        for champ in champs:
            productions |= mouvements.mapped(champ)
        if productions:
            return productions

        origine = (self.origin or "").strip()
        if origine:
            productions = Production.sudo().search([("name", "=", origine)], limit=1)
        return productions

    def _fma_commande_de_la_vente(self):
        """Commande a l'origine du transfert, directe ou via l'ordre de fabrication.

        Une livraison porte sa commande dans sale_id. Les transferts d'un OF
        n'en ont aucune : ils sont rattaches a l'OF, qui lui la connait.
        """
        self.ensure_one()
        if self.sale_id:
            return self.sale_id[:1]
        for production in self._fma_ordres_de_fabrication():
            commande = production._fma_commande_de_la_vente()
            if commande:
                return commande
        return self.env["sale.order"]

    @api.depends("sale_id", "move_ids")
    def _compute_x_studio_projet_de_la_vente(self):
        """Projet de la vente, sur la livraison comme sur les transferts d'OF.

        La dependance se limite a sale_id et move_ids, deux champs apportes
        par des modules dont custom depend et donc charges avant lui. Ni les
        champs de l'OF, ni x_studio_projet n'y figurent : Odoo resout les
        dependances au chargement de CHAQUE module, et custom vient en 257e
        position sur 356. Un champ pas encore declare y fait echouer le
        demarrage de la base entiere — c'est ce qui s'est produit avec
        sale_line_id sur l'ordre de fabrication.

        Tout le reste est donc lu au moment du calcul, si le registre le
        connait alors.

        Consequence assumee : le transfert ne se recalcule pas si l'OF
        retrouve sa commande apres coup, ni si le projet change sur une
        commande deja livree. Les deux se rattrapent en rouvrant
        l'enregistrement, et l'ordre normal des choses — commande, puis OF,
        puis transferts — les rend marginaux.
        """
        for picking in self:
            commande = picking._fma_commande_de_la_vente()
            projet = (
                commande.x_studio_projet
                if commande and "x_studio_projet" in commande._fields
                else False
            )
            # Meme regle que sur l'ordre de fabrication : un calcul qui ne
            # trouve rien se tait plutot que d'effacer.
            picking.x_studio_projet_de_la_vente = (
                projet or picking.x_studio_projet_de_la_vente
            )
