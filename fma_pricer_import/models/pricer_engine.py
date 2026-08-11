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
import unicodedata

from odoo import _, models
from odoo.exceptions import UserError

from ..pivot import logikal

_logger = logging.getLogger(__name__)


def sans_accent(texte):
    """Minuscules et sans accent, pour rapprocher des noms saisis a la main.

    Le pricer nomme ses temps « Debit », l'atelier a baptise ses postes
    « Debit FMA » avec un accent. Une comparaison litterale ne les rapproche
    pas, et l'operation disparaissait de la nomenclature.
    """
    plie = unicodedata.normalize("NFD", texte or "")
    return "".join(c for c in plie if not unicodedata.combining(c)).strip().lower()


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

        sale_lines, missing_lines = self._sync_sale_lines(order, quotation)

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
            lots |= self._sync_lot(order, lot_pivot, sale_lines, missing_lines)

        for warning in quotation.warnings:
            order.message_post(body=_("Import pricer : %s", warning))

        incomplete = lots.filtered("import_incomplete")
        if incomplete:
            order.message_post(
                body=_(
                    "Import incomplet sur %(names)s : le lot est cree mais "
                    "ne pourra pas etre confirme tant que les manques ne sont "
                    "pas leves.",
                    names=", ".join(incomplete.mapped("display_name")),
                )
            )
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

        Un import ne bloque **pas** sur une position introuvable : le lot et
        les autres positions restent valides. Le manque est remonte a
        l'appelant, qui l'inscrit sur le lot concerne.

        Renvoie ``({empreinte: sale.order.line}, {empreinte: libelle manquant})``.
        """
        found = {}
        missing = {}
        for pivot_line in quotation.sale_lines():
            men = pivot_line.menuiserie
            if not men.is_manufactured:
                continue
            key = signature_hash(men)
            line = self._find_sale_line(
                order, pivot_line, key, quotation.project.get("name", "")
            )
            if not line:
                missing.setdefault(key, []).append(
                    _(
                        "menuiserie %(ref)s (%(desc)s) : aucune ligne de devis "
                        "correspondante",
                        ref=pivot_line.ref,
                        desc=pivot_line.description,
                    )
                )
                continue
            template = line.product_id.product_tmpl_id
            unchanged = template.pricer_signature == key
            # Champ technique : le commercial qui importe n'a pas forcement
            # le droit d'ecrire sur les articles.
            template.sudo().pricer_signature = key
            found[key] = line
            issues = self._sync_manufactured_product(
                line.product_id, pivot_line, unchanged=unchanged
            )
            if issues:
                missing.setdefault(key, []).extend(issues)

        return found, missing

    # ------------------------------------------------------------------
    # Article fabrique et nomenclature
    # ------------------------------------------------------------------
    def _sync_manufactured_product(self, product, pivot_line, unchanged=False):
        """Rend l'article de la menuiserie fabricable, et lui pose sa nomenclature.

        ``sqlite_connector`` cree l'article de chaque menuiserie **sans route**
        et n'ecrit qu'une seule nomenclature, portee par l'article de projet.
        Resultat : la menuiserie se vend mais ne se fabrique pas. On corrige les
        deux ici, menuiserie par menuiserie.

        Renvoie la liste des composants qui n'ont pas pu etre rattaches.
        """
        tmpl = product.product_tmpl_id.sudo()
        routes = tmpl.route_ids
        for xmlid in ("mrp.route_warehouse0_manufacture", "stock.route_warehouse0_mto"):
            route = self.env.ref(xmlid, raise_if_not_found=False)
            if route and route not in routes:
                routes |= route
        vals = {"is_storable": True, "purchase_ok": False}
        if routes != tmpl.route_ids:
            vals["route_ids"] = [(6, 0, routes.ids)]
        tmpl.write(vals)

        return self._sync_bom(product, pivot_line, unchanged=unchanged)

    def _debit_product(self, product):
        """Sous-ensemble « debite » d'une menuiserie.

        C'est lui qui materialise les profiles dans la nomenclature : l'OF de
        debit du lot le produit en consommant les **barres** du lot, l'OF
        d'assemblage en consomme un par menuiserie. Il n'a volontairement pas
        de nomenclature — sinon les profiles seraient comptes deux fois, une
        fois en barres entieres et une fois en metres lineaires.
        """
        code = "%s-DEB" % (product.default_code or product.name)
        Product = self.env["product.product"].sudo()
        debit = Product.search([("default_code", "=", code)], limit=1)
        if debit:
            return debit
        return Product.create(
            {
                "name": _("%s - debite", product.name),
                "default_code": code,
                "type": "consu",
                "is_storable": True,
                "purchase_ok": False,
                "sale_ok": False,
                "uom_id": product.uom_id.id,
                "categ_id": product.categ_id.id,
            }
        )

    def _sync_bom(self, product, pivot_line, unchanged=False):
        """(Re)construit la nomenclature d'une menuiserie.

        Une nomenclature par menuiserie, et non une pour toute l'affaire :
        1 sous-ensemble debite + la quincaillerie + le vitrage, en quantites
        **pour un exemplaire**.
        """
        men = pivot_line.menuiserie
        issues = []
        components = []

        debit = self._debit_product(product)
        components.append((debit, 1.0))

        for comp in men.components:
            if comp.kind == "glass":
                found, problem = self._find_glass(comp, men.position or men.ref)
            else:
                found, problem = self._find_product(comp.code, comp.color)
            if not found:
                if problem not in issues:
                    issues.append(problem)
                continue
            components.append((found, comp.qty))

        Bom = self.env["mrp.bom"].sudo()
        bom = Bom.search(
            [
                ("product_tmpl_id", "=", product.product_tmpl_id.id),
                ("type", "=", "normal"),
            ],
            limit=1,
        )

        # Cinq lots d'une meme menuiserie decrivent la meme chose : seule la
        # quantite a fabriquer change. Si l'empreinte du chiffrage n'a pas
        # bouge et que la nomenclature existe deja, il n'y a rien a refaire.
        if unchanged and bom and bom.bom_line_ids:
            return issues

        # Une resolution incomplete ne doit jamais ecraser une nomenclature
        # correcte : c'est ce qui faisait disparaitre le vitrage au deuxieme
        # import. On signale le manque et on laisse l'existant en place.
        if issues and bom and bom.bom_line_ids:
            return issues
        merged = {}
        for item, qty in components:
            merged[item] = merged.get(item, 0.0) + qty
        lines = [
            (0, 0, {
                "product_id": item.id,
                "product_qty": qty,
                "product_uom_id": item.uom_id.id,
            })
            for item, qty in merged.items()
            if qty
        ]
        # Le debit est mutualise sur le lot : son temps appartient a l'OF de
        # debit, pas aux OF d'assemblage. Il part donc sur la nomenclature du
        # sous-ensemble debite.
        operations, missing_wc = self._bom_operations(men, product, skip=("Debit",))
        issues.extend(missing_wc)
        issues.extend(self._sync_debit_bom(debit, men))

        vals = {
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "type": "normal",
            "product_qty": 1.0,
            "product_uom_id": product.uom_id.id,
            "code": pivot_line.ref,
            "operation_ids": [(5, 0, 0)] + operations,
            # On repart des composants du fichier : la nomenclature est le
            # reflet du chiffrage, pas un cumul d'imports successifs.
            "bom_line_ids": [(5, 0, 0)] + lines,
        }
        if bom:
            bom.write(vals)
        else:
            Bom.create(vals)
        return issues

    def _sync_debit_bom(self, debit, men):
        """Nomenclature du sous-ensemble debite : la gamme de debit, sans composant.

        Aucune ligne de composant : les barres viennent du besoin matiere du
        lot, qui varie d'un lot a l'autre alors que la nomenclature, elle, est
        commune. Cette nomenclature ne sert qu'a porter le temps de debit.
        """
        operations, missing = self._bom_operations(men, debit, keep=("Debit",))
        if not operations:
            return missing

        Bom = self.env["mrp.bom"].sudo()
        bom = Bom.search(
            [
                ("product_tmpl_id", "=", debit.product_tmpl_id.id),
                ("type", "=", "normal"),
            ],
            limit=1,
        )
        vals = {
            "product_tmpl_id": debit.product_tmpl_id.id,
            "product_id": debit.id,
            "type": "normal",
            "product_qty": 1.0,
            "product_uom_id": debit.uom_id.id,
            "operation_ids": [(5, 0, 0)] + operations,
            "bom_line_ids": [(5, 0, 0)],
        }
        if bom:
            bom.write(vals)
        else:
            Bom.create(vals)
        return missing

    def _workcenters(self, product):
        """Postes de charge candidats, et ceux explicitement rattaches.

        Renvoie deux structures : le rattachement declare par le metier
        (champ « Operation pricer » sur le poste), qui fait foi, et la liste
        des postes tries du nom le plus court au plus long, pour le
        rapprochement par nom en repli.

        La societe est celle de l'article, ou a defaut celle de
        l'utilisateur : un article sans societe — le cas courant — reduisait
        le filtre a « company_id = False » et ne trouvait aucun poste, alors
        que tous en portent une.
        """
        company = product.company_id or self.env.company
        postes = self.env["mrp.workcenter"].search(
            [("company_id", "in", [company.id, False])]
        )
        declares = {}
        for poste in postes:
            if poste.pricer_operation:
                declares.setdefault(sans_accent(poste.pricer_operation), poste)
        par_nom = sorted(
            ((sans_accent(w.name), w) for w in postes),
            key=lambda couple: (len(couple[0]), couple[0]),
        )
        return declares, par_nom

    def _bom_operations(self, men, product, skip=(), keep=None):
        """Gamme d'une menuiserie, a partir des temps du pricer.

        Le connecteur agrege ces temps au niveau de l'affaire, sur la
        nomenclature de projet. Ici ils sont ramenes a la menuiserie et a
        l'unite, ce qui les rend exploitables par OF d'assemblage.
        """
        operations = []
        missing = []
        declares, par_nom = self._workcenters(product)
        for operation in men.operations:
            if keep is not None and operation.name not in keep:
                continue
            if operation.name in skip:
                continue

            prefixe = sans_accent(operation.name)

            # 1. Le rattachement declare par le metier fait foi.
            workcenter = declares.get(prefixe)
            if not workcenter:
                # 2. Repli : rapprochement par le debut du nom.
                candidats = [w for cle, w in par_nom if cle.startswith(prefixe)]
                if not candidats:
                    label = _(
                        "operation %(name)s : aucun poste de charge de ce nom. "
                        "Renseignez « Opération pricer » sur le poste concerné.",
                        name=operation.name,
                    )
                    if label not in missing:
                        missing.append(label)
                    continue

                # Plusieurs postes commencent par le meme mot (« Usinage
                # FMA », « Usinage F2M », « Usinage Simple »...). On retient
                # le nom le plus court, et on signale : c'est au metier de
                # trancher, pas au code de choisir en silence.
                workcenter = candidats[0]
                if len(candidats) > 1:
                    label = _(
                        "operation %(name)s : %(nb)s postes possibles "
                        "(%(liste)s). %(retenu)s a ete retenu — renseignez "
                        "« Opération pricer » sur le bon poste pour lever le doute.",
                        name=operation.name,
                        nb=len(candidats),
                        liste=", ".join(c.display_name for c in candidats),
                        retenu=workcenter.display_name,
                    )
                    if label not in missing:
                        missing.append(label)
            operations.append(
                (0, 0, {
                    "name": operation.name,
                    "workcenter_id": workcenter.id,
                    "time_cycle_manual": operation.minutes,
                    "sequence": operation.sequence,
                })
            )
        return operations, missing

    def _find_glass(self, comp, position):
        """Retrouve le vitrage d'une position.

        Le vitrage n'a pas de reference propre cote Odoo — le connecteur le
        numerote ``<affaire>_1``, ``<affaire>_2`` — mais il lui pose la
        **position** dans ``x_studio_position`` (le nom de l'elevation). Le
        lien vitrage -> menuiserie est donc porte par la donnee : on s'appuie
        dessus, et les dimensions ne servent qu'a departager deux vitrages
        d'une meme position.
        """
        Product = self.env["product.product"]
        fields_ = Product._fields
        absent = _(
            "vitrage %(code)s %(w)sx%(h)s de la position %(pos)s : article "
            "introuvable dans Odoo",
            code=comp.code,
            w=int(comp.width_mm),
            h=int(comp.height_mm),
            pos=position,
        )
        if "x_studio_position" not in fields_:
            return Product, absent

        # La position de base, pas « A_1 » : au deuxieme import le fichier
        # parle de « A_2 » alors que le vitrage a ete cree sous « A ». Sans ca,
        # la nomenclature reconstruite perdait son vitrage.
        candidates = Product.search([("x_studio_position", "=", position)])
        if not candidates:
            return Product, absent
        if len(candidates) == 1:
            return candidates, None

        if "x_studio_hauteur_mm" in fields_:
            exact = candidates.filtered(
                lambda p: int(p.x_studio_hauteur_mm or 0) == int(comp.height_mm)
                and int(p.x_studio_largeur_mm or 0) == int(comp.width_mm)
            )
            if len(exact) == 1:
                return exact, None
            if len(exact) > 1:
                # Deux vitrages identiques de la meme position : c'est le meme
                # article cote Odoo, le premier fait foi.
                return exact[:1], None
        return Product, _(
            "vitrage %(code)s de la position %(pos)s : %(n)s articles "
            "possibles, rattachement impossible",
            code=comp.code,
            pos=position,
            n=len(candidates),
        )

    def _find_sale_line(self, order, pivot_line, key, project=""):
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

        # Reference posee par le connecteur : affaire + position de base.
        refs = {r.strip().upper() for r in pivot_line.refs if r}
        position = getattr(pivot_line.menuiserie, "position", "")
        if project and position:
            refs.add(("%s_%s" % (project, position)).upper())
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
    def _sync_lot(self, order, lot_pivot, sale_lines, missing_lines=None):
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

        issues = self._sync_lot_lines(lot, lot_pivot, sale_lines, missing_lines)
        issues += self._sync_lot_materials(lot, lot_pivot)
        self._set_lot_debit_product(lot)
        lot.import_issues = "\n".join("- %s" % i for i in issues) or False
        if issues:
            lot.message_post(
                body=_(
                    "Import incomplet :<br/><pre>%s</pre>", lot.import_issues
                )
            )
        return lot

    def _sync_lot_lines(self, lot, lot_pivot, sale_lines, missing_lines=None):
        """Repartit les quantites des lignes de devis sur ce lot.

        Renvoie la liste des menuiseries du lot qui n'ont pas pu etre
        affectees : le lot existe, mais il lui manque des menuiseries.
        """
        missing_lines = missing_lines or {}
        issues = []
        vals = []
        for men in lot_pivot.menuiseries:
            if not men.is_manufactured:
                continue
            key = signature_hash(men)
            line = sale_lines.get(key)
            issues.extend(missing_lines.get(key) or [])
            if not line:
                if key not in missing_lines:
                    issues.append(
                        _("menuiserie %s : ligne de devis introuvable", men.ref)
                    )
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
        return issues

    def _set_lot_debit_product(self, lot):
        """Fait produire a l'OF de debit le sous-ensemble de *cette* menuiserie.

        Sans ca, le lot retomberait sur l'article debite generique parametre
        sur la societe, et l'en-cours de tous les lots serait valorise sur le
        meme article. On ne le fait que si le lot ne fabrique qu'une seule
        menuiserie : au-dela, un debite unique n'aurait pas de sens et
        l'article generique reste le bon choix.
        """
        products = lot.line_ids.mapped("product_id")
        if len(products) != 1:
            return
        lot.product_debit_id = self._debit_product(products)

    def _sync_lot_materials(self, lot, lot_pivot):
        """Enregistre les barres optimisees par le pricer comme besoin du lot.

        Les quantites sont celles du plan de coupe du lot : ce sont les barres
        qui seront reellement consommees par l'OF de debit, chute comprise.

        Un profile introuvable dans Odoo ne fait pas echouer l'import : les
        autres barres sont enregistrees et le manque est renvoye a l'appelant.
        Le lot restera bloque a la confirmation, la ou l'incidence est reelle.
        """
        # Besoin reel en metres, par reference et teinte : la somme des coupes
        # de toutes les menuiseries du lot. C'est ce qui entre en en-cours ;
        # l'ecart avec les barres est la chute, et il devient mesurable.
        need_mm = {}
        for men in lot_pivot.menuiseries:
            for cut in men.debit:
                key = (cut.code, cut.color)
                need_mm[key] = need_mm.get(key, 0.0) + cut.total_mm * men.qty

        by_key = {}
        missing = {}
        for bar in lot_pivot.bars:
            key = (bar.code, bar.color)
            entry = by_key.setdefault(key, {"qty": 0.0, "length": bar.length_mm})
            entry["qty"] += bar.qty

        by_product = {}
        for key, entry in by_key.items():
            code, color = key
            product, problem = self._find_product(code, color)
            if not product:
                missing[problem] = missing.get(problem, 0.0) + entry["qty"]
                continue
            acc = by_product.setdefault(
                product, {"qty": 0.0, "length": 0.0, "need": 0.0}
            )
            acc["qty"] += entry["qty"]
            acc["length"] = entry["length"] / 1000.0
            acc["need"] += need_mm.get(key, 0.0) / 1000.0

        vals = [
            {
                "lot_id": lot.id,
                "product_id": product.id,
                # L'unite est un calcule stocke *requis* : on la fournit
                # explicitement plutot que de dependre de l'ordre de calcul
                # a la creation.
                "product_uom_id": product.uom_id.id,
                "product_qty": acc["qty"],
                "bar_length": acc["length"],
                "debit_length": acc["need"],
                "note": _("Barres optimisees par le pricer pour ce lot"),
            }
            for product, acc in by_product.items()
        ]
        if vals:
            # sudo : donnee derivee du fichier, que le commercial n'a pas le
            # droit d'ecrire directement (cf. _sync_lot).
            self.env["fma.lot.material.line"].sudo().create(vals)
        return [
            _("%(detail)s (%(qty)s barre(s) non reprises)", detail=d, qty=int(q))
            for d, q in sorted(missing.items())
        ]

    def _find_product(self, code, color=""):
        """Retrouve un article par sa reference **et sa teinte**.

        ``sqlite_connector`` cree un article par couple (reference, teinte) :
        le ``default_code`` est suffixe par la couleur, et
        ``x_studio_ref_int_logikal`` / ``x_studio_color_logikal`` portent les
        deux valeurs du pricer. Chercher sur la seule reference reviendrait a
        prendre une teinte au hasard — donc a acheter la mauvaise barre.

        Renvoie ``(article, motif)``. Le motif decrit ce qui a empeche de
        trancher quand aucun article ne convient ; il est inscrit sur le lot,
        et n'interrompt pas l'import.
        """
        Product = self.env["product.product"]
        code = (code or "").strip()
        color = (color or "").strip()
        if not code:
            return Product, _("profile sans reference dans le fichier")

        absent = _(
            "profile %(code)s en %(color)s : article inexistant dans Odoo",
            code=code,
            color=color or _("sans teinte"),
        )

        fields_ = Product._fields
        if "x_studio_ref_int_logikal" not in fields_:
            product = Product.search([("default_code", "=", code)], limit=1)
            return product, (absent if not product else None)

        candidates = Product.search([("x_studio_ref_int_logikal", "=", code)])
        if not candidates:
            product = Product.search([("default_code", "=", code)], limit=1)
            return product, (absent if not product else None)

        if "x_studio_color_logikal" in fields_:
            exact = candidates.filtered(
                lambda p: (p.x_studio_color_logikal or "").strip() == color
            )
            if exact:
                return exact[:1], None

        if len(candidates) == 1:
            # Une seule teinte connue pour cette reference : pas d'ambiguite.
            return candidates, None

        # Plusieurs teintes, aucune ne correspond : choisir au hasard ferait
        # acheter la mauvaise barre. On ne reprend pas la ligne et on le dit.
        return Product, _(
            "profile %(code)s : existe en %(colors)s, mais pas en %(wanted)s",
            code=code,
            colors=", ".join(
                sorted((p.x_studio_color_logikal or "?") for p in candidates)
            ),
            wanted=color or _("sans teinte"),
        )
