from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    # --- Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02) ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # x_studio_compte / x_studio_gneration_n_compte_1 / x_studio_mode_de_rglement
    # étaient déjà utilisés dans create()/write()/_prepare_order() ci-dessous
    # sans être déclarés -- ils fonctionnaient via le mécanisme Studio.
    # Champs volontairement exclus de ce portage (voir STUDIO_AUDIT.md) :
    # - x_studio_civilit_1, x_studio_motif_de_blocage, x_studio_nd_cover_accord,
    #   x_studio_selection_field_6du_1j97gmlnf : sélections dont les valeurs
    #   n'ont pas pu être vérifiées en base au moment du portage.
    # - x_studio_related_field_2cd_1jgpadkig, x_studio_related_field_5g_1jgpabllj,
    #   x_studio_related_field_883_1jj19o2np : champs liés dont la cible
    #   ("related=") n'a pas pu être vérifiée en base.
    # - x_studio_commercial : marqué "OLD"/déprécié par le métier côté Studio.
    x_studio_adresse_dmat_facturation = fields.Char(string="Adresse Démat Facturation")
    x_studio_allianz_couverture_euleur = fields.Float(string="ALLIANZ COUVERTURE EULEUR")
    x_studio_allianz_eh_decision = fields.Char(string="assurance-crédit")
    x_studio_allianz_nd_cover = fields.Boolean(string="ALLIANZ ND COVER")
    x_studio_allianz_nd_cover_1 = fields.Date(string="ALLIANZ ND COVER ")
    x_studio_bic = fields.Char(string="BIC")
    x_studio_boolean_field_1lb_1jkvbtk2n = fields.Boolean(string="Nouveau Case à cocher")
    x_studio_cgv_rib = fields.Boolean(string="CGV + RIB")
    x_studio_char_field_G6qIE = fields.Char(string="siren")
    x_studio_civilit = fields.Char(string="Civilité")
    x_studio_client_bloque = fields.Boolean(string="Client Bloqué")
    x_studio_code = fields.Char(string="Code", readonly=True)
    x_studio_code_diap = fields.Char(string="Code Diap")
    x_studio_code_naf = fields.Char(string="code NAF")
    x_studio_code_tiers = fields.Char(string="Code (tiers)")
    x_studio_commercial_1 = fields.Many2one("hr.employee", string="Commercial")
    x_studio_compte = fields.Integer(string="Compte")
    x_studio_compte_proginov = fields.Char(string="Compte PROGINOV")
    x_studio_encours_autoris = fields.Float(string="Encours Autorisé")
    x_studio_etablissement = fields.Char(string="Etablissement")
    x_studio_gneration_n_compte_1 = fields.Boolean(string="Géneration N° compte")
    x_studio_iban = fields.Char(string="IBAN")
    x_studio_iziqo_1 = fields.Boolean(string="Iziqo")
    x_studio_mode_de_rglement = fields.Char(string="Mode de réglement")
    x_studio_mode_de_rglement_dsa = fields.Many2one("x_reglements", string="Mode de règlement")
    x_studio_mtt_echu = fields.Float(string="Mtt Echu")
    x_studio_mtt_non_echu = fields.Float(string="Mtt Non Echu")
    x_studio_ref_logikal = fields.Char(string="Ref. LOGIKAL")
    x_studio_remise = fields.Float(string="Remise")

    x_studio_mode_de_rglement_1 = fields.Selection(
        [
            ("ESPECES", "ESPECES"),
            ("CHEQUE BANCAIRE", "CHEQUE BANCAIRE"),
            ("VIREMENT BANCAIRE", "VIREMENT BANCAIRE"),
            ("L.C.R. DIRECTE", "L.C.R. DIRECTE"),
            ("L.C.R. A L ACCEPTATION", "L.C.R. A L ACCEPTATION"),
            ("PRELEVEMENT", "PRELEVEMENT"),
            ("L.C.R. MAGNETIQUE", "L.C.R. MAGNETIQUE"),
            ("BOR", "BOR"),
            ("CARTE BANCAIRE", "CARTE BANCAIRE"),
            ("CREDIT DOCUMENTAIRE", "CREDIT DOCUMENTAIRE"),
        ],
        string="Mode de Règlement",
        default="VIREMENT BANCAIRE",
    )

    part_mode_de_reglement = fields.Selection(
        [
            ("ESPECES", "ESPECES"),
            ("CHEQUE BANCAIRE", "CHEQUE BANCAIRE"),
            ("VIREMENT BANCAIRE", "VIREMENT BANCAIRE"),
            ("L.C.R. DIRECTE", "L.C.R. DIRECTE"),
            ("L.C.R. A L ACCEPTATION", "L.C.R. A L ACCEPTATION"),
            ("PRELEVEMENT", "PRELEVEMENT"),
            ("L.C.R. MAGNETIQUE", "L.C.R. MAGNETIQUE"),
            ("BOR", "BOR"),
            ("CARTE BANCAIRE", "CARTE BANCAIRE"),
            ("CREDIT DOCUMENTAIRE", "CREDIT DOCUMENTAIRE"),
        ],
        string="Mode de Règlement",
        default="VIREMENT BANCAIRE",
    )

    part_commercial = fields.Selection(
        [
            ("A DEFINIR", "A Définir"),
            ("Adrien LAISNE", "Adrien LAISNE"),
            ("Alexandre BLOT", "Alexandre BLOT"),
            ("Alexandre DAUDE", "Alexandre DAUDE"),
            ("Alexandre DODE", "Alexandre DODE"),
            ("Alexandre POILANE", "Alexandre POILANE"),
            ("Cédric SEGUIN", "Cédric SEGUIN"),
            ("Carlos DA TORRE", "Carlos DA TORRE"),
            ("Cédric SANDRE", "Cédric SANDRE"),
            ("Christian GUILLARD", "Christian GUIHARD"),
            ("Cyril JACQUEMET", "Cyril JACQUEMET"),
            ("David JOUGLARD", "David JOUGLARD"),
            ("David CHARPENTIER", "David CHARPENTIER"),
            ("Franck SARAZIN", "Franck SARAZIN"),
            ("Frédéric DUCHEMIN", "Frédéric DUCHEMIN"),
            ("Grégory GIROLLET", "Grégory GIROLLET"),
            ("Guillaume GALLARDO", "Guillaume GALLARDO"),
            ("Hubert BOURDARAIS", "Hubert BOURDARIAS"),
            ("Jean JUSTAFRE", "Jean JUSTAFRE"),
            ("Jérôme DECAIX", "Jérôme DECAIX"),
            ("Karine HERVOUET", "Karine HERVOUET"),
            ("Mathieu LACAM", "Mathieu LACAM"),
            ("Mathieu LOISEAUX", "Mathieu LOISEAUX"),
            ("Maxime DE SOUSA", "Maxime DE SOUSA"),
            ("Mickaël DUH", "Mickaël DUH"),
            ("Nicolas FONTENEAU", "Nicolas FONTENEAU"),
            ("Nicolas FONTENEAU 1", "Nicolas FONTENEAU 1"),
            ("Olivier PECHEUR", "Olivier PECHEUR"),
            ("Pierre PINEAU", "Pierre PINEAU"),
            ("Pierre ROYER", "Pierre ROYER"),
            ("Quentin MOREAU", "Quentin MOREAU"),
            ("Quentin MOREAU 1", "Quentin MOREAU 1"),
            ("Richard ROTH", "Richard ROTH"),
            ("Richard ROTH 1", "Richard ROTH 1"),
            ("Richard ROTH 2", "Richard ROTH 2"),
            ("Recrutement 1", "Recrutement 1"),
            ("Recrutement 2", "Recrutement 2"),
            ("Recrutement 3", "Recrutement 3"),
            ("Recrutement 4", "Recrutement 4"),
            ("Recrutement 5", "Recrutement 5"),
            ("Sami ABID", "Sami ABID"),
            ("Stéphane MOUSSEL", "Stéphane MOUSSEL"),
            ("Vincent PERROT", "Vincent PERROT"),
            ("Client Direct", "Client Direct"),
            ("Sans Affectation", "Sans Affectation"),
        ],
        string="Commercial",
        default="A DEFINIR",
    )

    part_civilite = fields.Selection(
        [
            ("SARL", "SARL"),
            ("EURL", "EURL"),
            ("EI", "EI"),
            ("SAS", "SAS"),
            ("SASU", "SASU"),
            ("SCI", "SCI"),
            ("Madame ou Monsieur", "Madame ou Monsieur"),
            ("SA", "SA"),
            ("SNC", "SNC"),
            ("SCOP", "SCOP"),
            ("SCEA", "SCEA"),
            ("SELARL", "SELARL"),
            ("LLC", "LLC"),
            ("COLLECTIVITE", "COLLECTIVITE"),
        ],
        string="Civilité",
        default="SARL",
    )

    part_siren = fields.Char(string="SIREN")
    part_bic = fields.Char(string="BIC")
    part_iban = fields.Char(string="IBAN")
    part_affacturage = fields.Boolean(string="Affacturage")
    part_couverture = fields.Boolean(string="ALLIANZ ND COVER")
    part_date_couverture = fields.Date(string="ALLIANZ ND COVER (date)")
    part_montant_couverture = fields.Float(string="ALLIANZ COUVERTURE EULEUR")
    part_decision = fields.Char(string="ASSURANCE-CREDIT")
    part_code_tiers = fields.Integer(string="Code Tiers")

    attachment_ids = fields.Many2many(
        "ir.attachment",
        "res_partner_ir_attachment_rel",
        "partner_id",
        "attachment_id",
        string="Attachments",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("x_studio_gneration_n_compte_1", False):
                last_record = self.search(
                    [("is_company", "=", True), ("x_studio_compte", "!=", False)],
                    order="x_studio_compte desc",
                    limit=1,
                )
                last_code = last_record.x_studio_compte if last_record else 0
                vals["x_studio_compte"] = last_code + 1
                vals["x_studio_gneration_n_compte_1"] = False
        return super(ResPartner, self).create(vals_list)

    def write(self, vals):
        for partner in self:
            # Si la case est cochée, génère le numéro uniquement si pas déjà défini
            if (
                vals.get("x_studio_gneration_n_compte_1", False)
                and not partner.x_studio_compte
            ):
                last_record = self.search(
                    [("is_company", "=", True), ("x_studio_compte", "!=", False)],
                    order="x_studio_compte desc",
                    limit=1,
                )
                last_code = last_record.x_studio_compte if last_record else 0
                new_code = last_code + 1

                partner.x_studio_compte = new_code

                # Décoche le booléen après génération
                vals["x_studio_gneration_n_compte_1"] = False

        return super(ResPartner, self).write(vals)

    def _prepare_order(self):
        order_vals = super(ResPartner, self)._prepare_order()
        order_vals["x_studio_mode_de_rglement"] = self.x_studio_mode_de_rglement_1
        return order_vals
