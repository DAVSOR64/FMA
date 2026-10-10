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

* la quincaillerie et le vitrage partent en Pre-Fab quelques jours ouvres
  avant le debit (reglage de societe), le temps
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

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)

#: Ce qui ne se regroupe PAS par lot. Le REMPLISSAGE — vitrages ET
#: panneaux, « All / Remplissage » — se commande pour la commande client et
#: non pour le lot : il arrive deja decoupe a la menuiserie, et sa
#: destination (chariot pour l'atelier, palette pour le chantier) commande
#: son bon bien avant le lot.
#:
#: Le test porte sur le CLASSEMENT de l'article et non sur sa famille
#: d'appro : tous les articles de FMA n'ont pas de famille renseignee, mais
#: tous ont une categorie, et _fma_classe_matiere remonte l'une puis
#: l'autre. C'est deja la regle du besoin matiere — on n'en invente pas une
#: seconde.
CLASSES_HORS_LOT = ("remplissage",)


#: Etiquette commerciale de la commande -> code de l'entrepot qui fabrique.
#:
#: C'est la regle metier, et elle est directe : une affaire etiquetee FMA se
#: fabrique a La Regrippiere, une affaire F2M a La Remaudiere. Rien ne se
#: deduit de l'article ni de l'adresse — on l'a tente, et un OF de debit est
#: parti a La Chapelle pendant que l'assemblage se faisait a La Regrippiere.
ENTREPOT_PAR_ETIQUETTE = {
    "FMA": "LRE",
    "F2M": "REM",
}

#: L'atelier que l'etiquette designe, pour les lots qui n'en portent pas.
#: Meme regle que l'entrepot, et c'est voulu : « FMA » fabrique a La
#: Regrippiere, « F2M » a La Remaudiere. Le rapprochement se fait sur le
#: CODE de l'atelier, et sur son nom a defaut — un referentiel sans code
#: renseigne ne doit pas priver les ordres de leur atelier.
#: Les accents d'un referentiel saisi a la main ne doivent pas faire rater
#: un rapprochement : « Regrippiere » et « Regrippière » se valent.
_ACCENTS = str.maketrans("ÀÁÂÃÄÅÈÉÊËÌÍÎÏÒÓÔÕÖÙÚÛÜÇàáâãäåèéêëìíîïòóôõöùúûüç",
                         "AAAAAAEEEEIIIIOOOOOUUUUCaaaaaaeeeeiiiiooooouuuuc")


def _sans_accent(texte):
    return (texte or "").translate(_ACCENTS)


