from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    # --- Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02) ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # 27 champs volontairement exclus de ce portage (voir STUDIO_AUDIT.md) :
    # - 19 champs "related_field_*" (cible "related=" non vérifiable en base).
    # - x_studio_centre_de_frais, x_studio_commercial, x_studio_materiaux,
    #   x_studio_mode_de_reglement, x_studio_motif_impay : sélections dont
    #   les valeurs n'ont pas pu être vérifiées.
    # - x_studio_commercial_1_mtn : marqué "OLD"/déprécié côté Studio.
    # - x_studio_mode_de_reglement_1, x_studio_projet_vente : non stockés
    #   côté Studio (probablement liés), pas portés pour éviter de figer
    #   leur valeur.
    x_studio_affaire_relance = fields.Char(string="Affaire relance")
    x_studio_code_tiers = fields.Char(string="Code (tiers)", readonly=True)
    x_studio_compte = fields.Char(string="Compte", readonly=True)
    x_studio_compte_1 = fields.Integer(string="Compte", readonly=True)
    x_studio_courriel = fields.Char(string="Courriel", readonly=True)
    x_studio_libelle_1 = fields.Char(string="Libelle", readonly=True)
    x_studio_many2one_field_kKSU8 = fields.Many2one("account.analytic.account", string="Compte analytique")
    x_studio_reglement = fields.Char(string="Reglement", readonly=True)

    x_studio_rfrence_affaire = fields.Char(string="Affaire")
    x_studio_imputation_2 = fields.Char(string="Référence Commande Client")
    x_studio_delegation_fac = fields.Boolean(string="Déléagtion")
    x_studio_com_delegation_fac = fields.Char(string="Commentaire Délégation :")
    x_studio_mode_de_rglement = fields.Char(string="Mode de réglement")
    x_studio_related_field_m8sZb = fields.Char(string="test")
    x_studio_mode_de_rglement_1 = fields.Char(string="Mode de réglement")

    inv_mode_de_reglement = fields.Selection(
        related="partner_id.part_mode_de_reglement", string="Mode de Règlement"
    )
    inv_code_tiers = fields.Integer(
        related="partner_id.part_code_tiers", string="Code Tiers"
    )
    inv_commercial = fields.Selection(
        related="partner_id.part_commercial", string="Commercial"
    )
    inv_commande_client = fields.Char(string="N° Commande Client")
    inv_affacturage = fields.Boolean(
        related="partner_id.part_affacturage", string="Affacturage"
    )
    inv_activite = fields.Char(string="Activité")
    is_txt_created = fields.Boolean(string="TXT Created")
