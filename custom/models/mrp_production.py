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
    # Projet de la vente : le « Projet mtn » de la commande a l'origine de
    # l'OF, c'est-a-dire sale.order.x_studio_projet — et non project_id, qui
    # porte le projet analytique « Analytic Project (...) », un autre
    # enregistrement.
    #
    # Calcule et stocke, mais avec une regle absolue : ne jamais effacer. Une
    # premiere version ecrivait False quand la commande restait introuvable,
    # et le recalcul de masse a vide le champ sur toute la production.
    x_studio_projet_de_la_vente = fields.Many2one(
        "project.project",
        string="Projet de la vente",
        compute="_compute_x_studio_projet_de_la_vente",
        store=True,
        readonly=False,
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
        """Commande a l'origine de l'OF, par trois chemins successifs.

        Le troisieme est celui qui manquait, et c'est le seul qui reponde sur
        la majorite du parc : reference_ids.sale_ids. C'est le mecanisme v19
        qui alimente le bouton « Ventes » de l'OF, et c'est celui que la regle
        d'automatisation Studio utilise pour poser
        x_studio_mtn_mrp_sale_order. Sans lui, un OF comme LRE/LRE/04506
        affiche sa commande a l'ecran alors que le code ne la trouve pas.
        """
        self.ensure_one()
        commande = self.sale_line_id.order_id if "sale_line_id" in self._fields else False
        if not commande and "x_studio_mtn_mrp_sale_order" in self._fields:
            commande = self.x_studio_mtn_mrp_sale_order
        if not commande and "reference_ids" in self._fields:
            references = self.reference_ids
            if "sale_ids" in references._fields:
                commande = references.sale_ids
        return commande[:1] if commande else self.env["sale.order"]

    @api.depends("x_studio_mtn_mrp_sale_order")
    def _compute_x_studio_projet_de_la_vente(self):
        """Recopie le « Projet mtn » de la commande sur l'OF.

        La dependance ne cite QUE x_studio_mtn_mrp_sale_order, seul champ
        declare par custom lui-meme. Ni sale_line_id, ni reference_ids, ni
        x_studio_projet n'y figurent : custom charge en 257e position sur 356,
        avant les modules qui les apportent, et Odoo resout les dependances au
        chargement de CHAQUE module. Nommer un champ pas encore declare fait
        echouer le demarrage de la base entiere — c'est deja arrive ici.

        Ces champs sont donc lus au moment du calcul, quand le registre les
        connait. Le prix a payer est qu'un OF rattache par reference_ids seul
        ne declenche pas de recalcul spontane ; l'automatisation Studio pose
        x_studio_mtn_mrp_sale_order et c'est elle qui l'amorce.
        """
        # Les valeurs deja en base, lues d'un coup en SQL. Relire le champ
        # depuis l'enregistrement, au sein de son propre calcul, est le genre
        # de detour dont Odoo ne garantit rien pendant un recalcul de masse —
        # et c'est cette garde-la qui protege la donnee. Elle doit etre sure.
        anciennes = {}
        existants = [i for i in self.ids if isinstance(i, int)]
        if existants:
            self.env.cr.execute(
                "SELECT id, x_studio_projet_de_la_vente FROM mrp_production"
                " WHERE id IN %s", (tuple(existants),))
            anciennes = dict(self.env.cr.fetchall())

        for production in self:
            commande = production._fma_commande_de_la_vente()
            projet = (
                commande.x_studio_projet
                if commande and "x_studio_projet" in commande._fields
                else False
            )
            # Ne JAMAIS effacer. Ce champ portait des valeurs Studio saisies
            # ou posees par une automatisation avant d'etre calcule : ecrire
            # False quand la commande reste introuvable les detruirait, et un
            # recalcul de masse le ferait sur toute la base d'un coup. C'est
            # exactement ce qui s'est produit. Un calcul qui ne trouve rien se
            # tait.
            production.x_studio_projet_de_la_vente = (
                projet or anciennes.get(production.id) or False
            )
