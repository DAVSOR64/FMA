from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # --- Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02) ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # 12 champs volontairement exclus de ce portage (voir STUDIO_AUDIT.md) :
    # - 10 champs "related_field_*" (cible "related=" non vérifiable).
    # - x_studio_statut_de_la_commande : sélection, valeurs non vérifiées.
    # - x_studio_mtn_projet_mo : many2one vers "stock.reference", modèle
    #   dont l'existence n'a pas pu être confirmée en base (accès SSH
    #   indisponible) -- à vérifier avant de le porter, une relation vers un
    #   modèle inexistant ferait échouer l'installation du module.
    #
    # Point notable : 7 champs différents (x_studio_affaire +
    # x_studio_many2one_field_J9w45/Luqxc/Vc214/fQVOa/oYral/uBzGv +
    # x_studio_many2many_field_JTFem), tous étiquetés "Affaire" et tous liés
    # à x_affaire, jamais renommés -- signe probable d'essais répétés côté
    # Studio. Portés tels quels (fidélité du schéma), mais à clarifier avec
    # le métier lequel est réellement utilisé.
    x_studio_affaire = fields.Char(string="Affaire", readonly=True)
    x_studio_many2many_field_JTFem = fields.Many2many("x_affaire", string="Affaire")
    x_studio_many2one_field_fQVOa = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_J9w45 = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_Luqxc = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_oYral = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_uBzGv = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_Vc214 = fields.Many2one("x_affaire", string="Affaire")
    x_studio_n_bl = fields.Char(string="N° BL")
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
