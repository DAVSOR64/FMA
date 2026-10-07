# -*- coding: utf-8 -*-
"""Tableau de bord d'ordonnancement, a la maille du LOT.

L'ecran d'ordonnancement existant repond a « ou en est cet ordre de
fabrication ». La question du metier est autre : « cette AFFAIRE va-t-elle
sortir a temps ». Elle ne se lit ni sur un ordre ni sur une commande, mais
sur les lots — et le client final, lui, ne connait pas cette notion.

Ce tableau repond donc a trois questions, lot par lot, regroupees par
affaire :

1. le lot est-il planifie — le debit a une fin de fab, les assemblages
   aussi ;
2. la matiere est-elle commandee, et pour quand — profiles, vitrage et
   quincaillerie separement, parce qu'elles ne viennent ni des memes
   fournisseurs ni aux memes delais ;
3. ce qui en decoule tient-il l'engagement client.

TROIS FAMILLES, PAS QUATRE. Le referentiel en declare quatre, mais le
metier en lit trois : un complementaire EST un profile, et les panneaux
suivent le vitrage. Surtout, un article SANS famille est de la
quincaillerie — c'est deja la regle de la liste de quincaillerie, on ne
s'en invente pas une seconde.

CHAMPS STOCKES, RECALCUL PAR CRON. Le rattachement des achats au lot est
algorithmique : il remonte la chaine reception -> collecte -> composant,
donc hors de portee d'un @api.depends, et trop couteux pour un calcul a
l'affichage. Les dates de fabrication, elles, se suivent normalement.
"""
import logging

from odoo import _, api, fields, models

from odoo.addons.fma_mrp_ordonnancement.models.constants import (
    FMA_POSTE_KEYS,
    FMA_POSTES_SCORES,
    FMA_STATUT_RECEPTION,
)

_logger = logging.getLogger(__name__)

#: Familles d'appro du referentiel -> colonne du tableau. Une famille
#: absente de ce dictionnaire — y compris l'absence de famille — tombe en
#: quincaillerie.
COLONNE_PAR_FAMILLE = {
    "profil": "profil",
    "complementaire": "profil",
    "vitrage": "vitrage",
    "panneaux": "vitrage",
}

COLONNES_MATIERE = ("profil", "vitrage", "quincaillerie")

STATUT_LOT = [
    ("non_planifie", "Non planifié"),
    ("retard", "En retard"),
    ("attention", "À surveiller"),
    ("ok", "À l'heure"),
]


