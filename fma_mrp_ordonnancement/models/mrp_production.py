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
        compute='_compute_fma_nb_reperes', store=True,
        help="Nombre de lignes de la commande de vente portant un bien non "
             "stockable, hors lignes marquées « Exclu du comptage des "
             "repères » (éco-participation notamment).",
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
    # Commande de vente de l'OF
    #
    # Tout ce qui vient du devis en dépend : date d'engagement, bons de
    # livraison, nombre de repères. Or sale_line_id n'est pas toujours
    # renseigné chez FMA — d'où le champ x_studio_mtn_mrp_sale_order, déclaré
    # par le module custom. Un seul point de résolution, stocké, pour que les
    # autres champs puissent en dépendre proprement.
    # ------------------------------------------------------------------
    fma_sale_order_id = fields.Many2one(
        'sale.order',
        string="Commande de vente",
        compute='_compute_fma_sale_order', store=True, index=True,
    )

    # ------------------------------------------------------------------
    # Colonne E : début du débit
    #
    # Ce n'est pas la date de l'OF mais celle de la PREMIÈRE opération de
    # débit (Débit FMA, Débit F2M...), et c'est la date du macro-planning
    # qui fait foi, pas date_start de l'ordre de travail.
    # ------------------------------------------------------------------
    fma_date_debut_debit = fields.Datetime(
        string="Début débit",
        compute='_compute_fma_date_debut_debit', store=True,
        help="macro_planned_start de l'opération de débit la plus précoce.",
    )

    # ------------------------------------------------------------------
    # Colonne G : fin de production
    #
    # Champ Studio x_studio_date_de_fin, porté par l'OF. Il n'est pas déclaré
    # en Python : on le lit comme le fait déjà mrp_capacity_planning, et on
    # le recopie ici pour disposer d'une version cherchable.
    # ------------------------------------------------------------------
    fma_date_fin_prod = fields.Date(
        string="Fin production",
        compute='_compute_fma_date_fin_prod', store=True,
    )

    # ------------------------------------------------------------------
    # Colonne H : date de livraison initiale = engagement pris au devis
    # ------------------------------------------------------------------
    fma_date_liv_initiale = fields.Date(
        string="Date liv. initiale",
        compute='_compute_fma_date_liv_initiale', store=True,
        help="Livraison promise au client, portée par commitment_date. "
             "Distincte de la date révisée (so_date_de_livraison_prevu) et de "
             "la date planifiée du bon de livraison.",
    )

    # ------------------------------------------------------------------
    # Colonne F : marqueur manuel « planifier »
    #
    # Le classeur ne calculait rien ici : l'ordonnanceur tapait « P » pour dire
    # qu'il avait traité l'OF. C'est une intention, pas un état déduit.
    # À ne pas confondre avec is_programmed (mrp_capacity_planning), qui vaut
    # vrai dès qu'un ordre de travail porte une date. is_programmed est calculé
    # non stocké : il s'affiche mais ne peut ni se filtrer ni se regrouper.
    # ------------------------------------------------------------------
    fma_planifie = fields.Boolean(
        string="Planifié",
        tracking=True,
        help="Marqueur de l'ordonnanceur, équivalent du « P » de la colonne "
             "« planifier » du classeur.",
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

    @api.depends(
        'fma_sale_order_id.order_line.x_studio_position',
        'fma_sale_order_id.order_line.product_id.type',
        'fma_sale_order_id.order_line.product_id.is_storable',
        'fma_sale_order_id.order_line.product_id.fma_exclu_reperes',
    )
    def _compute_fma_nb_reperes(self):
        """Colonne T : un repère = une ligne de devis portant une menuiserie.

        Le critère est la **position** du repère (x_studio_position, related du
        produit) : sur A25-07-02581/2, les dix lignes menuiserie la portent
        (« Repère M », « Repère BG »...), tandis que l'éco-contribution, la
        ligne d'affaire et la remise commerciale ne la portent pas. Le seul
        critère « bien non stockable » en retenait douze.

        Repli sur ce critère pour les commandes anciennes où la position n'est
        renseignée sur aucune ligne.
        """
        for production in self:
            lignes = production.fma_sale_order_id.order_line.filtered(
                lambda ligne: not ligne.display_type
                and ligne.product_id
                and not ligne.product_id.fma_exclu_reperes
            )
            avec_position = lignes.filtered(
                lambda ligne: (ligne.x_studio_position or '').strip()
            )
            if avec_position:
                production.fma_nb_reperes = len(avec_position)
            else:
                production.fma_nb_reperes = len(lignes.filtered(
                    lambda ligne: ligne.product_id.type == 'consu'
                    and not ligne.product_id.is_storable
                ))

    @api.depends('x_studio_niveau_de_complexite')
    def _compute_fma_complexite(self):
        """Colonne U : score de complexité, depuis le champ saisi sur l'OF."""
        poids_par_code = self.env['fma.complexite.niveau']._poids_par_code()
        for production in self:
            production.fma_score_complexite = self._fma_score_complexite(
                production.x_studio_niveau_de_complexite, poids_par_code,
            )

    @api.model
    def _fma_score_complexite(self, texte, poids_par_code):
        """Analyse le texte « A*3 » / « C*4 », une ligne par niveau.

        Reproduit la formule U2 du classeur : une ligne sans « * » compte pour
        un, un code inconnu pèse zéro.
        """
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
            score += poids_par_code.get(code, 0) * max(quantite, 0)
        return score

    @api.depends('sale_line_id.order_id', 'x_studio_mtn_mrp_sale_order')
    def _compute_fma_sale_order(self):
        """Résout la commande de vente, sale_line_id puis champ de secours."""
        for production in self:
            production.fma_sale_order_id = (
                production.sale_line_id.order_id
                or production.x_studio_mtn_mrp_sale_order
                or False
            )

    @api.depends(
        'workorder_ids.macro_planned_start',
        'workorder_ids.workcenter_id.fma_poste_type',
    )
    def _compute_fma_date_debut_debit(self):
        """Colonne E : macro_planned_start de la première opération de débit."""
        for production in self:
            debits = production.workorder_ids.filtered(
                lambda wo: wo.workcenter_id.fma_poste_type == 'debit'
                and wo.macro_planned_start
            )
            dates = debits.mapped('macro_planned_start')
            production.fma_date_debut_debit = min(dates) if dates else False

    @api.depends('state')
    def _compute_fma_date_fin_prod(self):
        """Colonne G : recopie du champ Studio de fin de fabrication.

        x_studio_date_de_fin n'est pas declaré en Python : impossible de le
        citer dans un @api.depends sans risquer une erreur au montage du
        registre. Le recalcul est déclenché par write() ci-dessous.
        """
        for production in self:
            valeur = (
                getattr(production, 'x_studio_date_de_fin', False)
                or getattr(production, 'x_studio_date_fin', False)
            )
            production.fma_date_fin_prod = fields.Date.to_date(valeur) if valeur else False

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
        """Colonnes L à Q : dates d'arrivée et réceptions, par famille.

        La famille est portée par la catégorie du produit acheté, pas par le
        fournisseur : une même commande peut mélanger des familles, et un même
        fournisseur en livrer plusieurs. La ventilation se fait donc ligne à
        ligne.

        Le lien OF -> commandes d'achat est algorithmique (voir
        _fma_purchase_orders), donc hors de portée d'@api.depends : le recalcul
        est déclenché depuis purchase.order, purchase.order.line, stock.picking
        et product.category, avec le cron en filet de sécurité.
        """
        for production in self:
            par_famille = {famille: [] for famille in FMA_CATEGORIES_APPRO_KEYS}
            for purchase in production._fma_purchase_orders():
                for ligne in purchase.order_line:
                    if ligne.display_type or not ligne.product_id:
                        continue
                    famille = ligne.product_id.product_tmpl_id._fma_famille_appro()
                    if famille in par_famille:
                        par_famille[famille].append(ligne)

            complet = True
            for famille, lignes in par_famille.items():
                production['fma_date_arrivee_%s' % famille] = \
                    production._fma_date_arrivee(lignes)
                statut = production._fma_statut_reception(lignes)
                production['fma_statut_reception_%s' % famille] = statut
                if statut in ('pending', 'partial'):
                    complet = False
            production.fma_appro_complet = complet

    @api.depends(
        'fma_sale_order_id.picking_ids.scheduled_date',
        'fma_sale_order_id.picking_ids.state',
        'fma_sale_order_id.delivery_status',
    )
    def _compute_fma_livraison(self):
        """Colonnes J et K.

        Les transferts de livraison appartiennent à la commande de vente, pas
        à l'OF : mrp.production.picking_ids ne porte que les mouvements de
        composants et de produit fini, jamais le bon de livraison client.
        C'est ce qui laissait ces deux colonnes vides.

        Pour le statut, on privilégie delivery_status quand il est renseigné,
        et on retombe sur l'état des bons de livraison sinon.
        """
        for production in self:
            sale_order = production.fma_sale_order_id
            livraisons = sale_order.picking_ids.filtered(
                lambda picking: picking.picking_type_id.code == 'outgoing'
                and picking.state != 'cancel'
            ) if sale_order else self.env['stock.picking']

            dates = [
                picking.scheduled_date for picking in livraisons
                if picking.scheduled_date
            ]
            production.fma_date_livraison = max(dates).date() if dates else False

            statut_natif = sale_order.delivery_status if sale_order else False
            if statut_natif:
                production.fma_statut_livraison = {
                    'full': 'full',
                    'partial': 'partial',
                    'started': 'partial',
                    'pending': 'pending',
                }.get(statut_natif, 'pending')
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

    @api.depends('fma_sale_order_id.commitment_date')
    def _compute_fma_date_liv_initiale(self):
        """Colonne H : la livraison promise au client, et elle seule.

        commitment_date porte l'engagement d'origine. Ne pas le confondre avec
        so_date_de_livraison_prevu, qui porte la date *révisée* : sur
        A25-07-02581/2, l'engagement est au 26/08 alors que le client a demandé
        le 01/09 par la suite. C'est le 26/08 qui mesure la tenue du délai.
        """
        for production in self:
            engagement = production.fma_sale_order_id.commitment_date
            production.fma_date_liv_initiale = (
                fields.Date.to_date(engagement) if engagement else False
            )

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
    def _fma_date_arrivee(self, lignes):
        """Arrivée prévue la plus tardive d'un lot de lignes d'achat.

        C'est la ligne qui arrive en dernier qui contraint le lancement, pas
        la première.
        """
        dates = [ligne.date_planned for ligne in lignes if ligne.date_planned]
        if not dates:
            return False
        plus_tardive = max(dates)
        return plus_tardive.date() if hasattr(plus_tardive, 'date') else plus_tardive

    @api.model
    def _fma_statut_reception(self, lignes):
        """Agrège l'état de réception d'un lot de lignes d'achat.

        On raisonne sur les quantités reçues ligne à ligne plutôt que sur le
        statut d'en-tête de la commande : une commande peut mélanger des
        familles, et seule la part qui concerne la famille compte.
        """
        if not lignes:
            return 'none'
        recues = 0
        partielles = 0
        for ligne in lignes:
            attendu = ligne.product_qty or 0.0
            recu = ligne.qty_received or 0.0
            if attendu and recu >= attendu:
                recues += 1
            elif recu > 0:
                partielles += 1
        if recues == len(lignes):
            return 'full'
        if recues or partielles:
            return 'partial'
        return 'pending'

    # ==================================================================
    # Déclencheur pour les champs Studio
    # ==================================================================
    def write(self, vals):
        result = super().write(vals)
        # x_studio_date_de_fin n'est pas déclaré en Python : aucun @api.depends
        # ne peut le viser, on redemande donc le calcul à la main.
        if {'x_studio_date_de_fin', 'x_studio_date_fin'} & set(vals):
            self._fma_marquer_recalcul(['fma_date_fin_prod'], productions=self)
        return result

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
            ['fma_sale_order_id']
            + self._fma_champs_heures_et_scores()
            + self._fma_champs_appro()
            + ['fma_nb_reperes', 'fma_score_complexite', 'fma_date_livraison',
               'fma_statut_livraison', 'fma_date_liv_initiale',
               'fma_date_debut_debit', 'fma_date_fin_prod']
        )
        self._fma_marquer_recalcul(champs, productions=productions, force=True)
        productions.flush_recordset()
        _logger.info(
            "Ordonnancement FMA : %s OF réévalués par le cron.", len(productions),
        )
        return True