NOM_ATELIER_PAR_ETIQUETTE = {
    "FMA": ("LRE", "REGRIPPIERE"),
    "F2M": ("REM", "REMAUDIERE"),
}


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

    # La date de DEBUT DU DEBIT, des qu'il existe. C'est le moment ou le lot
    # entre reellement en fabrication : le debit est le premier travail, tout
    # le reste en decoule. Avant generation, la valeur saisie a la mise en lot
    # sert d'amorce aux OF crees.
    #
    # Calculee et stockee, comme « Fin de fabrication » juste au-dessus : les
    # deux suivent alors le debit sans que personne ait a les recopier. Une
    # replanification qui deplace le debit les deplace avec lui.
    date_planned_start = fields.Datetime(
        string="Date planifiee",
        compute="_compute_date_planned_start",
        store=True,
        readonly=False,
        default=fields.Datetime.now,
        tracking=True,
        help="Date de debut de l'OF de debit. Avant generation des ordres, "
        "la date saisie a la mise en lot.",
    )

    @api.depends(
        "production_ids.date_start",
        "production_ids.lot_production_type",
        "production_ids.state",
    )
    def _compute_date_planned_start(self):
        sans_debit = self.browse()
        for lot in self:
            debit = lot.production_ids.filtered(
                lambda p: p.lot_production_type == "debit"
                and p.state != "cancel"
            )[:1]
            if debit and debit.date_start:
                lot.date_planned_start = debit.date_start
            else:
                sans_debit |= lot
        if not sans_debit:
            return

        # Pas encore de debit : on garde la date saisie a la mise en lot.
        # Elle amorce les ordres a leur creation, et la perdre ici aurait ete
        # facile — ce calcul se declenche des la confirmation de la commande,
        # qui rattache les assemblages bien avant que le debit existe.
        #
        # La valeur est relue en base et non sur l'enregistrement : le champ
        # est en cours de calcul, le lire par l'ORM relancerait ce meme calcul.
        enregistres = [i for i in sans_debit.ids if isinstance(i, int)]
        stocke = {}
        if enregistres:
            self.env.cr.execute(
                "SELECT id, date_planned_start FROM fma_lot_fabrication"
                " WHERE id = ANY(%s)", (enregistres,))
            stocke = dict(self.env.cr.fetchall())
        for lot in sans_debit:
            lot.date_planned_start = (
                stocke.get(lot.id) or lot.create_date or fields.Datetime.now()
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

    @api.depends("name", "line_ids.order_id.name")
    def _compute_display_name(self):
        """« A26-00-00002 - Lot 3 » : la commande, puis le rang du lot dedans.

        Ni LOT-2026-0025, un numero de sequence global qui ne situe rien, ni
        « TR1 - lot3 », le nom de la phase LOGIKAL, qui ne parle qu'au
        chiffreur et change de forme d'un chiffrage a l'autre.

        Le rang est la position du lot parmi ceux de la meme commande, dans
        l'ordre ou ils ont ete crees — donc dans l'ordre des imports. C'est
        ainsi que l'atelier les designe : le lot 1, le lot 2, le lot 3.

        La reference LOGIKAL ne disparait pas, elle reste dans son champ, ou
        le chiffreur la retrouve pour rapprocher avec le pricer.
        """
        # Un seul search pour tout le lot d'enregistrements : ce calcul se
        # declenche sur chaque liste et chaque many2one, une requete par ligne
        # se paierait immediatement.
        commandes = {
            lot.line_ids.order_id[:1].id
            for lot in self if lot.line_ids.order_id
        }
        rangs = {}
        if commandes:
            compteur = {}
            for frere in self.sudo().search(
                    [("line_ids.order_id", "in", list(commandes))],
                    order="id"):
                cle = frere.line_ids.order_id[:1].id
                compteur[cle] = compteur.get(cle, 0) + 1
                rangs[frere.id] = compteur[cle]

        for lot in self:
            commande = lot.line_ids.order_id[:1]
            rang = rangs.get(lot.id)
            if commande and rang:
                lot.display_name = "%s - Lot %s" % (commande.name, rang)
            elif commande:
                # Lot pas encore enregistre : aucun rang ne peut etre etabli.
                lot.display_name = "%s - %s" % (commande.name, lot.name)
            else:
                lot.display_name = lot.name


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

    #: Nombre de remontees successives depuis les composants des OF vers les
    #: achats. La chaine reelle en compte quatre — composant, collecte des
    #: composants, reception, ligne d'achat — et un OF intermediaire en ajoute
    #: autant. Six bornent largement, et bornent surtout une chaine qu'un
    #: parametrage pourrait refermer sur elle-meme.
    PROFONDEUR_ACHAT = 6

    def _lignes_achat_du_lot(self):
        """Les lignes d'achat nees des besoins de ce lot.

        On ne se fie pas au champ lot_fabrication_id de la ligne d'achat. Il
        est calcule ET STOCKE a la naissance de la ligne — or a cet instant
        l'OF d'assemblage n'appartient encore a aucun lot : l'appro natif cree
        ses achats PENDANT la confirmation de la commande, et le rattachement
        au lot n'a lieu qu'apres. Le champ reste vide pour toujours.

        On repart donc des mouvements. Et il faut les remonter jusqu'au bout :
        en fabrication a deux etapes, l'achat n'alimente pas directement l'OF.
        La chaine est

            ligne d'achat -> reception (fournisseur -> LRE/STOCK)
                          -> collecte des composants (STOCK -> Pre-fab)
                          -> composant de l'OF

        Ma premiere version ne franchissait qu'un maillon : elle tombait sur
        la collecte des composants, qui ne porte aucune ligne d'achat, et
        repartait aussitot vers les OF. Elle ne trouvait donc que les achats
        nes de l'OF de debit, jamais ceux de la quincaillerie.

        On remonte maintenant sans compter les maillons : a chaque tour on
        releve les lignes d'achat des mouvements vus, puis on passe a ce qui
        les alimente — et aux composants des OF intermediaires, le kit
        quincaillerie notamment.
        """
        self.ensure_one()
        Ligne = self.env["purchase.order.line"]
        lignes = Ligne.search([("lot_fabrication_id", "=", self.id)])

        a_voir = self.production_ids.move_raw_ids
        vus_moves, vus_ordres = set(), set()
        for _niveau in range(self.PROFONDEUR_ACHAT):
            a_voir = a_voir.filtered(lambda m: m.id not in vus_moves)
            if not a_voir:
                break
            vus_moves |= set(a_voir.ids)
            if "purchase_line_id" in a_voir._fields:
                lignes |= a_voir.mapped("purchase_line_id")
            amont = a_voir.move_orig_ids
            ordres = amont.production_id.filtered(
                lambda p: p.id not in vus_ordres)
            vus_ordres |= set(ordres.ids)
            a_voir = amont | ordres.move_raw_ids

        # DEUXIEME CHEMIN, ET LE SEUL QUI MARCHE AVANT CONFIRMATION. Un bon
        # en brouillon n'a aucun mouvement de reception : le chainage
        # ci-dessus ne peut donc rien trouver, et c'est l'etat dans lequel
        # vivent les achats tant que l'acheteur ne les a pas envoyes. Le
        # lien, a ce stade, est « move_dest_ids » pose par
        # l'approvisionnement SUR LA LIGNE D'ACHAT : les mouvements que
        # cette ligne est censee servir.
        #
        # Constate sur A26-10-07853 : quatre quincailleries TECHNAL et les
        # deux panneaux SIPO restaient sur un bon « de commande » que plus
        # aucun lot ne revendiquait, alors qu'ils servent chacun un repere
        # precis.
        if "move_dest_ids" in Ligne._fields:
            # Les mouvements du lot, a tous les niveaux : composants des
            # ordres, et transferts de matiere. En fabrication a deux etapes
            # l'appro vise la COLLECTE, pas le composant de l'ordre.
            cibles = self.production_ids.move_raw_ids | self.picking_matiere_ids.move_ids
            if cibles:
                lignes |= Ligne.search([("move_dest_ids", "in", cibles.ids)])

        # Troisieme filet, independant du chainage : l'ORIGINE. Odoo y recopie
        # le nom du document qui a declenche le besoin — le lot, l'ordre de
        # fabrication, la commande. Le chainage des mouvements m'a menti trois
        # fois de suite ; un rapprochement par le texte ne depend d'aucune
        # topologie et attrape ce qu'il laisse passer.
        # PAS LE NOM DE LA COMMANDE DE VENTE. Deux lots d'une meme affaire le
        # partagent : ce nom ne peut, par construction, distinguer personne.
        # Chaque lot ramassait donc TOUTES les lignes d'achat de l'affaire.
        # Constate sur A26-10-07853 : seize lignes revendiquees par les deux
        # lots, dont les panneaux du repere 001 et ceux du repere 002, qui
        # appartiennent pourtant chacun a un lot et un seul.
        #
        # Ne restent que des noms propres au lot : le sien et ceux de ses
        # ordres de fabrication.
        noms = [self.name]
        noms += self.production_ids.mapped("name")
        noms = [n for n in noms if n]
        if noms:
            Achat = self.env["purchase.order"]
            candidats = Achat.search(
                [
                    ("state", "in", ("draft", "sent")),
                    ("company_id", "=", self.company_id.id),
                    ("origin", "!=", False),
                ]
            )
            proches = candidats.filtered(
                lambda a: any(nom in (a.origin or "") for nom in noms)
            )
            lignes |= proches.order_line
        return lignes

    def _rattacher_achats(self):
        """Pose le lot sur les lignes d'achat qui le concernent.

        Repare ce que le calcul stocke ne pouvait pas voir a la naissance de
        la ligne. Une affectation manuelle deja faite n'est pas touchee.
        """
        self.ensure_one()
        lignes = self._lignes_achat_du_lot().filtered(
            lambda l: not l.lot_fabrication_id)
        if lignes:
            lignes.write({"lot_fabrication_id": self.id})
        return lignes

    def _rattacher_bon_au_lot(self, achat):
        """Pose sur le bon le lot, la commande et le projet de l'affaire.

        UN BON NE DE L'APPROVISIONNEMENT NE PORTE RIEN DE TOUT CELA. Les
        champs de rattachement FMA — commande client, projet — sont poses a
        la confirmation du devis par du code qui ne s'execute pas quand Odoo
        cree un bon pour un besoin d'OF, ni quand nous en ouvrons un pour un
        lot. Les achats du deuxieme lot d'une affaire sortaient donc des
        ecrans de suivi : ils existaient, mais rattaches a rien.

        On les renseigne depuis le lot, qui connait sa commande. Une valeur
        deja posee n'est pas touchee : elle peut venir d'une affectation
        manuelle de l'acheteur sur une affaire a tranches.
        """
        self.ensure_one()
        vals = {}
        if achat.lot_fabrication_id != self:
            vals["lot_fabrication_id"] = self.id

        commande = self.sale_order_ids.sorted("id")[:1]
        if commande:
            if "fma_sale_order_id" in achat._fields and not achat.fma_sale_order_id:
                vals["fma_sale_order_id"] = commande.id
            projet = (
                commande.x_studio_projet_de_la_vente
                if "x_studio_projet_de_la_vente" in commande._fields
                else False
            )
            if (projet and "x_studio_projet_du_so" in achat._fields
                    and not achat.x_studio_projet_du_so):
                vals["x_studio_projet_du_so"] = projet.id
        if vals:
            achat.write(vals)

    def _bon_du_lot(self, lignes):
        """Le bon qui doit porter ces lignes — un bon PAR LOT.

        Le metier veut une commande d'achat par lot et par fournisseur. Or le
        bon ne de la confirmation du devis couvre toute la commande client :
        une affaire de trois lots le partage. Il ne peut donc pas servir de
        bon d'accueil tel quel.

        On retient le bon qui ne porte QUE des lignes de ce lot — il y en a
        un des que le lot a deja ete regroupe une fois. A defaut on en ouvre
        un neuf, et le bon partage se vide de la part qui revient au lot.

        Le plus ancien d'abord : c'est celui ne de la confirmation, il porte
        deja la reference du devis dans son origine.
        """
        self.ensure_one()
        candidats = lignes.order_id.filtered(
            lambda a: a.state in ("draft", "sent")).sorted("id")
        for achat in candidats:
            # « Les lignes de ce bon sont toutes a nous » : rien a scinder,
            # ce bon est deja le bon du lot pour ce fournisseur.
            reelles = achat.order_line.filtered(
                lambda l: not l.display_type and l.product_id)
            if reelles and not (reelles - lignes):
                return achat
        return self.env["purchase.order"].create(
            candidats[0]._fma_vals_bon_lot())

    def _fusionner_achats_du_lot(self):
        """Un bon de commande par lot ET par fournisseur.

        C'est la regle du metier, et elle n'est pas celle d'Odoo : l'appro
        natif groupe par fournisseur et par type d'operation, sans rien
        savoir des lots. Un lot se retrouvait donc eclate sur plusieurs bons
        — la quincaillerie nee de la confirmation du devis, les profiles nes
        de la generation de l'OF de debit — et, a l'inverse, un meme bon
        portait les lots d'une affaire entiere.

        Les deux travers se corrigent du meme geste, en raisonnant LIGNE A
        LIGNE plutot que bon a bon : on rassemble les lignes du lot par
        fournisseur, puis on les pose sur un bon qui n'appartient qu'a ce
        lot. Celui qui est deja dans ce cas sert d'accueil ; sinon on en
        ouvre un, et le bon partage se vide de la part qui revient au lot.

        LE VITRAGE EST HORS DE CE JEU. Il s'achete pour la commande client,
        pas pour le lot : il arrive deja decoupe a la menuiserie, et sa
        destination — chariot pour l'atelier, palette pour le chantier —
        commande son bon bien avant le lot. Le melanger aux profiles
        obligerait a le rouvrir a chaque nouveau lot.

        Ne sont rapproches que les bons de MEME fournisseur, meme societe,
        meme devise et meme type d'operation : on ne melange pas deux
        receptions ni deux monnaies. Et seulement les bons en brouillon : une
        fois envoye au fournisseur, un bon ne se recompose pas dans le dos de
        l'acheteur.

        Encadre : au pire le fournisseur recoit deux bons, ce qui est genant,
        pas bloquant.
        """
        self.ensure_one()
        Achat = self.env["purchase.order"]
        try:
            classes = {}

            def dans_le_lot(ligne):
                if ligne.display_type or not ligne.product_id:
                    return False
                if ligne.order_id.state not in ("draft", "sent"):
                    return False
                article = ligne.product_id
                if article.id not in classes:
                    classes[article.id] = article._fma_classe_matiere()
                return classes[article.id] not in CLASSES_HORS_LOT

            lignes = self._lignes_achat_du_lot().filtered(dans_le_lot)
            commandes = lignes.order_id
            if not lignes:
                self._rendre_compte_achats(lignes, commandes, Achat)
                return commandes

            par_flux = {}
            for ligne in lignes:
                achat = ligne.order_id
                cle = (
                    achat.partner_id.id,
                    achat.company_id.id,
                    achat.currency_id.id,
                    achat.picking_type_id.id,
                )
                par_flux.setdefault(cle, self.env["purchase.order.line"])
                par_flux[cle] |= ligne

            gardes = Achat
            for du_flux in par_flux.values():
                cible = self._bon_du_lot(du_flux)
                gardes |= cible
                a_deplacer = du_flux - cible.order_line
                anciens = a_deplacer.order_id
                origines = [cible.origin or ""] + [
                    a.origin or "" for a in anciens]
                if a_deplacer:
                    a_deplacer.write({"order_id": cible.id})
                    anciens.invalidate_recordset(["order_line"])
                vides = anciens.filtered(
                    lambda a: not a.order_line and a.state in ("draft", "sent"))
                if vides:
                    # ANNULER AVANT DE SUPPRIMER. Odoo refuse de supprimer un
                    # bon d'achat qui n'est pas annule — « In order to delete
                    # a purchase order, you must cancel it first ». Le
                    # unlink() direct levait une UserError, avalee par le
                    # except de cette methode : les lignes etaient bien
                    # deplacees, mais les bons vides restaient en brouillon.
                    vides.button_cancel()
                    vides.unlink()
                # L'origine du bon absorbe garde sa trace : sans cela, on
                # perdrait le lien vers l'OF de debit.
                retenues = []
                for origine in origines:
                    for jeton in (origine or "").split(", "):
                        jeton = jeton.strip()
                        if jeton and jeton not in retenues:
                            retenues.append(jeton)
                if retenues:
                    cible.origin = ", ".join(retenues)
                self._rattacher_bon_au_lot(cible)
            self._rendre_compte_achats(lignes, commandes, gardes)
            return gardes
        except Exception as erreur:  # noqa: BLE001 — trace, pas de blocage
            # DIRE L'ECHEC SUR LE LOT, pas seulement dans le log serveur. Ce
            # except a masque pendant des semaines un unlink() impossible : le
            # regroupement s'arretait au milieu et l'ecran n'en montrait rien.
            # Un rapprochement a moitie fait se voit — deux bons pour un
            # fournisseur — mais sa cause, elle, ne se lisait nulle part.
            _logger.exception(
                "Regroupement des achats du lot %s", self.name)
            self.message_post(body=_(
                "Regroupement des achats interrompu : %(erreur)s<br/>"
                "Les bons d'achat existent, seul leur rapprochement reste a "
                "faire — a verifier avant d'envoyer au fournisseur.",
                erreur=erreur,
            ))
            return Achat

    def _rendre_compte_achats(self, lignes, avant, apres):
        """Ecrit sur le lot ce que le regroupement a trouve, et ce qu'il a fait.

        Ce rapprochement a echoue trois fois de suite sans rien dire, et
        chaque essai a coute un aller-retour. Il rend desormais compte : de
        quoi juger sans ouvrir de shell.

        On n'ecrit que lorsqu'il y a matiere a lire — rien trouve, ou plusieurs
        bons qui subsistent pour un meme fournisseur.
        """
        self.ensure_one()
        restants = {}
        for achat in apres:
            restants.setdefault(achat.partner_id, []).append(achat.name)
        doublons = {p: n for p, n in restants.items() if len(n) > 1}
        if lignes and not doublons and len(avant) == len(apres):
            return
        detail = [_(
            "Achats du lot : %(lignes)s ligne(s) trouvee(s), %(avant)s bon(s) "
            "avant regroupement, %(apres)s apres.",
            lignes=len(lignes), avant=len(avant), apres=len(apres),
        )]
        if not lignes:
            detail.append(_(
                "<br/>Aucune ligne d'achat rattachee au lot : ni par le "
                "chainage des mouvements, ni par l'origine des bons."
            ))
        for partner, noms in doublons.items():
            detail.append(_(
                "<br/>%(frs)s garde %(nb)s bons : %(noms)s.",
                frs=partner.display_name, nb=len(noms), noms=", ".join(noms),
            ))
        self.message_post(body="".join(detail))

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

    def _sortir_les_debits_du_transfert(self):
        """Retire du transfert matiere les ensembles debites.

        Ils n'ont rien a y faire : le debit les produit DIRECTEMENT en
        Pre-Fab, la ou l'assemblage vient les chercher. Les laisser dans le
        bon de sortie revenait a demander au magasin de les prelever en stock
        six jours avant que le debit existe — la ligne sortait « Pas
        disponible », et l'assemblage creusait du negatif en Pre-Fab pendant
        que la quantite produite dormait au stock.

        C'est l'autre moitie du correctif, et elle est indissociable de la
        premiere : deposer en Pre-Fab sans retirer le prelevement laisserait
        un mouvement qui ne peut pas se servir.

        Les mouvements sont annules plutot que supprimes : un mouvement
        confirme ne se supprime pas sans laisser Odoo incoherent, et une
        ligne annulee se voit — on saura pourquoi elle n'est pas la.

        Encadre : au pire le transfert garde une ligne de trop, ce qui est
        genant et visible. Une exception empecherait de generer les ordres.
        """
        self.ensure_one()
        try:
            transferts = self.picking_matiere_ids - self.picking_profile_ids
            mouvements = transferts.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
                and m.product_id.fma_semi_fini == "debit"
            )
            if not mouvements:
                return self.env["stock.move"]
            noms = mouvements.mapped("product_id.default_code")
            mouvements._action_cancel()
            self.message_post(body=_(
                "Sortie matière : %(nb)s ensemble(s) débité(s) retiré(s) du "
                "bon — %(noms)s. Le débit les produit directement en "
                "Pré-Fab, il n'y a rien à prélever en stock.",
                nb=len(mouvements), noms=", ".join(n for n in noms if n),
            ))
            return mouvements
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Retrait des ensembles debites du lot %s", self.name)
            return self.env["stock.move"]

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

    def _apres_ajout_composant(self, mouvements):
        """Range dans le lot ce qu'un composant ajoute sur un ordre a cree.

        Ajouter un composant sur un ordre confirme lance l'approvisionnement
        standard : un prelevement Stock -> Pre-Fab, et un achat si l'article
        est a la commande. Odoo rattache ce prelevement au bon de sortie de
        l'ordre tant qu'il est ouvert et pas imprime ; sinon il en ouvre un
        autre, un par ordre. On refait donc ici ce que « Generer les OF » fait
        une fois pour toutes : UN bon ouvert par niveau, et les achats
        rattaches au lot.

        Un bon deja valide n'est pas rouvert : le complement part sur un
        nouveau bon, que le lot retrouve par le chainage des mouvements.

        Encadre, avec point de reprise : ranger est un confort, et une erreur
        ici ne doit ni empecher d'ajouter un composant ni laisser la
        transaction dans un etat inutilisable.
        """
        self.ensure_one()
        mouvements = mouvements.exists()
        try:
            with self.env.cr.savepoint():
                self._fusionner_sorties_matiere()
                self._rattacher_achats()
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Rangement apres ajout de composant sur le lot %s", self.name)
        if not mouvements:
            return
        bons = mouvements.move_orig_ids.picking_id
        # La liste ne change que si une quincaillerie — ou un article que rien
        # ne classe, et qu'elle garde par prudence — vient d'etre ajoutee.
        liste = any(
            article._fma_classe_matiere() in ("quincaillerie", False)
            for article in mouvements.product_id
        )
        self.message_post(
            body=_(
                "Composant(s) ajoute(s) sur %(ordres)s : %(articles)s. "
                "%(suite)s%(liste)s",
                ordres=", ".join(
                    mouvements.raw_material_production_id.mapped("name")),
                articles=", ".join(
                    "%s × %s" % (m.product_id.display_name, m.product_uom_qty)
                    for m in mouvements),
                suite=(
                    _("Sortie matiere : %s.", ", ".join(bons.mapped("name")))
                    if bons else
                    _("Aucun prelevement cree : a prendre sur la Pre-Fab.")
                ),
                liste=(
                    _(" La liste de quincaillerie est a reimprimer si elle "
                      "l'a deja ete.") if liste else ""
                ),
            )
        )

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

            deja = lot.production_ids
            productions = lot._generate_debit_order()
            debit_cree = productions - deja
            productions |= lot._generate_assembly_orders()

            # Un OF cree reste en brouillon : il ne reserve rien, n'entre pas
            # au planning et n'apparait pas dans le flux atelier. Les OF
            # d'assemblage issus de l'appro natif, eux, arrivent confirmes —
            # le lot produisait donc des OF de debit invisibles a cote d'OF
            # d'assemblage actifs.
            a_confirmer = productions.filtered(lambda p: p.state == "draft")
            if a_confirmer:
                a_confirmer.action_confirm()

            # Apres la confirmation seulement : c'est la que procure_method
            # est arrete, et donc qu'on sait si les achats partiront.
            debit = lot.production_ids.filtered(
                lambda p: p.lot_production_type == "debit" and p.state != "cancel"
            )[:1]
            if debit:
                lot._verifier_appro_debit(debit)
            # Les sous-produits de l'OF de debit qu'on vient de creer : une
            # reconstruction des produits finis, tant qu'il etait en
            # brouillon, a pu les emporter. Confirme, il ne les perd plus.
            if debit_cree:
                lot._poser_sous_produits_debit(debit_cree)

            # Prelevements et achats n'existent qu'une fois les ordres
            # confirmes : c'est ici, et pas avant, qu'on peut les regrouper.
            lot._fusionner_sorties_matiere()
            lot._sortir_les_debits_du_transfert()
            lot._rattacher_achats()
            lot._fusionner_achats_du_lot()

            # Apres la confirmation, avant le chainage : la scission cree des
            # ordres que la planification doit ensuite dater.
            lot._scinder_assemblages_par_serie()

            lot._chainer_debit_et_assemblage()

            if lot.state == "confirmed":
                lot.state = "progress"
        return True

    def _numeros_de_serie(self, product, nombre):
        """Cree ``nombre`` numeros « <reference article>-001 » pour l'article.

        La reference de l'article porte deja l'affaire et la position —
        « A26-00-00002_E-MEXT-C1 » —, le rang suffit a designer l'exemplaire.
        Un numero de sequence generique aurait demande de remonter a l'article
        pour savoir de quelle menuiserie on parle.

        Le rang repart du nombre d'exemplaires deja crees pour cet article, et
        les noms deja pris sont sautes : une meme ligne de devis peut etre
        lotie en plusieurs fois, et deux lots ne doivent pas se disputer le
        numero 001.
        """
        self.ensure_one()
        Lot = self.env["stock.lot"].sudo()
        base = (product.default_code or product.name or "SN").strip()
        existants = set(
            Lot.search([("product_id", "=", product.id)]).mapped("name"))
        noms, rang = [], len(existants)
        while len(noms) < nombre:
            rang += 1
            nom = "%s-%03d" % (base, rang)
            if nom not in existants:
                noms.append(nom)
        return Lot.create([
            {
                "name": nom,
                "product_id": product.id,
                "company_id": self.company_id.id,
            }
            for nom in noms
        ])

    def _scinder_assemblages_par_serie(self):
        """Un ordre par menuiserie, chacun portant son numero de serie.

        Sans cela, une ligne de 2 menuiseries donne un ordre de 2, et
        l'operateur doit penser a « Preparer l'OF » plutot qu'a « Appliquer »
        dans l'ecran des numeros de serie — le bouton a eviter etant le bleu.
        Un oubli et les deux menuiseries se declarent d'un coup, sans identite
        propre.

        Surtout, le magasin prepare les casiers AVANT que l'atelier produise.
        Un casier vaut une menuiserie ; si le numero n'existe qu'au moment de
        la declaration, le magasin travaille sur des rangs anonymes et rien ne
        rapproche le casier 2 du numero 2. En posant les numeros ici, le
        rapprochement est acquis de bout en bout, du casier au SAV.

        On emploie la scission native, celle-la meme que le wizard appelle.
        Les champs du lot sont en copy=False, mais _get_backorder_mo_vals les
        reporte : les ordres issus de la scission restent dans le lot.
        """
        self.ensure_one()
        candidats = self.production_assembly_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
            and p.product_id.tracking == "serial"
            and not p.lot_producing_ids
        )
        obtenus = self.env["mrp.production"]
        for mo in candidats:
            nombre = int(round(mo.product_qty or 0))
            if nombre < 1:
                continue
            numeros = self._numeros_de_serie(mo.product_id, nombre)
            if nombre == 1:
                # Rien a scinder : l'ordre porte deja une seule menuiserie, il
                # lui manquait juste son numero.
                mo.lot_producing_ids = [Command.link(numeros[0].id)]
                obtenus |= mo
                continue
            try:
                ordres = mo._split_productions({mo: [1] * nombre})
            except Exception:  # noqa: BLE001 — trace, pas de blocage
                _logger.exception(
                    "Scission par numero de serie de %s", mo.display_name)
                numeros.unlink()
                continue
            for ordre, numero in zip(ordres, numeros):
                ordre.lot_producing_ids = [Command.link(numero.id)]
            obtenus |= ordres

        if obtenus:
            self.message_post(
                body=_(
                    "%(nb)s menuiserie(s) numerotee(s) : un ordre et un "
                    "numero de serie chacune. Les casiers du magasin portent "
                    "les memes numeros.",
                    nb=len(obtenus),
                )
            )
        return obtenus

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

    def action_replanifier_depuis_debit(self):
        """Replanifie le lot en partant de la fin de fab du DEBIT.

        Le retroplanning natif va de la livraison vers l'amont, OF par OF.
        L'ordonnanceur, lui, raisonne dans l'autre sens : il tient le banc de
        debit, decide quand ce lot y passe, et tout le reste suit. C'est le
        debit qui est la ressource rare et partagee — les assemblages, non.

        On part donc de « Fin de fab » saisie sur l'OF de debit, on mesure de
        combien elle deplace le debit, et on applique ce meme decalage a tous
        les assemblages du lot. Le decalage plutot qu'un recalcul complet :
        l'ordre relatif des menuiseries, et les arbitrages de capacite deja
        rendus, n'ont aucune raison de changer parce qu'on decale le lot.

        Chaque assemblage est ensuite recalcule par le moteur existant, qui
        applique les regles de capacite et le calendrier. Aucune regle metier
        n'est reecrite ici.

        Deux choses suivent le mouvement : la sortie matiere, calee quelques jours
        ouvres du debit, et le controle de la date de livraison client, qui
        dit si le lot tient encore l'engagement. Les achats, eux, ne bougent
        PAS : le compte rendu nomme les bons a revoir (cf. _achats_a_revoir).
        """
        self.ensure_one()
        debit = self.production_ids.filtered(
            lambda p: p.lot_production_type == "debit"
            and p.state not in ("done", "cancel")
        )[:1]
        if not debit:
            termine = self.production_ids.filtered(
                lambda p: p.lot_production_type == "debit"
                and p.state == "done"
            )[:1]
            if termine:
                raise UserError(_(
                    "L'ordre de debit %(of)s est deja termine : sa fin de fab "
                    "ne pilote plus rien.\n\n"
                    "Utilisez « Replanifier », qui recale les assemblages "
                    "seuls depuis la date de fin de fab du lot.",
                    of=termine.display_name,
                ))
            raise UserError(
                _("Le lot %s n'a pas d'ordre de debit actif.", self.name))
        if not debit.macro_forced_end:
            raise UserError(
                _(
                    "Renseignez « Fin de fab » sur l'ordre de debit %s : "
                    "c'est elle qui pilote la replanification du lot.",
                    debit.display_name,
                )
            )
        if not hasattr(debit, "compute_macro_schedule_from_date_fin"):
            raise UserError(
                _("Le module de planification de capacite n'est pas installe."))

        ancienne = debit.date_finished
        nouvelle = fields.Datetime.to_datetime(debit.macro_forced_end)
        decalage = timedelta(0)
        if ancienne:
            decalage = nouvelle.date() - fields.Datetime.to_datetime(
                ancienne).date()

        assemblages = self.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state not in ("done", "cancel")
        )

        # A SEC D'ABORD. La replanification d'un OF, dans ce depot, controle
        # la date de livraison AVANT d'ecrire et bloque si elle ne tient pas.
        # On suit la meme regle : rien n'est ecrit tant que le lot entier n'a
        # pas passe le controle. Ecrire puis constater laisserait un lot a
        # moitie deplace.
        self._controler_livraison(assemblages, decalage, nouvelle.date())

        debit.compute_macro_schedule_from_date_fin()
        deplaces = self._decaler_assemblages(assemblages, decalage, debit)
        depart_matiere = self._planifier_sortie_matiere(debit)

        self._rendre_compte_replanification(
            debit, decalage, deplaces, depart_matiere,
            self._achats_a_revoir())
        return True

    def _decaler_assemblages(self, assemblages, decalage, debit):
        """Applique le decalage du debit aux assemblages, sans en croiser un.

        Un assemblage ne peut pas commencer avant que le debit soit fini : il
        consomme l'ensemble debite. Apres le decalage, on verifie, et on
        repousse ceux qui auraient pris de l'avance.
        """
        Production = self.env["mrp.production"]
        fin_debit = debit.date_finished or debit.date_start
        fin_debit = (fields.Datetime.to_datetime(fin_debit).date()
                     if fin_debit else False)
        deplaces = Production.browse()

        for mo in assemblages:
            # La MEME projection que celle annoncee dans le popup : le
            # decalage et le report derriere le debit sont deja dedans.
            cible = self._fin_projetee(mo, decalage, fin_debit)
            if not cible:
                continue
            # Une cible egale a la date du jour n'est pas un deplacement : ne
            # pas la reecrire, et surtout ne pas la compter. Le compte rendu
            # annoncait « 1 assemblage suivent » apres un decalage nul, et
            # l'atelier en concluait que la replanification ne marchait pas.
            if cible == mo._date_fin_de_fab():
                continue
            mo._set_date_fin_de_fab(cible)
            mo.compute_macro_schedule_from_date_fin()
            deplaces |= mo

            # Le moteur de capacite peut encore avoir place le debut avant la
            # fin du debit, en etalant l'assemblage sur une fenetre chargee.
            # Une passe de rattrapage, et une seule : au-dela, ce n'est plus
            # un decalage, c'est une replanification a refaire.
            if fin_debit and mo.date_start:
                debut = fields.Datetime.to_datetime(mo.date_start).date()
                if debut < fin_debit:
                    mo._set_date_fin_de_fab(
                        cible + timedelta(days=(fin_debit - debut).days + 1))
                    mo.compute_macro_schedule_from_date_fin()
        return deplaces

    def _achats_a_revoir(self):
        """Les bons d'achat du lot, pour information — SANS les deplacer.

        Odoo ne recale pas les achats tout seul, et c'est voulu. Une date de
        reception n'est pas une consequence mecanique du planning atelier :
        c'est une negociation avec le fournisseur, que lui seul peut
        accepter. La deplacer dans Odoo ne la deplace pas chez lui — on
        obtiendrait une base qui affiche une date a laquelle personne n'a
        souscrit, et un acheteur qui croit l'affaire reglee.

        Le lot les NOMME donc dans son compte rendu, et l'achat tranche.
        """
        return self._lignes_achat_du_lot().order_id

    def _fin_projetee(self, mo, decalage, fin_debit):
        """Fin de fab qu'aura CET assemblage apres la replanification.

        Deux termes, et le second est celui qu'on oubliait : le decalage du
        debit, puis le report de l'assemblage qui commencerait avant que le
        debit soit fini. Un assemblage consomme l'ensemble debite — il ne
        peut pas le preceder.

        Sans ce second terme, un decalage nul donnait une projection nulle :
        le popup annoncait des assemblages au 06/11 derriere un debit fini le
        16/11, et le controle de livraison les declarait a l'heure. Ils
        etaient en retard certain, et c'est l'ecriture qui l'aurait decouvert.

        Le calcul se fait a sec, sans rien ecrire, et c'est le meme qui sert a
        afficher, a controler et a poser la cible : les trois ne peuvent plus
        se contredire.
        """
        fin = mo.date_finished
        if not fin:
            return None
        cible = fields.Datetime.to_datetime(fin).date() + decalage
        debut = mo.date_start
        if fin_debit and debut:
            debut = fields.Datetime.to_datetime(debut).date() + decalage
            if debut < fin_debit:
                cible += timedelta(days=(fin_debit - debut).days + 1)
        return cible

    def _controler_livraison(self, assemblages, decalage, fin_debit=None):
        """Controle a sec : le lot deplace tient-il encore l'engagement ?

        Deux blocages, et ce sont ceux que la replanification d'un OF applique
        deja dans mrp_capacity_planning. On les reprend a la maille du lot
        plutot que d'inventer un autre comportement pour le meme geste.

        Une date de livraison introuvable bloque. Ce n'est pas de la rigidite :
        sans elle on ne controle rien, et on deplacerait un lot sans savoir ce
        qu'on engage. La remonter est le travail de _get_macro_target_date,
        qui passe par la ligne de vente puis par x_studio_mtn_mrp_sale_order.

        Un depassement bloque aussi. Le message dit de combien, et pour
        quelle menuiserie : on ne demande pas a l'ordonnanceur de deviner ce
        qu'il faut negocier.

        Rien n'est ecrit ici : le controle precede l'ecriture, sans quoi un
        refus laisserait un lot a moitie deplace.
        """
        self.ensure_one()
        if not assemblages or not hasattr(
                assemblages[0], "_get_macro_target_date"):
            return

        sans_date, en_retard = [], []
        for mo in assemblages:
            cible, _commande = mo._get_macro_target_date()
            if not cible:
                sans_date.append(mo)
                continue
            projetee = self._fin_projetee(mo, decalage, fin_debit)
            if not projetee:
                continue
            cible = fields.Datetime.to_datetime(cible).date()
            if projetee > cible:
                en_retard.append((mo, projetee, cible, (projetee - cible).days))

        if sans_date:
            raise UserError(_(
                "Date de livraison introuvable pour %(nb)s menuiserie(s) : "
                "%(liste)s.\n\n"
                "Sans elle, le lot ne peut pas etre replanifie : rien ne "
                "permettrait de dire si la nouvelle date tient l'engagement.\n"
                "Renseignez la date de livraison prevue sur la commande, ou "
                "rattachez l'ordre a sa commande.",
                nb=len(sans_date),
                liste=", ".join(sans_date.mapped("display_name")[:8]),
            ))

        if en_retard:
            detail = "\n".join(
                "%-22s fin %s   livraison %s   retard %d j" % (
                    mo.display_name, projetee.strftime("%d/%m/%Y"),
                    cible.strftime("%d/%m/%Y"), retard)
                for mo, projetee, cible, retard in en_retard[:10]
            )
            raise ValidationError(_(
                "\u26a0\ufe0f BLOCAGE : le lot deplace ne tient plus la date de "
                "livraison client.\n\n"
                "%(detail)s\n\n"
                "Modifiez la fin de fab du debit ou negociez la livraison "
                "avant de replanifier.",
                detail=detail,
            ))

    def _rendre_compte_replanification(self, debit, decalage, deplaces,
                                       depart_matiere, achats):
        """Ce que la replanification a fait, et ce qu'elle n'a pas pu faire."""
        self.ensure_one()
        jours = decalage.days if decalage else 0
        if deplaces:
            suite = _("%(nb)s assemblage(s) suivent : %(noms)s.",
                      nb=len(deplaces),
                      noms=", ".join(deplaces.mapped("display_name")))
        else:
            # Dire pourquoi rien n'a bouge. Sans cette phrase, l'ecran est
            # identique avant et apres : on ne distingue pas « il n'y avait
            # rien a faire » d'une replanification qui echoue en silence.
            suite = _(
                "Aucun assemblage deplace : le decalage est de %(jours)s "
                "jour(s) et ils commencent deja apres la fin du debit.",
                jours=jours)
        corps = [_(
            "Replanification depuis le debit %(of)s : fin de fab au "
            "%(fin)s, soit %(jours)s jour(s) de decalage. %(suite)s",
            of=debit.display_name,
            fin=debit.macro_forced_end,
            jours=jours,
            suite=suite,
        )]
        if depart_matiere:
            corps.append(_(
                "<br/>Sortie matiere ramenee au %(date)s.", date=depart_matiere))
        if achats:
            corps.append(_(
                "<br/><b>%(nb)s bon(s) d'achat a revoir</b> — %(noms)s. "
                "Leurs dates n'ont PAS ete modifiees : une date de reception "
                "se negocie avec le fournisseur, elle ne se deduit pas du "
                "planning atelier. A l'achat de trancher.",
                nb=len(achats), noms=", ".join(achats.mapped("name")),
            ))
        self.message_post(body="".join(corps))

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
        if not assemblages:
            return False

        # UN DEBIT TERMINE N'EMPECHE PLUS DE REPLANIFIER. Il bloquait tout :
        # une fois le lot debite, plus aucune date d'assemblage ne bougeait,
        # alors que c'est precisement le moment ou l'atelier a besoin de les
        # reordonner. On replanifie donc les assemblages seuls, et on ne
        # touche pas au debit : ce qui est fait est fait.
        debit_fige = not debit or debit.state in ("done", "cancel")

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

            if debit_fige:
                # Rien a caler en amont : le debit est fait, ou absent.
                self.message_post(body=_(
                    "Replanification des assemblages seuls, a partir du "
                    "%(debut)s : le debit est deja termine.",
                    debut=min(debuts),
                ))
                return True

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

            # 4. La quincaillerie et le vitrage sortent quelques jours ouvres avant le
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

    #: Repli quand la societe ne porte pas le reglage — un lot ne doit pas
    #: rester sans date de sortie parce qu'un champ est vide.
    JOURS_AVANCE_QUINCAILLERIE = 6

    def _jours_avance_matiere(self):
        """Jours ouvres entre la sortie matiere et le debut du debit."""
        self.ensure_one()
        reglage = self.company_id.fma_lot_jours_avance_matiere
        return reglage if reglage and reglage > 0 else self.JOURS_AVANCE_QUINCAILLERIE

    def _planifier_sortie_matiere(self, debit):
        """Cale la sortie matiere avant le debut du debit, delai reglable.

        Le delai etait fige a trois jours dans le code. Il est passe a six, et
        il rechangera : le magasin garnit un casier par menuiserie, et le
        nombre de menuiseries par lot bouge lui aussi. Il vit donc dans les
        reglages de la societe, ou le metier peut le corriger sans build.

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
        jours = self._jours_avance_matiere()
        calendrier = self.company_id.resource_calendar_id
        cible = False
        if calendrier:
            cible = calendrier.plan_days(-jours, depart, compute_leaves=True)
        if not cible:
            # Sans calendrier exploitable, le meme nombre de jours calendaires
            # vaut mieux qu'une sortie non datee, qui ne serait jamais
            # preparee.
            cible = depart - timedelta(days=jours)

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

        L'ETIQUETTE COMMERCIALE decide, et rien d'autre : FMA fabrique a La
        Regrippiere, F2M a La Remaudiere. La regle est directe, elle n'a pas
        a etre devinee.

        Le reste n'est que du rattrapage, pour un lot dont la commande n'est
        pas etiquetee. On copie alors le type d'operation des OF d'assemblage
        — ils viennent de l'appro natif, c'est le choix d'Odoo lui-meme pour
        cette commande — puis a defaut le manu_type_id de l'entrepot de la
        commande, le type de fabrication que l'entrepot DESIGNE.

        La recherche ne vient qu'en dernier : prendre « le premier
        mrp_operation de l'entrepot » rend n'importe lequel quand il y en a
        plusieurs, et c'est ainsi qu'un OF de debit CBMF/LRE est sorti face a
        des assemblages LRE/LRE.
        """
        self.ensure_one()
        Type = self.env["stock.picking.type"]
        domaine = [
            ("code", "=", "mrp_operation"),
            ("company_id", "in", (self.company_id.id, False)),
        ]

        picking_type = self._picking_type_par_etiquette()
        if picking_type:
            return picking_type

        assemblages = self.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state != "cancel"
            and p.picking_type_id
        )
        if assemblages:
            return assemblages[0].picking_type_id

        entrepot = self.sale_order_ids.warehouse_id[:1]
        if entrepot and "manu_type_id" in entrepot._fields:
            picking_type = entrepot.manu_type_id
            if picking_type:
                return picking_type
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

    #: Les champs ou chercher l'etiquette, dans l'ordre. tag_ids d'abord :
    #: c'est le champ STANDARD d'Odoo, celui que le formulaire affiche sous
    #: « Etiquettes » et que les commerciaux remplissent.
    #:
    #: x_studio_etiquette_1 est un ancien champ Studio. Il portait encore la
    #: valeur sur certaines bases et pas sur d'autres — d'ou un debit qui
    #: partait sur le bon entrepot ici et sur le mauvais la, a code
    #: rigoureusement identique. On le garde en second, pour les commandes
    #: anciennes qui n'ont que lui, et le jour ou plus aucune ne l'utilise il
    #: disparaitra de cette liste.
    CHAMPS_ETIQUETTE = ("tag_ids", "x_studio_etiquette_1")

    def _etiquette_commerciale(self):
        """L'etiquette de la commande : « FMA » ou « F2M ».

        On lit le premier champ present qui porte une etiquette connue. Aucun
        des deux n'est suppose exister : ils viennent d'ailleurs, et un champ
        absent ne doit pas faire tomber la generation des ordres.
        """
        self.ensure_one()
        commandes = self.sale_order_ids
        if not commandes:
            return ""
        for champ in self.CHAMPS_ETIQUETTE:
            if champ not in commandes._fields:
                continue
            for tag in commandes.mapped(champ):
                nom = (tag.name or "").strip().upper()
                if nom in ENTREPOT_PAR_ETIQUETTE:
                    return nom
        return ""

    def _atelier_par_etiquette(self):
        """L'atelier que l'etiquette de la commande designe.

        « FMA » fabrique a La Regrippiere, « F2M » a La Remaudiere — la meme
        regle que pour l'entrepot, parce que c'est le meme site. Les ordres
        d'un lot sortaient sans atelier, donc hors du macro-planning et des
        restitutions de capacite, qui raisonnent par atelier.

        Le rapprochement se fait sur le CODE de l'atelier, puis sur son nom :
        un referentiel ou le code n'est pas renseigne ne doit pas priver les
        ordres de leur atelier. Les accents sont ignores — « Regrippiere » et
        « Regrippière » doivent se valoir.

        Rien trouve, rien pose : l'ordonnanceur garde la main, et un atelier
        absent vaut mieux qu'un mauvais.
        """
        self.ensure_one()
        Atelier = self.env["fma.atelier"]
        reperes = NOM_ATELIER_PAR_ETIQUETTE.get(self._etiquette_commerciale())
        if not reperes:
            return Atelier
        code, nom = reperes
        trouve = Atelier.search(
            [("code", "=ilike", code),
             ("company_id", "in", (False, self.company_id.id))], limit=1)
        if trouve:
            return trouve
        for candidat in Atelier.search(
                [("company_id", "in", (False, self.company_id.id))]):
            if nom in _sans_accent(candidat.name or "").upper():
                return candidat
        return Atelier

    def _picking_type_par_etiquette(self):
        """Le type de fabrication de l'entrepot que l'etiquette designe.

        L'etiquette designe un ENTREPOT, pas un type d'operation. Reste a
        choisir, dans cet entrepot, lequel de ses types de fabrication employer
        — et manu_type_id n'est pas toujours le bon.

        Constate : etiquette FMA, entrepot LRE, assemblages en LRE/LRE et
        debit en CBMF/LR. L'entrepot declare CBMF comme type de fabrication,
        alors que l'appro natif place les assemblages sur un autre. Le debit
        partait donc du bon entrepot mais du mauvais atelier, ce qui revient au
        meme pour la production : le sous-ensemble debite n'arrive pas la ou on
        l'assemble.

        On prend donc d'abord le type des ASSEMBLAGES du lot, a condition
        qu'il releve de l'entrepot que l'etiquette designe. C'est le choix
        d'Odoo lui-meme pour cette commande, et c'est celui qui garantit que
        debit et assemblage se retrouvent. manu_type_id ne sert que si les
        assemblages n'existent pas encore ou relevent d'un autre entrepot —
        auquel cas c'est l'etiquette qui tranche, comme demande.

        Un entrepot introuvable ou sans type de fabrication ne bloque pas : on
        le dit sur le lot et on laisse les autres chemins repondre.
        """
        self.ensure_one()
        etiquette = self._etiquette_commerciale()
        code = ENTREPOT_PAR_ETIQUETTE.get(etiquette)
        if not code:
            return self.env["stock.picking.type"]

        entrepot = self.env["stock.warehouse"].search(
            [("code", "=", code), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        if entrepot:
            # 1. Le type des assemblages, s'il releve bien de cet entrepot :
            #    c'est le choix d'Odoo pour cette commande, et celui qui
            #    garantit que debit et assemblage se retrouvent.
            assemblages = self.production_ids.filtered(
                lambda p: p.lot_production_type == "assemblage"
                and p.state != "cancel"
                and p.picking_type_id.warehouse_id == entrepot
            )
            if assemblages:
                return assemblages[0].picking_type_id

            # 2. A defaut, le type de l'entrepot dont la SEQUENCE porte le
            #    code de l'entrepot.
            #
            #    LA REGRIPPIERE en a deux : « Production », numerotant en
            #    CBMF/LRE/, et « LA REGRIPIERRE : Production », numerotant en
            #    LRE/LRE/. Le premier est un reliquat d'une ancienne
            #    configuration — et c'est lui que manu_type_id designe. Un
            #    debit genere avant que les assemblages soient rattaches
            #    sortait donc sous un numero CBMF, dans le bon entrepot mais
            #    sous le nom d'un autre atelier, et le metier lisait le nom.
            #
            #    On choisit donc sur la sequence et non sur le champ de
            #    l'entrepot : le prefixe dit ou l'ordre sera lu, et c'est ce
            #    que l'etiquette promet.
            types = self.env["stock.picking.type"].search([
                ("code", "=", "mrp_operation"),
                ("warehouse_id", "=", entrepot.id),
                ("company_id", "in", (self.company_id.id, False)),
            ])
            attendu = "%s/" % code
            coherents = types.filtered(
                lambda t: (t.sequence_id.prefix or "").upper().startswith(
                    attendu)
            )
            if coherents:
                return coherents[0]

            # 3. En dernier ressort seulement, le type que l'entrepot
            #    declare. Il peut designer n'importe lequel des siens.
            if "manu_type_id" in entrepot._fields and entrepot.manu_type_id:
                return entrepot.manu_type_id

        self.message_post(
            body=_(
                "Etiquette %(etiquette)s : entrepot « %(code)s » introuvable "
                "ou sans type de fabrication. Les ordres du lot partiront sur "
                "l'entrepot de la commande.",
                etiquette=etiquette,
                code=code,
            )
        )
        return self.env["stock.picking.type"]

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

        # L'atelier, deduit de l'etiquette comme l'entrepot. Sans lui les
        # ordres du lot sortaient hors du macro-planning et des restitutions
        # de capacite, qui raisonnent par atelier. Le champ vient de
        # fma_atelier — dependance declaree, mais le controle ne coute rien.
        if "atelier_id" in Production._fields:
            atelier = self._atelier_par_etiquette()
            if atelier:
                vals["atelier_id"] = atelier.id

        # La commande, sur l'OF de debit comme sur les autres. Il n'a pas de
        # ligne de vente — c'est le lot entier qu'il debite, pas une
        # menuiserie — et rien ne l'y rattachait : ni le numero de commande a
        # l'ecran, ni le projet, ni les recherches par affaire.
        #
        # On passe par x_studio_mtn_mrp_sale_order et non par sale_line_id :
        # poser une ligne de vente ferait croire a l'appro natif que le besoin
        # de cette ligne est couvert par cet OF, et il cesserait de creer l'OF
        # d'assemblage qui, lui, produit vraiment la menuiserie.
        commandes = self.sale_order_ids
        if commandes:
            vals["origin"] = "%s - %s" % (
                self.name, ", ".join(commandes.mapped("name")))
            if len(commandes) == 1 and "x_studio_mtn_mrp_sale_order" in Production._fields:
                vals["x_studio_mtn_mrp_sale_order"] = commandes.id

        return vals

    def _generate_debit_order(self):
        """Cree l'OF de debit du lot (1 par lot).

        Le controle ne se fie pas au seul production_debit_id : le champ peut
        etre vide alors que l'OF existe -- creation par un autre chemin,
        remise en brouillon, reprise de donnees. On regarde aussi les OF
        rattaches au lot, et on en profite pour recoller le champ. Sans cela,
        un second clic sur « Generer les OF » fabriquerait un deuxieme OF de
        debit, qui consommerait les memes barres.
        """
        self.ensure_one()
        existant = self.production_debit_id
        if not existant or existant.state == "cancel":
            existant = self.production_ids.filtered(
                lambda p: p.lot_production_type == "debit" and p.state != "cancel"
            )[:1]
        if existant:
            if self.production_debit_id != existant:
                self.production_debit_id = existant
            return existant

        Production = self.env["mrp.production"]
        picking_type = self._get_picking_type()

        # Un OF ne produit qu'un article, or une seance de debit sort un
        # ensemble debite PAR REPERE : les barres sont mutualisees, les coupes
        # ne le sont pas.
        #
        # L'article de l'ordre est donc celui du LOT — « Debit du lot »,
        # generique, non suivi en stock — et sa quantite le nombre de
        # menuiseries du lot : c'est ce que l'atelier lit sur l'ordre. Les
        # ensembles debites sortent TOUS en sous-produits, au meme rang. Avant
        # la 1.60, le premier repere etait l'article de l'ordre : un lot de 10
        # menuiseries affichait « 8 », la quantite de son premier repere.
        #
        # Repli quand aucune ligne ne porte son ensemble debite — lot saisi a
        # la main, ou importe avant que le lien n'existe : l'article debite
        # du lot, sans sous-produit, comme avant.
        sorties = self._sous_produits_debit()
        if sorties:
            product = self._get_product_debit_lot()
        else:
            product = self._get_product_debit()
        qty = self.menuiserie_qty or 1.0

        vals = self._common_production_vals(picking_type)
        vals.update(
            {
                "product_id": product.id,
                "product_qty": qty,
                uom_fname(Production): product.uom_id.id,
                # Pas de nomenclature, volontairement : celle d'un ensemble
                # debite ne porte la gamme que d'UN repere, et pour un
                # exemplaire. Le temps de debit du lot est la somme de ses
                # reperes, et c'est nous qui la posons — cf. _operations_debit.
                "bom_id": False,
                "lot_production_type": "debit",
            }
        )
        production = Production.create(vals)
        # Les barres viennent du besoin matiere du lot et non d'une
        # nomenclature : elles varient d'un lot a l'autre.
        production._add_lot_material_moves(self.material_line_ids)
        # Encadre : la gamme est de l'information. Une signature native qui
        # aurait bouge d'une version a l'autre ne doit pas empecher le lot de
        # sortir son OF de debit.
        try:
            self._poser_operations_debit(production)
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Gamme de debit du lot %s", self.name)
        # En DERNIER : tant que l'ordre est en brouillon, Odoo reconstruit ses
        # produits finis des qu'une date, une quantite ou l'article bouge, et
        # il ne recree alors que l'article principal. Poser la gamme deplace
        # la date de fin. action_generate_orders repasse derriere la
        # confirmation, ou plus rien ne les efface.
        self._poser_sous_produits_debit(production)

        self.production_debit_id = production
        self._verifier_debit_profiles(production)
        if sorties and product.is_storable:
            self.message_post(
                body=_(
                    "OF de debit : l'article « %(article)s » est suivi en "
                    "stock. Il ne represente que la seance de debit et "
                    "s'accumulera en stock a chaque lot : decochez « Suivre "
                    "l'inventaire » sur sa fiche.",
                    article=product.display_name,
                )
            )
        self.message_post(
            body=_("OF de debit %s genere.", production.display_name)
        )
        return production

    # ------------------------------------------------------------------
    # Ce que l'OF de debit sort : un ensemble debite par repere
    # ------------------------------------------------------------------
    def _get_product_debit_lot(self):
        """L'article que porte l'OF de debit, PROPRE A L'AFFAIRE.

        Il s'appelait « [DEB-LOT] Debit du lot », generique et partage par
        toutes les affaires : sur un ecran de stock ou de valorisation, les
        debits de dix chantiers se confondaient en une seule ligne. Il porte
        desormais la reference de la commande — « A26-10-07853_DEB ».

        L'article est cree a la demande et reutilise ensuite : deux lots
        d'une meme affaire partagent le leur, ce qui est voulu — c'est la
        meme seance de debit vue deux fois.

        Repli sur l'article generique quand le lot n'a pas de commande : un
        lot saisi a la main doit pouvoir se generer.
        """
        self.ensure_one()
        commande = self.sale_order_ids.sorted("id")[:1]
        if not commande or not commande.name:
            return self._get_product_debit_lot_generique()
        reference = "%s_DEB" % commande.name
        Article = self.env["product.product"]
        article = Article.search(
            [("default_code", "=", reference)], limit=1)
        if article:
            return article
        modele = self._get_product_debit_lot_generique()
        return Article.create({
            "name": "Débit du lot — %s" % commande.name,
            "default_code": reference,
            # Copies du generique : c'est lui qui porte le parametrage juste
            # — type, categorie, unite, routes. Les recopier evite d'inventer
            # une configuration a cote de celle que le metier a reglee.
            "type": modele.type,
            # NON STOCKABLE, et c'est tout l'interet d'un article par
            # affaire. Celui-ci n'est qu'une etiquette : Odoo exige qu'un
            # ordre produise un article, une seance de debit n'en produit pas
            # un mais autant qu'il y a de reperes — ils sortent en
            # sous-produits et emportent la totalite du cout. Le laisser
            # stockable creait une quantite fantome, valorisee a zero, que
            # personne ne consomme jamais.
            "is_storable": False,
            "categ_id": modele.categ_id.id,
            "uom_id": modele.uom_id.id,
            "purchase_ok": False,
            "sale_ok": False,
            "fma_semi_fini": modele.fma_semi_fini,
            "company_id": False,
        })

    def _get_product_debit_lot_generique(self):
        """L'article generique « Debit du lot », repli et modele.

        Il reste le parametrage de reference — type, categorie, unite — dont
        l'article d'affaire est une copie. Ce n'est jamais un ensemble debite
        de repere : un article ne peut pas etre a la fois le produit et le
        sous-produit d'un meme ordre.
        """
        self.ensure_one()
        reperes = self.line_ids.product_debit_id
        candidats = self.company_id.fma_lot_product_debit_id
        defaut = self.env.ref(
            "fma_lot_fabrication.product_ensemble_debite",
            raise_if_not_found=False,
        )
        if defaut:
            candidats |= defaut
        for candidat in candidats:
            if candidat not in reperes and candidat.fma_semi_fini != "debit":
                return candidat
        raise UserError(
            _(
                "Aucun article « Debit du lot » n'est parametre : l'OF de "
                "debit n'a pas d'article a porter.\n"
                "Renseignez « Article debite par defaut » dans Fabrication > "
                "Configuration > Parametres > Lots de fabrication, avec un "
                "article generique qui n'est l'ensemble debite d'aucune "
                "menuiserie."
            )
        )

    def _sous_produits_debit(self):
        """{ensemble debite: quantite} des reperes du lot, dans l'ordre.

        Deux lignes du lot peuvent porter le meme ensemble debite — la meme
        menuiserie sur deux lignes de commande : leurs quantites se cumulent,
        un ordre ne porte pas deux sorties du meme article.
        """
        self.ensure_one()
        sorties = {}
        for ligne in self.line_ids:
            article = ligne.product_debit_id
            if not article or float_is_zero(
                    ligne.product_qty, precision_digits=2):
                continue
            sorties[article] = sorties.get(article, 0.0) + ligne.product_qty
        return sorties

    def _metres_de_profile(self, product):
        """Longueur de profile qu'UN ensemble debite demande, en metres.

        Lue sur sa nomenclature, que l'import ecrit en longueur : en metres
        (« ML », l'unite fine a laquelle la barre se rattache, ou le metre
        d'Odoo), a defaut en fraction de barre — ramenee en metres par la
        longueur de barre de la fiche article.

        ``0.0`` des qu'UNE ligne ne se laisse pas mesurer, ou sans
        nomenclature : une longueur partielle fausserait la repartition, mieux
        vaut alors s'en remettre aux quantites.
        """
        self.ensure_one()
        bom = self.env["mrp.bom"]._bom_find(
            product, company_id=self.company_id.id, bom_type="normal"
        ).get(product)
        if not bom or not bom.bom_line_ids:
            return 0.0
        Uom = self.env["uom.uom"]
        metre = self.env.ref("uom.product_uom_meter", raise_if_not_found=False)
        piece = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)

        def racine(uom):
            tete = (uom.parent_path or "").split("/")[0]
            return Uom.browse(int(tete)) if tete.isdigit() else uom

        total = 0.0
        for ligne in bom.bom_line_ids:
            uom, qty, article = (
                ligne.product_uom_id, ligne.product_qty, ligne.product_id)
            if not uom or qty <= 0:
                continue
            base = racine(uom)
            if metre and base == racine(metre):
                total += uom._compute_quantity(qty, metre, round=False)
            elif piece and base == racine(piece):
                # Compte a la piece — une fraction de barre : il faut la
                # longueur de la barre pour en faire des metres.
                longueur = (
                    article.x_studio_longueur_m
                    if "x_studio_longueur_m" in article._fields else 0.0
                ) or 0.0
                if not longueur or uom != article.uom_id:
                    return 0.0
                total += qty * longueur
            else:
                # Une unite propre a la base, « ML » et les barres qui s'y
                # rattachent : son unite de reference est le metre lineaire.
                total += uom._compute_quantity(qty, base, round=False)
        return total / (bom.product_qty or 1.0)

    def _parts_de_cout_debit(self, sorties):
        """{ensemble debite: part du cout de l'OF de debit, en %}.

        Les barres consommees sont le cout de l'ordre. Il va en totalite aux
        ensembles debites — l'article de l'ordre, « Debit du lot », n'est
        qu'une etiquette et ne porte rien — au prorata des metres de profile
        que chacun demande : metres par exemplaire, selon sa nomenclature,
        fois la quantite. Si un seul des ensembles ne se laisse pas mesurer,
        tout le lot est reparti au prorata des quantites : on ne melange pas
        des metres et des pieces.

        La somme fait 100, au centieme : l'arrondi va au plus gros, et Odoo
        refuse un total superieur a 100.
        """
        self.ensure_one()
        if not sorties:
            return {}
        poids = {
            article: self._metres_de_profile(article) * qty
            for article, qty in sorties.items()
        }
        if any(p <= 0 for p in poids.values()):
            poids = dict(sorties)
        total = sum(poids.values())
        if total <= 0:
            return {}
        centiemes = {
            article: int(round(10000.0 * p / total))
            for article, p in poids.items()
        }
        plus_gros = max(poids, key=lambda a: poids[a])
        centiemes[plus_gros] += 10000 - sum(centiemes.values())
        parts = {article: c / 100.0 for article, c in centiemes.items()}
        # La somme flottante peut depasser 100 d'un cheveu, et la contrainte
        # d'Odoo est stricte.
        while sum(parts.values()) > 100.0 and parts[plus_gros] >= 0.01:
            parts[plus_gros] = round(parts[plus_gros] - 0.01, 2)
        return parts

    def _poser_sous_produits_debit(self, production):
        """Pose sur l'OF de debit un sous-produit par ensemble debite.

        Sans effet sur un ordre de l'ancienne forme — celui dont l'article
        est l'ensemble debite du premier repere : il garde ses sous-produits
        et ses quantites tels qu'ils ont ete generes. Sans effet non plus sur
        un sous-produit deja present : on complete, on ne reecrit pas.

        Encadre : un sous-produit qui ne se pose pas ne doit pas empecher le
        lot de sortir son OF de debit — mais il le dit.
        """
        self.ensure_one()
        sorties = self._sous_produits_debit()
        if (not sorties or not production
                or production.state in ("done", "cancel")
                or production.product_id in sorties):
            return self.env["stock.move"]
        poses = self.env["stock.move"]
        try:
            with self.env.cr.savepoint():
                parts = self._parts_de_cout_debit(sorties)
                for article, qty in sorties.items():
                    poses |= production._add_debit_byproduct(
                        article, qty, parts.get(article, 0.0))
                # Sur un ordre deja confirme, un mouvement cree a la main
                # reste en brouillon : on le confirme, comme le fait Odoo
                # pour un sous-produit ajoute depuis l'ecran.
                if production.state != "draft":
                    poses.filtered(
                        lambda m: m.state == "draft")._action_confirm()
        except Exception:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Sous-produits de l'OF de debit du lot %s", self.name)
            self.message_post(
                body=_(
                    "OF de debit %(of)s : les ensembles debites n'ont pas pu "
                    "etre poses en sous-produits. Les assemblages ne "
                    "recevront pas leur debit — a reprendre avant de lancer.",
                    of=production.display_name,
                )
            )
            return self.env["stock.move"]
        return poses

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

    def _verifier_appro_debit(self, production):
        """Dit sur le lot si les profiles ne partiront pas a l'achat.

        Le constat demande un OF CONFIRME : procure_method n'est arrete qu'a
        ce moment-la. On le pose donc apres la confirmation, et on n'ecrit que
        si quelque chose cloche — un journal qui parle a chaque fois ne se lit
        plus.

        Trois situations, qui menent a trois endroits differents.

        Un OF de debit sans composant : il n'y a rien a acheter, et c'est le
        besoin matiere du lot qu'il faut regarder.

        Des articles SANS la route « Reapprovisionner sur commande » : Odoo
        les prendra sur stock, aucun achat ne partira. C'est la fiche article
        qu'il faut reprendre, pas le lot.

        Des articles EN MTO mais approvisionnes sur stock : la route est la,
        mais l'emplacement source n'a pas de regle MTO. Le message nomme cet
        emplacement.

        Le besoin et le disponible figurent a cote de chaque article : un
        profile deja en stock n'a rien a acheter, et ce n'est pas un defaut.
        Le dire evite de chercher un bug la ou il n'y en a pas.
        """
        self.ensure_one()
        moves = production.move_raw_ids
        if not moves:
            self.message_post(
                body=_(
                    "OF de debit %(of)s : aucun composant. Rien ne partira a "
                    "l'achat — le besoin matiere du lot compte %(nb)s ligne(s).",
                    of=production.display_name,
                    nb=len(self.material_line_ids),
                )
            )
            return

        mto = self.env.ref(
            "stock.route_warehouse0_mto", raise_if_not_found=False)
        if not mto:
            return

        # Trois etats possibles, trois causes differentes. On ne retient que
        # les deux qui empechent un achat.
        sans_mto = moves.filtered(lambda m: mto not in m.product_id.route_ids)
        sur_stock = moves.filtered(
            lambda m: mto in m.product_id.route_ids
            and m.procure_method != "make_to_order"
        )
        if not sans_mto and not sur_stock:
            return

        def _detail(mouvements):
            """Besoin et disponible : un article en stock n'a rien a acheter,
            et ce n'est pas un defaut. Le dire evite de chercher un bug."""
            return "<br/>".join(
                "%s — besoin %.2f %s, disponible %.2f" % (
                    m.product_id.display_name,
                    m.product_uom_qty,
                    m.product_uom.name,
                    m.product_id.free_qty,
                )
                for m in mouvements[:8]
            )

        corps = [_(
            "OF de debit %(of)s : composants pris depuis %(source)s.",
            of=production.display_name,
            source=production.location_src_id.complete_name or "?",
        )]
        if sans_mto:
            corps.append(_(
                "<br/><br/><b>%(nb)s article(s) sans route « Reapprovisionner "
                "sur commande »</b> : aucun achat ne partira pour eux, Odoo "
                "les prendra sur stock.<br/>%(liste)s",
                nb=len(sans_mto), liste=_detail(sans_mto),
            ))
        if sur_stock:
            corps.append(_(
                "<br/><br/><b>%(nb)s article(s) en MTO mais approvisionnes sur "
                "stock</b> : c'est l'emplacement source qui n'a pas de regle "
                "MTO.<br/>%(liste)s",
                nb=len(sur_stock), liste=_detail(sur_stock),
            ))
        self.message_post(body="".join(corps))

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

        # Profile ou non : le classement de l'article le dit (categorie,
        # famille), la table LOGIKAL d'origine en dernier recours. Un article
        # que rien ne classe n'est pas signale.
        intrus = consommes.filtered(
            lambda p: p._fma_classe_matiere() in ("quincaillerie", "remplissage")
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

    def _composants_reels(self, ordre, unites=1):
        """Ce qu'il faut sortir du stock pour UNE menuiserie de cet ordre.

        Lu sur les composants de l'ordre de fabrication, et non sur la
        nomenclature : c'est l'ordre qui dit ce qu'on va monter. Un composant
        ajoute apres coup — dans l'onglet Composants ou par « Ajouter un
        besoin » — y figure, un composant supprime ou annule n'y figure plus.

        Meme forme que ``_composants_unitaires`` : (article, quantite, unite).
        Un ordre qui porte plusieurs menuiseries est ramene a l'unite.

        L'ensemble debite est ecarte, pour la meme raison que la-bas : il ne
        sort pas du stock, il vient de la scie.
        """
        self.ensure_one()
        cumul = {}
        for mouvement in ordre.move_raw_ids:
            if mouvement.state == "cancel":
                continue
            article = mouvement.product_id
            if not article or article.fma_semi_fini == "debit":
                continue
            qty = mouvement.product_uom_qty
            if not qty and mouvement.state == "done":
                # Composant declare a l'atelier sans besoin initial : il a
                # bien ete pris, autant qu'il soit ecrit.
                qty = mouvement.quantity
            if not qty:
                continue
            cle = (article, mouvement.product_uom)
            cumul[cle] = cumul.get(cle, 0.0) + qty
        return [
            (article, qty / (unites or 1), uom)
            for (article, uom), qty in cumul.items()
        ]

    def _besoin_matiere(self):
        """Le besoin du lot, dans l'ordre ou il quitte le stock.

        Renvoie ``(profiles, prefab, casiers)``.

        ``profiles`` : toutes les barres du lot. Elles partent d'un bloc au
        banc de debit, parce que l'optimisation porte sur le lot entier — une
        barre sert plusieurs menuiseries, on ne peut pas en sortir la moitie.

        ``prefab`` : la quincaillerie et le vitrage, agreges. Ils partent en
        Pre-Fab avant le debit, et c'est ce document que le magasin suit pour garnir
        les casiers.

        ``casiers`` : le meme contenu, mais a l'unite — un casier par
        menuiserie, puisque c'est ainsi que le magasin travaille. Chaque
        casier porte son rang dans la ligne ; le jour ou les menuiseries
        seront suivies au numero de serie, ce rang deviendra ce numero.

        D'ou vient le contenu d'un casier : des COMPOSANTS REELS de l'ordre
        d'assemblage des que celui-ci existe, de la nomenclature avant. Un
        composant ajoute sur un ordre — une quincaillerie oubliee, une casse
        — sort donc sur la liste, et un composant retire en disparait. La
        nomenclature, elle, dit ce qui etait prevu, pas ce qu'on va monter.
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
            # Les ordres d'assemblage de cette ligne, dans l'ordre de leur
            # creation : la generation en cree un par menuiserie, avec son
            # numero de serie. Le rang du casier et le rang de l'ordre se
            # correspondent donc — c'est ce qui permet au magasin de garnir
            # « le casier 002 » et a l'atelier de declarer « la menuiserie
            # 002 » en parlant du meme exemplaire.
            ordres = self.env["mrp.production"].search(
                [("lot_line_id", "=", ligne.id),
                 ("state", "!=", "cancel"),
                 ("lot_production_type", "in", ("assemblage", False))],
                order="id",
            )
            du_lot = []
            for ordre in ordres:
                unites = max(int(round(ordre.product_qty or 0)), 1)
                contenu = self._composants_reels(ordre, unites)
                serie = ordre.lot_producing_ids[:1].name or ""
                for _unite in range(unites):
                    # Le numero de serie ne designe qu'UNE menuiserie : un
                    # ordre qui en porte plusieurs retombe sur le rang.
                    du_lot.append((serie if unites == 1 else "", contenu))

            # Ce que les ordres ne couvrent pas — avant leur generation, ou
            # pour une menuiserie ajoutee au lot depuis — vient de la
            # nomenclature : ce qui est prevu, faute de savoir ce qui est.
            nombre = max(int(ligne.product_qty or 0), len(du_lot))
            if len(du_lot) < nombre:
                prevu = self._composants_unitaires(ligne.product_id)
                du_lot += [("", prevu)] * (nombre - len(du_lot))

            for rang, (serie, contenu) in enumerate(du_lot, start=1):
                for article, qty, uom in contenu:
                    if not article or not qty:
                        continue
                    cle = (article, uom)
                    agrege[cle] = agrege.get(cle, 0.0) + qty
                casiers.append({
                    "ligne": ligne,
                    "rang": rang,
                    "sur": nombre,
                    "serie": serie,
                    "contenu": contenu,
                })

        return trier(barres), trier(agrege), casiers

    #: Libelle de chaque classe sur le document. L'ordre est celui du
    #: magasin : les barres partent au debit, le reste garnit les casiers.
    LIBELLE_CLASSE = {
        "profile": "Profilé",
        "remplissage": "Vitrage / panneau",
        "quincaillerie": "Quincaillerie",
    }
    ORDRE_CLASSE = {"profile": 0, "remplissage": 1, "quincaillerie": 2}

    def _besoin_matiere_complet(self, profiles, prefab):
        """TOUT le besoin du lot : profiles, vitrages et quincaillerie.

        Le recapitulatif ne portait que la quincaillerie. Le magasin a besoin
        de la totalite de ce que le lot consomme — c'est la premiere page du
        besoin matiere, celle qui dit ce qui doit etre sorti.

        Les deux sources ne se recouvrent pas : ``profiles`` vient des barres
        du lot, dimensionnees pour l'optimisation du debit, et ``prefab`` des
        COMPOSANTS REELS des ordres d'assemblage. Une quincaillerie ajoutee a
        la main sur une nomenclature ou sur un ordre y figure donc, et c'est
        tout l'interet de partir des ordres plutot que du fichier LOGIKAL.

        Chaque poste porte sa classe, pour que le document regroupe sans
        qu'on ait a la relire a l'impression.
        """
        self.ensure_one()
        postes = []
        classes = {}
        for source, classe_forcee in ((profiles, "profile"), (prefab, None)):
            for poste in source:
                article = poste["product"]
                if article.id not in classes:
                    classes[article.id] = article._fma_classe_matiere()
                classe = classe_forcee or classes[article.id] or "quincaillerie"
                postes.append({
                    "product": article,
                    "qty": poste["qty"],
                    "uom": poste["uom"],
                    "classe": classe,
                    "libelle": self.LIBELLE_CLASSE.get(classe, "Quincaillerie"),
                })
        postes.sort(key=lambda d: (
            self.ORDRE_CLASSE.get(d["classe"], 9),
            d["product"].default_code or d["product"].name or ""))
        return postes

    def _quincaillerie_par_repere(self, casiers):
        """La quincaillerie d'un lot, repere par repere.

        Le detail par ARTICLE sert la prise en rayon — un passage par
        article. Celui-ci sert le garnissage — un casier a la fois, avec sous
        les yeux ce qu'il doit contenir. Les deux lisent le meme contenu, qui
        vient des composants reels des ordres.

        Les profiles et les remplissages en sont exclus : ils ne passent pas
        par le casier. Un article que rien ne classe y reste — mieux vaut une
        ligne de trop, qu'on voit, qu'une ligne qui disparait en silence.
        """
        self.ensure_one()
        classes = {}
        blocs = []
        for casier in casiers:
            lignes = []
            for article, qty, uom in casier["contenu"]:
                if not article or not qty:
                    continue
                if article.id not in classes:
                    classes[article.id] = article._fma_classe_matiere()
                if classes[article.id] in ("profile", "remplissage"):
                    continue
                lignes.append({"product": article, "qty": qty, "uom": uom})
            if not lignes:
                continue
            lignes.sort(key=lambda d: (
                d["product"].default_code or d["product"].name or ""))
            blocs.append({
                "repere": self._repere_du_casier(casier),
                "casier": casier["serie"] or "%03d" % casier["rang"],
                "rang": casier["rang"],
                "sur": casier["sur"],
                "lignes": lignes,
            })
        return blocs

    def _repere_du_casier(self, casier):
        """La POSITION du repere, pas sa reference complete.

        Celle-ci vaut « A26-00-00002_E-MEXT-C3 » : le prefixe est l'affaire,
        identique sur tout le document, et il faisait deborder la colonne.
        """
        produit = casier["ligne"].product_id
        if ("x_studio_position" in produit._fields
                and produit.x_studio_position):
            return produit.x_studio_position
        code = produit.default_code or produit.name or ""
        return code.split("_")[-1] if "_" in code else code

    def _quincaillerie_par_article(self, casiers):
        """Le besoin regroupe par ARTICLE, avec son detail par casier.

        Le meme contenu que les pages de casier, lu dans l'autre sens. Une
        page par casier dit ce qu'il faut mettre dedans ; cette liste-ci dit
        combien prendre en rayon et comment le repartir. Le magasin fait un
        seul passage par article au lieu d'un passage par casier.

        C'est la forme de la « Liste de quincaillerie » que FMA connait deja :
        l'article, sa quantite globale, puis une ligne par casier servi.
        """
        self.ensure_one()
        par_article = {}
        # Une menuiserie se repete d'un casier a l'autre : on ne remonte les
        # categories qu'une fois par article.
        classes = {}
        for casier in casiers:
            ligne = casier["ligne"]
            # La POSITION seule, pas la reference complete. Celle-ci vaut
            # « A26-00-00002_E-MEXT-C3 » : le prefixe est l'affaire, identique
            # sur tout le document, et il faisait deborder la colonne sur
            # quatre lignes. Ce qui distingue un repere d'un autre, c'est ce
            # qui suit.
            produit = ligne.product_id
            repere = produit.x_studio_position if (
                "x_studio_position" in produit._fields
                and produit.x_studio_position) else ""
            if not repere:
                code = produit.default_code or ""
                repere = code.rpartition("_")[2] or code or produit.name or ""
            etiquette = casier.get("serie") or "%s/%s" % (
                casier["rang"], casier["sur"])

            for article, qty, uom in casier["contenu"]:
                if not article or not qty:
                    continue
                # QUINCAILLERIE seule. Ni vitrage ni profile : le vitrage se
                # commande et se livre a part, les profiles — complementaires
                # compris — passent par le debit. Ce document sert la prise en
                # rayon, et on ne prend en rayon que cela.
                #
                # C'est le CLASSEMENT de l'article qui le dit — categorie,
                # famille, sous-famille — et la table LOGIKAL d'origine
                # seulement pour l'article que rien ne range.
                # cf. product.product._fma_classe_matiere.
                #
                # Un article que rien ne classe n'est pas exclu : mieux vaut
                # une ligne de trop, qu'on voit, qu'une ligne qui disparait
                # en silence.
                if article.id not in classes:
                    classes[article.id] = article._fma_classe_matiere()
                if classes[article.id] in ("profile", "remplissage"):
                    continue
                poste = par_article.setdefault(article.id, {
                    "article": article,
                    "uom": uom,
                    "total": 0.0,
                    "detail": [],
                })
                poste["total"] += qty
                poste["detail"].append({
                    "qty": qty,
                    "casier": etiquette,
                    "repere": repere,
                })
        postes = list(par_article.values())
        emplacements = self._emplacements_stock(
            self.env["product.product"].browse(list(par_article)))
        for poste in postes:
            poste["emplacement"] = emplacements.get(poste["article"].id)
            # Precalcule pour le rowspan : QWeb n'a pas a compter.
            poste["nb"] = len(poste["detail"])

        # Tri par EMPLACEMENT d'abord : le magasin suit ses rayons, il ne
        # suit pas l'ordre alphabetique des references. Les articles sans
        # emplacement connu ferment la marche plutot que d'ouvrir la liste.
        return sorted(postes, key=lambda p: (
            not p["emplacement"],
            p["emplacement"].complete_name if p["emplacement"] else "",
            p["article"].default_code or "",
            p["article"].name or "",
        ))

    def _racine_stock(self):
        """L'emplacement Stock de l'entrepot du lot.

        Celui ou le magasin range, par opposition a la pre-fabrication, ou la
        matiere est deja reservee pour un ordre. Envoyer quelqu'un chercher en
        pre-fab, c'est l'envoyer prendre ce qui est deja promis a un autre lot.
        """
        self.ensure_one()
        types = self.production_ids.picking_type_id
        if not types:
            types = self._picking_type_par_etiquette()
        return types[:1].warehouse_id.lot_stock_id

    def _emplacements_stock(self, articles):
        """Ou chaque article se range, d'apres le stock reel.

        Aucun champ de la base ne porte l'emplacement de rangement d'un
        article : on le deduit des quants. C'est meme plus fiable qu'une
        saisie, qui vieillit des qu'on reorganise un rayon.

        On ne regarde que SOUS STOCK. La pre-fabrication en est exclue : ce
        qui s'y trouve est deja sorti pour un ordre, et y envoyer le magasin
        reviendrait a lui faire reprendre la matiere d'un autre lot.

        Quand un article est range a plusieurs endroits sous Stock, on prend
        le premier dans l'ordre des emplacements — celui que le magasin
        rencontre en premier dans sa tournee.
        """
        self.ensure_one()
        if not articles:
            return {}
        domaine = [
            ("product_id", "in", articles.ids),
            ("location_id.usage", "=", "internal"),
            ("company_id", "in", (self.company_id.id, False)),
            ("quantity", ">", 0),
        ]
        racine = self._racine_stock()
        if racine:
            domaine.append(("location_id", "child_of", racine.id))

        retenu = {}
        for quant in self.env["stock.quant"].sudo().search(
                domaine, order="location_id, id"):
            # Le premier rencontre l'emporte : la recherche est deja triee
            # par emplacement.
            retenu.setdefault(quant.product_id.id, quant.location_id)
        return retenu

    def action_imprimer_besoin_matiere(self):
        """Edite le besoin matiere du lot.

        Un bouton, et pas seulement une entree dans le menu « Imprimer » : le
        rapport est rattache au LOT, alors qu'on le cherche naturellement
        depuis le transfert de sortie. Sur le transfert, ce menu ne le propose
        pas — il n'y est pas rattache — et on conclut qu'il n'existe pas.
        """
        self.ensure_one()
        return self.env.ref(
            "fma_lot_fabrication.action_report_lot_sortie_matiere"
        ).report_action(self)

    def action_view_sortie_matiere(self):
        """Les bons de sortie matiere du lot : les barres, puis les casiers.

        L'action est construite a la main plutot que reprise d'un xmlid du
        standard : un identifiant d'action qui disparait d'une version a
        l'autre casserait le bouton, et on n'a besoin d'aucun de ses filtres.
        """
        self.ensure_one()
        pickings = self.picking_matiere_ids
        action = {
            "type": "ir.actions.act_window",
            "name": _("Sortie matière — %s", self.name),
            "res_model": "stock.picking",
            "domain": [("id", "in", pickings.ids)],
            "context": {"create": False},
        }
        if len(pickings) == 1:
            action["view_mode"] = "form"
            action["res_id"] = pickings.id
        else:
            action["view_mode"] = "list,form"
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
