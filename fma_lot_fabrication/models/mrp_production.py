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

    # Ce que l'OF de debit fabrique, en clair. Un OF ne porte qu'UN article
    # principal : sur un debit c'est l'ensemble debite du premier repere du
    # lot, avec sa quantite (« 8 » pour 8 chassis A TG), et les autres reperes
    # sortent en sous-produits. La quantite affichee n'est donc ni un nombre
    # de barres ni le nombre de menuiseries du lot — d'ou cette ligne.
    fma_contenu_debit = fields.Char(
        string="Contenu du débit",
        compute="_compute_fma_contenu_debit",
        help="Les menuiseries debitees par cet ordre : le lot entier. La "
        "quantite a produire de l'ordre n'est que celle du premier repere ; "
        "les autres figurent dans les sous-produits.",
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

    def _add_debit_byproduct(self, product, qty):
        """Ajoute un ensemble debite en SOUS-PRODUIT de l'OF de debit.

        Un ordre de fabrication ne produit qu'un article, or une seance de
        debit en sort autant qu'il y a de reperes dans le lot : les barres
        sont mutualisees, les coupes ne le sont pas. Le premier repere est
        l'article produit, les autres sont des sous-produits. C'est
        exactement ce que le mecanisme natif decrit — plusieurs sorties pour
        une meme consommation.
        """
        self.ensure_one()
        if not product or not qty:
            return self.env["stock.move"]
        deja = self.move_finished_ids.filtered(
            lambda m: m.product_id == product
        )
        if deja:
            return deja
        vals = self._get_move_finished_values(
            product.id, qty, product.uom_id.id
        )
        if self.origin:
            vals["origin"] = self.origin
        return self.env["stock.move"].create(vals)

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

        Le decalage se mesure entre la fin de fab demandee et celle que l'OF
        porte aujourd'hui. Il vaut zero tant que rien n'a ete saisi.
        """
        vide = (self.env["fma.lot.fabrication"],
                self.env["mrp.production"], timedelta(0))
        if self.lot_production_type != "debit" or not self.lot_fabrication_id:
            return vide
        demandee = self._date_fin_de_fab()
        if not demandee:
            return vide
        decalage = timedelta(0)
        if self.date_finished:
            decalage = demandee - fields.Datetime.to_datetime(
                self.date_finished).date()
        assemblages = self.lot_fabrication_id.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state not in ("done", "cancel")
        )
        return self.lot_fabrication_id, assemblages, decalage

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

    def action_apply_replan_preview(self, payload=None):
        """Applique au debit, puis entraine les assemblages et la matiere.

        Le decalage est mesure AVANT que super() n'ecrive : apres, l'ancienne
        date n'existe plus et on ne saurait plus de combien on a bouge.

        Les achats ne suivent pas, volontairement — cf. _achats_a_revoir.
        """
        lot, assemblages, decalage = self._lot_contexte_debit()
        resultat = super().action_apply_replan_preview(payload=payload)
        if not lot or not assemblages:
            return resultat

        deplaces = lot._decaler_assemblages(assemblages, decalage, self)
        depart_matiere = lot._planifier_sortie_matiere(self)
        lot._rendre_compte_replanification(
            self, decalage, deplaces, depart_matiere, lot._achats_a_revoir())
        return resultat
