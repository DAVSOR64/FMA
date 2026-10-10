# -*- coding: utf-8 -*-
"""Rattachement des ordres de fabrication a leur lot.

Les OF d'un meme lot sont relies par ``lot_fabrication_id`` (la reference de
lot) et non par le chainage parent/enfant natif : c'est ce qui permet de
regrouper 1 OF Debit + N OF Assemblage dans une seule vue, quel que soit le
mode de reapprovisionnement.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication",
        copy=False,
        index=True,
        ondelete="set null",
        help="Lot regroupant cet OF avec les autres OF de la meme serie.",
    )
    lot_production_type = fields.Selection(
        [
            ("debit", "Debit"),
            ("quincaillerie", "Quincaillerie"),
            ("assemblage", "Assemblage"),
        ],
        string="Type dans le lot",
        copy=False,
        index=True,
        help="Debit : 1 par lot, consomme les profiles. "
        "Quincaillerie : 1 par ligne, produit le kit, sans operation. "
        "Assemblage : 1 par ligne, point de declaration de fabrication.",
    )

    # Ce que l'OF de debit fabrique, en clair. Un OF ne porte qu'UN article :
    # sur un debit c'est « Debit du lot », generique, et sa quantite est le
    # nombre de menuiseries du lot ; les ensembles debites, un par repere,
    # sortent en sous-produits. Cette ligne donne le detail sans avoir a
    # ouvrir l'onglet.
    #
    # Les ordres generes avant la 1.60 gardent l'ancienne forme : l'article
    # est l'ensemble debite du PREMIER repere et la quantite la sienne (« 8 »
    # pour 8 chassis A TG d'un lot de 10), les autres reperes en
    # sous-produits. La ligne y est d'autant plus utile.
    fma_contenu_debit = fields.Char(
        string="Contenu du débit",
        compute="_compute_fma_contenu_debit",
        help="Les menuiseries debitees par cet ordre : le lot entier, repere "
        "par repere. La quantite a produire de l'ordre est le nombre de "
        "menuiseries du lot ; chaque repere sort en sous-produit. Sur un "
        "ordre genere avant ce fonctionnement, elle n'est que celle du "
        "premier repere.",
    )

    @api.depends("lot_production_type", "lot_fabrication_id.line_ids.product_qty",
                 "lot_fabrication_id.line_ids.product_id")
    def _compute_fma_contenu_debit(self):
        for of in self:
            lignes = of.lot_fabrication_id.line_ids
            if of.lot_production_type != "debit" or not lignes:
                of.fma_contenu_debit = False
                continue
            morceaux = []
            for ligne in lignes:
                reference = ligne.product_id.default_code or ligne.product_id.name or "?"
                # Le repere est la fin de la reference : « <affaire>_<repere> ».
                repere = reference.split("_", 1)[1] if "_" in reference else reference
                quantite = ligne.product_qty or 0.0
                morceaux.append("%s × %s" % (
                    repere.strip(),
                    int(quantite) if float(quantite).is_integer() else quantite))
            total = sum(lignes.mapped("product_qty"))
            of.fma_contenu_debit = "Lot de %s menuiserie%s : %s" % (
                int(total) if float(total).is_integer() else total,
                "s" if total > 1 else "",
                ", ".join(morceaux))
    lot_line_id = fields.Many2one(
        "fma.lot.fabrication.line",
        string="Ligne de lot",
        copy=False,
        ondelete="set null",
    )
    lot_sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de commande",
        copy=False,
        index=True,
        ondelete="set null",
    )
    lot_sale_order_id = fields.Many2one(
        related="lot_sale_line_id.order_id",
        string="Commande liee",
        store=True,
    )

    # ------------------------------------------------------------------
    # Composants ajoutes hors nomenclature
    # ------------------------------------------------------------------
    def _lot_move_vals(self, product, qty, uom=None):
        """Valeurs d'un composant ajoute hors nomenclature.

        On delegue a ``_get_move_raw_values``, la methode native qui construit
        les composants d'un OF : elle gere l'emplacement de production, la
        methode d'approvisionnement, l'entrepot et les dates, et elle suit les
        renommages de champs de ``stock.move`` d'une version a l'autre.
        """
        self.ensure_one()
        vals = self._get_move_raw_values(product, qty, uom or product.uom_id)
        if self.origin:
            vals["origin"] = self.origin
        return vals

    def _add_debit_component(self, product_debit, qty):
        """Ajoute l'ensemble debite du lot aux composants de l'OF assemblage.

        C'est le lien matiere entre l'OF Debit (qui produit l'ensemble) et
        l'OF Assemblage (qui le consomme).

        La nomenclature de la menuiserie porte desormais son propre ensemble
        debite : dans le cas courant, le composant est deja la et il n'y a
        rien a ajouter. On ne se contente pas de comparer l'article, on
        regarde s'il y a DEJA un ensemble debite, quel qu'il soit : un lot
        importe avant que chaque ligne ne porte le sien pointe encore vers
        l'ensemble generique, et on en consommerait deux.
        """
        self.ensure_one()
        if not product_debit or not qty:
            return self.env["stock.move"]
        already = self.move_raw_ids.filtered(
            lambda m: m.product_id == product_debit
            or m.product_id.fma_semi_fini == "debit"
        )
        if already:
            return already
        return self.env["stock.move"].create(
            self._lot_move_vals(product_debit, qty)
        )

    def _add_debit_byproduct(self, product, qty, cost_share=0.0):
        """Ajoute un ensemble debite en SOUS-PRODUIT de l'OF de debit.

        Un ordre de fabrication ne produit qu'un article, or une seance de
        debit en sort autant qu'il y a de reperes dans le lot : les barres
        sont mutualisees, les coupes ne le sont pas. L'article de l'ordre est
        « Debit du lot », et chaque repere est un sous-produit. C'est
        exactement ce que le mecanisme natif decrit — plusieurs sorties pour
        une meme consommation.

        ``cost_share`` : la part, en pourcent, du cout de l'ordre — les
        barres — que ce sous-produit emporte. Le lot la calcule au prorata
        des metres de profile (cf. _parts_de_cout_debit).

        Un sous-produit deja present est rendu tel quel : ni sa quantite ni
        sa part ne sont reecrites.
        """
        self.ensure_one()
        if not product or not qty:
            return self.env["stock.move"]
        deja = self.move_finished_ids.filtered(
            lambda m: m.product_id == product and m.state != "cancel"
        )
        if deja:
            return deja
        vals = self._get_move_finished_values(
            product.id, qty, product.uom_id.id
        )
        vals["cost_share"] = cost_share or 0.0
        # Un sous-produit ne reprend pas la destination de l'article de
        # l'ordre : il ne va pas a ce qui attendrait « Debit du lot ».
        vals["move_dest_ids"] = []
        # IL VA EN PRE-FAB, PAS AU STOCK. Les barres coupees ne repartent
        # jamais en magasin : elles restent au pied du banc jusqu'a
        # l'assemblage. Les deposer au stock obligeait a les en ressortir par
        # un transfert date SIX JOURS AVANT que le debit les produise — d'ou
        # une ligne « Pas disponible » sur le bon de sortie matiere, puis du
        # negatif en Pre-Fab a l'assemblage pendant que la quantite restait
        # en stock. On les depose la ou l'assemblage viendra les chercher.
        prefab = self._emplacement_assemblage()
        if prefab:
            vals["location_dest_id"] = prefab.id
        if self.origin:
            vals["origin"] = self.origin
        return self.env["stock.move"].create(vals)

    def _emplacement_assemblage(self):
        """La ou les ordres d'assemblage du lot prennent leurs composants.

        On la lit sur les ordres eux-memes plutot que de la nommer : le lot
        peut vivre dans n'importe quel entrepot — LRE, REM — et chacun a sa
        propre Pre-Fab. Sans ordre d'assemblage encore cree, on ne devine
        rien et l'appelant garde la destination par defaut.
        """
        self.ensure_one()
        lot = self.lot_fabrication_id
        if not lot:
            return self.env["stock.location"]
        assemblages = lot.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state != "cancel"
        )
        return assemblages[:1].location_src_id

    def _cal_price(self, consumed_moves):
        """Le cout de l'OF de debit va a ses sous-produits, quoi qu'il arrive.

        Odoo repartit le cout d'un ordre entre ses sous-produits selon leur
        part (``cost_share``) — mais seulement quand l'article de l'ordre est
        valorise au cout moyen ou en FIFO. Sinon il s'arrete avant : l'article
        de l'ordre prend son cout standard et les sous-produits ne recoivent
        rien.

        Or l'article d'un OF de debit est « Debit du lot », une etiquette sans
        categorie de valorisation particuliere : sur une base au cout
        standard par defaut, les barres consommees ne seraient portees par
        aucun ensemble debite, et les menuiseries sortiraient sans leur
        profile. On applique donc ici la meme repartition que le natif, avec
        le meme cout — composants, postes de charge, cout additionnel.

        Sans effet si le natif a deja reparti, sur un ordre qui n'est pas un
        debit, ou sans la valorisation de stock.
        """
        res = super()._cal_price(consumed_moves)
        try:
            self._fma_valoriser_sous_produits_debit(consumed_moves)
        except Exception:  # noqa: BLE001 — la cloture de l'ordre prime
            _logger.exception(
                "Valorisation des sous-produits de %s", self.display_name)
        return res

    def _fma_valoriser_sous_produits_debit(self, consumed_moves):
        self.ensure_one()
        Move = self.env["stock.move"]
        if (self.lot_production_type != "debit"
                or "cost_method" not in self.product_id._fields
                or "value" not in Move._fields
                or "price_unit" not in Move._fields):
            return
        if self.product_id.cost_method in ("fifo", "average"):
            return  # le natif vient de le faire
        sous_produits = self.move_byproduct_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
            and m.quantity > 0 and m.cost_share > 0
        )
        if not sous_produits:
            return
        principal = self.move_finished_ids.filtered(
            lambda m: m.product_id == self.product_id
            and m.state not in ("done", "cancel") and m.quantity > 0
        )[:1]
        cout = sum(move.value for move in consumed_moves)
        for operation in self.workorder_ids:
            if hasattr(operation, "_cal_cost"):
                cout += operation._cal_cost()
        if principal and "extra_cost" in self._fields:
            cout += self.extra_cost * principal.product_uom._compute_quantity(
                principal.quantity, principal.product_id.uom_id)
        for move in sous_produits:
            if move.product_id.cost_method not in ("fifo", "average"):
                continue
            quantite = move.product_uom._compute_quantity(
                move.quantity, move.product_id.uom_id)
            if quantite:
                move.price_unit = cout * move.cost_share / 100.0 / quantite

    def _add_lot_material_moves(self, material_lines):
        """Alimente les composants de l'OF Debit depuis le besoin matiere."""
        self.ensure_one()
        Move = self.env["stock.move"]
        moves = Move.browse()
        existing = self.move_raw_ids.mapped("product_id")
        for line in material_lines:
            if line.product_id in existing:
                continue
            moves |= Move.create(
                self._lot_move_vals(
                    line.product_id, line.product_qty, line.product_uom_id
                )
            )
        return moves

    def _autoconfirm_production(self):
        """Un composant ajoute sur un ordre du lot rejoint la sortie du lot.

        C'est par ici que passe TOUT ajout de composant sur un ordre deja
        confirme — une ligne dans l'onglet Composants comme le bouton
        « Ajouter un besoin » : le standard confirme le nouveau mouvement et
        lance son approvisionnement. On laisse faire, puis on range le
        prelevement cree dans le bon de sortie du lot.

        On ne se declenche que s'il y a reellement un composant en brouillon
        a confirmer : la methode est aussi appelee a chaque modification des
        operations.
        """
        # Releve AVANT super() : la confirmation peut fondre un mouvement
        # dans un autre et le supprimer, on ne pourrait plus le lire apres.
        par_lot = {}
        for production in self:
            lot = production.lot_fabrication_id
            if not lot or production.state in ("done", "cancel"):
                continue
            nouveaux = production.move_raw_ids.filtered(
                lambda m: m.state == "draft")
            if nouveaux:
                par_lot[lot] = par_lot.get(
                    lot, self.env["stock.move"]) | nouveaux
        res = super()._autoconfirm_production()
        for lot, nouveaux in par_lot.items():
            lot._apres_ajout_composant(nouveaux)
        return res

    # ------------------------------------------------------------------
    # Reliquats
    # ------------------------------------------------------------------
    def _get_backorder_mo_vals(self):
        """Le reliquat reste dans le lot.

        Declarer une menuiserie sur un OF de dix cree un reliquat de neuf, par
        copie. Or tous les champs du lot sont en copy=False — a raison : un OF
        duplique a la main ne doit pas se retrouver dans le lot d'origine. Mais
        le reliquat, lui, EST le meme travail : sans ce report, les neuf
        menuiseries restantes sortaient du lot, de son etat, de sa vue et de sa
        planification.
        """
        vals = super()._get_backorder_mo_vals()
        vals.update(
            {
                "lot_fabrication_id": self.lot_fabrication_id.id,
                "lot_production_type": self.lot_production_type,
                "lot_line_id": self.lot_line_id.id,
                "lot_sale_line_id": self.lot_sale_line_id.id,
            }
        )
        return vals

    # ------------------------------------------------------------------
    # Propagation d'etat vers le lot
    # ------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            lots = self.mapped("lot_fabrication_id")
            if lots:
                lots._check_production_done()
        return res

    def action_view_lot_fabrication(self):
        self.ensure_one()
        if not self.lot_fabrication_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Lot de fabrication"),
            "res_model": "fma.lot.fabrication",
            "res_id": self.lot_fabrication_id.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------
    # Replanification d'un OF de debit : le lot entier suit
    # ------------------------------------------------------------------
    def _lot_contexte_debit(self):
        """(lot, assemblages, decalage) quand CET OF est le debit d'un lot.

        Le decalage ne se mesure PAS entre la fin de fab demandee et
        ``date_finished`` : poser la fin de fab recale l'OF immediatement, si
        bien que les deux sont deja egales quand on arrive ici. Le decalage
        valait donc toujours zero et aucun assemblage ne suivait jamais le
        debit — constate sur LRE/LRE/04950, avance du 13 au 11 novembre, dont
        l'assemblage etait reste au 20.

        On le mesure sur l'ecart a la regle de chainage du lot, la seule qui
        ne depende d'aucun etat perdu : **le debit finit la veille ouvree du
        premier assemblage** (cf. _chainer_debit_et_assemblage). La veille
        ouvree du premier assemblage tel qu'il est place aujourd'hui dit ou le
        debit devrait finir ; l'ecart avec la ou il finit vraiment est ce dont
        les assemblages doivent bouger. Avancer le debit les avance, le
        retarder les retarde, et un lot deja chaine donne zero.

        Le repli sur l'ancienne mesure sert aux lots dont aucun assemblage
        n'est encore place : sans date de debut, il n'y a pas de veille a
        comparer.
        """
        vide = (self.env["fma.lot.fabrication"],
                self.env["mrp.production"], timedelta(0))
        if self.lot_production_type != "debit" or not self.lot_fabrication_id:
            return vide
        demandee = self._date_fin_de_fab()
        if not demandee:
            return vide
        assemblages = self.lot_fabrication_id.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state not in ("done", "cancel")
        )
        return self.lot_fabrication_id, assemblages, self._decalage_du_debit(
            demandee, assemblages)

    def _decalage_du_debit(self, demandee, assemblages):
        """De combien les assemblages doivent suivre la fin de fab du debit.

        Les deux bornes sont ramenees au calendrier du poste avant d'etre
        soustraites. « Fin de fab » peut tomber un jour chome — c'etait le cas
        du 11 novembre sur LRE/LRE/04950 — et l'atelier debite alors la veille
        ouvree. Comparer la date saisie plutot que le jour reellement travaille
        donnerait un decalage faux d'un jour.
        """
        self.ensure_one()
        debuts = [d for d in assemblages.mapped("date_start") if d]
        # mrp_capacity_planning n'est pas une dependance declaree de ce
        # module : sans lui, pas de calendrier de poste, donc pas de veille
        # ouvree a comparer.
        if debuts and hasattr(self, "_previous_working_day"):
            premier = fields.Datetime.to_datetime(min(debuts)).date()
            poste = self.workorder_ids[-1:].workcenter_id
            veille = self._previous_working_day(premier, poste)
            reelle = self._previous_or_same_working_day(demandee, poste)
            return (reelle or demandee) - veille
        if self.date_finished:
            return demandee - fields.Datetime.to_datetime(
                self.date_finished).date()
        return timedelta(0)

    def _build_replan_preview_payload(self):
        """Controle la livraison sur les ASSEMBLAGES, pas sur le debit.

        Le controle natif compare la fin de fab de CET OF a la date de
        livraison. Sur un debit, c'est sans objet : le debit ne se livre pas.
        On peut le pousser jusqu'au jour de la livraison et le voir passer au
        vert, alors que les assemblages qu'il alimente tombent forcement
        apres — le retard est reel, et personne ne le signale.

        Ce qui compte, c'est la fin de fab des menuiseries. On les controle
        donc a leur date projetee, avec la meme regle et le meme blocage que
        partout ailleurs, et on les montre dans le popup pour que la decision
        se prenne sur des dates, pas sur une intuition.
        """
        payload = super()._build_replan_preview_payload()
        lot, assemblages, decalage = self._lot_contexte_debit()
        if not lot or not assemblages:
            return payload

        # Meme controle que la replanification au niveau du lot : une date de
        # livraison introuvable bloque, un depassement aussi. La fin visee du
        # debit lui sert a repousser les assemblages qui le precederaient.
        fin_debit = self._date_fin_de_fab()
        lot._controler_livraison(assemblages, decalage, fin_debit)

        lignes = []
        for mo in assemblages.sorted(lambda m: m.name or ""):
            projetee = lot._fin_projetee(mo, decalage, fin_debit)
            cible, _commande = mo._get_macro_target_date()
            lignes.append({
                "name": mo.display_name or "",
                "fin": projetee.strftime("%d/%m/%Y") if projetee else "-",
                "livraison": (
                    fields.Datetime.to_datetime(cible).strftime("%d/%m/%Y")
                    if cible else "-"),
            })
        payload["fma_assemblages"] = lignes
        payload["fma_decalage"] = decalage.days
        payload["fma_fin_debit"] = fin_debit.strftime("%d/%m/%Y")
        return payload

    def _render_replan_preview_html(self, payload):
        """Ajoute au popup les assemblages qui vont suivre le debit."""
        html = super()._render_replan_preview_html(payload)
        lignes = payload.get("fma_assemblages")
        if not lignes:
            return html
        rangs = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (l.get("name", ""), l.get("fin", "-"), l.get("livraison", "-"))
            for l in lignes
        )
        return html + """
            <h4 style="margin-top:12px">Assemblages du lot — debit fini le %s</h4>
            <table class="table table-sm">
                <thead><tr>
                    <th>OF</th><th>Fin de fab projetee</th>
                    <th>Livraison client</th>
                </tr></thead>
                <tbody>%s</tbody>
            </table>
            <div style="color:#666;font-size:90%%">
                Les bons d'achat ne sont pas deplaces : une date de reception
                se negocie avec le fournisseur.
            </div>
        """ % (payload.get("fma_fin_debit", "-"), rangs)

    def _dire_pourquoi_rien_a_decaler(self, lot):
        """Trace la raison pour laquelle aucun assemblage n'a suivi le debit.

        Trois cas, et ils n'appellent pas la meme suite : l'ordre n'est pas un
        debit, il n'appartient a aucun lot, ou le lot n'a pas d'assemblage
        actif rattache. Le dernier est le plus courant et le moins visible —
        les assemblages existent, mais sans lot_fabrication_id, donc le lot ne
        les voit pas.
        """
        self.ensure_one()
        if self.lot_production_type != "debit":
            raison = _("cet ordre n'est pas un debit de lot")
        elif not self.lot_fabrication_id:
            raison = _("cet ordre n'est rattache a aucun lot")
        elif not lot:
            raison = _("la fin de fab n'est pas renseignee sur le debit")
        else:
            total = len(lot.production_ids.filtered(
                lambda p: p.lot_production_type == "assemblage"))
            raison = _(
                "le lot %(lot)s ne porte aucun assemblage actif "
                "(%(total)s rattache(s), tous termines ou annules)",
                lot=lot.display_name, total=total,
            )
        corps = _("Replanification : aucun assemblage decale — %(raison)s.",
                  raison=raison)
        self.message_post(body=corps)
        if lot:
            lot.message_post(body=corps)

    def action_apply_replan_preview(self, payload=None):
        """Applique au debit, puis entraine les assemblages et la matiere.

        Le decalage est mesure AVANT que super() n'ecrive : apres, l'ancienne
        date n'existe plus et on ne saurait plus de combien on a bouge.

        Les achats ne suivent pas, volontairement — cf. _achats_a_revoir.
        """
        lot, assemblages, decalage = self._lot_contexte_debit()
        resultat = super().action_apply_replan_preview(payload=payload)
        if not lot or not assemblages:
            # Silence jusqu'ici : replanifier le debit n'entrainait rien et
            # rien ne disait pourquoi. On le dit, sur l'ordre et sur le lot,
            # avec ce qui a ete regarde — c'est la seule facon de distinguer
            # « il n'y avait rien a decaler » d'un defaut.
            self._dire_pourquoi_rien_a_decaler(lot)
            return resultat

        deplaces = lot._decaler_assemblages(assemblages, decalage, self)
        depart_matiere = lot._planifier_sortie_matiere(self)
        # Le besoin a bouge : les achats encore en brouillon suivent. Ceux
        # qui sont partis chez le fournisseur ne bougent pas — ils sont
        # NOMMES dans le compte rendu, et c'est a l'achat de negocier.
        lot._recaler_dates_achat()
        lot._rendre_compte_replanification(
            self, decalage, deplaces, depart_matiere, lot._achats_a_revoir())
        return resultat
