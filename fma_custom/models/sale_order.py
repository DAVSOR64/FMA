# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rules migrated from Odoo Studio automations / server actions.

Origin (Studio):
- base.automation "Bloquer la confirmation de devis si pas de CGV et RIB"
- base.automation "Client bloqué"
- base.automation "MAJ Champs Mtt A facturer"
- ir.actions.server "Recalculer 'Restant HT (pivot)'" (button)
- ir.actions.server "Calcul PRI" (button, id 1214) and its orphan batch
  variant (id 1215, never bound to a cron or a button) -> merged here into
  one engine with both a button and a cron entry point.
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
import datetime
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

VITRAGE_CATEG_NAMES = ("all vitrage", "All / 02_REMPLISSAGE")

FIELD_ACHAT_MATIERE = "so_achat_matiere_reel"
FIELD_ACHAT_VITRAGE = "so_achat_vitrage_reel"
FIELD_COUT_APPRO_AFFAIRE = "x_studio_so_cout_appro_affaire"
FIELD_COUT_APPRO_STOCK = "x_studio_so_cout_appro_stock"
FIELD_APPRO_TOTAL = "x_studio_montant_total_appro"
FIELD_APPRO_NOT_DEL_NOT_INV = "x_studio_montant_non_livr_non_factur"
FIELD_APPRO_DEL_NOT_INV = "x_studio_montant_livr_non_factur"
FIELD_APPRO_DEL_INV = "x_studio_montant_livr_factur"

PRI_FIELDS = (
    FIELD_ACHAT_MATIERE,
    FIELD_ACHAT_VITRAGE,
    FIELD_COUT_APPRO_AFFAIRE,
    FIELD_COUT_APPRO_STOCK,
    FIELD_APPRO_TOTAL,
    FIELD_APPRO_NOT_DEL_NOT_INV,
    FIELD_APPRO_DEL_NOT_INV,
    FIELD_APPRO_DEL_INV,
)


def _categ_full_name(categ):
    return categ.complete_name or categ.name or ""


def _is_vitrage(product):
    """Vitrage ou panneau : le remplissage, par opposition a la matiere.

    D'abord par la famille d'approvisionnement de l'article (categorie,
    famille, sous-famille — module d'ordonnancement, s'il est installe), qui
    se regle a l'ecran. Le NOM de la categorie reste accepte, comme avant : il
    ne reconnaissait que deux libelles exacts, et un vitrage range ailleurs
    passait en matiere sans que rien ne le dise.
    """
    modele = product.product_tmpl_id
    if hasattr(modele, "_fma_famille_appro") and modele:
        if modele._fma_famille_appro() in ("vitrage", "panneaux"):
            return True
    categ = product.categ_id
    return _categ_full_name(categ) in VITRAGE_CATEG_NAMES or (categ.name or "") in VITRAGE_CATEG_NAMES


def _line_uom(line):
    """Unite d'une ligne de vente ou d'achat.

    ``product_uom`` y est devenu ``product_uom_id`` en v19 : le calcul du PRI
    s'arretait sur une AttributeError des la premiere ligne. Le nom est
    resolu a l'execution ; stock.move, lui, a garde ``product_uom``.
    """
    if "product_uom_id" in line._fields:
        return line.product_uom_id
    return line.product_uom


def _has_bom(product, env):
    return bool(
        env["mrp.bom"].search(
            ["|", ("product_id", "=", product.id), ("product_tmpl_id", "=", product.product_tmpl_id.id)],
            limit=1,
        )
    )


def _pol_qty_received_or_ordered(pol):
    return pol.qty_received or pol.product_qty or 0.0


def _pol_montant(pol, qty, sale_currency, company):
    """Montant HT d'une ligne d'achat pour ``qty``, en devise de la commande.

    Le prix unitaire est celui du SOUS-TOTAL de la ligne — remise deduite,
    taxes exclues meme quand le prix est saisi TTC — et non ``price_unit``.
    """
    if pol.product_qty:
        unit = pol.price_subtotal / pol.product_qty
    else:
        unit = pol.price_unit * (1.0 - (pol.discount or 0.0) / 100.0)
    if pol.currency_id and pol.currency_id != sale_currency:
        conv_date = pol.order_id.date_order or datetime.date.today()
        unit = pol.currency_id._convert(unit, sale_currency, company, conv_date)
    return unit * qty


def _vers_unite_article(uom, qty, product):
    """``qty`` exprimee dans l'unite de la fiche article.

    Un profile s'achete et se stocke a la barre, sa nomenclature de debit le
    compte au metre : rien ne se compare sans cette conversion. Deux unites
    sans rapport entre elles : on garde la quantite telle quelle plutot que
    d'arreter le calcul.
    """
    if not uom or uom == product.uom_id:
        return qty
    try:
        return uom._compute_quantity(qty, product.uom_id, round=False)
    except Exception:  # noqa: BLE001 — unites incompatibles
        return qty


