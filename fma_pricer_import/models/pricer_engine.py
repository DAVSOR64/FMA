# -*- coding: utf-8 -*-
"""Moteur d'import : format pivot -> lots, affectations et besoin matiere.

Ce moteur ne cree ni articles ni nomenclatures : c'est ``sqlite_connector``
qui alimente le referentiel et les lignes de devis. Le moteur apporte ce que
rien ne fait aujourd'hui :

* creer le **lot de fabrication** decrit par le fichier (LOGIKAL le porte
  nativement dans sa table ``Phases``) ;
* repartir la quantite de chaque ligne de devis **par lot**, pour qu'une seule
  ligne commerciale puisse etre fabriquee en plusieurs lots ;
* enregistrer les **barres** optimisees par le pricer comme besoin matiere du
  lot, ce qui alimente l'OF de debit et les achats.

Il est **idempotent** : redeposer le fichier d'un lot remet ce lot a plat sans
toucher aux autres.
"""
import hashlib
import logging

from odoo import _, models
from odoo.exceptions import UserError

from ..pivot import logikal

_logger = logging.getLogger(__name__)


def signature_hash(menuiserie):
    """Empreinte stable et courte, stockable sur l'article fabrique."""
    return hashlib.sha1(repr(menuiserie.signature()).encode("utf-8")).hexdigest()


