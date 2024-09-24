import logging
from odoo import models, fields, api
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_studio_ref_affaire = fields.Char(string="Affaire")
    x_studio_imputation = fields.Char(string="Numéro Commande Client")
    x_studio_delegation = fields.Boolean(string="Délégation")
    x_studio_com_delegation = fields.Char(string="Commentaire Délégation:")
    x_studio_mode_de_rglement_1 = fields.Selection(
        [
            ('ESPECES','ESPECES'),
            ('CHEQUE BANCAIRE','CHEQUE BANCAIRE'),
            ('VIREMENT BANCAIRE','VIREMENT BANCAIRE'),
            ('L.C.R. DIRECTE','L.C.R. DIRECTE'),
            ('L.C.R. A L ACCEPTATION','L.C.R. A L ACCEPTATION'),
            ('PRELEVEMENT','PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE','L.C.R. MAGNETIQUE'),
            ('BOR','BOR'),
            ('CARTE BANCAIRE','CARTE BANCAIRE'),
            ('CREDIT DOCUMENTAIRE','CREDIT DOCUMENTAIRE'),
        ],
        string="Mode de Règlement",

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
    so_date_de_reception = fields.Date(string="Date de réception:")
    so_date_de_modification = fields.Date(string="Date de modification :")
    so_date_de_commande = fields.Date(string="Date de la commande")
    so_date_bpe = fields.Date(string="BPE du :")
    so_date_de_reception_devis = fields.Date(string="Demande reçue le :")
    so_date_du_devis = fields.Date(string="Devis fait le :")
    so_date_de_modification_devis = fields.Date(string="Devis modifié le :")
    so_date_devis_valide = fields.Date(string="Devis validé le :")

    so_date_ARC = fields.Date(string="ARC du :")
    so_date_bon_pour_fab = fields.Date(string="Bon pour Fab. le :")
    so_date_de_fin_de_production_reel = fields.Date(string="Fin de production le :")
    so_date_de_livraison_prevu = fields.Date(string="Date de livraison prévue le :", compute='_compute_so_date_de_livraison_prevu', store=True)
    so_statut_avancement_production = fields.Char(string="Statut Avancement Production")
    so_gamme = fields.Char(string="GAMME")
    so_delai_confirme_en_semaine = fields.Integer(string="Délai confirmé (en semaines)")

    #Onglet Analyse Financière
    so_achat_matiere_devis = fields.Monetary(string="Achat Matière (Devis)")
    so_achat_vitrage_devis = fields.Monetary(string="Achat Vitrage (Devis)")
    so_cout_mod_devis = fields.Monetary(string="Coût MOD (Devis)")
    so_mtt_facturer_devis = fields.Monetary(string="Montant à Facturer H.T. (Devis)")
    so_marge_brute_devis = fields.Monetary(string="Marge Brute en € (Devis)",compute='_compute_so_marge_brute_devis',store=True)
    so_prc_marge_brute_devis = fields.Float(string="Marge Brute en % (Devis)",compute='_compute_so_prc_marge_brute_devis',store=True)
    so_mcv_devis = fields.Monetary(string="M.C.V. en € (Devis)",compute='_compute_so_mcv_devis',store=True)
    so_prc_mcv_devis = fields.Float(string="M.C.V. en (Devis)",compute='_compute_so_prc_mcv_devis',store=True)

    so_achat_matiere_be = fields.Monetary(string="Achat Matière (B.E.)")
    so_achat_vitrage_be = fields.Monetary(string="Achat Vitrage (B.E.)")
    so_cout_mod_be = fields.Monetary(string="Coût MOD (B.E.)")
    so_mtt_facturer_be = fields.Monetary(string="Montant à Facturer H.T. (B.E.)")
    so_marge_brute_be = fields.Monetary(string="Marge Brute en € (B.E.)",compute='_compute_so_marge_brute_be',store=True)
    so_prc_marge_brute_be = fields.Float(string="Marge Brute en % (B.E.)",compute='_compute_so_prc_marge_brute_be',store=True)
    so_mcv_be = fields.Monetary(string="M.C.V. en € (B.E.)",compute='_compute_so_mcv_be',store=True)
    so_prc_mcv_be = fields.Float(string="M.C.V. en (B.E.)",compute='_compute_so_prc_mcv_be',store=True)

    so_achat_matiere_reel = fields.Monetary(string="Achat Matière (Réel)")
    so_achat_vitrage_reel = fields.Monetary(string="Achat Vitrage (Réel)")
    so_cout_mod_reel = fields.Monetary(string="Coût MOD (Réel)")
    so_mtt_facturer_reel = fields.Monetary(string="Montant à Facturer H.T. (Réel)")
    so_marge_brute_reel = fields.Monetary(string="Marge Brute en € (Réel)",compute='_compute_so_marge_brute_reel',store=True)
    so_prc_marge_brute_reel = fields.Float(string="Marge Brute en % (Réel)",compute='_compute_so_prc_marge_brute_reel',store=True)
    so_mcv_reel = fields.Monetary(string="M.C.V. en € (Réel)",compute='_compute_so_mcv_reel',store=True)
    so_prc_mcv_reel = fields.Float(string="M.C.V. en (Réel)",compute='_compute_so_prc_mcv_reel',store=True)
    
    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['x_studio_rfrence_affaire'] = self.x_studio_ref_affaire
        invoice_vals['x_studio_imputation_2'] = self.x_studio_imputation
        invoice_vals['x_studio_delegation_fac'] = self.x_studio_delegation
        invoice_vals['x_studio_com_delegation_fac'] = self.x_studio_com_delegation
        invoice_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        invoice_vals['x_studio_date_de_la_commande'] = self.x_studio_date_de_la_commande
        return invoice_vals

    