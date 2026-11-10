# -*- coding: utf-8 -*-
"""Rattachement des achats aux lots de fabrication.

Le lien vit sur la LIGNE d'achat, pas sur l'en-tete. C'est la regle metier
qui l'impose : une barre optimisee dans un lot ne sert pas ailleurs, mais un
bon de commande regroupe les besoins de plusieurs lots des lors qu'ils
partagent le fournisseur et le projet. Un lien porte par l'en-tete forcerait
un PO par lot, ou perdrait tous les lots sauf un.

L'en-tete porte donc la liste des lots concernes, deduite de ses lignes.
"""
import re

from odoo import api, fields, models

# Jetons plausibles d'une reference de lot dans un champ "origin" libre.
ORIGIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_/\-]+")

#: Prefixe de la ligne de description qui porte le lot. Il sert a deux
#: choses : le magasin le lit sur le bon imprime, et nous le reconnaissons
#: pour le remplacer au lieu de l'empiler quand le lot change.
PREFIXE_LOT = "Lot : "


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication",
        compute="_compute_lot_fabrication_id",
        store=True,
        readonly=False,
        index="btree_not_null",
        ondelete="set null",
        help="Lot a l'origine de ce besoin. Renseigne automatiquement quand "
        "la ligne provient d'un OF du lot, modifiable manuellement.",
    )

    @api.depends(
        "move_dest_ids.raw_material_production_id.lot_fabrication_id",
        "order_id.origin",
    )
    def _compute_lot_fabrication_id(self):
        Lot = self.env["fma.lot.fabrication"]
        for line in self:
            # 1. Via les mouvements de destination -> OF -> lot, en remontant
            #    les OF de proche en proche.
            lot = line._lot_par_chainage(line.move_dest_ids)

            # 2. Repli : la reference de lot figure dans l'origine du PO. Les
            #    regles de reappro y recopient la reference de l'OF ou du lot
            #    selon les configurations.
            if not lot and line.order_id.origin:
                jetons = ORIGIN_TOKEN_RE.findall(line.order_id.origin)
                if jetons:
                    lot = Lot.search(
                        [
                            ("name", "in", jetons),
                            ("company_id", "=", line.order_id.company_id.id),
                        ],
                        limit=1,
                    )

            # Une affectation manuelle fait foi. L'affectation est
            # inconditionnelle : un compute stocke doit donner une valeur a
            # CHAQUE enregistrement, sans quoi Odoo leve « failed to assign ».
            line.lot_fabrication_id = line.lot_fabrication_id or lot

        # Le lot vient parfois APRES la creation de la ligne : le mouvement
        # qui le porte n'est rattache qu'ensuite. C'est pour cela que la
        # description se repose ici et pas seulement a la creation.
        self._fma_poser_lot_en_description()

    # ------------------------------------------------------------------
    # Le lot, ecrit dans la description de la ligne
    # ------------------------------------------------------------------
    def _fma_description_sans_lot(self, texte):
        """``texte`` debarrasse de la ligne de lot qu'on y aurait deja mise.

        Sans cela, un lot reaffecte empilerait les mentions au lieu de
        corriger la premiere.
        """
        lignes = [
            ligne for ligne in (texte or "").splitlines()
            if not ligne.strip().startswith(PREFIXE_LOT)
        ]
        return "\n".join(lignes).rstrip()

    def _fma_poser_lot_en_description(self):
        """Ajoute le lot a la description de la ligne d'achat.

        La designation de l'article ne suffit pas au magasin : elle dit CE
        QUI est commande, pas POUR QUEL LOT. Deux lots d'une meme affaire
        commandent la meme quincaillerie, et le bon de commande regroupe les
        deux — sans cette mention, rien sur le document ne permet de repartir
        ce qui arrive.

        On ne touche qu'a NOTRE ligne : tout ce que l'acheteur a saisi
        au-dessus est conserve tel quel. Et on n'ecrit que si le texte change
        reellement, pour ne pas rouvrir en boucle les lignes a chaque
        recalcul du lot.
        """
        for ligne in self:
            base = ligne._fma_description_sans_lot(ligne.name)
            if ligne.lot_fabrication_id:
                attendu = "%s\n%s%s" % (
                    base, PREFIXE_LOT, ligne.lot_fabrication_id.display_name)
            else:
                attendu = base
            if attendu != (ligne.name or ""):
                ligne.name = attendu

    @api.model_create_multi
    def create(self, vals_list):
        lignes = super().create(vals_list)
        # Lire le lot force le calcul stocke s'il est encore en attente.
        lignes.lot_fabrication_id
        lignes._fma_poser_lot_en_description()
        return lignes

    def write(self, vals):
        res = super().write(vals)
        # Une reaffectation manuelle du lot doit se voir sur le document.
        # Pas de recursion : la pose n'ecrit que « name ».
        if "lot_fabrication_id" in vals:
            self._fma_poser_lot_en_description()
        return res


    #: Profondeur de remontee des ordres de fabrication. Trois niveaux
    #: couvrent largement le cas reel — quincaillerie, assemblage — et bornent
    #: une chaine qu'un parametrage pourrait refermer sur elle-meme.
    PROFONDEUR_CHAINAGE = 3

    def _lot_par_chainage(self, moves):
        """Le lot au bout de la chaine des ordres de fabrication.

        L'achat n'alimente pas toujours directement l'OF qui porte le lot. Un
        sous-ensemble s'intercale : la quincaillerie achetee entre dans l'OF
        du kit, dont le produit fini entre dans l'OF d'assemblage, et c'est
        CELUI-LA qui appartient au lot. Une remontee d'un seul niveau ne
        trouvait rien, et le bon de commande sortait sans lot — constate sur
        P28117.

        On remonte donc : les OF alimentes par ces mouvements, puis ce que
        leurs produits finis alimentent a leur tour, jusqu'a rencontrer un lot.
        """
        Lot = self.env["fma.lot.fabrication"]
        vus = set()
        profondeur = self.PROFONDEUR_CHAINAGE
        while moves and profondeur:
            ordres = moves.raw_material_production_id
            lot = ordres.lot_fabrication_id[:1]
            if lot:
                return lot
            ordres = ordres.filtered(lambda p: p.id not in vus)
            if not ordres:
                break
            vus |= set(ordres.ids)
            # Ce que ces OF produisent alimente peut-etre un OF du lot.
            moves = ordres.move_finished_ids.move_dest_ids
            profondeur -= 1
        return Lot


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    lot_fabrication_ids = fields.Many2many(
        "fma.lot.fabrication",
        string="Lots de fabrication",
        compute="_compute_lot_fabrication_ids",
        store=True,
        help="Lots dont ce bon de commande couvre les besoins.",
    )

    @api.depends("order_line.lot_fabrication_id")
    def _compute_lot_fabrication_ids(self):
        for order in self:
            order.lot_fabrication_ids = order.order_line.lot_fabrication_id

    # Ancien lien d'en-tete. Conserve declare et retire des ecrans : il ne
    # pouvait porter qu'un lot, ce qui interdisait le regroupement des achats.
    # Sa suppression viendra dans une version ulterieure — retirer un champ et
    # sa reference en vue dans la meme mise a jour fait echouer le
    # deploiement, les vues etant validees une par une.
    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication (obsolète)",
        index="btree_not_null",
        ondelete="set null",
    )

    def _fma_vals_bon_lot(self):
        """L'en-tete d'un bon jumeau, pour accueillir les lignes d'un lot.

        Champ par champ, et non un copy() : copier un bon de commande
        duplique ses lignes, or on veut precisement un bon VIDE ou deplacer
        les lignes existantes. Les champs nommes sont ceux qui engagent le
        fournisseur et ceux qui pilotent la reception.
        """
        self.ensure_one()
        vals = {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "date_order": self.date_order,
            "origin": self.origin,
            "partner_ref": self.partner_ref,
            "user_id": self.user_id.id,
            "picking_type_id": self.picking_type_id.id,
            "payment_term_id": self.payment_term_id.id,
            "fiscal_position_id": self.fiscal_position_id.id,
            "dest_address_id": self.dest_address_id.id,
        }
        # Les champs de rattachement FMA, sans lesquels l'achat sortirait des
        # ecrans de suivi de l'affaire. Lus avec precaution : ils viennent de
        # modules qui ne sont pas tous installes partout.
        for nom in ("x_studio_projet_du_so", "fma_sale_order_id"):
            valeur = self[nom] if nom in self._fields else False
            if valeur:
                vals[nom] = valeur.id if hasattr(valeur, "id") else valeur
        return vals

    def action_view_lot_fabrication(self):
        self.ensure_one()
        lots = self.lot_fabrication_ids
        if not lots:
            return False
        action = {
            "type": "ir.actions.act_window",
            "name": "Lots de fabrication",
            "res_model": "fma.lot.fabrication",
        }
        if len(lots) == 1:
            action.update({"res_id": lots.id, "view_mode": "form"})
        else:
            action.update({
                "domain": [("id", "in", lots.ids)],
                "view_mode": "list,form",
            })
        return action
