from datetime import timedelta
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    state = fields.Selection(
        selection=[
            ("draft", "Devis"),
            ("sent", "Devis envoyé"),
            ("validated", "Validé"),
            ("sale", "Bon de commande"),
            ("done", "Verrouillé"),
            ("cancel", "Annulé"),
        ],
        ondelete={"validated": "set default"},
        default="draft",
        string="Statut",
        tracking=True,
    )

    date_bpe = fields.Date(string="Date BPE")

    # Le « Vendeur » natif d'Odoo est, chez FMA, le deviseur : l'utilisateur
    # qui etablit le devis. Le commercial, lui, est un employe sans licence,
    # porte par commercial_id. On ne change que le libelle : le champ reste le
    # user_id standard, avec ses filtres, ses droits et ses rapports.
    user_id = fields.Many2one(string="Deviseur")

    # --- Champs migrés depuis Odoo Studio ---
    # Noms techniques conservés à l'identique, aucune migration de données.
    # Champs volontairement exclus de ce portage (voir STUDIO_AUDIT.md) :
    # - x_studio_bureau_etudes, x_studio_com, x_studio_deviseur_1,
    #   x_studio_nom_com_2 : sélections dont les valeurs n'ont pas pu être
    #   vérifiées en base au moment du portage. (x_studio_avancement,
    #   x_studio_commercial_si_prospect et x_studio_motif_annul l'ont été
    #   depuis, cf. plus bas.)
    # - x_studio_related_field_* (6 champs) : champs liés Studio dont la
    #   cible ("related=") n'a pas pu être vérifiée en base.
    # - x_studio_calcul_raf_ht : non stocké côté Studio (probablement un
    #   champ lié), pas porté tel quel pour éviter de figer sa valeur.
    # - x_studio_commercial, x_studio_commercial_mtn_1,
    #   x_studio_montant_facturer_en_ht,
    #   x_studio_mtt_facturer_en_ht, x_studio_mtt_facturer_ht_ : marqués
    #   "OLD"/déprécié par le métier lui-même côté Studio.
    # --- Champs Studio portes le 2026-08-09 ------------------------------
    # Definitions relevees directement en base (ir_model_fields et
    # ir_model_fields_selection) : les valeurs sont reprises a l'identique,
    # y compris quand la valeur stockee et son libelle divergent. Toute
    # retouche ici rendrait invisibles les devis portant l'ancienne valeur.
    #
    # Ce portage est necessaire pour que les vues du depot puissent placer
    # ces champs : un champ « manual » cree par Studio n'existe pas encore
    # dans le registre au moment ou les vues des modules sont chargees.
    x_studio_avancement = fields.Selection(
        selection=[("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5")],
        string="Avancement",
    )
    x_studio_commercial_si_prospect = fields.Selection(
        selection=[
            ("Adrien LAISNE", "Adrien LAISNE"),
            ("Alexandre BLOT", "Alexandre BLOT"),
            ("Alexandre POILANE", "Alexandre POILANE"),
            ("Arnaud Kherfouche", "Arnaud Kherfouche"),
            ("Baptiste BOUJU", "Baptiste BOUJU"),
            ("Carlos DA TORRE", "Carlos DA TORRE"),
            ("Cedric KERGOSIEN", "Cédric KERGOSIEN"),
            ("Cédric SEGUIN", "Cédric SEGUIN"),
            ("Christian GUIHARD", "Christian GUIHARD"),
            ("Christophe CARPENTIER", "Christophe CARPENTIER"),
            ("Cyril JACQUEMET", "Cyril JACQUEMET"),
            ("David CHARPENTIER", "David CHARPENTIER"),
            ("David MAILLOT", "David MAILLOT"),
            ("David PROVOST", "David PROVOST"),
            ("Frédéric RAVIER", "Frédéric RAVIER"),
            ("Hubert BOURDARIAS", "Hubert BOURDARIAS"),
            ("Jean-Jacques LOPES", "Jean-Jacques LOPES"),
            ("Jérôme DECAIX", "Jérôme DECAIX"),
            ("Karine HERVOUET", "Karine HERVOUET"),
            ("Laurent MILANO", "Laurent MILANO"),
            ("Lucas DESBRINI", "Lucas DESBRINI"),
            ("Mathieu LACAM", "Mathieu LACAM"),
            ("Mathieu LOISEAUX", "Mathieu LOISEAUX"),
            ("Mickael DUH", "Mickael DUH"),
            ("Nicolas HUTIN", "Nicolas HUTIN"),
            ("Paul DOS SANTOS", "Paul DOS SANTOS"),
            ("Pierre MONTIN", "Pierre MONTIN"),
            ("Pierre PINEAU", "Pierre PINEAU"),
            ("Richard ROTH", "Richard ROTH"),
            ("Rosa ALVES", "Rosa ALVES"),
            ("Sami ABID", "Sami ABID"),
            ("Sébastien LAVENU", "Sébastien LAVENU"),
            ("Stephane MOUSSEL", "Stephane MOUSSEL"),
            ("Vincent PERROT", "Vincent PERROT"),
            ("NON DEFINI", "NON DEFINI"),
        ],
        string="Commercial SI PROSPECT",
    )
    x_studio_motif_annul = fields.Selection(
        selection=[
            # Valeurs telles quelles en base. Deux d'entre elles ont un
            # libelle qui ne correspond pas a la valeur stockee ; c'est le
            # cas en production, on ne le corrige pas ici.
            ("KKJN?", "Dossier transmis - Pas de retour"),
            ("Retard Travaux", "Retard Travaux"),
            ("Projet ajourné", "En bonne voie"),
            ("Changement Typologie", "Changement Typologie"),
            ("Perdu par le client", "Perdu par le client"),
            ("Perdu face à un concurrent", "Perdu face à un concurrent"),
        ],
        string="Statut Affaire",
    )
    # Marque « OLD » par le metier. Porte uniquement pour que les vues du
    # depot puissent le retirer de l'ecran ; a supprimer le jour ou les
    # donnees auront ete reprises.
    x_studio_commercial_client_mtn = fields.Many2one(
        "hr.employee",
        string="OLD",
    )

    x_studio_ach_matire = fields.Monetary(string="Achat Matière (BE)", currency_field="currency_id")
    x_studio_ach_vitrage = fields.Monetary(string="Achat Vitrage (BE)", currency_field="currency_id")
    x_studio_achat_mat = fields.Monetary(string="Achat Matière (Réel)", currency_field="currency_id")
    x_studio_achat_matire = fields.Monetary(string="Achat Matière (Devis)", currency_field="currency_id")
    x_studio_achat_vit = fields.Monetary(string="Achat Vitrage (Réel)", currency_field="currency_id")
    x_studio_achat_vitrage = fields.Monetary(string="Achat Vitrage (Devis)", currency_field="currency_id")
    x_studio_avancement_crm = fields.Many2one("crm.stage", string="Avancement CRM")
    # Le bureau d'etude est le responsable du projet. Mesure avant bascule :
    # 6 348 devis renseignes, 6 348 identiques au responsable du projet,
    # 0 divergent — et tout devis ayant un bureau d'etude a un projet. Le
    # recalcul est donc sans perte.
    #
    # compute + store + readonly=False, comme commercial_id : la valeur est
    # figee sur le devis. Changer le responsable d'un projet ne doit pas
    # reecrire l'historique, notamment les destinataires des mails de retard
    # deja envoyes.
    #
    # Domaine : le departement porte deux libelles selon la langue
    # (« BEC-Ventes » en francais, « Sales » en anglais). On accepte les deux
    # plutot que de filtrer sur un identifiant, qui differe d'un
    # environnement a l'autre.
    x_studio_bureau_dtude = fields.Many2one(
        "res.users",
        string="Bureau d'étude",
        compute="_compute_x_studio_bureau_dtude",
        store=True,
        readonly=False,
        domain="[('employee_ids.department_id.name', 'in', ['BEC-Ventes', 'Sales'])]",
    )

    # Depuis project_id et non x_studio_projet : le projet du devis est
    # desormais porte par le champ natif. Voir la migration 19.0.1.0.26.
    @api.depends("project_id")
    def _compute_x_studio_bureau_dtude(self):
        for order in self:
            order.x_studio_bureau_dtude = order.project_id.user_id

    # Rang de la commande au sein de son projet : la « tranche ». Il n'y a pas
    # d'objet tranche — une tranche EST une commande, et un projet a une ou
    # plusieurs commandes. Le numero est donc deduit, jamais saisi : il ne
    # peut etre ni oublie, ni faux, ni duplique.
    #
    # Le classement se fait par identifiant, pas par date : les identifiants
    # sont monotones, donc une nouvelle tranche prend toujours le rang
    # suivant et ne renumerote jamais ses aînées. Classer par date_order
    # obligerait a recalculer toute la fratrie des qu'on antidate un devis.
    tranche_no = fields.Integer(
        string="Tranche",
        compute="_compute_tranche_no",
        store=True,
        help="Rang de cette commande parmi celles de son projet.",
    )

    @api.depends("project_id")
    def _compute_tranche_no(self):
        # Une seule recherche pour tout le lot, et non un comptage par
        # enregistrement : le calcul se declenche sur l'ensemble des devis a
        # la creation de la colonne.
        rangs = {}
        projets = self.mapped("project_id")
        if projets:
            compteur = {}
            freres = self.env["sale.order"].search(
                [("project_id", "in", projets.ids)], order="project_id, id"
            )
            for frere in freres:
                rang = compteur.get(frere.project_id.id, 0) + 1
                compteur[frere.project_id.id] = rang
                rangs[frere.id] = rang
        for order in self:
            order.tranche_no = rangs.get(order.id, 0) if order.project_id else 0

    def action_creer_chantier(self):
        """Ouvre la fiche chantier, deja numerotee depuis ce devis.

        Le geste reste celui d'aujourd'hui : on part du devis, on tape le
        libelle de l'affaire, et le chantier s'appelle « <numero du devis> -
        <libelle> ». Seule la recopie du numero disparait.

        On ouvre le formulaire au lieu de creer directement : le libelle
        n'est pas devinable, et un projet cree puis renomme laisserait des
        traces dans le suivi. L'utilisateur voit ce qu'il valide.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.project",
            "view_mode": "form",
            "target": "new",
            "name": "Nouveau chantier",
            "context": {
                "default_name": "%s - " % self.name,
                "default_x_code_affaire": self.name,
                "default_partner_id": self.partner_id.id,
                "default_company_id": self.company_id.id,
                # Rattache le devis des la sauvegarde du chantier : sans ca il
                # faudrait revenir sur le devis pour le selectionner.
                "fma_devis_a_rattacher": self.id,
            },
        }

    # La reference que lisent les metiers : « A24-04-01435/2 ». Elle reproduit
    # a l'identique le format ecrit a la main jusqu'ici dans le nom du projet,
    # mais elle est fabriquee — donc jamais oubliee, jamais fausse, jamais en
    # double, et sans toucher a la moindre sequence.
    #
    # Pas de suffixe quand le chantier n'a qu'une commande : « /1 » tout seul
    # n'apprend rien, et c'est deja l'usage constate dans les donnees. Le
    # suffixe apparait de lui-meme sur les deux commandes le jour ou une
    # deuxieme tranche est creee, puisque le calcul depend du compte de
    # tranches porte par le projet.
    x_ref_tranche = fields.Char(
        string="Référence affaire",
        compute="_compute_x_ref_tranche",
        store=True,
        index="btree_not_null",
    )

    @api.depends(
        "project_id.x_code_affaire",
        "project_id.x_tranche_count",
        "tranche_no",
    )
    def _compute_x_ref_tranche(self):
        for order in self:
            code = order.project_id.x_code_affaire
            if not code:
                order.x_ref_tranche = False
            elif order.project_id.x_tranche_count > 1 and order.tranche_no:
                order.x_ref_tranche = "%s/%s" % (code, order.tranche_no)
            else:
                order.x_ref_tranche = code
    x_studio_bureau_etude = fields.Char(string="Bureau Etudes")
    x_studio_char_field_4c7_1jfiimqpn = fields.Char(string="X Studio Char Field 4C7 1Jfiimqpn")
    x_studio_commande_client = fields.Boolean(string="Commande Client?")
    x_studio_commentaire_supplmentaire = fields.Char(string="Commentaire Supplémentaire")
    # Nom du commercial, HISTORIQUE. 13 494 devis le portent, herite de
    # Studio. On le laisse volontairement fige : les commerciaux des devis
    # deja etablis ne doivent pas etre reecrits.
    #
    # Il n'est donc PAS calcule depuis commercial_id : en faire un reflet
    # aurait vide ou reecrit ces 13 494 valeurs des qu'on aurait alimente le
    # nouveau champ. Les consommateurs (export PowerBI, mails de retard)
    # lisent commercial_id en priorite et retombent sur celui-ci.
    x_studio_commercial_1 = fields.Char(string="Commercial (historique)", readonly=True)
    x_studio_date_bpe = fields.Date(string="Date BPE")
    x_studio_date_de_modification = fields.Datetime(string="Date de Modification")
    x_studio_date_de_rception = fields.Date(string="Date de Réception")
    x_studio_date_de_relance_1 = fields.Datetime(string="Date de relance 1")
    x_studio_date_de_relance_2 = fields.Datetime(string="Date de relance 2")
    x_studio_date_field_IuGus = fields.Date(string="New Date")
    x_studio_datetime_field_22b_1jcrk40tn = fields.Datetime(string="Nouveau Datetime")
    # Ancien champ texte, 592 enregistrements, remplace par user_id.
    # Libelle distinct pour ne pas le confondre avec le vrai deviseur.
    x_studio_deviseur = fields.Char(string="Deviseur (ancien)")
    # Many2many auto-référencé sur sale.order lui-même : aucune table de
    # relation ni donnée existante côté Studio (champ probablement
    # abandonné/mal configuré, x_studio_etiquette_1 ci-dessous porte le
    # même libellé "Etiquette" vers crm.tag). Relation/colonnes explicites
    # obligatoires ici car Odoo ne peut pas déduire un nom de table
    # canonique quand source et destination sont le même modèle.
    x_studio_etiquette = fields.Many2many(
        "sale.order",
        relation="x_studio_etiquette_sale_order_rel",
        column1="sale_order_id1",
        column2="sale_order_id2",
        string="Etiquette",
    )
    # Relation explicite requise : x_studio_many2many_field_7ae_1jshd7qf2
    # ci-dessous pointe aussi sale.order -> crm.tag sans nom de table
    # explicite, ce qui ferait collisionner les deux sur la même table
    # canonique auto-déduite par Odoo.
    x_studio_etiquette_1 = fields.Many2many(
        "crm.tag",
        relation="x_studio_etiquette_1_crm_tag_rel",
        string="Etiquette",
    )
    x_studio_gamme = fields.Many2one("x_gamme_mtn", string="Gamme")
    x_studio_m_brute_ = fields.Float(string=" Marge Brute en % (BE)")
    x_studio_m_brute_en_ = fields.Monetary(string=" Marge Brute en € (BE)", currency_field="currency_id")
    x_studio_m_sur_cots_variables_ = fields.Float(string="M.C.V. en % (BE)")
    x_studio_m_sur_cots_variables_en_ = fields.Monetary(string="M.C.V. en € (BE)", currency_field="currency_id")
    x_studio_many2many_field_2ee_1jsee0cpo = fields.Many2many("project.tags", string="Nouveau Many2Many")
    x_studio_many2many_field_495_1jsedj4nk = fields.Many2many("documents.tag", string="Nouveau Many2Many")
    x_studio_many2many_field_7ae_1jshd7qf2 = fields.Many2many(
        "crm.tag",
        relation="x_studio_m2m_7ae_1jshd7qf2_crm_tag_rel",
        string="Nouveau Étiquettes",
    )
    x_studio_many2many_field_95p_1ilmrb25m = fields.Many2many("x_affaire", string="Nouveau Many2Many")
    x_studio_marge_b_ = fields.Float(string=" Marge Brute en % (Réel)")
    x_studio_marge_b_en_ = fields.Monetary(string=" Marge Brute en € (Réel)", currency_field="currency_id")
    x_studio_marge_brute_ = fields.Float(string=" Marge Brute en % (Devis)")
    x_studio_marge_brute_en_ = fields.Monetary(string=" Marge Brute en € (Devis)", currency_field="currency_id")
    x_studio_marge_sur_cots_variables_ = fields.Float(string="M.C.V. en % (Devis)")
    x_studio_marge_sur_cots_variables_en_ = fields.Monetary(string="M.C.V. en € (Devis)", currency_field="currency_id")
    x_studio_mcv_ = fields.Float(string="M.C.V. en % (Réel)")
    x_studio_mcv_en_ = fields.Monetary(string="M.C.V. en € (Réel)", currency_field="currency_id")
    x_studio_mo = fields.Monetary(string="Coûts MOD (Réel)", currency_field="currency_id")
    x_studio_mo_vendue = fields.Monetary(string="Coût MOD (Devis)", currency_field="currency_id")
    x_studio_mo_vendue_1 = fields.Monetary(string="Coût MOD (BE)", currency_field="currency_id")
    x_studio_mode_de_rglement = fields.Char(string="Mode de Règlement")
    x_studio_montant_livr_factur = fields.Monetary(string="Montant livré facturé", currency_field="currency_id")
    x_studio_montant_livr_non_factur = fields.Monetary(string="Montant livré non facturé", currency_field="currency_id")
    x_studio_montant_non_livr_non_factur = fields.Monetary(string="Montant non livré non facturé", currency_field="currency_id")
    x_studio_montant_total_appro = fields.Monetary(string="Montant total appro", currency_field="currency_id")
    x_studio_nom_commercial = fields.Char(string="Sélection commercial", readonly=True)
    x_studio_numro_iziqo = fields.Char(string="Numéro Iziqo")
    x_studio_plannifier_en_prod = fields.Boolean(string="Planifié en Prod")
    # « Projet » tout court : c'est ce champ qui pilote l'affaire chez FMA.
    # Il est consomme par le tableau de bord MRP (jointures SQL directes sur
    # so.x_studio_projet), la rentabilite projet, la propagation vers les
    # achats et l'export PowerBI. Le nom technique ne bouge donc pas.
    x_studio_projet = fields.Many2one("project.project", string="Projet")
    x_studio_restant_a_facturer_ht_pivot = fields.Monetary(string="RAF HT", currency_field="currency_id", readonly=True)
    x_studio_so_cout_appro_affaire = fields.Monetary(string="Appro Affaire", currency_field="currency_id")
    x_studio_so_cout_appro_stock = fields.Monetary(string="Appro Stock", currency_field="currency_id")
    x_studio_srie = fields.Many2one("x_serie_mtn", string="Série")

    @api.onchange("so_date_de_livraison")
    def _onchange_so_date_de_livraison(self):
        # Synchronise la date de livraison prévue avec commitment_date
        if self.so_date_de_livraison:
            self.commitment_date = self.so_date_de_livraison

    # Init date validation devis
    def action_validation(self):
        for order in self:
            order.state = "validated"
            order.x_studio_date_de_la_commande = fields.Datetime.today()
            # so_date_devis_valide est un fields.Date : on y met une date, pas
            # un datetime. C'est ce champ qui alimente le taux de
            # transformation (x_nb_valide / x_montant_valide) du tableau de
            # bord : un devis validé compte comme commande.
            order.so_date_devis_valide = fields.Date.context_today(order)
            order.x_studio_avancement = "5"  # Mettre x_studio_avancement à '5'

    # Extra: Allows confirmation from the custom 'validated' state as well.
    def _confirmation_error_message(self):
        self.ensure_one()
        if self.state == "validated":
            if any(
                not line.display_type
                and not line.is_downpayment
                and not line.product_id
                for line in self.order_line
            ):
                return super()._confirmation_error_message()
            return False
        return super()._confirmation_error_message()

    # Init date BPE lors de la confirmation du devis
    # def action_confirm(self):
    # for order in self:
    # order.so_date_bon_pour_fab = fields.Datetime.today()  # Ajout de la deuxième initialisation de date
    # return super(SaleOrder, self).action_confirm()

    # Champ booléen pour désactiver le bouton de confirmation
    disable_confirm_button = fields.Boolean(
        string="Désactiver le bouton de confirmation",
        compute="_compute_disable_confirm_button",
    )

    @api.depends("partner_id", "so_commande_client")
    def _compute_disable_confirm_button(self):
        # Liste des partner_id pour lesquels le champ so_commande_client est obligatoire
        special_partner_ids = [
            49473,
            49472,
            49471,
            49756,
            50997,
            49918,
            49919,
            49920,
            50758,
            49750,
            49450,
        ]  # Remplacez par les ID réels des clients
        for order in self:
            # Désactiver le bouton si le partner_id est dans la liste et que le champ so_commande_client est vide
            if (
                order.partner_id.id in special_partner_ids
                and not order.so_commande_client
            ):
                order.disable_confirm_button = True
            else:
                order.disable_confirm_button = False

    # Init date fin de production réel
    def button_mark_done(self):
        for order in self:
            order.so_date_de_fin_de_production_reel = fields.Date.today()
        return super(SaleOrder, self).button_mark_done()

    # Init date de modification devis
    def action_quotation_send(self):
        for order in self:
            order.so_date_de_modification_devis = fields.Date.today()
        return super(SaleOrder, self).action_quotation_send()

    # Méthode create : mise à jour du mode de règlement et de la date de modification du devis
    @api.model_create_multi
    def create(self, vals_list):
        fma_tag = self.env["crm.tag"].search([("name", "=", "FMA")], limit=1)
        f2m_tag = self.env["crm.tag"].search([("name", "=", "F2M")], limit=1)

        for vals in vals_list:
            # Si la date du devis est définie, la copier dans la date de modification du devis
            if "so_date_du_devis" in vals:
                vals["so_date_de_modification_devis"] = vals["so_date_du_devis"]

            # Si un partner_id est présent, mettre à jour le mode de règlement
            if "partner_id" in vals:
                partner = self.env["res.partner"].browse(vals["partner_id"])
                vals[
                    "x_studio_mode_de_rglement_1"
                ] = partner.x_studio_mode_de_rglement_1

            # Mise à jour de l'entrepôt en fonction des tags

            # if 'tag_ids' in vals:
            #     tag_updates = vals.get('tag_ids', [])
            #     if tag_updates and fma_tag.id in tag_updates[0][2]:
            #         warehouse_regripiere = self.env['stock.warehouse'].search([('name', '=', 'LA REGRIPPIERE')], limit=1)
            #         if warehouse_regripiere:
            #             vals['warehouse_id'] = warehouse_regripiere.id
            #     if tag_updates and f2m_tag.id in tag_updates[0][2]:
            #         warehouse_remaudiere = self.env['stock.warehouse'].search([('name', '=', 'LA REMAUDIERE')], limit=1)
            #         if warehouse_remaudiere:
            #             vals['warehouse_id'] = warehouse_remaudiere.id

            # improvement in condition
            if "tag_ids" in vals:
                tag_updates = vals.get("tag_ids", [])
                if tag_updates:
                    if (
                        isinstance(tag_updates[0], (list, tuple))
                        and len(tag_updates[0]) > 2
                        and tag_updates[0][0] == 6
                    ):
                        tag_ids = tag_updates[0][2]
                        if fma_tag.id in tag_ids:
                            warehouse_regripiere = self.env["stock.warehouse"].search(
                                [("name", "=", "LA REGRIPPIERE")], limit=1
                            )
                            if warehouse_regripiere:
                                vals["warehouse_id"] = warehouse_regripiere.id
                        if f2m_tag.id in tag_ids:
                            warehouse_remaudiere = self.env["stock.warehouse"].search(
                                [("name", "=", "LA REMAUDIERE")], limit=1
                            )
                            if warehouse_remaudiere:
                                vals["warehouse_id"] = warehouse_remaudiere.id

                    elif (
                        isinstance(tag_updates[0], (list, tuple))
                        and len(tag_updates[0]) > 1
                        and tag_updates[0][0] == 4
                    ):
                        tag_id = tag_updates[0][1]
                        if fma_tag.id == tag_id:
                            warehouse_regripiere = self.env["stock.warehouse"].search(
                                [("name", "=", "LA REGRIPPIERE")], limit=1
                            )
                            if warehouse_regripiere:
                                vals["warehouse_id"] = warehouse_regripiere.id
                        if f2m_tag.id == tag_id:
                            warehouse_remaudiere = self.env["stock.warehouse"].search(
                                [("name", "=", "LA REMAUDIERE")], limit=1
                            )
                            if warehouse_remaudiere:
                                vals["warehouse_id"] = warehouse_remaudiere.id

        return super(SaleOrder, self).create(vals_list)

    # Méthode write : mise à jour du mode de règlement et de la date de modification du devis
    def write(self, vals):
        _logger.info("Appel de write avec vals: %s", vals)

        # Si la date du devis est modifiée, copier la même valeur dans la date de modification du devis
        if "so_date_du_devis" in vals:
            vals["so_date_de_modification_devis"] = vals["so_date_du_devis"]

        # Si partner_id est modifié, mettre à jour le champ x_studio_mode_de_rglement_1
        if "partner_id" in vals:
            partner = self.env["res.partner"].browse(vals["partner_id"])
            vals["x_studio_mode_de_rglement_1"] = partner.x_studio_mode_de_rglement_1

        # Appel de la méthode write parente
        res = super(SaleOrder, self).write(vals)
        # self.ids et non self.id : write s'applique a un ensemble, et self.id
        # sur plus d'un enregistrement leve « Expected singleton ». Une simple
        # trace rendait donc impossible toute ecriture groupee sur les devis.
        _logger.info("Devis mis à jour: %s", self.ids)

        # Mise à jour de l'entrepôt si les tags sont modifiés
        if "tag_ids" in vals:
            _logger.info("Appel de _update_warehouse après mise à jour")
            self._update_warehouse()

        return res

    # Mise à jour de l'entrepôt en fonction des tags
    def _update_warehouse(self):
        _logger.info("Début de _update_warehouse pour le devis: %s", self.ids)
        fma_tag = self.env["crm.tag"].search([("name", "=", "FMA")], limit=1)
        f2m_tag = self.env["crm.tag"].search([("name", "=", "F2M")], limit=1)
        for order in self:
            _logger.info("Tags actuels: %s", order.tag_ids)
            if fma_tag in order.tag_ids:
                warehouse_regripiere = self.env["stock.warehouse"].search(
                    [("name", "=", "LA REGRIPPIERE")], limit=1
                )
                if warehouse_regripiere:
                    order.warehouse_id = warehouse_regripiere.id
            else:
                warehouse_remaudiere = self.env["stock.warehouse"].search(
                    [("name", "=", "LA REMAUDIERE")], limit=1
                )
                if warehouse_remaudiere:
                    order.warehouse_id = warehouse_remaudiere.id

    # # Init date de livraison prévue et synchronisation avec commitment_date
    # @api.depends('so_date_bpe', 'so_delai_confirme_en_semaine')
    # def _compute_so_date_de_livraison(self):
    #     for order in self:
    #         if order.so_date_bpe and order.so_delai_confirme_en_semaine:
    #             # Calculer la date de livraison prévue
    #             order.so_date_de_livraison = order.so_date_bpe + timedelta(weeks=order.so_delai_confirme_en_semaine)
    #             # Synchroniser avec commitment_date
    #             order.commitment_date = order.so_date_de_livraison
    #         else:
    #             # Réinitialiser si les valeurs nécessaires sont manquantes
    #             order.so_date_de_livraison = False
    #             order.commitment_date = False

    # # Calcul des marges et coûts pour le devis
    # @api.depends('so_mtt_facturer_devis', 'so_achat_vitrage_devis', 'so_achat_matiere_devis')
    # def _compute_so_marge_brute_devis(self):
    #     for order in self:
    #         order.so_marge_brute_devis = order.so_mtt_facturer_devis - order.so_achat_vitrage_devis - order.so_achat_matiere_devis

    # @api.depends('so_marge_brute_devis', 'so_mtt_facturer_devis')
    # def _compute_so_prc_marge_brute_devis(self):
    #     for order in self:
    #         if order.so_mtt_facturer_devis:
    #             order.so_prc_marge_brute_devis = (order.so_marge_brute_devis / order.so_mtt_facturer_devis) * 100
    #         else:
    #             order.so_prc_marge_brute_devis = 0.0

    # @api.depends('so_marge_brute_devis', 'so_cout_mod_devis')
    # def _compute_so_mcv_devis(self):
    #     for order in self:
    #         order.so_mcv_devis = order.so_marge_brute_devis - order.so_cout_mod_devis

    # @api.depends('so_mcv_devis', 'so_mtt_facturer_devis')
    # def _compute_so_prc_mcv_devis(self):
    #     for order in self:
    #         if order.so_mtt_facturer_devis:
    #             order.so_prc_mcv_devis = (order.so_mcv_devis / order.so_mtt_facturer_devis) * 100
    #         else:
    #             order.so_prc_mcv_devis = 0.0

    # # Calcul des marges et coûts pour BE
    # @api.depends('so_mtt_facturer_be', 'so_achat_vitrage_be', 'so_achat_matiere_be')
    # def _compute_so_marge_brute_be(self):
    #     for order in self:
    #         order.so_marge_brute_be = order.so_mtt_facturer_be - order.so_achat_vitrage_be - order.so_achat_matiere_be

    # @api.depends('so_marge_brute_be', 'so_mtt_facturer_be')
    # def _compute_so_prc_marge_brute_be(self):
    #     for order in self:
    #         if order.so_mtt_facturer_be:
    #             order.so_prc_marge_brute_be = (order.so_marge_brute_be / order.so_mtt_facturer_be) * 100
    #         else:
    #             order.so_prc_marge_brute_be = 0.0

    # @api.depends('so_marge_brute_be', 'so_cout_mod_be')
    # def _compute_so_mcv_be(self):
    #     for order in self:
    #         order.so_mcv_be = order.so_marge_brute_be - order.so_cout_mod_be

    # @api.depends('so_mcv_be', 'so_mtt_facturer_be')
    # def _compute_so_prc_mcv_be(self):
    #     for order in self:
    #         if order.so_mtt_facturer_be:
    #             order.so_prc_mcv_be = (order.so_mcv_be / order.so_mtt_facturer_be) * 100
    #         else:
    #             order.so_prc_mcv_be = 0.0

    # # Calcul des marges et coûts pour le réel
    # @api.depends('so_mtt_facturer_reel', 'so_achat_vitrage_reel', 'so_achat_matiere_reel')
    # def _compute_so_marge_brute_reel(self):
    #     for order in self:
    #         order.so_marge_brute_reel = order.so_mtt_facturer_reel - order.so_achat_vitrage_reel - order.so_achat_matiere_reel

    # @api.depends('so_marge_brute_reel', 'so_mtt_facturer_reel')
    # def _compute_so_prc_marge_brute_reel(self):
    #     for order in self:
    #         if order.so_mtt_facturer_reel:
    #             order.so_prc_marge_brute_reel = (order.so_marge_brute_reel / order.so_mtt_facturer_reel) * 100
    #         else:
    #             order.so_prc_marge_brute_reel = 0.0

    # @api.depends('so_marge_brute_reel', 'so_cout_mod_reel')
    # def _compute_so_mcv_reel(self):
    #     for order in self:
    #         order.so_mcv_reel = order.so_marge_brute_reel - order.so_cout_mod_reel

    # @api.depends('so_mcv_reel', 'so_mtt_facturer_reel')
    # def _compute_so_prc_mcv_reel(self):
    #     for order in self:
    #         if order.so_mtt_facturer_reel:
    #             order.so_prc_mcv_reel = (order.so_mcv_reel / order.so_mtt_facturer_reel) * 100
    #         else:
    #             order.so_prc_mcv_reel = 0.0
