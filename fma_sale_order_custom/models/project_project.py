# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models

# Un code affaire commence par A, deux chiffres d'annee, deux de mois, puis un
# compteur : « A24-04-01435 ». C'est le numero du premier devis du chantier —
# c'est ainsi que les affaires sont nommees chez FMA, et on le conserve. Ce
# qui suit dans le nom du projet (« /1 », un separateur, un libelle) n'en fait
# pas partie.
MOTIF_CODE = re.compile(r"^A\d{2}-\d{2}-\d+")


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

    @api.model_create_multi
    def create(self, vals_list):
        """Deduit le code affaire du nom quand il n'est pas fourni.

        Le nom d'un chantier commence par le numero de son premier devis :
        « A24-04-01435 - COULISSANTS COPRO ». Plutot que d'exiger une saisie
        de plus, on relit ce numero dans le nom. Un projet cree depuis un
        autre ecran que le devis recoit donc son code sans que personne y
        pense.
        """
        for vals in vals_list:
            if vals.get("x_code_affaire"):
                continue
            nom = vals.get("name")
            # Le nom peut arriver en dictionnaire de traductions.
            if isinstance(nom, dict):
                nom = nom.get("fr_FR") or nom.get("en_US")
            trouve = MOTIF_CODE.match((nom or "").strip())
            if trouve:
                vals["x_code_affaire"] = trouve.group(0)

        projets = super().create(vals_list)

        # Chantier cree depuis un devis : on le rattache tout de suite, sinon
        # il faudrait revenir sur le devis pour le selectionner a la main.
        devis_id = self.env.context.get("fma_devis_a_rattacher")
        if devis_id and len(projets) == 1:
            devis = self.env["sale.order"].browse(devis_id).exists()
            if devis and not devis.project_id:
                # x_studio_bureau_dtude se recalcule depuis project_id.user_id.
                # Sur un devis qui n'en a pas encore, laisser le calcul poser
                # le responsable du chantier est exactement ce qu'on veut ;
                # sur un devis deja renseigne, ce serait un ecrasement.
                avant = devis.x_studio_bureau_dtude
                devis.project_id = projets.id
                if avant and devis.x_studio_bureau_dtude != avant:
                    devis.x_studio_bureau_dtude = avant

        return projets

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