class FmaPricerEngine(models.AbstractModel):
    _name = "fma.pricer.engine"
    _description = "Moteur d'import des chiffrages pricer"

    # ------------------------------------------------------------------
    # Entree
    # ------------------------------------------------------------------
    def import_file(self, order, path, source=None):
        """Lit un export pricer et l'applique au devis ``order``."""
        quotation = logikal.parse(path, source=source)
        return self.apply(order, quotation)

    def apply(self, order, quotation):
        """Applique un chiffrage pivot a un devis.

        Renvoie les lots crees ou mis a jour.
        """
        order.ensure_one()
        self._check_bars_usable(order, quotation)

        sale_lines = self._sync_sale_lines(order, quotation)

        # Lots fictifs regroupant les positions non fabriquees
        # (eco-contribution, transport) : rien a produire.
        lots_pivot = [
            lot
            for lot in quotation.lots
            if any(m.is_manufactured for m in lot.menuiseries)
        ]
        self._set_quantities(lots_pivot, sale_lines)

        lots = self.env["fma.lot.fabrication"]
        for lot_pivot in lots_pivot:
            lots |= self._sync_lot(order, lot_pivot, sale_lines)

        for warning in quotation.warnings:
            order.message_post(body=_("Import pricer : %s", warning))
        return lots

    def _set_quantities(self, lots_pivot, sale_lines):
        """Recale la quantite de chaque ligne sur la somme de ses lots.

        C'est l'invariant du dispositif : **la quantite vendue est la somme des
        quantites fabriquees par lot**. Le poser explicitement rend l'import
        rejouable — redeposer le fichier d'un lot deja importe remplace sa
        contribution au lieu de s'y ajouter.

        La quantite est fixee *avant* la creation des affectations, sinon la
        contrainte « quantite lotie <= quantite commandee » se declencherait au
        passage.
        """
        keys = {lot.guid or lot.ref for lot in lots_pivot}

        incoming = {}
        for lot_pivot in lots_pivot:
            for men in lot_pivot.menuiseries:
                if not men.is_manufactured:
                    continue
                sig = signature_hash(men)
                incoming[sig] = incoming.get(sig, 0.0) + men.qty

        for sig, line in sale_lines.items():
            # Ce que les *autres* lots fabriquent deja de cette ligne.
            others = sum(
                alloc.product_qty
                for alloc in self.env["fma.lot.fabrication.line"].search(
                    [("sale_line_id", "=", line.id)]
                )
                if (alloc.lot_id.pricer_lot_key or alloc.lot_id.logikal_ref)
                not in keys
            )
            line.product_uom_qty = others + incoming.get(sig, 0.0)

    # ------------------------------------------------------------------
    # Controles
    # ------------------------------------------------------------------
    def _check_bars_usable(self, order, quotation):
        """Refuse un fichier dont l'optimisation deborde du lot.

        Une barre qui porte des coupes de plusieurs lots rend chaque lot
        infabricable isolement : le fichier a ete optimise au niveau affaire,
        pas au niveau lot. Importer ses quantites reviendrait a sous-commander
        la matiere.
        """
        if quotation.bars_per_lot:
            return
        raise UserError(
            _(
                "Ce fichier a ete optimise au niveau de l'affaire : une meme "
                "barre alimente plusieurs lots, donc aucun lot n'est "
                "fabricable seul.\n\n%(detail)s\n\n"
                "Relancez l'optimisation par lot dans le pricer et exportez "
                "un fichier par lot.",
                detail="\n".join(quotation.warnings),
            )
        )

    # ------------------------------------------------------------------
    # Lignes de devis
    # ------------------------------------------------------------------
    def _sync_sale_lines(self, order, quotation):
        """Associe chaque position fabriquee du fichier a une ligne de devis.

        Les lignes elles-memes sont creees par ``sqlite_connector``. Le moteur
        se contente de les retrouver, de leur poser l'empreinte du chiffrage,
        et de **fusionner** celles qui decrivent le meme produit fabrique :
        c'est ce qui ramene les cinq positions ``A_1``..``A_5`` d'une affaire
        lotie a une seule ligne commerciale.

        Renvoie ``{empreinte: sale.order.line}``.
        """
        found = {}
        missing = []
        for pivot_line in quotation.sale_lines():
            men = pivot_line.menuiserie
            if not men.is_manufactured:
                continue
            key = signature_hash(men)
            line = self._find_sale_line(order, pivot_line, key)
            if not line:
                missing.append("%s (%s)" % (pivot_line.ref, pivot_line.description))
                continue
            # Champ technique : le commercial qui importe n'a pas forcement
            # le droit d'ecrire sur les articles.
            line.product_id.product_tmpl_id.sudo().pricer_signature = key
            found[key] = line

        if missing:
            raise UserError(
                _(
                    "Ces positions du fichier n'ont pas de ligne "
                    "correspondante dans le devis %(order)s :\n\n%(list)s\n\n"
                    "Lancez d'abord l'import du chiffrage, qui cree les "
                    "articles et les lignes, puis relancez la mise en lot.",
                    order=order.display_name,
                    list="\n".join("- %s" % m for m in missing),
                )
            )
        return found

    def _find_sale_line(self, order, pivot_line, key):
        """Retrouve la ligne de devis qui porte ce produit fabrique.

        Trois passes, de la plus sure a la plus permissive : l'empreinte deja
        posee par un import precedent, puis la reference du pricer telle que
        le connecteur la reporte sur l'article, puis la designation.
        """
        lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)

        match = lines.filtered(
            lambda l: l.product_id.product_tmpl_id.pricer_signature == key
        )
        if match:
            return self._merge_duplicates(match)

        refs = {r.strip().upper() for r in pivot_line.refs if r}
        match = lines.filtered(
            lambda l: (l.product_id.default_code or "").strip().upper() in refs
        )
        if match:
            return self._merge_duplicates(match)

        wanted = (pivot_line.description or "").strip().upper()
        if wanted:
            match = lines.filtered(
                lambda l: (l.product_id.name or "").strip().upper() == wanted
            )
            if match:
                return self._merge_duplicates(match)
        return self.env["sale.order.line"]

    def _merge_duplicates(self, lines):
        """Ramene plusieurs lignes d'un meme produit fabrique a une seule.

        Un import par lot cree une ligne a chaque depot. Commercialement, le
        client doit voir une ligne unique avec la quantite totale ; le
        decoupage en lots est une information de production, portee par
        ``fma.lot.fabrication.line``.
        """
        if len(lines) == 1:
            return lines
        # On conserve la ligne deja affectee a un lot : ``sale_line_id`` est en
        # ``ondelete="restrict"``, supprimer celle-la ferait echouer l'import.
        allocated = self.env["fma.lot.fabrication.line"].search(
            [("sale_line_id", "in", lines.ids)]
        )
        keep = allocated[:1].sale_line_id or lines[:1]
        # La quantite n'est pas cumulee ici : elle est recalee ensuite sur la
        # somme des lots par ``_set_quantities``.
        (lines - keep).unlink()
        return keep

    # ------------------------------------------------------------------
    # Lots
    # ------------------------------------------------------------------
    def _sync_lot(self, order, lot_pivot, sale_lines):
        """Cree ou met a jour le lot decrit par le fichier."""
        Lot = self.env["fma.lot.fabrication"]
        key = lot_pivot.guid or lot_pivot.ref
        lot = Lot.search(
            [
                ("pricer_lot_key", "=", key),
                ("company_id", "=", order.company_id.id),
            ],
            limit=1,
        )
        if lot and lot.state != "draft":
            raise UserError(
                _(
                    "Le lot %(lot)s (%(ref)s) n'est plus en brouillon : "
                    "il ne peut pas etre reimporte.",
                    lot=lot.display_name,
                    ref=lot_pivot.ref,
                )
            )
        if not lot:
            lot = Lot.create(
                {
                    "pricer_lot_key": key,
                    "logikal_ref": lot_pivot.ref,
                    "company_id": order.company_id.id,
                }
            )
        else:
            # Reimport : on repart d'un lot vierge plutot que de cumuler.
            lot.line_ids.unlink()
            # Besoin matiere : le commercial ne l'ecrit pas a la main, il est
            # en lecture seule pour lui (cf. ir.model.access de
            # fma_lot_fabrication). C'est une donnee derivee du fichier.
            lot.material_line_ids.sudo().unlink()
            lot.logikal_ref = lot_pivot.ref

        self._sync_lot_lines(lot, lot_pivot, sale_lines)
        self._sync_lot_materials(lot, lot_pivot)
        return lot

    def _sync_lot_lines(self, lot, lot_pivot, sale_lines):
        """Repartit les quantites des lignes de devis sur ce lot."""
        vals = []
        for men in lot_pivot.menuiseries:
            if not men.is_manufactured:
                continue
            line = sale_lines.get(signature_hash(men))
            if not line:
                continue
            vals.append(
                {
                    "lot_id": lot.id,
                    "sale_line_id": line.id,
                    "product_qty": men.qty,
                }
            )
        if vals:
            self.env["fma.lot.fabrication.line"].create(vals)

    def _sync_lot_materials(self, lot, lot_pivot):
        """Enregistre les barres optimisees par le pricer comme besoin du lot.

        Les quantites sont celles du plan de coupe du lot : ce sont les barres
        qui seront reellement consommees par l'OF de debit, chute comprise.
        """
        by_product = {}
        missing = set()
        for bar in lot_pivot.bars:
            product = self._find_product(bar.code, bar.color)
            if not product:
                missing.add(
                    "%s / %s" % (bar.code, bar.color or _("sans teinte"))
                )
                continue
            by_product[product] = by_product.get(product, 0.0) + bar.qty

        if missing:
            raise UserError(
                _(
                    "Ces references de profile du lot %(lot)s n'existent pas "
                    "dans Odoo :\n\n%(list)s\n\n"
                    "Elles sont normalement creees par l'import du chiffrage.",
                    lot=lot_pivot.ref,
                    list="\n".join("- %s" % m for m in sorted(missing)),
                )
            )

        vals = [
            {
                "lot_id": lot.id,
                "product_id": product.id,
                "product_qty": qty,
                "note": _("Barres optimisees par le pricer pour ce lot"),
            }
            for product, qty in by_product.items()
        ]
        if vals:
            # sudo : donnee derivee du fichier, que le commercial n'a pas le
            # droit d'ecrire directement (cf. _sync_lot).
            self.env["fma.lot.material.line"].sudo().create(vals)

    def _find_product(self, code, color=""):
        """Retrouve un article par sa reference **et sa teinte**.

        ``sqlite_connector`` cree un article par couple (reference, teinte) :
        le ``default_code`` est suffixe par la couleur, et
        ``x_studio_ref_int_logikal`` / ``x_studio_color_logikal`` portent les
        deux valeurs du pricer. Chercher sur la seule reference reviendrait a
        prendre une teinte au hasard — donc a acheter la mauvaise barre.
        """
        code = (code or "").strip()
        if not code:
            return self.env["product.product"]

        Product = self.env["product.product"]
        fields_ = Product._fields
        if "x_studio_ref_int_logikal" not in fields_:
            return Product.search([("default_code", "=", code)], limit=1)

        domain = [("x_studio_ref_int_logikal", "=", code)]
        candidates = Product.search(domain)
        if not candidates:
            return Product.search([("default_code", "=", code)], limit=1)

        color = (color or "").strip()
        if "x_studio_color_logikal" in fields_:
            exact = candidates.filtered(
                lambda p: (p.x_studio_color_logikal or "").strip() == color
            )
            if exact:
                return exact[:1]

        if len(candidates) == 1:
            # Une seule teinte connue pour cette reference : pas d'ambiguite.
            return candidates

        raise UserError(
            _(
                "La reference %(code)s existe dans Odoo en %(count)s teintes "
                "(%(colors)s), mais aucune ne correspond a la teinte "
                "%(wanted)s du fichier.\n\n"
                "Verifiez l'article, ou relancez l'import du chiffrage qui le "
                "cree avec la bonne teinte.",
                code=code,
                count=len(candidates),
                colors=", ".join(
                    sorted(
                        (p.x_studio_color_logikal or "?")
                        for p in candidates
                    )
                ),
                wanted=color or _("(sans teinte)"),
            )
        )
