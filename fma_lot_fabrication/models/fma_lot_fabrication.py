# -*- coding: utf-8 -*-
"""Lot de fabrication FMA.

Un lot regroupe des lignes de devis (= des menuiseries) pour la production.
Il porte deux niveaux d'ordres de fabrication :

* 1 OF Debit  -> niveau lot, consomme les profiles, porte l'optimisation de
  coupe et sert de point d'entree aux approvisionnements ;
* N OF Assemblage -> 1 par menuiserie, c'est la que l'on declare la
  fabrication ligne par ligne.

Les deux niveaux sont relies par ``lot_fabrication_id`` (la reference de lot),
et non par le chainage parent/enfant natif d'Odoo.
"""
import logging

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
                if fin_forcee and "x_studio_date_de_fin" in mo._fields:
                    # Fin imposee par l'ordonnanceur : meme retroplanning,
                    # autre borne.
                    mo.x_studio_date_de_fin = fields.Datetime.to_datetime(
                        fin_forcee
                    ).date()
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

            if "x_studio_date_de_fin" not in debit._fields:
                return False
            debit.x_studio_date_de_fin = veille
            debit.compute_macro_schedule_from_date_fin()

            # macro_forced_end n'est ecrit que par la planification depuis la
            # vente. Le debit, lui, est planifie depuis une date de fin : le
            # champ restait vide, et « Fin de fab » n'affichait rien sur ces
            # OF. On y pose la fin reellement calculee.
            if "macro_forced_end" in debit._fields and debit.date_finished:
                debit.with_context(mail_notrack=True).macro_forced_end = (
                    debit.date_finished
                )
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

        self.message_post(
            body=_(
                "Planification : assemblage a partir du %(assemblage)s, "
                "debit termine le %(debit)s.",
                assemblage=min(debuts),
                debit=veille,
            )
        )
        return True

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
        product = self._get_product_debit()
        picking_type = self._get_picking_type()
        qty = self.menuiserie_qty or 1.0

        bom = self.env["mrp.bom"]._bom_find(
            product, company_id=self.company_id.id, bom_type="normal"
        ).get(product)

        vals = self._common_production_vals(picking_type)
        vals.update(
            {
                "product_id": product.id,
                "product_qty": qty,
                uom_fname(Production): product.uom_id.id,
                "bom_id": bom.id if bom else False,
                "lot_production_type": "debit",
            }
        )
        production = Production.create(vals)
        # L'article debite peut porter une nomenclature *sans composant*, qui
        # ne sert qu'a porter la gamme de debit : les barres, elles, varient
        # d'un lot a l'autre et viennent du besoin matiere. Il faut donc les
        # ajouter aussi dans ce cas.
        if not bom or not bom.bom_line_ids:
            production._add_lot_material_moves(self.material_line_ids)

        self.production_debit_id = production
        self.message_post(
            body=_("OF de debit %s genere.", production.display_name)
        )
        return production

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
            production._add_debit_component(product_debit, line.product_qty)
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
