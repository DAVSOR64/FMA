import logging
from odoo import models, fields, api
from odoo.tools import float_round
from datetime import timedelta

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    main_contact_id = fields.Many2one(
        'res.partner',
        string="Contact principal",
        help="Contact principal chez le client."
    )

    @api.onchange('partner_id')
    def _onchange_partner_id_clear_main_contact(self):
        """Quand le client change, on réinitialise le Contact principal."""
        res = super(SaleOrder, self)._onchange_partner_id()
        self.main_contact_id = False
        return res
    # >>>>>> FIN NOUVEAU CHAMP <<<<<<

    x_studio_ref_affaire = fields.Char(string="Affaire")
    x_studio_imputation = fields.Char(string="Numéro Commande Client")
    x_studio_delegation = fields.Boolean(string="Délégation")
    x_studio_com_delegation = fields.Char(string="Commentaire Délégation:")
    x_studio_mode_de_rglement_1 = fields.Selection(
        [
            ('ESPECES', 'ESPECES'),
            ('CHEQUE BANCAIRE', 'CHEQUE BANCAIRE'),
            ('VIREMENT BANCAIRE', 'VIREMENT BANCAIRE'),
            ('L.C.R. DIRECTE', 'L.C.R. DIRECTE'),
            ('L.C.R. A L ACCEPTATION', 'L.C.R. A L ACCEPTATION'),
            ('PRELEVEMENT', 'PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE', 'L.C.R. MAGNETIQUE'),
            ('BOR', 'BOR'),
            ('CARTE BANCAIRE', 'CARTE BANCAIRE'),
            ('CREDIT DOCUMENTAIRE', 'CREDIT DOCUMENTAIRE'),
        ],
        string="Mode de Règlement",
    )

    so_type_camion_bl = fields.Selection(
        [
            ('Fourgon 20m3 (150€ + 0.50€/km)', 'Fourgon 20m3 (150€ + 0.50€/km)'),
            ('GEODIS', 'GEODIS'),
            ('Porteur avec hayon (base)', 'Porteur avec hayon (base)'),
            ('Semi-remorque (base)', 'Semi-remorque (base)'),
            ('Semi-remorque avec hayon (base)', 'Semi-remorque avec hayon (base)'),
            ('Semi-remorque plateau (base)', 'Semi-remorque plateau (base)'),
            ('Semi-remorque chariot embarqué (650€)', 'Semi-remorque chariot embarqué (650€)'),
            ('Autre (sur devis)', 'Autre (sur devis)'),
        ],
        string="Type de camion (Hayon palette maxi 2400mm)",
    )

    so_acces_bl = fields.Char(string="Accès")
    so_horaire_ouverture_bl = fields.Float(string='Horaire ouverture', widget='float_time')
    so_horaire_fermeture_bl = fields.Float(string='Horaire fermeture', widget='float_time')

    x_studio_date_de_la_commande = fields.Date(string="Date de la Commande")
    is_all_service = fields.Boolean(string="Is All Service")
    delivery_set = fields.Boolean(string="Delivery Set")
    recompute_delivery_price = fields.Boolean(string="Delivery Price")

    so_mode_reglement = fields.Selection(related='partner_id.part_mode_de_reglement', string="Mode de Règlement")
    so_commercial = fields.Selection(related='partner_id.part_commercial', string="Commercial")
    so_code_tiers = fields.Integer(related='partner_id.part_code_tiers', string="Code Tiers")
    so_commande_client = fields.Char(string="N° Commande Client")

    so_delegation = fields.Boolean(string="Délégation?")
    so_commmentaire_delegation = fields.Char(string="Commentaire Délégation")
    so_date_de_reception = fields.Date(string="Date de réception")
    so_date_de_modification = fields.Date(string="Date de modification")
    so_date_de_commande = fields.Date(string="Date de la commande")
    so_date_bpe = fields.Date(string="BPE du : ")
    so_date_de_reception_devis = fields.Date(string="Demande reçue le :", required=True, default=fields.Date.today())
    so_date_du_devis = fields.Date(string="Devis fait le : ")
    so_date_de_modification_devis = fields.Date(string="Devis modifié le : ")
    so_date_devis_valide = fields.Date(string="Devis validé le : ")

    so_date_ARC = fields.Date(string="ARC du : ")
    so_date_bon_pour_fab = fields.Date(string="Bon pour Fab. le : ")
    so_date_de_fin_de_production_reel = fields.Date(string="Fin de production du : ")
    so_date_de_livraison = fields.Date(string="Livraison prévue le : ", compute='_compute_so_date_de_livraison', store=True)
    so_date_de_livraison_prevu = fields.Date(string="Livraison prévue le : ")
    so_statut_avancement_production = fields.Char(string="Statut Avancement Production")
    so_delai_confirme_en_semaine = fields.Integer(string="Délai confirmé (en semaines)")

    # Onglet Analyse Financière (Devis)
    so_achat_matiere_devis = fields.Monetary(string="Achat Matière (Devis)")
    so_achat_vitrage_devis = fields.Monetary(string="Achat Vitrage (Devis)")
    so_cout_mod_devis = fields.Monetary(string="Coût MOD (Devis)")
    so_mtt_facturer_devis = fields.Monetary(string="Montant à Facturer H.T. (Devis)")
    so_marge_brute_devis = fields.Monetary(string="Marge Brute en € (Devis)", compute='_compute_so_marge_brute_devis', store=True)
    so_prc_marge_brute_devis = fields.Float(string="Marge Brute en % (Devis)", compute='_compute_so_prc_marge_brute_devis', store=True)
    so_mcv_devis = fields.Monetary(string="M.C.V. en € (Devis)", compute='_compute_so_mcv_devis', store=True)
    so_prc_mcv_devis = fields.Float(string="M.C.V. en % (Devis)", compute='_compute_so_prc_mcv_devis', store=True)

    # Champs formatés pour affichage arrondi avec "%" ajouté
    so_prc_marge_brute_devis_display = fields.Char(
        compute='_compute_so_prc_marge_brute_devis_display',
        string="Marge Brute en % (Devis)"
    )
    so_prc_mcv_devis_display = fields.Char(
        compute='_compute_so_prc_mcv_devis_display',
        string="M.C.V. en % (Devis)"
    )

    @api.depends('so_prc_marge_brute_devis')
    def _compute_so_prc_marge_brute_devis_display(self):
        for record in self:
            marge_brute_arrondie = "{:.1f}".format(float_round(record.so_prc_marge_brute_devis, precision_digits=1))
            record.so_prc_marge_brute_devis_display = f"{marge_brute_arrondie} %"

    @api.depends('so_prc_mcv_devis')
    def _compute_so_prc_mcv_devis_display(self):
        for record in self:
            mcv_arrondi = "{:.1f}".format(float_round(record.so_prc_mcv_devis, precision_digits=1))
            record.so_prc_mcv_devis_display = f"{mcv_arrondi} %"

    # Onglet Analyse Financière (B.E.)
    so_achat_matiere_be = fields.Monetary(string="Achat Matière (B.E.)")
    so_achat_vitrage_be = fields.Monetary(string="Achat Vitrage (B.E.)")
    so_cout_mod_be = fields.Monetary(string="Coût MOD (B.E.)")
    so_mtt_facturer_be = fields.Monetary(string="Montant à Facturer H.T. (B.E.)")
    so_marge_brute_be = fields.Monetary(string="Marge Brute en € (B.E.)", compute='_compute_so_marge_brute_be', store=True)
    so_prc_marge_brute_be = fields.Float(string="Marge Brute en % (B.E.)", compute='_compute_so_prc_marge_brute_be', store=True)
    so_mcv_be = fields.Monetary(string="M.C.V. en € (B.E.)", compute='_compute_so_mcv_be', store=True)
    so_prc_mcv_be = fields.Float(string="M.C.V. en % (B.E.)", compute='_compute_so_prc_mcv_be', store=True)

    so_prc_marge_brute_be_display = fields.Char(
        compute='_compute_so_prc_marge_brute_be_display',
        string="Marge Brute en % (B.E.)"
    )
    so_prc_mcv_be_display = fields.Char(
        compute='_compute_so_prc_mcv_be_display',
        string="M.C.V. en % (B.E.)"
    )

    @api.depends('so_prc_marge_brute_be')
    def _compute_so_prc_marge_brute_be_display(self):
        for record in self:
            marge_brute_arrondie_be = "{:.1f}".format(float_round(record.so_prc_marge_brute_be, precision_digits=1))
            record.so_prc_marge_brute_be_display = f"{marge_brute_arrondie_be} %"

    @api.depends('so_prc_mcv_be')
    def _compute_so_prc_mcv_be_display(self):
        for record in self:
            mcv_arrondi_be = "{:.1f}".format(float_round(record.so_prc_mcv_be, precision_digits=1))
            record.so_prc_mcv_be_display = f"{mcv_arrondi_be} %"

    # Onglet Analyse Financière (Réel)
    so_achat_matiere_reel = fields.Monetary(string="Achat Matière (Réel)")
    so_achat_vitrage_reel = fields.Monetary(string="Achat Vitrage (Réel)")
    so_cout_mod_reel = fields.Monetary(string="Coût MOD (Réel)")
    so_mtt_facturer_reel = fields.Monetary(string="Montant à Facturer H.T. (Réel)")
    so_marge_brute_reel = fields.Monetary(string="Marge Brute en € (Réel)", compute='_compute_so_marge_brute_reel', store=True)
    so_prc_marge_brute_reel = fields.Float(string="Marge Brute en % (Réel)", compute='_compute_so_prc_marge_brute_reel', store=True)
    so_mcv_reel = fields.Monetary(string="M.C.V. en € (Réel)", compute='_compute_so_mcv_reel', store=True)
    so_prc_mcv_reel = fields.Float(string="M.C.V. en % (Réel)", compute='_compute_so_prc_mcv_reel', store=True)

    so_prc_marge_brute_reel_display = fields.Char(
        compute='_compute_so_prc_marge_brute_reel_display',
        string="Marge Brute en % (Réel)"
    )
    so_prc_mcv_reel_display = fields.Char(
        compute='_compute_so_prc_mcv_reel_display',
        string="M.C.V. en % (Réel)"
    )

    @api.depends('so_prc_marge_brute_reel')
    def _compute_so_prc_marge_brute_reel_display(self):
        for record in self:
            marge_brute_arrondie_reel = "{:.1f}".format(float_round(record.so_prc_marge_brute_reel, precision_digits=1))
            record.so_prc_marge_brute_reel_display = f"{marge_brute_arrondie_reel} %"

    @api.depends('so_prc_mcv_reel')
    def _compute_so_prc_mcv_reel_display(self):
        for record in self:
            mcv_arrondi_reel = "{:.1f}".format(float_round(record.so_prc_mcv_reel, precision_digits=1))
            record.so_prc_mcv_reel_display = f"{mcv_arrondi_reel} %"

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['x_studio_rfrence_affaire'] = self.x_studio_ref_affaire
        invoice_vals['x_studio_imputation_2'] = self.x_studio_imputation
        invoice_vals['x_studio_delegation_fac'] = self.x_studio_delegation
        invoice_vals['x_studio_com_delegation_fac'] = self.x_studio_com_delegation
        invoice_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        invoice_vals['x_studio_date_de_la_commande'] = self.x_studio_date_de_la_commande
        return invoice_vals

    @api.depends('so_date_bpe', 'so_delai_confirme_en_semaine')
    def _compute_so_date_de_livraison(self):
        for order in self:
            if order.so_date_bpe and order.so_delai_confirme_en_semaine:
                order.so_date_de_livraison = order.so_date_bpe + timedelta(weeks=order.so_delai_confirme_en_semaine)
                order.so_date_de_livraison_prevu = order.so_date_bpe + timedelta(weeks=order.so_delai_confirme_en_semaine)
                order.commitment_date = order.so_date_de_livraison
            else:
                order.so_date_de_livraison = False
                order.commitment_date = False

    @api.depends('so_mtt_facturer_devis', 'so_achat_vitrage_devis', 'so_achat_matiere_devis')
    def _compute_so_marge_brute_devis(self):
        for order in self:
            order.so_marge_brute_devis = order.so_mtt_facturer_devis - order.so_achat_vitrage_devis - order.so_achat_matiere_devis

    @api.depends('so_marge_brute_devis', 'so_cout_mod_devis')
    def _compute_so_mcv_devis(self):
        for order in self:
            order.so_mcv_devis = order.so_marge_brute_devis - order.so_cout_mod_devis

    @api.depends('so_mtt_facturer_be', 'so_achat_vitrage_be', 'so_achat_matiere_be')
    def _compute_so_marge_brute_be(self):
        for order in self:
            order.so_marge_brute_be = order.so_mtt_facturer_be - order.so_achat_vitrage_be - order.so_achat_matiere_be

    @api.depends('so_marge_brute_be', 'so_cout_mod_be')
    def _compute_so_mcv_be(self):
        for order in self:
            order.so_mcv_be = order.so_marge_brute_be - order.so_cout_mod_be

    @api.depends('so_mtt_facturer_reel', 'so_achat_vitrage_reel', 'so_achat_matiere_reel')
    def _compute_so_marge_brute_reel(self):
        for order in self:
            order.so_marge_brute_reel = order.so_mtt_facturer_reel - order.so_achat_vitrage_reel - order.so_achat_matiere_reel

    @api.depends('so_marge_brute_reel', 'so_cout_mod_reel')
    def _compute_so_mcv_reel(self):
        for order in self:
            order.so_mcv_reel = order.so_marge_brute_reel - order.so_cout_mod_reel

    @api.depends('so_marge_brute_devis', 'so_mtt_facturer_devis')
    def _compute_so_prc_marge_brute_devis(self):
        for order in self:
            if order.so_mtt_facturer_devis:
                order.so_prc_marge_brute_devis = (order.so_marge_brute_devis / order.so_mtt_facturer_devis) * 100
            else:
                order.so_prc_marge_brute_devis = 0.0

    @api.depends('so_mcv_devis', 'so_mtt_facturer_devis')
    def _compute_so_prc_mcv_devis(self):
        for order in self:
            if order.so_mtt_facturer_devis:
                order.so_prc_mcv_devis = (order.so_mcv_devis / order.so_mtt_facturer_devis) * 100
            else:
                order.so_prc_mcv_devis = 0.0

    @api.depends('so_marge_brute_be', 'so_mtt_facturer_be')
    def _compute_so_prc_marge_brute_be(self):
        for order in self:
            if order.so_mtt_facturer_be:
                order.so_prc_marge_brute_be = (order.so_marge_brute_be / order.so_mtt_facturer_be) * 100
            else:
                order.so_prc_marge_brute_be = 0.0

    @api.depends('so_mcv_be', 'so_mtt_facturer_be')
    def _compute_so_prc_mcv_be(self):
        for order in self:
            if order.so_mtt_facturer_be:
                order.so_prc_mcv_be = (order.so_mcv_be / order.so_mtt_facturer_be) * 100
            else:
                order.so_prc_mcv_be = 0.0

    @api.depends('so_marge_brute_reel', 'so_mtt_facturer_reel')
    def _compute_so_prc_marge_brute_reel(self):
        for order in self:
            if order.so_mtt_facturer_reel:
                order.so_prc_marge_brute_reel = (order.so_marge_brute_reel / order.so_mtt_facturer_reel) * 100
            else:
                order.so_prc_marge_brute_reel = 0.0

    @api.depends('so_mcv_reel', 'so_mtt_facturer_reel')
    def _compute_so_prc_mcv_reel(self):
        for order in self:
            if order.so_mtt_facturer_reel:
                order.so_prc_mcv_reel = (order.so_mcv_reel / order.so_mtt_facturer_reel) * 100
            else:
                order.so_prc_mcv_reel = 0.0
