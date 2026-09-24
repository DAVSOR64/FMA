# -*- coding: utf-8 -*-
"""Lot de fabrication FMA.

Un lot regroupe des lignes de devis (= des menuiseries) pour la production.
Il porte deux niveaux d'ordres de fabrication :

* 1 OF Debit -> niveau lot, consomme les profiles — et eux seuls —, porte les
  operations Debit et CU, et sert de point d'entree aux approvisionnements ;
* 1 OF Assemblage par ligne de lot -> consomme l'ensemble debite, la
  quincaillerie et le vitrage, c'est la que l'on declare la fabrication.

Il n'y a pas de troisieme niveau. Un OF de quincaillerie a existe : il ne
produisait rien et ne portait aucune operation, son seul travail reel etant
le transfert Stock -> Pre-Fab de ses composants. Ce transfert existe en
propre — c'est la sortie matiere du lot — et le kit est devenu une
nomenclature phantom, eclatee dans l'OF d'assemblage.

La matiere sort en DEUX temps, et donc en deux documents : les prelevements
de composants sont regroupes par niveau, jamais entre les deux.

* la quincaillerie et le vitrage partent en Pre-Fab a J-3 ouvres, le temps
  pour le magasin de garnir un casier par menuiserie ;
* les profiles partent au banc de debit avec l'OF de debit, qui les consomme
  TOUS — c'est le lot entier qui est optimise, pas une menuiserie.

Les fondre en un seul bon reviendrait a sortir les barres trois jours trop
tot, et a les faire passer par le casier alors qu'elles vont a la scie.

Quincaillerie et assemblage portent la quantite de la ligne : l'atelier
declare menuiserie par menuiserie, Odoo cree le reliquat du reste.

Les niveaux sont relies par ``lot_fabrication_id`` (la reference de lot), et
non par le chainage parent/enfant natif d'Odoo.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


def uom_fname(model):
    """Nom du champ UoM sur ``model``.

    Odoo a renomme ``product_uom`` en ``product_uom_id`` a des versions
    differentes selon les modeles ; on resout le nom au runtime plutot que de
    le figer, pour rester compatible entre versions.
    """
    if "product_uom_id" in model._fields:
        return "product_uom_id"
    return "product_uom"


def date_start_fname(model):
    """Nom du champ de date de debut planifiee sur mrp.production."""
    if "date_start" in model._fields:
        return "date_start"
    return "date_planned_start"


class FmaLotFabrication(models.Model):
    _name = "fma.lot.fabrication"
    _description = "Lot de fabrication"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_planned_start desc, name desc"

    name = fields.Char(
        string="Numero de lot",
        required=True,
        copy=False,
        readonly=False,
        default="/",
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirme"),
            ("progress", "En production"),
            ("done", "Termine"),
            ("cancel", "Annule"),
        ],
        string="Etat",
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Societe",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Client",
        compute="_compute_partner_id",
        store=True,
        tracking=True,
        help="Client du (ou du premier) devis loti. Un lot peut couvrir "
        "plusieurs commandes d'un meme chantier.",
    )
    # Fin de fabrication du lot : la plus tardive de ses assemblages. Stockee
    # et modifiable — la modifier puis « Replanifier » fait remonter tout le
    # lot depuis cette date, debit compris. C'est la prise de l'ordonnanceur
    # sur le planning, la ou la date de livraison est la promesse au client.
    date_fin_fab = fields.Datetime(
        string="Fin de fabrication",
        compute="_compute_date_fin_fab",
        store=True,
        readonly=False,
        help="Date de fin des OF d'assemblage du lot. La modifier puis "
        "cliquer sur « Replanifier » recalcule les dates de debut, debit "
        "compris.",
    )

    @api.depends(
        "production_assembly_ids.date_finished",
        "production_assembly_ids.state",
    )
    def _compute_date_fin_fab(self):
        for lot in self:
            actifs = lot.production_assembly_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
            )
            dates = [d for d in actifs.mapped("date_finished") if d]
            lot.date_fin_fab = max(dates) if dates else False

    date_planned_start = fields.Datetime(
        string="Date planifiee",
        default=fields.Datetime.now,
        tracking=True,
        help="Date reprise sur les OF generes.",
    )

    # --- Composition du lot -------------------------------------------------
    line_ids = fields.One2many(
        "fma.lot.fabrication.line",
        "lot_id",
        string="Menuiseries du lot",
        copy=True,
    )
    material_line_ids = fields.One2many(
        "fma.lot.material.line",
        "lot_id",
        string="Besoin matiere",
        copy=True,
        help="Besoin matiere du lot (profiles, renforts...). Utilise comme "
        "composants de l'OF Debit lorsque l'article debite n'a pas de "
        "nomenclature dediee.",
    )
    menuiserie_qty = fields.Float(
        string="Menuiseries",
        compute="_compute_menuiserie_qty",
        store=True,
        help="Nombre total de menuiseries du lot (somme des quantites lotees).",
    )
    max_menuiserie = fields.Integer(
        string="Maximum par lot",
        compute="_compute_max_menuiserie",
        help="Plafond parametre au niveau de la societe.",
    )
    sale_order_ids = fields.Many2many(
        "sale.order",
        string="Commandes",
        compute="_compute_sale_order_ids",
        store=False,
    )
    sale_order_count = fields.Integer(
        string="Nb commandes",
        compute="_compute_sale_order_ids",
    )

    # --- Production ---------------------------------------------------------
    product_debit_id = fields.Many2one(
        "product.product",
        string="Article debite",
        domain="[('type', '=', 'consu')]",
        tracking=True,
        help="Article intermediaire produit par l'OF Debit et consomme par "
        "chaque OF Assemblage. Par defaut, l'article parametre sur la societe.",
    )
    production_ids = fields.One2many(
        "mrp.production",
        "lot_fabrication_id",
        string="Ordres de fabrication",
    )
    production_debit_id = fields.Many2one(
        "mrp.production",
        string="OF Debit",
        copy=False,
        readonly=True,
    )
    picking_profile_ids = fields.Many2many(
        "stock.picking",
        string="Sortie profilés",
        compute="_compute_picking_matiere_ids",
        help="Le transfert qui amene les barres du lot au debit.",
    )
    picking_matiere_count = fields.Integer(
        string="Sorties matiere",
        compute="_compute_picking_matiere_ids",
    )
    picking_matiere_ids = fields.Many2many(
        "stock.picking",
        string="Sortie matiere",
        compute="_compute_picking_matiere_ids",
        help="Tous les transferts qui amenent la matiere du lot : les barres "
        "au debit, la quincaillerie et le vitrage aux casiers.",
    )

    production_quincaillerie_ids = fields.One2many(
        "mrp.production",
        "lot_fabrication_id",
        string="OF Quincaillerie",
        domain=[("lot_production_type", "=", "quincaillerie")],
    )
    production_assembly_ids = fields.One2many(
        "mrp.production",
        "lot_fabrication_id",
        string="OF Assemblage",
        domain=[("lot_production_type", "=", "assemblage")],
    )
    production_count = fields.Integer(
        string="Nb OF",
        compute="_compute_production_count",
    )
    # Les achats se retrouvent par les LIGNES et non par l'en-tete : un bon
    # de commande regroupe plusieurs lots des lors qu'ils partagent le
    # fournisseur et le projet, et un One2many sur l'en-tete n'en aurait
    # rattache qu'un seul.
    purchase_ids = fields.Many2many(
        "purchase.order",
        string="Achats du lot",
        compute="_compute_purchase_ids",
    )
    purchase_count = fields.Integer(
        string="Nb achats",
        compute="_compute_purchase_count",
    )

    # --- Divers -------------------------------------------------------------
    logikal_ref = fields.Char(
        string="Reference LOGIKAL",
        tracking=True,
        help="Reference du lot / de l'optimisation cote LOGIKAL, pour "
        "rapprochement.",
    )
    note = fields.Html(string="Notes")

    _name_company_uniq = models.Constraint(
        "unique(name, company_id)",
        "Le numéro de lot doit être unique par société.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("production_ids.move_raw_ids.move_orig_ids.picking_id")
    def _compute_picking_matiere_ids(self):
        """Les transferts qui alimentent les OF du lot.

        On remonte par le chainage des mouvements et non par picking_ids :
        en v19 ce champ ne rend pas les transferts de composants, ce qui nous
        avait deja coute une reprise de dates de fabrication.
        """
        for lot in self:
            tous = lot._pickings_de(lot.production_ids)
            lot.picking_profile_ids = lot._pickings_de(lot.production_debit_id)
            lot.picking_matiere_ids = tous
            lot.picking_matiere_count = len(tous)

    def _pickings_de(self, productions):
        """Transferts qui amenent les composants de ces ordres."""
        return productions.move_raw_ids.move_orig_ids.picking_id

    def _fusionner_sorties_matiere(self):
        """Ramene les prelevements du lot a un document par niveau.

        Le magasin doit avoir UN bon en main pour les barres et UN pour la
        quincaillerie, pas un par ordre de fabrication : trois reperes ne font
        pas trois fois le tour des allees.

        En v17 et v18, il suffisait d'un groupe d'approvisionnement commun,
        Odoo fondait alors les mouvements dans un meme transfert.
        procurement.group N'EXISTE PLUS en v19 — le demarrage de la base l'a
        dit sans detour, « unknown comodel_name » — et stock.move.group_id a
        disparu avec lui. On regroupe donc nous-memes, apres confirmation.

        Debit et assemblage restent separes : les barres vont au banc de
        debit, la quincaillerie au casier, et trois jours plus tot.

        Encadre : une erreur de regroupement ne doit pas empecher de generer
        les ordres. Au pire le magasin a plusieurs bons, ce qui est genant,
        pas bloquant.
        """
        self.ensure_one()
        garde = self.env["stock.picking"]
        try:
            for productions in (
                self.production_debit_id,
                self.production_ids - self.production_debit_id,
            ):
                garde |= self._fusionner(self._pickings_de(productions))
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Regroupement des sorties matiere du lot %s", self.name)
        return garde

    def _fusionner(self, pickings):
        """Fond des transferts de meme flux en un seul.

        Meme flux veut dire meme type d'operation et memes emplacements : on
        ne melange pas ce qui part de deux magasins, ni une reception avec une
        sortie. Le premier transfert recoit les mouvements des autres, qui
        sont supprimes une fois vides.
        """
        pickings = pickings.filtered(lambda p: p.state not in ("done", "cancel"))
        if len(pickings) < 2:
            return pickings

        par_flux = {}
        for picking in pickings:
            cle = (
                picking.picking_type_id.id,
                picking.location_id.id,
                picking.location_dest_id.id,
            )
            par_flux[cle] = par_flux.get(cle, self.env["stock.picking"]) | picking

        gardes = self.env["stock.picking"]
        for du_flux in par_flux.values():
            cible, autres = du_flux[0], du_flux[1:]
            gardes |= cible
            if not autres:
                continue
            autres.move_ids.write({"picking_id": cible.id})
            autres.invalidate_recordset(["move_ids"])
            vides = autres.filtered(lambda p: not p.move_ids)
            if vides:
                vides.unlink()
        return gardes

    @api.depends("line_ids.product_qty")
    def _compute_menuiserie_qty(self):
        for lot in self:
            lot.menuiserie_qty = sum(lot.line_ids.mapped("product_qty"))

    @api.depends("company_id")
    def _compute_max_menuiserie(self):
        for lot in self:
            lot.max_menuiserie = lot.company_id.fma_lot_max_menuiserie or 0

    @api.depends("line_ids.order_id")
    def _compute_sale_order_ids(self):
        for lot in self:
            orders = lot.line_ids.mapped("order_id")
            lot.sale_order_ids = orders
            lot.sale_order_count = len(orders)

    @api.depends("line_ids.order_id")
    def _compute_partner_id(self):
        for lot in self:
            orders = lot.line_ids.mapped("order_id")
            lot.partner_id = orders[:1].partner_id

    @api.depends("production_ids")
    def _compute_production_count(self):
        for lot in self:
            lot.production_count = len(lot.production_ids)

    @api.depends("purchase_ids")
    def _compute_purchase_ids(self):
        Ligne = self.env["purchase.order.line"]
        for lot in self:
            lignes = Ligne.search([("lot_fabrication_id", "=", lot.id)])
            lot.purchase_ids = lignes.order_id

    def _compute_purchase_count(self):
        for lot in self:
            lot.purchase_count = len(lot.purchase_ids)

    # ------------------------------------------------------------------
    # Contraintes
    # ------------------------------------------------------------------
    @api.constrains("line_ids", "company_id")
    def _check_max_menuiserie(self):
        for lot in self:
            maximum = lot.company_id.fma_lot_max_menuiserie
            if not maximum:
                continue
            total = sum(lot.line_ids.mapped("product_qty"))
            if float_compare(total, maximum, precision_digits=2) > 0:
                raise ValidationError(
                    _(
                        "Le lot %(lot)s contient %(qty)s menuiseries, or le "
                        "maximum autorise est de %(max)s.\n"
                        "Ce plafond est parametrable dans Fabrication > "
                        "Configuration > Parametres.",
                        lot=lot.name,
                        qty=total,
                        max=maximum,
                    )
                )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                company_id = vals.get("company_id") or self.env.company.id
                vals["name"] = self.env["ir.sequence"].with_company(
                    company_id
                ).next_by_code("fma.lot.fabrication") or _("Nouveau lot")
        return super().create(vals_list)

    def copy_data(self, default=None):
        default = dict(default or {})
        default.setdefault("name", "/")
        default.setdefault("state", "draft")
        return super().copy_data(default)

    def unlink(self):
        for lot in self:
            if lot.production_ids:
                raise UserError(
                    _(
                        "Impossible de supprimer le lot %s : des ordres de "
                        "fabrication lui sont rattaches. Annulez-le plutot.",
                        lot.name,
                    )
                )
        return super().unlink()

    # ------------------------------------------------------------------
    # Transitions d'etat
    # ------------------------------------------------------------------
    def action_confirm(self):
        for lot in self:
            if lot.state != "draft":
                continue
            if not lot.line_ids:
                raise UserError(
                    _("Le lot %s ne contient aucune menuiserie.", lot.name)
                )
            lot.state = "confirmed"
        return True

    def action_draft(self):
        for lot in self:
            if lot.production_ids.filtered(lambda p: p.state != "cancel"):
                raise UserError(
                    _(
                        "Le lot %s a des OF actifs : annulez-les avant de "
                        "repasser le lot en brouillon.",
                        lot.name,
                    )
                )
            lot.state = "draft"
        return True

    def action_cancel(self):
        for lot in self:
            productions = lot.production_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
            )
            if productions:
                productions.action_cancel()
            lot.state = "cancel"
        return True

    def _check_production_done(self):
        """Bascule le lot en ``done`` quand tous ses OF sont termines."""
        for lot in self:
            if lot.state not in ("progress", "confirmed"):
                continue
            productions = lot.production_ids.filtered(
                lambda p: p.state != "cancel"
            )
            if productions and all(p.state == "done" for p in productions):
                lot.state = "done"

    # ------------------------------------------------------------------
    # Generation des ordres de fabrication
    # ------------------------------------------------------------------
    def action_generate_orders(self):
        """Genere 1 OF Debit + N OF Assemblage pour chaque lot.

        Idempotent : les OF deja generes (et non annules) ne sont pas
        recrees, ce qui permet de relancer le bouton apres avoir ajoute une
        menuiserie au lot.
        """
        for lot in self:
            if lot.state == "cancel":
                raise UserError(
                    _("Le lot %s est annule.", lot.name)
                )
            if not lot.line_ids:
                raise UserError(
                    _("Le lot %s ne contient aucune menuiserie.", lot.name)
                )
            if lot.state == "draft":
                lot.action_confirm()

            productions = lot._generate_debit_order()
            productions |= lot._generate_assembly_orders()

            # Un OF cree reste en brouillon : il ne reserve rien, n'entre pas
            # au planning et n'apparait pas dans le flux atelier. Les OF
            # d'assemblage issus de l'appro natif, eux, arrivent confirmes —
            # le lot produisait donc des OF de debit invisibles a cote d'OF
            # d'assemblage actifs.
            a_confirmer = productions.filtered(lambda p: p.state == "draft")
            if a_confirmer:
                a_confirmer.action_confirm()

            # Les prelevements de composants n'existent qu'une fois les ordres
            # confirmes : c'est ici, et pas avant, qu'on peut les regrouper.
            lot._fusionner_sorties_matiere()

            lot._chainer_debit_et_assemblage()

            if lot.state == "confirmed":
                lot.state = "progress"
        return True

    def action_replanifier_lot(self):
        """Replanifie le lot depuis la date de fin de fabrication saisie.

        Le rétroplanning part normalement de la date de livraison. Ici, c'est
        l'ordonnanceur qui impose la fin : on garde la meme mecanique, mais
        bornee par sa date. Le debit suit, comme toujours une veille ouvree
        avant le premier assemblage.
        """
        self.ensure_one()
        if not self.date_fin_fab:
            raise UserError(
                _(
                    "Renseignez la date de fin de fabrication du lot %s avant "
                    "de replanifier.",
                    self.name,
                )
            )
        self._chainer_debit_et_assemblage(fin_forcee=self.date_fin_fab)
        return True

    def _chainer_debit_et_assemblage(self, security_days=6, fin_forcee=None):
        """Planifie le lot : l'assemblage depuis la livraison, le debit avant.

        Le retroplanning existe deja dans mrp_capacity_planning, mais il
        raisonne par OF isole : chaque assemblage remontait de son cote depuis
        la date de livraison, et le debit — cree apres la confirmation, sans
        ligne de commande — n'etait jamais planifie. On obtenait des
        assemblages dates avant le debit qui les alimente.

        On ne reecrit aucune regle metier : on enchaine les deux methodes
        existantes.

        1. Les assemblages remontent depuis la date de livraison, delai de
           securite deduit.
        2. Le debit doit etre fini la veille ouvree du premier assemblage.
        3. Il remonte a son tour depuis cette date de fin.

        Un echec de planification ne doit pas empecher les OF d'exister : ils
        sont deja crees quand on arrive ici. On trace dans le fil du lot.
        """
        self.ensure_one()
        debit = self.production_debit_id
        assemblages = self.production_assembly_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        if not debit or debit.state in ("done", "cancel") or not assemblages:
            return False

        # mrp_capacity_planning n'est pas une dependance de ce module.
        if not hasattr(debit, "compute_macro_schedule_from_sale"):
            return False

        try:
            for mo in assemblages:
                if fin_forcee:
                    # Fin imposee par l'ordonnanceur : meme retroplanning,
                    # autre borne. « Fin de fab » porte la date, le champ
                    # Studio la suit.
                    mo._set_date_fin_de_fab(
                        fields.Datetime.to_datetime(fin_forcee).date()
                    )
                    mo.compute_macro_schedule_from_date_fin()
                    continue
                cible, commande = mo._get_macro_target_date()
                if cible:
                    mo.compute_macro_schedule_from_sale(
                        commande or mo, security_days=security_days
                    )

            debuts = [d for d in assemblages.mapped("date_start") if d]
            if not debuts:
                return False

            premier = fields.Datetime.to_datetime(min(debuts)).date()
            poste = debit.workorder_ids[:1].workcenter_id
            veille = debit._previous_working_day(premier, poste)

            # « Fin de fab » du debit : la veille ouvree du premier
            # assemblage. Un seul geste pose les deux champs — le debit etait
            # jusqu'ici le seul OF ou « Fin de fab » restait vide, parce que
            # macro_forced_end n'etait ecrit que par la planification depuis
            # la vente.
            debit._set_date_fin_de_fab(veille)
            debit.compute_macro_schedule_from_date_fin()

            # 4. La quincaillerie et le vitrage sortent a J-3 ouvres avant le
            #    debit : c'est le temps qu'il faut au magasin pour garnir un
            #    casier par menuiserie. On date le bon de sortie lui-meme, la
            #    ou on datait l'OF de quincaillerie qui ne servait qu'a cela.
            #    Les profiles, eux, partent avec le debit.
            depart_kits = self._planifier_sortie_matiere(debit)
        except Exception as erreur:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception("Chainage debit/assemblage du lot %s", self.name)
            self.message_post(
                body=_(
                    "Planification du lot impossible : %(erreur)s<br/>"
                    "Les ordres de fabrication existent, seules leurs dates "
                    "restent a caler.",
                    erreur=erreur,
                )
            )
            return False

        if depart_kits:
            corps = _(
                "Planification : quincaillerie et vitrage a sortir le %(kits)s, "
                "debit termine le %(debit)s, assemblage a partir du "
                "%(assemblage)s.",
                kits=depart_kits,
                debit=veille,
                assemblage=min(debuts),
            )
        else:
            corps = _(
                "Planification : assemblage a partir du %(assemblage)s, "
                "debit termine le %(debit)s.",
                assemblage=min(debuts),
                debit=veille,
            )
        self.message_post(body=corps)
        return True

    #: Jours ouvres entre la sortie de la matiere et le debut du debit.
    JOURS_AVANCE_QUINCAILLERIE = 3

    def _planifier_sortie_matiere(self, debit):
        """Cale la sortie matiere a J-3 ouvres avant le debut du debit.

        Jours OUVRES, sur le calendrier de la societe : trois jours calendaires
        avant un lundi tomberaient un vendredi soir, et le magasin garnirait
        les casiers pendant le week-end.

        C'est la date du bon de sortie de la quincaillerie et du vitrage —
        celui que le groupe d'approvisionnement des assemblages a fondu en un
        seul document. La sortie des profiles, elle, n'est pas concernee :
        elle suit l'OF de debit, qui les consomme tous.

        Elle datait auparavant les OF de quincaillerie ; ils n'existent plus,
        mais les lots d'avant en ont encore, et ils sont dates de la meme
        facon pour ne pas rester en arriere.

        Renvoie la date retenue, ou False si rien n'a ete planifie.
        """
        self.ensure_one()
        if not debit.date_start:
            return False

        # Seulement la quincaillerie et le vitrage : les barres suivent l'OF
        # de debit, elles n'ont rien a faire en Pre-Fab trois jours plus tot.
        sorties = (self.picking_matiere_ids - self.picking_profile_ids).filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        kits = self.production_quincaillerie_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        if not sorties and not kits:
            return False

        depart = fields.Datetime.to_datetime(debit.date_start)
        calendrier = self.company_id.resource_calendar_id
        cible = False
        if calendrier:
            cible = calendrier.plan_days(
                -self.JOURS_AVANCE_QUINCAILLERIE, depart, compute_leaves=True
            )
        if not cible:
            # Sans calendrier exploitable, trois jours calendaires valent mieux
            # qu'une sortie non datee, qui ne serait jamais preparee.
            cible = depart - timedelta(days=self.JOURS_AVANCE_QUINCAILLERIE)

        if sorties:
            sorties.write({"scheduled_date": cible})
        if kits:
            kits.write({date_start_fname(self.env["mrp.production"]): cible})
        return fields.Datetime.to_datetime(cible).date()

    def _get_product_debit(self):
        """Article intermediaire produit par l'OF Debit."""
        self.ensure_one()
        if self.product_debit_id:
            return self.product_debit_id
        product = self.company_id.fma_lot_product_debit_id
        if not product:
            product = self.env.ref(
                "fma_lot_fabrication.product_ensemble_debite",
                raise_if_not_found=False,
            )
        if not product:
            raise UserError(
                _(
                    "Aucun article debite n'est parametre.\n"
                    "Renseignez-le sur le lot, ou dans Fabrication > "
                    "Configuration > Parametres > Lots de fabrication."
                )
            )
        self.product_debit_id = product
        return product

    def _get_picking_type(self):
        """Type d'operation de fabrication, sur l'atelier de la commande.

        Les OF d'assemblage viennent de l'appro natif, qui suit l'entrepot du
        devis. Ceux que le lot cree — le debit en tete — doivent partir du
        meme atelier, sinon le debit se fabrique a un endroit et l'assemblage
        a un autre : constate sur la staging, un OF de debit sur CBM face a
        des assemblages sur LRE.

        On cherche le type de l'entrepot de la commande, et on ne retombe sur
        le premier type de la societe que si le lot n'est rattache a aucune
        commande.
        """
        self.ensure_one()
        Type = self.env["stock.picking.type"]
        domaine = [
            ("code", "=", "mrp_operation"),
            ("company_id", "in", (self.company_id.id, False)),
        ]

        entrepot = self.sale_order_ids.warehouse_id[:1]
        if entrepot:
            picking_type = Type.search(
                domaine + [("warehouse_id", "=", entrepot.id)], limit=1
            )
            if picking_type:
                return picking_type

        picking_type = Type.search(domaine, limit=1)
        if not picking_type:
            raise UserError(
                _(
                    "Aucun type d'operation de fabrication n'est configure "
                    "pour la societe %s.",
                    self.company_id.display_name,
                )
            )
        return picking_type

    def _common_production_vals(self, picking_type):
        self.ensure_one()
        Production = self.env["mrp.production"]
        vals = {
            "company_id": self.company_id.id,
            "picking_type_id": picking_type.id,
            "origin": self.name,
            "lot_fabrication_id": self.id,
        }
        if self.date_planned_start:
            vals[date_start_fname(Production)] = self.date_planned_start

        # Le chantier de la commande, repris sur l'OF. Le champ existe depuis
        # Studio mais plus rien ne l'alimentait : les OF sortaient sans
        # projet, donc hors de tout suivi par chantier. Il est declare par le
        # module « custom », dont celui-ci ne depend pas — d'ou le controle.
        projet = self.sale_order_ids.project_id[:1]
        if projet and "x_studio_projet_de_la_vente" in Production._fields:
            vals["x_studio_projet_de_la_vente"] = projet.id

        return vals

    def _generate_debit_order(self):
        """Cree l'OF de debit du lot (1 par lot)."""
        self.ensure_one()
        if self.production_debit_id and self.production_debit_id.state != "cancel":
            return self.production_debit_id

        Production = self.env["mrp.production"]
        picking_type = self._get_picking_type()

        # Un OF ne produit qu'un article, or une seance de debit sort un
        # ensemble debite PAR REPERE : les barres sont mutualisees, les coupes
        # ne le sont pas. Le premier repere est l'article produit, les autres
        # suivent en sous-produits.
        #
        # Repli sur l'ensemble debite generique de la societe quand aucune
        # ligne ne porte le sien — lot saisi a la main, ou importe avant que
        # le lien n'existe.
        lignes = self.line_ids.filtered(
            lambda l: l.product_debit_id and not float_is_zero(
                l.product_qty, precision_digits=2)
        )
        if lignes:
            principale, autres = lignes[0], lignes[1:]
            product = principale.product_debit_id
            qty = principale.product_qty
        else:
            principale = autres = self.env["fma.lot.fabrication.line"]
            product = self._get_product_debit()
            qty = self.menuiserie_qty or 1.0

        vals = self._common_production_vals(picking_type)
        vals.update(
            {
                "product_id": product.id,
                "product_qty": qty,
                uom_fname(Production): product.uom_id.id,
                # Pas de nomenclature, volontairement : celle de l'ensemble
                # debite ne porte la gamme que d'UN repere, et pour un
                # exemplaire. Le temps de debit du lot est la somme de ses
                # reperes, et c'est nous qui la posons — cf. _operations_debit.
                "bom_id": False,
                "lot_production_type": "debit",
            }
        )
        production = Production.create(vals)
        # Encadre : les sous-produits et la gamme sont de l'information. Une
        # signature native qui aurait bouge d'une version a l'autre ne doit
        # pas empecher le lot de sortir son OF de debit.
        try:
            for ligne in autres:
                production._add_debit_byproduct(
                    ligne.product_debit_id, ligne.product_qty)
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Sous-produits de l'OF de debit du lot %s", self.name)
        # Les barres viennent du besoin matiere du lot et non d'une
        # nomenclature : elles varient d'un lot a l'autre.
        production._add_lot_material_moves(self.material_line_ids)
        try:
            self._poser_operations_debit(production)
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Gamme de debit du lot %s", self.name)

        self.production_debit_id = production
        self._verifier_debit_profiles(production)
        self.message_post(
            body=_("OF de debit %s genere.", production.display_name)
        )
        return production

    def _poser_operations_debit(self, production):
        """Le temps de debit du lot : la somme de ses reperes.

        L'import pose la gamme de debit — Debit et CU (banc) — sur la
        nomenclature de l'ensemble debite de chaque menuiserie, pour UN
        exemplaire. Un lot de trois reperes n'a pas de nomenclature qui les
        additionne, et l'OF de debit sortait donc sans aucune operation : sur
        le lot TR1 - lot1, les 531 minutes de debit n'etaient nulle part.

        On cumule ici par poste de charge et par operation, temps unitaire
        multiplie par la quantite de la ligne.
        """
        self.ensure_one()
        Bom = self.env["mrp.bom"]
        cumul = {}
        for ligne in self.line_ids:
            if not ligne.product_debit_id:
                continue
            bom = Bom._bom_find(
                ligne.product_debit_id,
                company_id=self.company_id.id,
                bom_type="normal",
            ).get(ligne.product_debit_id)
            for operation in bom.operation_ids if bom else []:
                cle = (operation.workcenter_id.id, operation.name)
                minutes, sequence = cumul.get(cle, (0.0, operation.sequence))
                cumul[cle] = (
                    minutes + (operation.time_cycle_manual or 0.0) * ligne.product_qty,
                    min(sequence, operation.sequence),
                )
        if not cumul:
            return self.env["mrp.workorder"]

        Workorder = self.env["mrp.workorder"]
        ordres = Workorder.browse()
        for (workcenter_id, nom), (minutes, sequence) in sorted(
            cumul.items(), key=lambda item: item[1][1]
        ):
            if not workcenter_id or minutes <= 0:
                continue
            ordres |= Workorder.create(
                {
                    "name": nom,
                    "production_id": production.id,
                    "workcenter_id": workcenter_id,
                    "duration_expected": minutes,
                    "sequence": sequence,
                }
            )
        return ordres

    def _verifier_debit_profiles(self, production):
        """L'OF de debit porte TOUS les profiles du lot, et rien d'autre.

        Les deux sens comptent.

        Rien d'autre : le besoin matiere vient du plan de coupe, donc de la
        table Profiles — par construction, des barres. Mais rien n'empeche
        d'ajouter une ligne a la main, et une quincaillerie consommee au debit
        ne serait plus disponible pour le casier.

        Tous : l'optimisation porte sur le lot entier, une barre sert
        plusieurs menuiseries. Un profile qui manque a l'OF de debit est un
        profile que personne ne sortira du stock — et la coupe s'arretera au
        banc, sans que rien ne l'ait annonce.

        On ne bloque ni dans un cas ni dans l'autre — un lot ne doit pas
        rester en rade pour un article mal classe — mais on l'ecrit sur le
        lot, la ou quelqu'un le lira.
        """
        Template = self.env["product.template"]
        consommes = production.move_raw_ids.product_id

        manquants = self.material_line_ids.product_id - consommes
        if manquants:
            self.message_post(
                body=_(
                    "OF de debit : %(nb)s profile(s) du plan de coupe n'y sont "
                    "pas consommes — %(liste)s. Personne ne les sortira du "
                    "stock.",
                    nb=len(manquants),
                    liste=", ".join(manquants.mapped("display_name")),
                )
            )

        if "fma_nature_logikal" not in Template._fields:
            return
        intrus = consommes.filtered(
            lambda p: p.fma_nature_logikal and p.fma_nature_logikal != "profile"
        )
        if not intrus:
            return
        self.message_post(
            body=_(
                "OF de debit : %(nb)s article(s) qui ne sont pas des profiles "
                "y sont consommes — %(liste)s. Le debit ne prend que des "
                "barres ; la quincaillerie et le vitrage vont au casier.",
                nb=len(intrus),
                liste=", ".join(intrus.mapped("display_name")),
            )
        )

    # L'OF de quincaillerie n'existe plus. Il ne produisait rien, ne portait
    # aucune operation, et son seul travail reel -- sortir la quincaillerie du
    # stock vers la Pre-Fab -- est celui du bon de sortie matiere du lot. Le
    # kit reste une nomenclature phantom, eclatee dans l'OF d'assemblage.
    #
    # Les champs production_quincaillerie_id(s) et le type « quincaillerie »
    # sont conserves : des lots d'avant en portent, et ils doivent rester
    # lisibles et planifiables.

    def _generate_assembly_orders(self):
        """Cree un OF d'assemblage par ligne de lot non encore servie."""
        self.ensure_one()
        Production = self.env["mrp.production"]
        picking_type = self._get_picking_type()
        product_debit = self._get_product_debit()
        created = Production.browse()

        for line in self.line_ids:
            if line.production_id and line.production_id.state != "cancel":
                continue
            if float_is_zero(line.product_qty, precision_digits=2):
                continue

            product = line.product_id
            if not product:
                continue

            bom = self.env["mrp.bom"]._bom_find(
                product, company_id=self.company_id.id, bom_type="normal"
            ).get(product)

            vals = self._common_production_vals(picking_type)
            vals.update(
                {
                    "product_id": product.id,
                    "product_qty": line.product_qty,
                    uom_fname(Production): (
                        line.sale_line_id.product_uom_id.id or product.uom_id.id
                    ),
                    "bom_id": bom.id if bom else False,
                    "lot_production_type": "assemblage",
                    "lot_line_id": line.id,
                    "lot_sale_line_id": line.sale_line_id.id,
                    "origin": "%s - %s" % (self.name, line.order_id.name or ""),
                }
            )
            production = Production.create(vals)
            # L'ensemble debite de CETTE menuiserie, et non celui du lot : les
            # coupes d'un repere ne montent pas un autre repere. L'ensemble
            # generique ne sert que de repli, pour un lot saisi a la main.
            production._add_debit_component(
                line.product_debit_id or product_debit, line.product_qty)
            line.production_id = production
            created |= production

        if created:
            self.message_post(
                body=_(
                    "%(count)s OF d'assemblage generes : %(names)s",
                    count=len(created),
                    names=", ".join(created.mapped("name")),
                )
            )
        return created

    # ------------------------------------------------------------------
    # Actions de navigation
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Besoin matiere, pour les editions du magasin
    # ------------------------------------------------------------------
    def _composants_unitaires(self, product):
        """Ce qu'il faut sortir du stock pour UNE menuiserie.

        On passe par ``explode`` et non par les lignes brutes : le kit
        quincaillerie est une nomenclature phantom, et c'est cette methode qui
        l'eclate en vraies pieces — celles que le magasin va chercher.

        L'ensemble debite est ecarte : il n'est pas sorti du stock, il est
        produit par l'OF de debit et rejoint le casier apres la scie.
        """
        self.ensure_one()
        Bom = self.env["mrp.bom"]
        bom = Bom._bom_find(
            product, company_id=self.company_id.id, bom_type="normal"
        ).get(product)
        if not bom:
            return []
        _boms, lignes = bom.explode(product, 1.0)
        composants = []
        for bom_line, donnees in lignes:
            article = bom_line.product_id
            if article.fma_semi_fini == "debit":
                continue
            composants.append(
                (article, donnees.get("qty", 0.0), bom_line.product_uom_id)
            )
        return composants

    def _besoin_matiere(self):
        """Le besoin du lot, dans l'ordre ou il quitte le stock.

        Renvoie ``(profiles, prefab, casiers)``.

        ``profiles`` : toutes les barres du lot. Elles partent d'un bloc au
        banc de debit, parce que l'optimisation porte sur le lot entier — une
        barre sert plusieurs menuiseries, on ne peut pas en sortir la moitie.

        ``prefab`` : la quincaillerie et le vitrage, agreges. Ils partent en
        Pre-Fab a J-3, et c'est ce document que le magasin suit pour garnir
        les casiers.

        ``casiers`` : le meme contenu, mais a l'unite — un casier par
        menuiserie, puisque c'est ainsi que le magasin travaille. Chaque
        casier porte son rang dans la ligne ; le jour ou les menuiseries
        seront suivies au numero de serie, ce rang deviendra ce numero.
        """
        self.ensure_one()

        def poste(article, qty, uom):
            return {"product": article, "uom": uom, "qty": qty}

        def trier(agrege):
            lignes = [poste(a, q, u) for (a, u), q in agrege.items()]
            lignes.sort(key=lambda d: (
                d["product"].default_code or d["product"].name or ""))
            return lignes

        # Les barres : besoin du lot, pas d'une menuiserie.
        barres = {}
        for materiel in self.material_line_ids:
            if not materiel.product_id or not materiel.product_qty:
                continue
            cle = (materiel.product_id, materiel.product_uom_id)
            barres[cle] = barres.get(cle, 0.0) + materiel.product_qty

        agrege = {}
        casiers = []
        for ligne in self.line_ids:
            if not ligne.product_id:
                continue
            contenu = self._composants_unitaires(ligne.product_id)
            for article, qty, uom in contenu:
                if not article or not qty:
                    continue
                cle = (article, uom)
                agrege[cle] = agrege.get(cle, 0.0) + qty * ligne.product_qty
            nombre = int(ligne.product_qty or 0)
            for rang in range(1, nombre + 1):
                casiers.append({
                    "ligne": ligne,
                    "rang": rang,
                    "sur": nombre,
                    "contenu": contenu,
                })

        return trier(barres), trier(agrege), casiers

    def action_view_sortie_matiere(self):
        """Le bon de sortie matiere du lot. Il ne devrait y en avoir qu'un."""
        self.ensure_one()
        pickings = self.picking_matiere_ids
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        action["domain"] = [("id", "in", pickings.ids)]
        if len(pickings) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = pickings.id
        return action

    def action_view_productions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mrp.mrp_production_action"
        )
        productions = self.production_ids
        action["domain"] = [("id", "in", productions.ids)]
        action["context"] = {
            "default_lot_fabrication_id": self.id,
            "search_default_lot_fabrication_id": self.id,
        }
        if len(productions) == 1:
            action["views"] = [
                (self.env.ref("mrp.mrp_production_form_view").id, "form")
            ]
            action["res_id"] = productions.id
        return action

    def action_view_purchases(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "purchase.purchase_rfq"
        )
        # Par les lignes : un bon de commande couvrant plusieurs lots doit
        # apparaitre sous chacun d'eux.
        action["domain"] = [("id", "in", self.purchase_ids.ids)]
        action["context"] = {}
        return action

    def action_view_sale_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sale.action_orders"
        )
        orders = self.sale_order_ids
        action["domain"] = [("id", "in", orders.ids)]
        if len(orders) == 1:
            action["views"] = [
                (self.env.ref("sale.view_order_form").id, "form")
            ]
            action["res_id"] = orders.id
        return action