class FmaLotFabrication(models.Model):
    _inherit = "fma.lot.fabrication"

    # --- L'affaire ----------------------------------------------------------
    ordo_commande_id = fields.Many2one(
        "sale.order",
        string="Affaire",
        compute="_compute_ordo", store=True, index="btree_not_null",
        help="La commande du lot. sale_order_ids est calcule non stocke : il "
        "ne peut etre ni groupe ni cherche, et ce tableau se lit par "
        "affaire.",
    )

    # --- Planification ------------------------------------------------------
    ordo_date_debit = fields.Date(
        string="Débit prévu le",
        compute="_compute_ordo", store=True,
        help="Fin de fab de l'OF de débit. Vide = lot non planifié.",
    )
    ordo_date_sortie = fields.Date(
        string="Lot fini le",
        compute="_compute_ordo", store=True,
        help="Fin de fab du dernier assemblage : la date à laquelle le lot "
        "est disponible pour la livraison.",
    )
    ordo_assemblages_planifies = fields.Char(
        string="Assemblages planifiés",
        compute="_compute_ordo", store=True,
        help="Nombre d'assemblages portant une fin de fab, sur le total.",
    )
    ordo_tout_planifie = fields.Boolean(
        string="Lot planifié",
        compute="_compute_ordo", store=True,
    )

    # --- Matiere ------------------------------------------------------------
    ordo_statut_profil = fields.Selection(
        FMA_STATUT_RECEPTION, string="Profilés",
        compute="_compute_ordo", store=True, default="none",
    )
    ordo_statut_vitrage = fields.Selection(
        FMA_STATUT_RECEPTION, string="Vitrage",
        compute="_compute_ordo", store=True, default="none",
    )
    ordo_statut_quincaillerie = fields.Selection(
        FMA_STATUT_RECEPTION, string="Quincaillerie",
        compute="_compute_ordo", store=True, default="none",
    )
    ordo_arrivee_profil = fields.Date(
        string="Profilés attendus le",
        compute="_compute_ordo", store=True,
    )
    ordo_arrivee_vitrage = fields.Date(
        string="Vitrage attendu le",
        compute="_compute_ordo", store=True,
    )
    ordo_arrivee_quincaillerie = fields.Date(
        string="Quincaillerie attendue le",
        compute="_compute_ordo", store=True,
    )
    ordo_matiere_le = fields.Date(
        string="Matière complète le",
        compute="_compute_ordo", store=True,
        help="La plus tardive des trois arrivées. C'est elle qui contraint "
        "le lancement du débit, pas la première.",
    )

    # --- Charge : heures, reperes, complexite, scores -----------------------
    #
    # Ce sont les colonnes du tableau d'ordonnancement des OF, portees au lot.
    # Trois regles d'agregation differentes, et les confondre donnerait des
    # chiffres faux :
    #
    # * LES HEURES S'ADDITIONNENT. Elles viennent des ordres de travail de
    #   chaque OF : la charge du lot est bien la somme de celle de ses ordres.
    #
    # * LES REPERES NE S'ADDITIONNENT PAS. Sur l'OF, ils se comptent sur la
    #   COMMANDE DE VENTE — les sommer sur les huit OF d'un lot de huit
    #   menuiseries multiplierait le resultat par huit. Au lot, un repere est
    #   une menuiserie.
    #
    # * LES SCORES NE S'ADDITIONNENT PAS NON PLUS, et c'est moins visible : un
    #   score est une NOTE, lue dans un bareme a partir du ratio heures /
    #   reperes. Additionner des notes ne veut rien dire. Le score du lot se
    #   relit donc dans le meme bareme, a partir du ratio du lot.
    #
    # La complexite, elle, s'additionne : elle est saisie par menuiserie.
    ordo_heure_debit = fields.Float(
        string="H. Débit", digits=(10, 2), compute="_compute_ordo", store=True)
    ordo_heure_banc = fields.Float(
        string="H. CU (banc)", digits=(10, 2), compute="_compute_ordo", store=True)
    ordo_heure_usinage = fields.Float(
        string="H. Usinage", digits=(10, 2), compute="_compute_ordo", store=True)
    ordo_heure_montage = fields.Float(
        string="H. Montage", digits=(10, 2), compute="_compute_ordo", store=True)
    ordo_heure_vitrage = fields.Float(
        string="H. Vitrage", digits=(10, 2), compute="_compute_ordo", store=True)
    ordo_heure_emballage = fields.Float(
        string="H. Emballage", digits=(10, 2), compute="_compute_ordo", store=True)
    ordo_heure_totale = fields.Float(
        string="Heures totales", digits=(10, 2),
        compute="_compute_ordo", store=True)

    ordo_nb_reperes = fields.Integer(
        string="Nb repères", compute="_compute_ordo", store=True,
        help="Au lot, un repère est une menuiserie : un ordre d'assemblage. "
        "Sur l'OF, les repères se comptent sur la commande de vente — les "
        "sommer sur les ordres d'un lot les multiplierait.",
    )
    ordo_score_complexite = fields.Integer(
        string="Score complexité", compute="_compute_ordo", store=True,
        help="Somme des scores de complexité des ordres du lot : la "
        "complexité est saisie menuiserie par menuiserie, elle s'additionne.",
    )
    ordo_score_debit = fields.Integer(
        string="Score Débit", compute="_compute_ordo", store=True)
    ordo_score_banc = fields.Integer(
        string="Score CU (banc)", compute="_compute_ordo", store=True)
    ordo_score_usinage = fields.Integer(
        string="Score Usinage", compute="_compute_ordo", store=True)
    ordo_score_montage = fields.Integer(
        string="Score Montage", compute="_compute_ordo", store=True)

    # --- Saisie de l'ordonnanceur -------------------------------------------
    #
    # Mêmes regles que sur le tableau des OF : saisissables par le groupe
    # « Modif Ordo » seulement, et suivis dans le fil pour qu'on sache qui a
    # coche et quand.
    ordo_planifie = fields.Boolean(
        string="Planifié", tracking=True,
        help="Marqueur de l'ordonnanceur, équivalent du « P » du classeur. "
        "Modifiable par les membres du groupe « Modif Ordo ».",
    )
    ordo_commentaire = fields.Text(
        string="Commentaires ordonnancement", tracking=True)
    ordo_peut_modifier = fields.Boolean(
        string="Peut modifier l'ordonnancement",
        compute="_compute_ordo_peut_modifier",
        help="Vrai pour les membres du groupe « Modif Ordo ». Rend la saisie "
        "possible pour eux seuls sans la masquer aux autres : un droit "
        "d'ecriture par champ n'existe pas nativement, et poser `groups` sur "
        "le champ le rendrait invisible.",
    )

    def _compute_ordo_peut_modifier(self):
        autorise = self.env["mrp.production"]._fma_utilisateur_peut_modifier()
        for lot in self:
            lot.ordo_peut_modifier = autorise

    # --- Engagement ---------------------------------------------------------
    # --- Engagement ---------------------------------------------------------
    ordo_livraison = fields.Date(
        string="Livraison client",
        compute="_compute_ordo", store=True,
        help="La plus proche des dates de livraison des commandes du lot : "
        "c'est la première qui engage.",
    )
    ordo_marge_jours = fields.Integer(
        string="Marge (jours)",
        compute="_compute_ordo", store=True,
        help="Jours entre la fin du lot et la livraison client. Négatif = "
        "le lot sort après la date promise.",
    )
    ordo_statut = fields.Selection(
        STATUT_LOT, string="Statut",
        compute="_compute_ordo", store=True, default="non_planifie",
    )

    @api.depends(
        "production_ids.state",
        "production_ids.date_start",
        "production_ids.date_finished",
        "production_ids.macro_forced_end",
        "production_ids.lot_production_type",
        "production_ids.fma_heure_totale",
        "production_ids.fma_score_complexite",
        "sale_order_ids.commitment_date",
    )
    def _compute_ordo(self):
        """Les achats ne sont pas dans les dependances — voir l'en-tete."""
        for lot in self:
            try:
                lot._calculer_ordo()
            except Exception:  # noqa: BLE001
                # Un tableau de bord ne doit pas empecher d'enregistrer un
                # lot. On neutralise la ligne et on trace.
                _logger.exception(
                    "Ordonnancement du lot %s", lot.name or lot.id)
                lot._vider_ordo()

    def _vider_ordo(self):
        """Valeurs neutres : un champ calcule stocke doit etre affecte."""
        self.ensure_one()
        self.ordo_commande_id = False
        self.ordo_date_debit = False
        self.ordo_date_sortie = False
        self.ordo_assemblages_planifies = "-"
        self.ordo_tout_planifie = False
        for colonne in COLONNES_MATIERE:
            self["ordo_statut_%s" % colonne] = "none"
            self["ordo_arrivee_%s" % colonne] = False
        self.ordo_matiere_le = False
        for poste in FMA_POSTE_KEYS:
            self["ordo_heure_%s" % poste] = 0.0
        self.ordo_heure_totale = 0.0
        self.ordo_nb_reperes = 0
        self.ordo_score_complexite = 0
        for poste in FMA_POSTES_SCORES:
            self["ordo_score_%s" % poste] = 0
        self.ordo_livraison = False
        self.ordo_marge_jours = 0
        self.ordo_statut = "non_planifie"

    # ------------------------------------------------------------------
    # Le calcul
    # ------------------------------------------------------------------
    def _calculer_ordo(self):
        self.ensure_one()
        commandes = self.sale_order_ids.sorted("id")
        self.ordo_commande_id = commandes[:1]
        self._calculer_ordo_planification()
        self._calculer_ordo_charge()
        # LE LOT TERMINE NE COUTE RIEN. Remonter la chaine des achats est une
        # suite de recherches, et un upgrade qui la joue sur tout l'historique
        # prendrait des minutes pour un resultat que personne ne lit : la
        # matiere d'un lot fabrique est arrivee, la question ne se pose plus.
        if self._ordo_lot_vivant():
            self._calculer_ordo_matiere()
        else:
            for colonne in COLONNES_MATIERE:
                self["ordo_statut_%s" % colonne] = "full"
                self["ordo_arrivee_%s" % colonne] = False
            self.ordo_matiere_le = False
        self._calculer_ordo_engagement()

    def _ordo_lot_vivant(self):
        """Reste-t-il quelque chose a fabriquer sur ce lot ?"""
        self.ensure_one()
        return bool(self.production_ids.filtered(
            lambda p: p.state not in ("done", "cancel")))

    def _calculer_ordo_planification(self):
        self.ensure_one()
        vivants = lambda p: p.state not in ("done", "cancel")  # noqa: E731

        debit = self.production_debit_id
        self.ordo_date_debit = debit._date_fin_de_fab() if debit else False

        assemblages = self.production_assembly_ids.filtered(vivants)
        planifies = assemblages.filtered(lambda p: p._date_fin_de_fab())
        self.ordo_assemblages_planifies = (
            "%s / %s" % (len(planifies), len(assemblages))
            if assemblages else "-"
        )
        self.ordo_tout_planifie = bool(
            self.ordo_date_debit and assemblages and
            len(planifies) == len(assemblages)
        )

        # « Lot fini le » se lit sur les assemblages TERMINES compris : un lot
        # a moitie fabrique garde sa date de sortie, sinon il disparaitrait
        # du tableau au pire moment.
        fins = [
            p._date_fin_de_fab() for p in self.production_assembly_ids
            if p.state != "cancel" and p._date_fin_de_fab()
        ]
        self.ordo_date_sortie = max(fins) if fins else False

    def _calculer_ordo_charge(self):
        """Heures, reperes, complexite et scores du lot."""
        self.ensure_one()
        ordres = self.production_ids.filtered(lambda p: p.state != "cancel")

        for poste in FMA_POSTE_KEYS:
            self["ordo_heure_%s" % poste] = sum(
                ordres.mapped("fma_heure_%s" % poste))
        self.ordo_heure_totale = sum(ordres.mapped("fma_heure_totale"))

        # Un repere = une menuiserie = un ordre d'assemblage. Le repli sur
        # menuiserie_qty couvre le lot pas encore eclate en ordres.
        assemblages = self.production_assembly_ids.filtered(
            lambda p: p.state != "cancel")
        self.ordo_nb_reperes = len(assemblages) or int(self.menuiserie_qty or 0)

        self.ordo_score_complexite = sum(ordres.mapped("fma_score_complexite"))

        # LE SCORE SE RELIT, IL NE S'ADDITIONNE PAS. C'est une note tiree d'un
        # bareme a partir du ratio heures / reperes : la moyenne de deux notes
        # n'est pas leur somme, et leur somme n'a aucun sens.
        bareme = self.env["fma.bareme.score"]
        par_poste = bareme._bareme_par_poste()
        for poste in FMA_POSTES_SCORES:
            if not self.ordo_nb_reperes:
                self["ordo_score_%s" % poste] = 0
                continue
            ratio = self["ordo_heure_%s" % poste] / self.ordo_nb_reperes
            self["ordo_score_%s" % poste] = bareme._score_pour(
                par_poste.get(poste, []), ratio)

    def _calculer_ordo_matiere(self):
        self.ensure_one()
        Production = self.env["mrp.production"]
        par_colonne = {colonne: [] for colonne in COLONNES_MATIERE}
        for ligne in self._lignes_achat_du_lot():
            if ligne.display_type or not ligne.product_id:
                continue
            famille = ligne.fma_famille_appro
            par_colonne[COLONNE_PAR_FAMILLE.get(famille, "quincaillerie")].append(
                ligne)

        arrivees = []
        for colonne, lignes in par_colonne.items():
            arrivee = Production._fma_date_arrivee(lignes)
            arrivee = fields.Date.to_date(arrivee) if arrivee else False
            self["ordo_arrivee_%s" % colonne] = arrivee
            self["ordo_statut_%s" % colonne] = Production._fma_statut_reception(
                lignes)
            if arrivee:
                arrivees.append(arrivee)
        self.ordo_matiere_le = max(arrivees) if arrivees else False

    def _calculer_ordo_engagement(self):
        self.ensure_one()
        dates = [
            fields.Date.to_date(commande.commitment_date)
            for commande in self.sale_order_ids
            if commande.commitment_date
        ]
        # La PLUS PROCHE : c'est la premiere livraison qui contraint le lot,
        # meme si une autre commande du meme lot va plus loin.
        self.ordo_livraison = min(dates) if dates else False
        self.ordo_marge_jours = (
            (self.ordo_livraison - self.ordo_date_sortie).days
            if self.ordo_livraison and self.ordo_date_sortie else 0
        )
        self.ordo_statut = self._statut_ordo()

    def _statut_ordo(self):
        """Le feu du lot. L'ordre des tests est l'ordre de gravite.

        « Non planifie » passe avant tout : sans dates, les autres mesures ne
        veulent rien dire et un feu vert serait un mensonge.
        """
        self.ensure_one()
        if not self._ordo_lot_vivant():
            return "ok"
        if not self.ordo_tout_planifie:
            return "non_planifie"
        if self.ordo_livraison and self.ordo_date_sortie:
            if self.ordo_date_sortie > self.ordo_livraison:
                return "retard"
        # La matiere doit etre la AVANT que le debit commence. Une arrivee le
        # jour meme passe : le magasin garnit les casiers en amont, c'est tout
        # l'objet du delai de sortie matiere.
        if self.ordo_date_debit and self.ordo_matiere_le:
            if self.ordo_matiere_le > self.ordo_date_debit:
                return "retard"
        manquantes = [
            colonne for colonne in COLONNES_MATIERE
            if self["ordo_statut_%s" % colonne] == "none"
        ]
        if manquantes:
            return "attention"
        return "ok"

    # ------------------------------------------------------------------
    # Recalcul
    # ------------------------------------------------------------------
    def action_recalculer_ordo(self):
        """Bouton : recalcule la ligne sans attendre le cron."""
        self._recalculer_ordo()
        return True

    def _recalculer_ordo(self):
        """Force le recalcul des champs du tableau sur ces lots."""
        if not self:
            return
        for nom, champ in self._fields.items():
            # Seuls les champs CALCULES ET STOCKES se forcent ainsi : sur un
            # champ ordinaire, add_to_compute leve.
            if nom.startswith("ordo_") and champ.compute and champ.store:
                self.env.add_to_compute(champ, self)
        self.env.flush_all()

    @api.model
    def cron_ordonnancement(self, lot_max=500):
        """Recalcule les lots encore vivants.

        Les achats arrivent, les receptions se font, les dates fournisseur
        bougent : rien de tout cela ne traverse un @api.depends. Le cron est
        le seul filet. On se limite aux lots dont il reste quelque chose a
        fabriquer — un lot entierement termine ne bougera plus.
        """
        lots = self.search([
            ("production_ids.state", "not in", ("done", "cancel")),
        ], limit=lot_max, order="id desc")
        if not lots:
            return True
        lots._recalculer_ordo()
        _logger.info("Ordonnancement FMA : %s lot(s) recalcule(s)", len(lots))
        return True

    # ------------------------------------------------------------------
    # Raccourcis
    # ------------------------------------------------------------------
    def action_ordo_voir_of(self):
        """Les ordres du lot, depuis le tableau de bord."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ordres de fabrication — %s", self.display_name),
            "res_model": "mrp.production",
            "view_mode": "list,form",
            "domain": [("id", "in", self.production_ids.ids)],
            "context": {"create": False},
        }

    def action_ordo_voir_achats(self):
        """Les bons d'achat du lot, familles confondues."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Achats — %s", self.display_name),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", self.purchase_ids.ids)],
            "context": {"create": False},
        }

    def action_ordo_voir_lignes_achat(self):
        """Le DETAIL : les lignes d'achat du lot, famille par famille.

        Le bon de commande ne suffit pas a repondre « la matiere de ce lot
        est-elle commandee » : un bon melange les lots et les familles. La
        ligne, elle, porte la famille et la quantite recue.
        """
        self.ensure_one()
        lignes = self._lignes_achat_du_lot()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lignes d'achat — %s", self.display_name),
            "res_model": "purchase.order.line",
            "view_mode": "list,form",
            # Notre liste, et pas celle d'Odoo : c'est la date de CHAQUE
            # ligne qu'il faut voir. L'en-tete du bon n'affiche que la plus
            # proche, alors que le tableau retient la plus tardive.
            "views": [
                (self.env.ref(
                    "fma_lot_fabrication.view_fma_lot_lignes_achat_list").id,
                 "list"),
                (False, "form"),
            ],
            "domain": [("id", "in", lignes.ids)],
            "context": {"create": False},
        }
