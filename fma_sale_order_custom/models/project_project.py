# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectProject(models.Model):
    """Le projet porte le chantier : son code, son chiffrage, son vendu.

    Jusqu'ici le montant chiffre d'une affaire etait porte par un devis a
    0 EUR cree pour l'occasion, faute d'objet ou le mettre. Ce devis fantome
    fausse le nombre de devis, le taux de transformation et l'encours, et son
    montant doit etre corrige a la main a chaque tranche vendue.

    On ne se sert pas du budget natif : il mesure un realise **comptable**
    face a une prevision, alors que le besoin porte sur le **vendu**,
    c'est-a-dire les commandes confirmees. Une commande confirmee non encore
    facturee ne produit aucune ecriture : le budget la verrait a zero.
    Le budget natif garde tout son sens pour le suivi des couts par chantier,
    via l'analytique — c'est un autre sujet.
    """

    _inherit = "project.project"

    # On declare l'inverse de sale.order.project_id plutot que de compter sur
    # un One2many natif : sale_project ne garantit pas son existence d'une
    # version a l'autre. Meme raison pour la devise, prise sur la societe.
    x_commande_ids = fields.One2many(
        "sale.order",
        "project_id",
        string="Commandes du chantier",
    )
    x_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Devise",
    )

    # Code affaire, sans suffixe de tranche. Historiquement ecrit dans le nom
    # du projet (« A24-04-01435/1 - COULISSANTS COPRO »), donc de facon
    # irreguliere : certains projets portent un suffixe, d'autres non, et il
    # ne designe pas la tranche — un projet en « /1 » peut porter six
    # commandes. On l'isole ici pour fabriquer les references de tranche sans
    # dependre de la facon dont le nom a ete saisi.
    x_code_affaire = fields.Char(
        string="Code affaire",
        index="btree_not_null",
        help="Code de l'affaire, sans suffixe de tranche. Alimente depuis le "
             "nom du projet a la reprise, saisissable ensuite.",
    )

    x_montant_chiffrage = fields.Monetary(
        string="Montant chiffré",
        currency_field="x_currency_id",
        help="Valeur totale estimee du chantier, saisie une seule fois.",
    )

    x_montant_vendu = fields.Monetary(
        string="Montant vendu",
        currency_field="x_currency_id",
        compute="_compute_montants_chantier",
        store=True,
        help="Somme hors taxes des commandes confirmees du chantier.",
    )

    x_reste_a_vendre = fields.Monetary(
        string="Reste à vendre",
        currency_field="x_currency_id",
        compute="_compute_montants_chantier",
        store=True,
    )

    x_tranche_count = fields.Integer(
        string="Nombre de tranches",
        compute="_compute_montants_chantier",
        store=True,
    )

    @api.depends(
        "x_commande_ids.state",
        "x_commande_ids.amount_untaxed",
        "x_montant_chiffrage",
    )
    def _compute_montants_chantier(self):
        for projet in self:
            commandes = projet.x_commande_ids
            vendues = commandes.filtered(lambda o: o.state in ("sale", "done"))
            projet.x_montant_vendu = sum(vendues.mapped("amount_untaxed"))
            projet.x_reste_a_vendre = (
                projet.x_montant_chiffrage - projet.x_montant_vendu
            )
            # Toutes les commandes comptent comme tranches, pas seulement les
            # confirmees : un devis en cours de negociation est une tranche, et
            # il doit deja porter son rang.
            projet.x_tranche_count = len(commandes)
