# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from .constants import (
    FMA_CATEGORIES_APPRO_KEYS,
    FMA_ETATS_CLOS,
    FMA_POSTE_KEYS,
    FMA_POSTES_SCORES,
    FMA_STATUT_RECEPTION,
)

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    """Reprise des colonnes de l'onglet TDB_SAISIE sur l'ordre de fabrication.

    Tous les champs calculés sont stockés : c'est la condition pour qu'ils
    soient filtrables, groupables et utilisables en tableau croisé. En
    contrepartie, chaque champ doit être invalidé explicitement quand sa source
    change sans qu'un chemin de dépendance existe (barèmes, commandes d'achat,
    famille fournisseur). Voir _fma_marquer_recalcul.
    """

    _inherit = 'mrp.production'

    # ------------------------------------------------------------------
    # Colonnes W à AA : heures prévues par poste de charge
    # ------------------------------------------------------------------
    fma_heure_debit = fields.Float(
        string="Heures Débit", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )
    fma_heure_banc = fields.Float(
        string="Heures CU (banc)", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )
    fma_heure_usinage = fields.Float(
        string="Heures Usinage", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )
    fma_heure_montage = fields.Float(
        string="Heures Montage", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )
    fma_heure_vitrage = fields.Float(
        string="Heures Vitrage", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )
    fma_heure_emballage = fields.Float(
        string="Heures Emballage", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )
    fma_heure_totale = fields.Float(
        string="Heures totales", digits=(10, 2),
        compute='_compute_fma_heures', store=True,
    )

    # ------------------------------------------------------------------
    # Colonnes T et U : repères et complexité
    # ------------------------------------------------------------------
    fma_nb_reperes = fields.Integer(
        string="Nb repères",
        compute='_compute_fma_complexite', store=True,
        help="Somme des multiplicateurs du champ « Niveau de complexité ». "
             "Une ligne « A*3 » compte 3 repères, une ligne « A » en compte 1.",
    )
    fma_score_complexite = fields.Integer(
        string="Score complexité",
        compute='_compute_fma_complexite', store=True,
        help="Somme, par ligne du champ « Niveau de complexité », du poids du "
             "niveau multiplié par le nombre de repères.",
    )

    # ------------------------------------------------------------------
    # Colonne V et extensions : scores par poste
    # ------------------------------------------------------------------
    fma_score_debit = fields.Integer(
        string="Score Débit", compute='_compute_fma_scores', store=True,
    )
    fma_score_banc = fields.Integer(
        string="Score CU (banc)", compute='_compute_fma_scores', store=True,
    )
    fma_score_usinage = fields.Integer(
        string="Score Usinage", compute='_compute_fma_scores', store=True,
    )
    fma_score_montage = fields.Integer(
        string="Score Montage", compute='_compute_fma_scores', store=True,
    )

    # ------------------------------------------------------------------
    # Colonnes L à Q : approvisionnements par famille
    # ------------------------------------------------------------------
    fma_date_arrivee_profil = fields.Date(
        string="Arrivée profilés", compute='_compute_fma_appro', store=True,
        help="Date d'arrivée prévue la plus tardive parmi les commandes "
             "d'achat de profilés rattachées à l'OF : c'est celle qui "
             "contraint le lancement.",
    )
    fma_date_arrivee_vitrage = fields.Date(
        string="Arrivée vitrage", compute='_compute_fma_appro', store=True,
    )
    fma_date_arrivee_panneaux = fields.Date(
        string="Arrivée panneaux", compute='_compute_fma_appro', store=True,
    )
    fma_date_arrivee_complementaire = fields.Date(
        string="Arrivée complémentaire", compute='_compute_fma_appro', store=True,
    )
    fma_statut_reception_profil = fields.Selection(
        FMA_STATUT_RECEPTION, string="Réception profilés",
        compute='_compute_fma_appro', store=True, default='none',
    )
    fma_statut_reception_vitrage = fields.Selection(
        FMA_STATUT_RECEPTION, string="Réception vitrage",
        compute='_compute_fma_appro', store=True, default='none',
    )
    fma_statut_reception_panneaux = fields.Selection(
        FMA_STATUT_RECEPTION, string="Réception panneaux",
        compute='_compute_fma_appro', store=True, default='none',
    )
    fma_statut_reception_complementaire = fields.Selection(
        FMA_STATUT_RECEPTION, string="Réception complémentaire",
        compute='_compute_fma_appro', store=True, default='none',
    )
    fma_appro_complet = fields.Boolean(
        string="Appro complet",
        compute='_compute_fma_appro', store=True,
        help="Vrai quand aucune famille d'approvisionnement n'est en attente "
             "ou partiellement reçue.",
    )

    # ------------------------------------------------------------------
    # Colonnes J et K : livraison
    # ------------------------------------------------------------------
    fma_date_livraison = fields.Date(
        string="Date livraison actuelle",
        compute='_compute_fma_livraison', store=True,
    )
    fma_statut_livraison = fields.Selection(
        [('pending', "Non livré"),
         ('partial', "Partiellement livré"),
         ('full', "Entièrement livré"),
         ('none', "Pas de livraison")],
        string="Statut de livraison",
        compute='_compute_fma_livraison', store=True, default='none',
    )

    # ------------------------------------------------------------------
    # Colonne S
    # ------------------------------------------------------------------
    fma_commentaire = fields.Text(string="Commentaires ordonnancement", tracking=True)

    # ==================================================================
    # Helpers d'invalidation
    # ==================================================================
    @api.model
    def _fma_champs_heures(self):
        return ['fma_heure_%s' % key for key in FMA_POSTE_KEYS] + ['fma_heure_totale']

    @api.model
    def _fma_champs_scores(self):
        return ['fma_score_%s' % poste for poste in FMA_POSTES_SCORES]

    @api.model
    def _fma_champs_heures_et_scores(self):
        return self._fma_champs_heures() + self._fma_champs_scores()

    @api.model
    def _fma_champs_appro(self):
        champs = ['fma_appro_complet']
        for famille in FMA_CATEGORIES_APPRO_KEYS:
            champs.append('fma_date_arrivee_%s' % famille)
            champs.append('fma_statut_reception_%s' % famille)
        return champs

    @api.model
    def _fma_domaine_ouvert(self):
        """OF encore pilotables. Inutile de recalculer un OF clos ou annulé."""
        return [('state', 'not in', FMA_ETATS_CLOS)]

    @api.model
    def _fma_marquer_recalcul(self, champs, productions=None, force=False):
        """Redemande le calcul de champs stockés dont la source a changé.

        Nécessaire pour tout ce qu'@api.depends ne peut pas atteindre :
        modification d'un barème, d'un niveau de complexité, du typage d'un
        poste de charge, de la famille d'un fournisseur, ou d'une commande
        d'achat rattachée à l'OF par résolution algorithmique.

        `force` sert au post_init_hook et au cron : pendant le chargement d'un
        module le registre n'est pas prêt, et la création des données de
        configuration déclencherait sinon un recalcul par enregistrement chargé.
        """
        if not force and not self.env.registry.ready:
            # Chargement du module : le post_init_hook fait le calcul complet.
            return
        if productions is None:
            productions = self.sudo().search(self._fma_domaine_ouvert())
        if not productions:
            return
        for nom in champs:
            champ = self._fields.get(nom)
            if champ is not None and champ.store and champ.compute:
                self.env.add_to_compute(champ, productions)

    # ==================================================================
    # Calculs
    # ==================================================================
    @api.depends(
        'workorder_ids',
        'workorder_ids.duration_expected',
        'workorder_ids.workcenter_id',
        'workorder_ids.workcenter_id.fma_poste_type',
    )
    def _compute_fma_heures(self):
        """Colonnes W à AA du TDB_SAISIE.

        Différence assumée avec le classeur : Excel utilisait un XLOOKUP, qui
        ne retenait que le premier ordre de travail d'un poste. On somme, afin
        qu'un OF comportant deux passages sur le même poste soit correctement
        valorisé.
        """
        for production in self:
            totaux = dict.fromkeys(FMA_POSTE_KEYS, 0.0)
            for workorder in production.workorder_ids:
                poste_type = workorder.workcenter_id.fma_poste_type
                if poste_type in totaux:
                    totaux[poste_type] += (workorder.duration_expected or 0.0) / 60.0
            for key in FMA_POSTE_KEYS:
                production['fma_heure_%s' % key] = totaux[key]
            production.fma_heure_totale = sum(totaux.values())

    @api.depends('x_studio_niveau_de_complexite')
    def _compute_fma_complexite(self):
        """Colonnes T et U du TDB_SAISIE."""
        poids_par_code = self.env['fma.complexite.niveau']._poids_par_code()
        for production in self:
            nb_reperes, score = self._fma_parser_complexite(
                production.x_studio_niveau_de_complexite, poids_par_code,
            )
            production.fma_nb_reperes = nb_reperes
            production.fma_score_complexite = score

    @api.model
    def _fma_parser_complexite(self, texte, poids_par_code):
        """Analyse le texte « A*3 » / « C*4 », une ligne par niveau.

        Reproduit les formules T2 et U2 du classeur : une ligne sans « * »
        compte pour un repère, un code inconnu pèse zéro dans le score mais
        compte bien dans le nombre de repères.
        """
        nb_reperes = 0
        score = 0
        for ligne in (texte or '').splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            code, _separateur, multiplicateur = ligne.partition('*')
            code = code.strip().upper()
            multiplicateur = multiplicateur.strip().replace(',', '.')
            try:
                quantite = int(float(multiplicateur)) if multiplicateur else 1
            except ValueError:
                quantite = 1
            if quantite < 0:
                quantite = 0
            nb_reperes += quantite
            score += poids_par_code.get(code, 0) * quantite
        return nb_reperes, score

    @api.depends('fma_nb_reperes', 'fma_heure_debit', 'fma_heure_banc',
                 'fma_heure_usinage', 'fma_heure_montage')
    def _compute_fma_scores(self):
        """Colonne V et ses équivalents banc / usinage / montage.

        Le barème vit dans fma.bareme.score : le modifier ne déclenche aucun
        recalcul automatique, d'où l'invalidation explicite portée par ce
        modèle-là.
        """
        baremes = self.env['fma.bareme.score']._bareme_par_poste()
        moteur = self.env['fma.bareme.score']
        for production in self:
            nb_reperes = production.fma_nb_reperes or 0
            for poste in FMA_POSTES_SCORES:
                if not nb_reperes:
                    production['fma_score_%s' % poste] = 0
                    continue
                ratio = production['fma_heure_%s' % poste] / nb_reperes
                production['fma_score_%s' % poste] = moteur._score_pour(
                    baremes.get(poste, []), ratio,
                )

    @api.depends('state', 'move_raw_ids')
    def _compute_fma_appro(self):
        """Colonnes L à Q du TDB_SAISIE.

        Le lien OF -> commandes d'achat est algorithmique (voir
        _fma_purchase_orders), donc hors de portée d'@api.depends : le recalcul
        est déclenché depuis purchase.order et stock.picking, avec le cron en
        filet de sécurité.
        """
        for production in self:
            par_famille = {famille: [] for famille in FMA_CATEGORIES_APPRO_KEYS}
            for purchase in production._fma_purchase_orders():
                famille = purchase.partner_id.fma_categorie_appro
                if famille in par_famille:
                    par_famille[famille].append(purchase)

            complet = True
            for famille, commandes in par_famille.items():
                date_arrivee = production._fma_date_arrivee(commandes)
                statut = production._fma_statut_reception(commandes)
                production['fma_date_arrivee_%s' % famille] = date_arrivee
                production['fma_statut_reception_%s' % famille] = statut
                if statut in ('pending', 'partial'):
                    complet = False
            production.fma_appro_complet = complet

    @api.depends('picking_ids', 'picking_ids.state', 'picking_ids.scheduled_date',
                 'sale_line_id.order_id.delivery_status')
    def _compute_fma_livraison(self):
        """Colonnes J et K du TDB_SAISIE.

        Colonne J : date planifiée du transfert de livraison.
        Colonne K : statut de livraison de la commande de vente. On privilégie
        sale.order.delivery_status, qui est la source exacte de l'export
        Excel, et on retombe sur l'état des transferts si aucune commande
        n'est résolue (OF sur stock).
        """
        for production in self:
            livraisons = production.picking_ids.filtered(
                lambda picking: picking.picking_type_id.code == 'outgoing'
                and picking.state != 'cancel'
            )
            dates = [
                picking.scheduled_date for picking in livraisons
                if picking.scheduled_date
            ]
            production.fma_date_livraison = max(dates).date() if dates else False

            statut_so = False
            sale_order = production.sale_line_id.order_id
            if sale_order and 'delivery_status' in sale_order._fields:
                statut_so = sale_order.delivery_status
            if statut_so:
                production.fma_statut_livraison = {
                    'full': 'full',
                    'partial': 'partial',
                    'started': 'partial',
                    'pending': 'pending',
                }.get(statut_so, 'pending')
            elif not livraisons:
                production.fma_statut_livraison = 'none'
            else:
                etats = set(livraisons.mapped('state'))
                if etats == {'done'}:
                    production.fma_statut_livraison = 'full'
                elif 'done' in etats:
                    production.fma_statut_livraison = 'partial'
                else:
                    production.fma_statut_livraison = 'pending'

    # ==================================================================
    # Résolution des commandes d'achat rattachées à l'OF
    # ==================================================================
    def _fma_purchase_orders(self):
        """Commandes d'achat liées à l'OF.

        Reprend la stratégie déjà éprouvée dans
        mrp_capacity_planning.mrp.production : méthode native de purchase_mrp,
        repli sur l'origine, puis rattachement par projet du SO pour les
        commandes saisies à la main hors chaîne d'approvisionnement.
        Remplace le découpage de texte du nom d'affaire (colonne R du
        classeur, qui était d'ailleurs en erreur).
        """
        self.ensure_one()
        purchases = self.env['purchase.order']
        try:
            purchases = self._get_purchase_orders()
        except AttributeError:
            purchases = self.env['purchase.order']

        if not purchases and self.name:
            purchases = self.env['purchase.order'].search([
                ('origin', 'ilike', self.name),
            ])

        sale_order = False
        try:
            sale_order = self._get_macro_target_date()[1]
        except Exception:  # pragma: no cover - dépend de mrp_capacity_planning
            _logger.debug("OF %s : commande de vente non résolue", self.name)

        if (
            sale_order
            and 'x_studio_projet' in sale_order._fields
            and sale_order.x_studio_projet
            and 'x_studio_projet_du_so' in self.env['purchase.order']._fields
        ):
            purchases |= self.env['purchase.order'].search([
                ('x_studio_projet_du_so', '=', sale_order.x_studio_projet.id),
            ])

        return purchases.filtered(lambda purchase: purchase.state != 'cancel')

    @api.model
    def _fma_date_arrivee(self, commandes):
        """Date d'arrivée prévue la plus tardive d'un lot de commandes."""
        dates = []
        for purchase in commandes:
            lignes = [
                ligne.date_planned for ligne in purchase.order_line
                if ligne.date_planned
            ]
            if lignes:
                dates.append(max(lignes))
            elif getattr(purchase, 'date_planned', False):
                dates.append(purchase.date_planned)
        if not dates:
            return False
        plus_tardive = max(dates)
        return plus_tardive.date() if hasattr(plus_tardive, 'date') else plus_tardive

    @api.model
    def _fma_statut_reception(self, commandes):
        """Agrège les statuts de réception d'un lot de commandes."""
        if not commandes:
            return 'none'
        statuts = set()
        for purchase in commandes:
            statut = getattr(purchase, 'receipt_status', False)
            if not statut:
                statut = self._fma_statut_reception_depuis_pickings(purchase)
            statuts.add(statut)
        statuts.discard(False)
        if not statuts:
            return 'none'
        if statuts == {'full'}:
            return 'full'
        if 'partial' in statuts or 'full' in statuts:
            return 'partial'
        return 'pending'

    @api.model
    def _fma_statut_reception_depuis_pickings(self, purchase):
        """Repli si purchase.order.receipt_status n'est pas disponible."""
        receptions = purchase.picking_ids.filtered(
            lambda picking: picking.state != 'cancel'
        )
        if not receptions:
            return 'pending'
        etats = set(receptions.mapped('state'))
        if etats == {'done'}:
            return 'full'
        if 'done' in etats:
            return 'partial'
        return 'pending'

    # ==================================================================
    # Cron de rattrapage
    # ==================================================================
    @api.model
    def _cron_fma_recalcul_ordonnancement(self):
        """Filet de sécurité nocturne.

        Ne remplace pas les déclencheurs : rattrape les cas non prévus
        (import en masse, correction directe en base, module tiers).
        """
        productions = self.sudo().search(self._fma_domaine_ouvert())
        if not productions:
            return True
        champs = (
            self._fma_champs_heures_et_scores()
            + self._fma_champs_appro()
            + ['fma_nb_reperes', 'fma_score_complexite',
               'fma_date_livraison', 'fma_statut_livraison']
        )
        self._fma_marquer_recalcul(champs, productions=productions, force=True)
        productions.flush_recordset()
        _logger.info(
            "Ordonnancement FMA : %s OF réévalués par le cron.", len(productions),
        )
        return True