def _qty_move_consumed(move):
    """Quantite d'un composant d'OF : le consomme, a defaut le besoin.

    Termine : ce qui a ete consomme. Avant : le besoin, ou ce qui est deja
    preleve s'il le depasse. ``quantity`` seul ne suffit pas — sur un OF
    partiellement reserve il ne vaut que la part reservee.
    """
    if move.state == "done":
        return move.quantity or 0.0
    return max(move.product_uom_qty or 0.0, move.quantity or 0.0)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # Prix de revient reel : ce que le calcul laisse a lire
    # ------------------------------------------------------------------
    fma_pri_reel = fields.Monetary(
        string="PRI réel (matière + vitrage)",
        currency_field="currency_id", readonly=True, copy=False,
        help="Achats rattaches a la commande + consommations des articles "
        "non achetes pour elle. Egal a la somme des lignes.",
    )
    fma_pri_date = fields.Datetime(
        string="PRI calculé le", readonly=True, copy=False)
    fma_pri_non_ventile = fields.Monetary(
        string="Dont coûts non ventilés, répartis",
        currency_field="currency_id", readonly=True, copy=False,
        help="Part du PRI qu'aucune ligne de commande ne porte en propre — "
        "achat rattache a la commande que nul ordre de fabrication ne "
        "consomme, ordre de fabrication sans ligne. Elle est repartie sur "
        "les lignes au prorata de leur cout.",
    )
    fma_pri_services = fields.Monetary(
        string="Dont sous-traitance / services",
        currency_field="currency_id", readonly=True, copy=False,
        help="Achats de services rattaches a la commande — sous-traitance, "
        "laquage, pose, transport. Ils sont compris dans « Achat Matière "
        "(Réel) » : la marge brute et la M.C.V. en tiennent compte.",
    )
    fma_cout_mod_odoo = fields.Monetary(
        string="MOD calculée par Odoo",
        currency_field="currency_id", readonly=True, copy=False,
        help="Pointages des ordres de travail des OF de la commande x cout "
        "horaire actuel de l'employe. Valeur au dernier Calcul PRI.",
    )
    fma_cout_mod_ecart = fields.Monetary(
        string="Écart MOD (saisie − calculée)",
        currency_field="currency_id", readonly=True, copy=False,
        help="« Coût MOD (Réel) », qui entre dans la M.C.V., moins la MOD "
        "calculee par Odoo. Nul tant que personne n'a saisi de valeur.",
    )
    fma_achats_non_rattaches_nb = fields.Integer(
        string="Achats du projet non rattachés à une commande",
        readonly=True, copy=False,
        help="Bons de commande confirmes qui portent le projet de cette "
        "commande mais aucune commande client. Ils ne sont comptes dans "
        "AUCUN prix de revient tant qu'ils ne sont pas rattaches (champ "
        "« Commande client » de l'achat). Valeur au dernier calcul.",
    )
    fma_achats_non_rattaches_montant = fields.Monetary(
        string="Montant non rattaché",
        currency_field="currency_id", readonly=True, copy=False)
    # Derniere valeur que le calcul a recopiee dans « Cout MOD (Reel) ». Sert
    # a reconnaitre une saisie manuelle : si le champ ne vaut plus ce qu'on y
    # avait mis, quelqu'un l'a corrige et on n'y touche plus.
    fma_cout_mod_reel_auto = fields.Monetary(
        string="Coût MOD réel recopié",
        currency_field="currency_id", readonly=True, copy=False)

    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._check_studio_client_bloque()
        orders.with_context(skip_studio_sync=True)._sync_studio_montant_a_facturer()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") == "draft":
            self._check_studio_client_bloque()
        if not self.env.context.get("skip_studio_sync"):
            self.with_context(skip_studio_sync=True)._sync_studio_montant_a_facturer()
        return res

    def action_confirm(self):
        for order in self:
            if not order.partner_id.x_studio_cgv_rib:
                raise UserError(
                    _("Impossible de confirmer le devis.\n\nLe client n'a pas validé les CGV + RIB.")
                )
        # Le controle du delai confirme et de la date de BPE est passe en
        # alerte sur la saisie de l'ARC (custom, _onchange_so_date_arc_alerte) :
        # il bloquait ici un geste legitime, l'ARC n'etant pas encore revenu.
        return super().action_confirm()

    def _check_studio_client_bloque(self):
        for order in self:
            if order.state == "draft" and order.partner_id.x_studio_client_bloque:
                raise UserError(_("Impossible de créer un devis.\n\nCe client est bloqué."))

    def _sync_studio_montant_a_facturer(self):
        for order in self:
            if order.so_mtt_facturer_reel != order.amount_untaxed:
                order.so_mtt_facturer_reel = order.amount_untaxed

    def action_recalculer_restant_ht(self):
        """Recalcule le RAF HT.

        Le bouton ne recopie plus rien. Il recopiait le champ Studio
        x_studio_calcul_raf_ht, non stocke, dans le champ stocke — d'ou deux
        valeurs qui divergeaient des que personne n'appuyait dessus.

        Le RAF est desormais un calcul STOCKE : il se tient a jour tout seul
        des que le total de la commande ou ses factures bougent. Le bouton
        reste, parce qu'une action serveur le cite et qu'il rassure, mais il
        ne fait plus que forcer le recalcul.
        """
        orders = self or self.search([])
        if "x_studio_restant_a_facturer_ht_pivot" in orders._fields:
            orders.invalidate_recordset(
                ["x_studio_restant_a_facturer_ht_pivot"])
            orders.modified(["amount_untaxed"])
        return True

    def action_calcul_pri(self):
        """Port of the "Calcul PRI" Studio button (id 1214).

        Au bouton, le calcul rend compte dans le fil de la commande. Le
        planificateur, lui, reste muet : un message par commande et par nuit
        noierait le fil.
        """
        self.with_context(fma_pri_message=True)._compute_pri()
        return True

    @api.model
    def cron_calcul_pri_batch(self):
        """Port of the orphan batch variant of "Calcul PRI" (id 1215):
        recompute PRI for every confirmed/done sale order that has at least
        one non-cancelled manufacturing order referencing it.
        """
        mos = self.env["mrp.production"].search([("state", "!=", "cancel")])
        so_names_with_mo = {mo.origin.strip() for mo in mos if mo.origin}
        sales_to_process = self.search([("state", "in", ("sale", "done"))]).filtered(
            lambda s: s.name in so_names_with_mo
        )
        for order in sales_to_process:
            try:
                order._compute_pri()
                self.env.cr.commit()
            except Exception as e:
                self.env["ir.logging"].sudo().create(
                    {
                        "name": "fma_custom.sale_order",
                        "type": "server",
                        "level": "ERROR",
                        "message": "[Calcul PRI] Erreur sur %s : %s" % (order.name, e),
                        "path": "cron_calcul_pri_batch",
                        "func": "cron_calcul_pri_batch",
                        "line": "0",
                    }
                )
                self.env.cr.rollback()

    # ------------------------------------------------------------------
    # Calcul du prix de revient reel
    # ------------------------------------------------------------------
    #
    # UN SEUL calcul, qui rend deux choses :
    #
    #   (a) les totaux de la commande — matiere, vitrage, appro — ceux que
    #       lit la colonne « Reel » de l'onglet Analyse Financiere ;
    #   (b) leur ventilation par ligne de commande. Ce n'est jamais un second
    #       total : la somme des lignes EST le total, au centime.
    #
    # La regle, a la commande :
    #
    #   PRI = achats RATTACHES a la commande
    #       + consommations des articles NON achetes pour elle, au cout de
    #         la fiche article.
    #
    # Article par article :
    #
    #   besoin  = composants reels des OF de la commande (ajouts manuels
    #             compris) + articles revendus tels quels ;
    #   achats  = lignes d'achat confirmees rattachees a la commande
    #             (champ « Commande client » de l'achat) ;
    #   cout    = montant des achats ; si le besoin depasse la quantite
    #             achetee, l'excedent — pris sur stock — est valorise au
    #             prix moyen de ces achats ; sans aucun achat, besoin x cout
    #             de la fiche.
    #
    # Un article achete ET consomme n'est donc compte qu'une fois, par
    # l'achat. Un article PRODUIT par un OF de la commande — l'ensemble
    # debite « <reference>-DEB », un sous-ensemble — n'est jamais valorise
    # comme composant : sa matiere est deja comptee sur l'OF qui le fabrique.
    #
    # La ventilation :
    #
    #   - le cout d'un article est reparti entre ceux qui le consomment, au
    #     prorata des quantites — la chute et le surplus achete suivent ;
    #   - un OF porte par une ligne de commande (assemblage) lui donne sa
    #     part ;
    #   - un OF sans ligne (le debit du lot) donne la sienne aux lignes dont
    #     les OF consomment ce qu'il produit, au prorata du besoin que la
    #     nomenclature de l'article produit exprime pour CET article : les
    #     metres de profile de « <reference>-DEB », fois la quantite ;
    #   - ce qui n'a pas de ligne est reparti au prorata du cout des lignes,
    #     et le montant ainsi reparti est garde a part pour rester visible.
    # ------------------------------------------------------------------

    #: Types d'article dont un achat NON consomme par un OF entre au PRI.
    #: Les services en font partie : la sous-traitance, le laquage, la pose
    #: achetes pour la commande sont un cout de la commande. Le transport
    #: est traite de meme, faute d'arbitrage ; il s'ecarterait ici ou par
    #: une categorie d'article.
    PRI_TYPES_ACHAT_HORS_OF = ("consu", "service")

    #: Niveaux de nomenclature / d'OF intermediaires traverses.
    PRI_PROFONDEUR = 4

    @api.model
    def _fma_domaine_projet(self, projets):
        """Domaine des commandes d'un projet.

        Le projet du devis vit dans ``project_id`` (natif) depuis la bascule
        19.0.1.0.26 de fma_sale_order_custom ; ``x_studio_projet`` reste lu,
        des commandes anciennes ne portant que lui.
        """
        champs = [c for c in ("project_id", "x_studio_projet") if c in self._fields]
        if not champs or not projets:
            return [("id", "=", 0)]
        return ["|"] * (len(champs) - 1) + [(c, "in", projets.ids) for c in champs]

    def _fma_projets(self):
        self.ensure_one()
        projets = self.env["project.project"]
        for champ in ("project_id", "x_studio_projet"):
            if champ in self._fields:
                projets |= self[champ]
        return projets

    def _pri_ordres_de_fabrication(self):
        """Les OF de la commande, annules exclus.

        Par les liens declares (lot, ligne de vente, references), et par
        l'origine — comparee par JETON entier : « origin ilike A26-01 »
        ramenait aussi les OF de « A26-01/2 », la tranche suivante.
        """
        self.ensure_one()
        Production = self.env["mrp.production"]
        ordres = Production
        if hasattr(self, "_fma_ordres_de_fabrication"):
            ordres |= self._fma_ordres_de_fabrication()
        if self.name:
            motif = re.compile(r"(?:^|[\s,;])%s(?:$|[\s,;])" % re.escape(self.name))
            ordres |= Production.search([("origin", "ilike", self.name)]).filtered(
                lambda o: motif.search(o.origin or ""))
        return ordres.filtered(lambda o: o.state != "cancel")

    def _pri_lignes_achat_des_of(self, ordres):
        """Lignes d'achat qui alimentent ces OF, en remontant les mouvements."""
        Ligne = self.env["purchase.order.line"]
        Move = self.env["stock.move"]
        lignes = Ligne
        a_voir = ordres.move_raw_ids
        vus = set()
        for _niveau in range(6):
            a_voir = a_voir.filtered(lambda m: m.id not in vus)
            if not a_voir:
                break
            vus |= set(a_voir.ids)
            if "purchase_line_id" in Move._fields:
                lignes |= a_voir.purchase_line_id
            if "created_purchase_line_ids" in Move._fields:
                lignes |= a_voir.created_purchase_line_ids
            a_voir = a_voir.move_orig_ids
        if "lot_fabrication_id" in Ligne._fields and "lot_fabrication_id" in ordres._fields:
            lots = ordres.lot_fabrication_id
            if lots:
                lignes |= Ligne.search([("lot_fabrication_id", "in", lots.ids)])
        return lignes

    def _pri_lignes_achat(self, ordres):
        """``(rattachees, non_rattachees)`` : les lignes d'achat confirmees.

        ``rattachees`` : celles dont la commande client est celle-ci. Ce sont
        les seules qui entrent au prix de revient.

        ``non_rattachees`` : celles qui portent le projet de la commande mais
        aucune commande. Elles ne sont ajoutees a aucune tranche ; on les
        signale, pour que quelqu'un les rattache.

        Avant de lire, on rejoue le rattachement automatique sur les achats
        qui n'ont pas encore de commande : ceux du projet et ceux que les OF
        de la commande ont fait naitre. C'est ce qui reprend les achats
        anterieurs au champ, sans migration.
        """
        self.ensure_one()
        Ligne = self.env["purchase.order.line"]
        projets = self._fma_projets()
        a_voir = self._pri_lignes_achat_des_of(ordres).filtered(
            lambda l: not l.fma_sale_order_id)
        if projets:
            a_voir |= Ligne.search([
                ("order_id.x_studio_projet_du_so", "in", projets.ids),
                ("order_id.state", "!=", "cancel"),
                ("fma_sale_order_id", "=", False),
            ])
        if a_voir:
            a_voir._fma_rattacher_commande()

        confirmees = [
            ("order_id.state", "in", ("purchase", "done")),
            ("display_type", "=", False),
            ("product_id", "!=", False),
        ]
        rattachees = Ligne.search(confirmees + [("fma_sale_order_id", "=", self.id)])
        non_rattachees = Ligne
        if projets:
            non_rattachees = Ligne.search(confirmees + [
                ("order_id.x_studio_projet_du_so", "in", projets.ids),
                ("fma_sale_order_id", "=", False),
            ])
        return rattachees, non_rattachees

    def _pri_ligne_de_l_of(self, ordre, lignes):
        """La ligne de commande qu'un OF fabrique, s'il en fabrique une."""
        champs = ordre._fields
        candidates = self.env["sale.order.line"]
        if "lot_sale_line_id" in champs:
            candidates |= ordre.lot_sale_line_id
        if "lot_line_id" in champs:
            candidates |= ordre.lot_line_id.sale_line_id
        if "sale_line_id" in champs:
            candidates |= ordre.sale_line_id
        candidates &= lignes
        if candidates:
            return candidates[0]
        # A defaut de lien : l'article, s'il ne figure que sur une ligne.
        memes = lignes.filtered(lambda l: l.product_id == ordre.product_id)
        return memes if len(memes) == 1 else self.env["sale.order.line"]

    def _pri_eclater_nomenclature(self, product, qty, niveau=0):
        """Besoin theorique d'un article : ses composants de dernier niveau.

        Ne sert qu'aux lignes SANS ordre de fabrication. Renvoie une liste de
        ``(article, quantite dans l'unite de l'article)``, vide si l'article
        n'a pas de nomenclature exploitable.
        """
        Bom = self.env["mrp.bom"]
        bom = Bom._bom_find(product, company_id=self.company_id.id).get(product)
        if not bom or not bom.bom_line_ids:
            return []
        _boms, eclatees = bom.explode(product, qty)
        feuilles = []
        for bom_line, donnees in eclatees:
            article = bom_line.product_id
            q = _vers_unite_article(
                bom_line.product_uom_id, donnees.get("qty", 0.0), article)
            sous = []
            if niveau < self.PRI_PROFONDEUR:
                sous = self._pri_eclater_nomenclature(article, q, niveau + 1)
            feuilles.extend(sous or [(article, q)])
        return feuilles

    def _pri_analyse(self):
        """Le prix de revient de la commande et sa ventilation par ligne.

        Ne modifie rien sur la commande (le rattachement automatique des
        achats excepte) : ``_compute_pri`` ecrit ce que ceci renvoie.
        """
        self.ensure_one()
        order = self
        devise = order.currency_id
        societe = order.company_id
        Bom = self.env["mrp.bom"]

        lignes = order.order_line.filtered(
            lambda l: l.product_id and not l.display_type and l.product_uom_qty > 0)
        ordres = order._pri_ordres_de_fabrication()
        par_id = {o.id: o for o in ordres}
        rattachees, non_rattachees = order._pri_lignes_achat(ordres)

        # ---------------------------------------------------- 1. besoins
        ligne_de = {o.id: order._pri_ligne_de_l_of(o, lignes) for o in ordres}
        fabriques = ordres.product_id | ordres.move_finished_ids.filtered(
            lambda m: m.state != "cancel").product_id

        # produits_de[of] = {article produit: quantite}
        # consommateurs[article] = {of: quantite consommee}
        produits_de, consommateurs = {}, {}
        for ordre in ordres:
            sorties = {}
            for move in ordre.move_finished_ids:
                if move.state == "cancel" or not move.product_id:
                    continue
                q = _vers_unite_article(
                    move.product_uom, _qty_move_consumed(move), move.product_id)
                sorties[move.product_id] = sorties.get(move.product_id, 0.0) + q
            if not sorties and ordre.product_id:
                sorties[ordre.product_id] = ordre.product_qty
            produits_de[ordre.id] = sorties

        # besoins[article] = {porteur: quantite}, porteur = ("sol", id) pour
        # une ligne de commande, ("of", id) pour un OF sans ligne.
        besoins = {}

        def besoin(article, porteur, qty):
            if qty > 0:
                du = besoins.setdefault(article, {})
                du[porteur] = du.get(porteur, 0.0) + qty

        for ordre in ordres:
            sol = ligne_de[ordre.id]
            porteur = ("sol", sol.id) if sol else ("of", ordre.id)
            for move in ordre.move_raw_ids:
                article = move.product_id
                if move.state == "cancel" or not article:
                    continue
                q = _vers_unite_article(
                    move.product_uom, _qty_move_consumed(move), article)
                if q <= 0:
                    continue
                du = consommateurs.setdefault(article.id, {})
                du[ordre.id] = du.get(ordre.id, 0.0) + q
                if article not in fabriques:
                    besoin(article, porteur, q)

        forfaits = []  # (ligne, article, cout) : ni OF ni nomenclature
        for sol in lignes:
            article = sol.product_id
            qty = _vers_unite_article(_line_uom(sol), sol.product_uom_qty, article)
            if not _has_bom(article, self.env):
                # Article revendu tel quel.
                besoin(article, ("sol", sol.id), qty)
                continue
            if article in fabriques:
                continue  # un OF le fabrique : ses composants font foi
            feuilles = order._pri_eclater_nomenclature(article, qty)
            if feuilles:
                for composant, q in feuilles:
                    besoin(composant, ("sol", sol.id), q)
            else:
                forfaits.append((sol, article, article.standard_price * qty))

        # ---------------------------------------------------- 2. achats
        achats = {}
        for pol in rattachees:
            article = pol.product_id
            qty = _pol_qty_received_or_ordered(pol)
            if qty <= 0:
                continue
            a = achats.setdefault(article, {
                "qty": 0.0, "montant": 0.0, "lignes": [], "par_sol": {}, "par_of": {}})
            montant = _pol_montant(pol, qty, devise, societe)
            a["qty"] += _vers_unite_article(_line_uom(pol), qty, article)
            a["montant"] += montant
            a["lignes"].append((pol, montant))
            if pol.fma_sale_line_id in lignes:
                sid = pol.fma_sale_line_id.id
                a["par_sol"][sid] = a["par_sol"].get(sid, 0.0) + montant
            elif ("laquage_production_id" in pol._fields
                    and pol.laquage_production_id.id in par_id):
                # Sous-traitance commandee pour UN ordre de fabrication :
                # elle suit la ligne de commande de cet ordre.
                oid = pol.laquage_production_id.id
                a["par_of"][oid] = a["par_of"].get(oid, 0.0) + montant

        # ---------------------------------------------------- 3. repartition
        besoin_bom = {}

        def besoin_nomenclature(produit, article):
            """Quantite de ``article`` pour UN ``produit``, selon sa nomenclature."""
            cle = (produit.id, article.id)
            if cle not in besoin_bom:
                bom = Bom._bom_find(produit, company_id=societe.id).get(produit)
                total = 0.0
                if bom:
                    for bl in bom.bom_line_ids:
                        if bl.product_id == article:
                            total += _vers_unite_article(
                                bl.product_uom_id, bl.product_qty, article)
                    total /= (bom.product_qty or 1.0)
                besoin_bom[cle] = total
            return besoin_bom[cle]

        def parts(ordre, article, niveau=0, au_besoin=True):
            """Lignes de commande servies par un OF : {id de ligne: part}."""
            sol = ligne_de[ordre.id]
            if sol:
                return {sol.id: 1.0}
            if niveau >= self.PRI_PROFONDEUR:
                return {}
            poids = {}
            for produit, qte_produite in produits_de[ordre.id].items():
                conso = {
                    oid: q for oid, q in consommateurs.get(produit.id, {}).items()
                    if oid != ordre.id
                }
                # Un meme repere peut etre debite dans deux lots : chaque
                # debit ne sert que les assemblages de SON lot.
                if "lot_fabrication_id" in ordre._fields and ordre.lot_fabrication_id:
                    du_lot = {
                        oid: q for oid, q in conso.items()
                        if par_id[oid].lot_fabrication_id == ordre.lot_fabrication_id
                    }
                    conso = du_lot or conso
                total = sum(conso.values())
                if not total:
                    continue
                servi = min(total, qte_produite) if qte_produite else total
                unitaire = besoin_nomenclature(produit, article) if au_besoin else 1.0
                if not unitaire:
                    continue
                for oid, q in conso.items():
                    for sid, part in parts(
                            par_id[oid], article, niveau + 1, au_besoin).items():
                        poids[sid] = poids.get(sid, 0.0) + unitaire * servi * q / total * part
            total = sum(poids.values())
            if not total:
                # L'article n'est cite par aucune nomenclature de ce que l'OF
                # produit (barre ajoutee a la main) : au nombre d'unites.
                return parts(ordre, article, niveau, False) if au_besoin else {}
            return {sid: p / total for sid, p in poids.items()}

        par_sol = {sol.id: {"matiere": 0.0, "vitrage": 0.0} for sol in lignes}
        totaux = {"matiere": 0.0, "vitrage": 0.0}
        sans_ligne = {"matiere": 0.0, "vitrage": 0.0}
        total_affaire = total_stock = total_services = 0.0
        services = []
        appro = {"total": 0.0, "ndni": 0.0, "dni": 0.0, "di": 0.0}
        detail = []

        def poser(classe, porteur, montant, article):
            if porteur and porteur[0] == "sol":
                repartition = {porteur[1]: 1.0}
            elif porteur:
                repartition = parts(par_id[porteur[1]], article)
                if not repartition:
                    # Ni nomenclature ni consommateur : au nombre d'unites.
                    repartition = parts(par_id[porteur[1]], article, 0, False)
            else:
                repartition = {}
            if not repartition:
                sans_ligne[classe] += montant
                return
            for sid, part in repartition.items():
                par_sol[sid][classe] += montant * part

        for article in set(besoins) | set(achats):
            du = besoins.get(article, {})
            n = sum(du.values())
            a = achats.get(article)
            if a and n <= 0 and article.type not in self.PRI_TYPES_ACHAT_HORS_OF:
                continue
            classe = "vitrage" if _is_vitrage(article) else "matiere"
            if a and a["qty"] > 0:
                unitaire = a["montant"] / a["qty"]
                excedent = 0.0
                if float_compare(n, a["qty"], precision_digits=6) > 0:
                    excedent = (n - a["qty"]) * unitaire
                cout = a["montant"] + excedent
                total_affaire += a["montant"]
                total_stock += excedent
                source = "achat"
                if article.type == "service":
                    total_services += a["montant"]
                    services.append((article, a["montant"]))
                for pol, montant in a["lignes"]:
                    appro["total"] += montant
                    recu, facture = pol.qty_received or 0.0, pol.qty_invoiced or 0.0
                    if recu == 0 and facture == 0:
                        appro["ndni"] += montant
                    elif recu > 0 and facture == 0:
                        appro["dni"] += montant
                    elif recu > 0 and facture > 0:
                        appro["di"] += montant
            else:
                unitaire = article.standard_price
                cout = n * unitaire
                total_stock += cout
                source = "fiche"
            totaux[classe] += cout
            detail.append((article, n, a["qty"] if a else 0.0, unitaire, cout, source))
            if n > 0:
                for porteur, q in du.items():
                    poser(classe, porteur, cout * q / n, article)
            else:
                # Achete, consomme par personne : sur la ligne de commande
                # que l'achat designe, sinon sans ligne.
                reste = cout
                for sid, montant in a["par_sol"].items():
                    par_sol[sid][classe] += montant
                    reste -= montant
                for oid, montant in a["par_of"].items():
                    poser(classe, ("of", oid), montant, article)
                    reste -= montant
                if not devise.is_zero(reste):
                    poser(classe, None, reste, article)

        for sol, article, cout in forfaits:
            classe = "vitrage" if _is_vitrage(article) else "matiere"
            totaux[classe] += cout
            total_stock += cout
            par_sol[sol.id][classe] += cout
            detail.append((article, sol.product_uom_qty, 0.0, article.standard_price, cout, "fiche"))

        # ------------------------------------- 4. ce qui n'a pas de ligne
        non_ventile = sans_ligne["matiere"] + sans_ligne["vitrage"]
        if lignes and non_ventile:
            base = {sid: v["matiere"] + v["vitrage"] for sid, v in par_sol.items()}
            if sum(base.values()) <= 0:
                base = {sol.id: sol.price_subtotal for sol in lignes}
            if sum(base.values()) <= 0:
                base = {sol.id: 1.0 for sol in lignes}
            somme = sum(base.values())
            for classe in ("matiere", "vitrage"):
                for sid, poids in base.items():
                    par_sol[sid][classe] += sans_ligne[classe] * poids / somme

        # ------------------------------------- 5. arrondi : lignes = total
        for classe in ("matiere", "vitrage"):
            totaux[classe] = devise.round(totaux[classe])
            if not par_sol:
                continue
            for valeurs in par_sol.values():
                valeurs[classe] = devise.round(valeurs[classe])
            ecart = totaux[classe] - sum(v[classe] for v in par_sol.values())
            if not devise.is_zero(ecart):
                lourde = max(par_sol, key=lambda sid: (par_sol[sid][classe], -sid))
                par_sol[lourde][classe] = devise.round(par_sol[lourde][classe] + ecart)

        montant_non_rattache = 0.0
        for pol in non_rattachees:
            qty = _pol_qty_received_or_ordered(pol)
            montant_non_rattache += _pol_montant(pol, qty, devise, societe)

        return {
            "matiere": totaux["matiere"],
            "vitrage": totaux["vitrage"],
            "affaire": total_affaire,
            "stock": total_stock,
            "appro": appro,
            "par_sol": par_sol,
            "non_ventile": devise.round(non_ventile) if lignes else 0.0,
            "services": devise.round(total_services),
            "detail_services": services,
            "non_rattachees": non_rattachees,
            "montant_non_rattache": devise.round(montant_non_rattache),
            "detail": detail,
            "ordres": ordres,
            "rattachees": rattachees,
        }

    def _pri_recopier_mod(self):
        """Recopie le cout MOD des pointages dans « Cout MOD (Reel) ».

        « Cout MOD (Reel) » entre dans la M.C.V. mais aucun programme ne
        l'ecrivait ; le cout tire des pointages vivait dans un autre onglet.
        On le recopie SEULEMENT si le champ est vide ou s'il vaut encore ce
        que ce calcul y avait mis : une valeur saisie a la main reste.

        Renvoie ``"recopie"``, ``"saisie"`` (valeur manuelle conservee) ou
        ``None`` (le cout des pointages n'existe pas sur cette base).
        """
        self.ensure_one()
        if ("so_cout_mod_reel_odoo" not in self._fields
                or "so_cout_mod_reel" not in self._fields):
            return None
        if hasattr(self, "_fma_recalculer_mod"):
            self._fma_recalculer_mod()
        devise = self.currency_id
        calcule = self.so_cout_mod_reel_odoo or 0.0
        actuel = self.so_cout_mod_reel or 0.0
        dernier = self.fma_cout_mod_reel_auto or 0.0
        if not devise.is_zero(actuel) and devise.compare_amounts(actuel, dernier) != 0:
            return "saisie"
        if devise.compare_amounts(actuel, calcule) != 0 or devise.compare_amounts(dernier, calcule) != 0:
            self.write({"so_cout_mod_reel": calcule, "fma_cout_mod_reel_auto": calcule})
        return "recopie"

    def _compute_pri(self):
        for order in self:
            resultat = order._pri_analyse()
            devise = order.currency_id

            for sol in order.order_line:
                valeurs = resultat["par_sol"].get(sol.id, {"matiere": 0.0, "vitrage": 0.0})
                pri = devise.round(valeurs["matiere"] + valeurs["vitrage"])
                ecrit = {
                    "fma_achat_matiere_reel": valeurs["matiere"],
                    "fma_achat_vitrage_reel": valeurs["vitrage"],
                    "fma_pri_reel": pri,
                    "fma_marge_brute_reelle": (
                        devise.round(sol.price_subtotal - pri)
                        if sol.id in resultat["par_sol"] else 0.0),
                }
                if any(devise.compare_amounts(sol[c] or 0.0, v) for c, v in ecrit.items()):
                    sol.write(ecrit)

            appro = resultat["appro"]
            vals = {
                FIELD_ACHAT_MATIERE: resultat["matiere"],
                FIELD_ACHAT_VITRAGE: resultat["vitrage"],
                FIELD_COUT_APPRO_AFFAIRE: resultat["affaire"],
                FIELD_COUT_APPRO_STOCK: resultat["stock"],
                FIELD_APPRO_TOTAL: appro["total"],
                FIELD_APPRO_NOT_DEL_NOT_INV: appro["ndni"],
                FIELD_APPRO_DEL_NOT_INV: appro["dni"],
                FIELD_APPRO_DEL_INV: appro["di"],
                "fma_pri_reel": devise.round(resultat["matiere"] + resultat["vitrage"]),
                "fma_pri_date": fields.Datetime.now(),
                "fma_pri_non_ventile": resultat["non_ventile"],
                "fma_pri_services": resultat["services"],
                "fma_achats_non_rattaches_nb": len(resultat["non_rattachees"].order_id),
                "fma_achats_non_rattaches_montant": resultat["montant_non_rattache"],
            }
            order.write({c: v for c, v in vals.items() if c in order._fields})

            mod = order._pri_recopier_mod()
            if mod:
                calcule = order.so_cout_mod_reel_odoo or 0.0
                order.write({
                    "fma_cout_mod_odoo": calcule,
                    "fma_cout_mod_ecart": devise.round(
                        (order.so_cout_mod_reel or 0.0) - calcule),
                })
            if self.env.context.get("fma_pri_message"):
                order._pri_rendre_compte(resultat, mod)

    def _pri_rendre_compte(self, resultat, mod):
        """Ecrit dans le fil de la commande ce que le calcul a trouve."""
        self.ensure_one()
        devise = self.currency_id

        def m(montant):
            return "%.2f %s" % (montant, devise.symbol or devise.name or "")

        corps = [escape(_(
            "Calcul PRI : matière %(mat)s, vitrage %(vit)s, soit %(pri)s — "
            "%(nof)s OF, %(nach)s ligne(s) d'achat rattachée(s).",
            mat=m(resultat["matiere"]), vit=m(resultat["vitrage"]),
            pri=m(resultat["matiere"] + resultat["vitrage"]),
            nof=len(resultat["ordres"]), nach=len(resultat["rattachees"]),
        ))]
        if resultat["non_ventile"]:
            corps.append(escape(_(
                "Dont %(nv)s sans ligne de commande, répartis au prorata du "
                "coût des lignes.", nv=m(resultat["non_ventile"]))))
        if resultat["detail_services"]:
            corps.append(escape(_(
                "Dont sous-traitance / services %(total)s, compris dans la "
                "matière : %(liste)s.",
                total=m(resultat["services"]),
                liste=" ; ".join(
                    "%s [%s] %s" % (
                        article.display_name,
                        article.categ_id.display_name or "-", m(montant))
                    for article, montant in resultat["detail_services"]))))
        achats = resultat["non_rattachees"].order_id
        if achats:
            corps.append(escape(_(
                "Achats du projet NON rattachés à une commande, donc comptés "
                "nulle part : %(noms)s (%(montant)s). Renseigner « Commande "
                "client » sur ces achats.",
                noms=", ".join(achats.mapped("name")),
                montant=m(resultat["montant_non_rattache"]))))
        if mod == "saisie":
            corps.append(escape(_(
                "Coût MOD (Réel) : valeur saisie à la main conservée "
                "(%(saisi)s) ; les pointages donnent %(calc)s.",
                saisi=m(self.so_cout_mod_reel), calc=m(self.so_cout_mod_reel_odoo))))
        elif mod == "recopie" and self.so_cout_mod_reel:
            corps.append(escape(_(
                "Coût MOD (Réel) repris des pointages : %(calc)s.",
                calc=m(self.so_cout_mod_reel))))
        self.message_post(body=Markup("<br/>").join(corps))

    # ------------------------------------------------------------------
    # Navigation depuis l'onglet Analyse Financiere
    # ------------------------------------------------------------------
    def action_pri_detail_lignes(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Prix de revient par ligne — %s", self.name),
            "res_model": "sale.order.line",
            "view_mode": "list",
            "views": [(self.env.ref("fma_custom.view_sale_order_line_pri_list").id, "list")],
            "domain": [("order_id", "=", self.id), ("display_type", "=", False)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def _pri_action_achats(self, nom, domaine):
        return {
            "type": "ir.actions.act_window",
            "name": nom,
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": domaine,
        }

    def action_pri_achats_non_rattaches(self):
        self.ensure_one()
        projets = self._fma_projets()
        lignes = self.env["purchase.order.line"]
        if projets:
            lignes = lignes.search([
                ("order_id.state", "in", ("purchase", "done")),
                ("order_id.x_studio_projet_du_so", "in", projets.ids),
                ("display_type", "=", False),
                ("product_id", "!=", False),
                ("fma_sale_order_id", "=", False),
            ])
        return self._pri_action_achats(
            _("Achats du projet non rattachés à une commande"),
            [("id", "in", lignes.order_id.ids)])

    def action_pri_achats_rattaches(self):
        self.ensure_one()
        lignes = self.env["purchase.order.line"].search(
            [("fma_sale_order_id", "=", self.id)])
        return self._pri_action_achats(
            _("Achats rattachés à %s", self.name),
            [("id", "in", lignes.order_id.ids)])


class SaleOrderLine(models.Model):
    """Ventilation du prix de revient reel par ligne de commande.

    Champs ordinaires, ecrits par ``sale.order._compute_pri`` : ils datent du
    dernier « Calcul PRI », comme les totaux de la commande. Leur somme est
    egale a ces totaux.
    """

    _inherit = "sale.order.line"

    fma_achat_matiere_reel = fields.Monetary(
        string="Matière réel", currency_field="currency_id",
        readonly=True, copy=False)
    fma_achat_vitrage_reel = fields.Monetary(
        string="Vitrage réel", currency_field="currency_id",
        readonly=True, copy=False)
    fma_pri_reel = fields.Monetary(
        string="PRI réel", currency_field="currency_id",
        readonly=True, copy=False,
        help="Matiere + vitrage de la ligne, au dernier Calcul PRI. Hors "
        "main-d'oeuvre.")
    fma_marge_brute_reelle = fields.Monetary(
        string="Marge brute réelle", currency_field="currency_id",
        readonly=True, copy=False,
        help="Sous-total HT de la ligne moins son PRI reel.")
