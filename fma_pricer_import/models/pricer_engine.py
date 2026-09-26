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
import xml.etree.ElementTree as ET

from odoo import Command, _, api, models
from odoo.exceptions import UserError

from ..pivot import logikal, techdesign, techdesign_order

_logger = logging.getLogger(__name__)

#: Pricers pour lesquels un module tiers cree deja les articles fabriques et
#: les lignes de devis — sqlite_connector pour LOGIKAL. Pour les autres, le
#: moteur doit les creer lui-meme avant de pouvoir les retrouver.
PRICERS_AVEC_REDACTEUR = {"logikal"}

#: Prefixe de reference par fournisseur, tel que sqlite_connector le compose :
#: « TEC 720028 ». Sans lui, un article cree ici ne serait pas reconnu comme
#: celui que LOGIKAL creerait, et les deux pricers feraient deux articles.
PREFIXES_FOURNISSEUR = {
    "TECHNAL": "TEC",
    "SAPA": "SAP",
    "WICONA": "WIC",
    "JANSEN": "JAN",
}

#: Routes posees par sqlite_connector sur tout article qu'il cree : fabrication
#: a la commande, et la route d'achat propre a FMA.
ROUTES_ARTICLE = ("stock.route_warehouse0_mto", "__export__.stock_route_54_b165c5dc")

#: Categorie des vitrages, celle qu'utilise sqlite_connector.
CATEGORIE_VITRAGE = "__export__.product_category_23_31345211"


#: Operations portees par l'OF de debit. CU (banc) y va aussi : c'est la
#: coupe, elle se fait sur la meme table que le debit et dans le meme temps.
OPERATIONS_DEBIT = ("Debit", "CU (banc)")


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
        """Lit un export pricer et l'applique au devis ``order``.

        Le format est reconnu au contenu et non a l'extension : le wizard
        recoit un televersement, dont le nom ne garantit rien.
        """
        quotation = self.read_file(path, source=source)
        return self.apply(order, quotation)

    @api.model
    def read_file(self, path, source=None):
        """Choisit l'adaptateur selon le format du fichier.

        Un export LOGIKAL est une base SQLite, un export TechDesign un
        document XML. Les deux se reconnaissent a leurs premiers octets, ce
        qui evite de faire confiance a l'extension.
        """
        with open(path, "rb") as fichier:
            entete = fichier.read(16)

        if entete.startswith(b"SQLite format 3"):
            return logikal.parse(path, source=source)

        racine = self._xml_root(path)
        if racine == "JobExport":
            return techdesign.parse(path, source=source)
        if racine == "root":
            # Commande fournisseur : elle complete un lot, elle n'en cree pas.
            return techdesign_order.parse(path, source=source)

        raise UserError(_(
            "Format de fichier non reconnu.\n\n"
            "Attendu : un export LOGIKAL (base SQLite) ou un export "
            "TechDesign (XML de chiffrage <JobExport>, ou de commande "
            "fournisseur).%(vu)s",
            vu=_("\nLu : document XML <%s>.", racine) if racine else "",
        ))

    @api.model
    def _xml_root(self, path):
        """Nom de la balise racine, sans charger le document entier.

        Un chiffrage TechDesign pese plusieurs mega-octets : on s'arrete au
        premier evenement plutot que de tout analyser pour un aiguillage.
        """
        try:
            for _evt, element in ET.iterparse(path, events=("start",)):
                return element.tag
        except ET.ParseError:
            return ""
        return ""

    def apply(self, order, quotation):
        """Applique un chiffrage pivot a un devis.

        Renvoie les lots crees ou mis a jour.
        """
        order.ensure_one()
        # Le site qui a chiffre — « FMA » ou « F2M » — departage les postes de
        # charge homonymes des deux ateliers. Il est lu dans les parametres du
        # fichier (REPORTVARIABLES / Addresses / OwnAddress01) et voyage par le
        # contexte, plutot que par la signature de six methodes
        # intermediaires.
        # Le site departage les postes de charge, l'affaire departage les
        # articles crees par le connecteur — vitrages en tete, qui portent la
        # position « A » dans toutes les affaires.
        self = self.with_context(
            fma_site=quotation.site,
            # A defaut d'offre dans le fichier — le chiffrage TechDesign n'en
            # porte pas —, le numero du devis fait l'affaire : c'est le prefixe
            # des references d'articles, celui-la meme sur lequel la resolution
            # du vitrage restreint ses candidats.
            fma_affaire=quotation.project.get("offer_no") or (order.name or ""),
            # Meme regle que pour les lignes de devis : le pricer qui n'a pas
            # de redacteur doit creer lui-meme les articles qui lui manquent.
            fma_creer_articles=quotation.pricer not in PRICERS_AVEC_REDACTEUR,
            # Longueur de barre par profile, relevee sur le plan de coupe de
            # l'affaire. C'est elle qui permet d'exprimer un besoin en metres
            # dans une unite qui compte des barres.
            fma_longueurs_barres=self._longueurs_de_barre(quotation),
        )
        self._check_offer_matches(order, quotation)
        self._check_bars_usable(order, quotation)

        self._ensure_sale_lines(order, quotation)
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
    def _check_offer_matches(self, order, quotation):
        """Refuse un fichier chiffre pour un autre devis.

        LOGIKAL inscrit le numero du devis dans ``Projects.OfferNo``, tranche
        comprise : « A26-08-09999/3 ». Deposer ce fichier sur le devis
        « A26-08-09999/1 » y cree un deuxieme article, une deuxieme
        nomenclature et une deuxieme ligne — la commande melange alors deux
        tranches, et plus rien ne le signale.

        Le cas s'est produit : les exports sont nommes « Tranche 1 Lot 3 » et
        « Tranche 3 Lot 1 », deux noms qui se ressemblent pour deux devis
        differents. Le controle coute une comparaison de chaines.

        On ne bloque que si le fichier porte un numero : un export sans
        OfferNo n'apprend rien et ne doit pas empecher de travailler.
        """
        offre = (quotation.project.get("offer_no") or "").strip()
        if not offre:
            return
        if offre.upper() == (order.name or "").strip().upper():
            return
        raise UserError(
            _(
                "Ce fichier a ete chiffre pour le devis %(offre)s, or vous "
                "l'importez dans %(devis)s.\n\n"
                "Deposer le chiffrage d'une autre tranche creerait ici un "
                "second article et une seconde nomenclature, et la commande "
                "melangerait deux tranches.\n\n"
                "Verifiez le fichier : « Tranche 1 Lot 3 » et « Tranche 3 "
                "Lot 1 » ne designent pas le meme devis.",
                offre=offre,
                devis=order.name or "",
            )
        )

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
    def _ensure_sale_lines(self, order, quotation):
        """Cree article et ligne de devis pour un pricer sans redacteur.

        LOGIKAL passe par ``sqlite_connector``, qui cree les articles fabriques
        et les lignes du devis ; le moteur se contente ensuite de les
        retrouver. TechDesign n'a pas cet equivalent : sans cela le devis
        restait vide, les lots naissaient orphelins, et le bouton « Lots » —
        dont le compteur se calcule depuis les lignes — restait masque.

        La reference reprend la convention du connecteur,
        « <projet>/<tranche>_<position> », sans quoi chaque reimport creerait
        un doublon au lieu de retrouver l'article. Le projet est ici le numero
        du devis : le chiffrage TechDesign n'en porte aucun.

        L'empreinte est posee des la creation, pour que la passe suivante
        retrouve la ligne par ce qu'elle est et non par sa designation.
        """
        if quotation.pricer in PRICERS_AVEC_REDACTEUR:
            return

        Product = self.env["product.product"].sudo()
        champs = Product._fields
        projet = (order.name or "").strip()
        tranche = order.x_tranche if "x_tranche" in order._fields else 0

        for pivot_line in quotation.sale_lines():
            men = pivot_line.menuiserie
            if not men or not men.is_manufactured:
                continue
            key = signature_hash(men)
            if self._find_sale_line(order, pivot_line, key,
                                    quotation.project.get("name", "")):
                continue

            position = men.position or pivot_line.ref
            code = "%s/%s_%s" % (projet, tranche or 0, position)
            produit = Product.search([("default_code", "=", code)], limit=1)
            if not produit:
                vals = {
                    "name": (men.description or position).strip(),
                    "default_code": code,
                    "list_price": men.price,
                    "uom_id": self.env.ref("uom.product_uom_unit").id,
                    "type": "consu",
                    "purchase_ok": False,
                    "sale_ok": True,
                    "invoice_policy": "delivery",
                }
                # Champs Studio du connecteur : presents en production, pas
                # forcement ailleurs. Ils portent le repere et les dimensions,
                # que le rapprochement du vitrage lit ensuite.
                if "x_studio_position" in champs:
                    vals["x_studio_position"] = position
                if "x_studio_hauteur_mm" in champs:
                    vals["x_studio_hauteur_mm"] = int(men.height_mm or 0)
                if "x_studio_largeur_mm" in champs:
                    vals["x_studio_largeur_mm"] = int(men.width_mm or 0)
                produit = Product.create(vals)
                _logger.info(
                    "Import pricer : article %s cree pour la menuiserie %s.",
                    code, position,
                )
            produit.product_tmpl_id.sudo().pricer_signature = key

            order.order_line = [(0, 0, {
                "product_id": produit.id,
                "name": (men.description or position).strip(),
                "product_uom_qty": pivot_line.qty,
                "price_unit": men.price,
            })]

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
        return self._semi_fini(product, "DEB", _("%s - debite"), "debit")

    def _quincaillerie_product(self, product):
        """Kit quincaillerie d'une menuiserie.

        Produit par l'OF de quincaillerie, consomme par l'OF d'assemblage : un
        kit par menuiserie. Il a, lui, une nomenclature — la quincaillerie —
        contrairement a l'ensemble debite, dont les barres sont propres au lot.
        """
        return self._semi_fini(product, "QUI", _("%s - kit quincaillerie"),
                               "quincaillerie")

    def _semi_fini(self, product, suffixe, libelle, nature):
        """Article intermediaire d'une menuiserie, cree a la premiere demande.

        La nature est marquee sur l'article (fma_semi_fini) : c'est elle, et non
        le suffixe de la reference, qui dit au lot quel OF generer.
        """
        code = "%s-%s" % (product.default_code or product.name, suffixe)
        Product = self.env["product.product"].sudo()
        article = Product.search([("default_code", "=", code)], limit=1)
        if article:
            if article.fma_semi_fini != nature:
                article.fma_semi_fini = nature
            return article
        return Product.create(
            {
                "name": libelle % product.name,
                "default_code": code,
                "type": "consu",
                "is_storable": True,
                "purchase_ok": False,
                "sale_ok": False,
                "uom_id": product.uom_id.id,
                "categ_id": product.categ_id.id,
                "fma_semi_fini": nature,
            }
        )

    def _routes(self):
        """Routes de l'article cree : MTO et achat, comme le connecteur."""
        ids = []
        for xmlid in ROUTES_ARTICLE:
            route = self.env.ref(xmlid, raise_if_not_found=False)
            if route:
                ids.append(Command.link(route.id))
            else:
                _logger.warning(
                    "Import pricer : route %s introuvable, article cree sans "
                    "elle.", xmlid,
                )
        return ids

    def _reference_article(self, comp):
        """Reference Odoo d'un composant, a la convention du connecteur.

        « TEC 720028.XBLACK » : prefixe du fournisseur, numero de base, puis la
        teinte. Le numero de base est la reference LOGIKAL privee de sa lettre
        fournisseur — « T720028 » donne « 720028 ».

        Reproduire cette convention est la condition pour qu'un article cree
        ici et le meme article cree par LOGIKAL n'en fassent qu'un.
        """
        prefixe = PREFIXES_FOURNISSEUR.get((comp.supplier or "").upper(), "")
        base = comp.code[1:] if prefixe and len(comp.code) > 1 else comp.code
        reference = ("%s %s" % (prefixe, base)).strip() if prefixe else comp.code
        return "%s.%s" % (reference, comp.color) if comp.color else reference

    def _creer_article(self, comp):
        """Cree l'article matiere absent de la base.

        Meme forme que ceux du connecteur : stockable, achetable, routes MTO et
        achat, et surtout x_studio_ref_int_logikal / x_studio_color_logikal
        renseignes — c'est sur eux que le prochain import le retrouvera au lieu
        d'en creer un second.
        """
        Product = self.env["product.product"].sudo()
        code = self._reference_article(comp)
        existant = Product.search([("default_code", "=", code)], limit=1)
        if existant:
            return existant

        champs = Product._fields
        vals = {
            "default_code": code,
            "name": (comp.description or comp.code).strip(),
            "uom_id": self.env.ref("uom.product_uom_unit").id,
            "purchase_ok": True,
            "sale_ok": True,
            "type": "consu",
            "is_storable": True,
            "route_ids": self._routes(),
        }
        for nom, valeur in (
            ("x_studio_ref_int_logikal", comp.code),
            ("x_studio_color_logikal", comp.color),
            ("x_studio_cration_auto", True),
        ):
            if nom in champs:
                vals[nom] = valeur
        produit = Product.create(vals)
        _logger.info("Import pricer : article %s cree (%s).", code, produit.name)
        return produit

    def _creer_vitrage(self, comp, position, rang):
        """Cree le vitrage absent de la base.

        Reference « <affaire>_<position>_<rang> », celle du connecteur : le
        vitrage n'a pas de reference fournisseur, il est identifie par la
        menuiserie qu'il garnit et son rang dans celle-ci. Le rang vient d'un
        tri stable, pour qu'un meme vitrage porte la meme reference d'un export
        a l'autre.
        """
        Product = self.env["product.product"].sudo()
        affaire = (self.env.context.get("fma_affaire") or "").strip()
        code = "%s_%s_%s" % (affaire, position, rang)
        existant = Product.search([("default_code", "=", code)], limit=1)
        if existant:
            return existant

        champs = Product._fields
        categorie = self.env.ref(CATEGORIE_VITRAGE, raise_if_not_found=False)
        vals = {
            "default_code": code,
            "name": (comp.code or comp.description or _("Vitrage")).strip(),
            "uom_id": self.env.ref("uom.product_uom_unit").id,
            "purchase_ok": True,
            "sale_ok": True,
            "type": "consu",
            "is_storable": True,
            "route_ids": self._routes(),
        }
        if categorie:
            vals["categ_id"] = categorie.id
        for nom, valeur in (
            ("x_studio_position", position),
            ("x_studio_hauteur_mm", int(comp.height_mm or 0)),
            ("x_studio_largeur_mm", int(comp.width_mm or 0)),
            ("x_studio_cration_auto", True),
        ):
            if nom in champs:
                vals[nom] = valeur
        produit = Product.create(vals)
        _logger.info("Import pricer : vitrage %s cree (%s).", code, produit.name)
        return produit

    def _rangs_vitrage(self, men):
        """Rang de chaque vitrage dans sa menuiserie, sur un tri stable.

        Trie sur la designation et les dimensions, jamais sur l'ordre de
        lecture : deux exports de la meme affaire doivent donner les memes
        references, sans quoi chaque import creerait un doublon.
        """
        vitrages = [c for c in men.components if c.kind == "glass"]
        ordre = sorted(
            range(len(vitrages)),
            key=lambda i: (
                vitrages[i].code or "",
                round(vitrages[i].width_mm),
                round(vitrages[i].height_mm),
            ),
        )
        rangs = {}
        for rang, index in enumerate(ordre, start=1):
            rangs[id(vitrages[index])] = rang
        return rangs

    def _sync_bom(self, product, pivot_line, unchanged=False):
        """(Re)construit la nomenclature d'une menuiserie.

        Une nomenclature par menuiserie, et non une pour toute l'affaire :
        1 sous-ensemble debite + la quincaillerie + le vitrage, en quantites
        **pour un exemplaire**.
        """
        men = pivot_line.menuiserie
        issues = []
        # La nomenclature de la menuiserie doit dire ce QU'ELLE EST, en
        # entier. Les ordres de fabrication en prennent ensuite chacun leur
        # part ; c'est a eux de se partager le travail, pas a la nomenclature
        # de se laisser amputer.
        #
        #   <ref>     : la menuiserie — l'ensemble debite, le kit
        #               quincaillerie, le vitrage, et les operations
        #               d'usinage, de montage et de vitrage ;
        #   <ref>-DEB : l'ensemble debite — les operations Debit et CU. Ses
        #               barres ne sont pas ici : elles viennent du plan de
        #               coupe du lot, ou une meme barre sert plusieurs
        #               menuiseries. Une nomenclature ne sait pas dire cela ;
        #               fma.lot.material.line, si ;
        #   <ref>-QUI : le kit quincaillerie — la quincaillerie, en phantom :
        #               Odoo l'eclate dans l'OF d'assemblage. Le kit reste un
        #               regroupement nomme pour les editions du magasin, mais
        #               plus rien ne le fabrique.
        #
        # L'ensemble debite avait ete retire d'ici, a l'epoque ou le lot
        # ajoutait a chaque OF d'assemblage un ensemble debite GENERIQUE : on
        # le consommait alors deux fois. Depuis que chaque ligne de lot porte
        # le sien (product_debit_id), _add_debit_component retrouve le meme
        # article et ne l'ajoute pas une seconde fois. La cause a disparu, la
        # ligne revient.
        components = []
        quincaillerie = []

        debit = self._debit_product(product)
        kit = self._quincaillerie_product(product)
        components.append((debit, 1.0))
        components.append((kit, 1.0))

        # Creation autorisee pour les pricers sans redacteur : LOGIKAL a son
        # connecteur, qui cree deja articles et vitrages avant l'import. Pour
        # les autres, un composant introuvable doit etre cree ici, sans quoi la
        # nomenclature sort amputee.
        creer = self.env.context.get("fma_creer_articles")
        rangs = self._rangs_vitrage(men) if creer else {}

        for comp in men.components:
            if comp.kind == "glass":
                found, problem = self._find_glass(comp, men.position or men.ref)
                if not found and creer:
                    found, problem = self._creer_vitrage(
                        comp, men.position or men.ref, rangs.get(id(comp), 1)
                    ), None
            elif comp.code:
                found, problem = self._find_product(comp.code, comp.color)
                if not found and creer:
                    found, problem = self._creer_article(comp), None
            else:
                # Ligne saisie a la main dans LOGIKAL : elle n'a pas de
                # reference article, mais le connecteur en fait bien un
                # article Odoo. C'est par la designation qu'on le retrouve.
                found, problem = self._find_article_libre(comp), None
                if not found:
                    problem = _(
                        "%(quoi)s : article libre introuvable dans Odoo",
                        quoi=self._libelle_composant(comp, men),
                    )
            if not found:
                if problem not in issues:
                    issues.append(problem)
                continue
            # Un composant ne peut pas etre l'article qu'il compose : Odoo
            # refuse la nomenclature pour cycle, et l'import entier echoue.
            #
            # Le cas se produit sur la resolution du vitrage, qui cherche par
            # x_studio_position — champ que porte AUSSI l'article de la
            # menuiserie, cree avec le repere. Sur LOGIKAL l'affaire departage
            # les candidats ; un chiffrage TechDesign n'en portant aucune, la
            # recherche retombait sur la menuiserie elle-meme.
            self._marquer_nature(
                found, "glass" if comp.kind == "glass" else "article")

            if found.id == product.id:
                probleme = _(
                    "%(genre)s %(code)s de la position %(pos)s : la recherche "
                    "retombe sur la menuiserie elle-meme, composant ignore",
                    genre=_("vitrage") if comp.kind == "glass" else _("article"),
                    code=comp.code,
                    pos=men.position or men.ref,
                )
                if probleme not in issues:
                    issues.append(probleme)
                continue
            if comp.kind == "glass":
                components.append((found, comp.qty))
            else:
                quincaillerie.append((found, comp.qty))

        Bom = self.env["mrp.bom"].sudo()
        bom = Bom.search(
            [
                ("product_tmpl_id", "=", product.product_tmpl_id.id),
                ("type", "=", "normal"),
            ],
            limit=1,
        )

        # La gamme se calcule avant les garde-fous : elle ne depend pas des
        # composants, et elle doit pouvoir etre corrigee sur une nomenclature
        # existante. Sans cela, un poste de charge cree ou renomme apres le
        # premier import n'entrait jamais dans les nomenclatures deja faites.
        #
        # Le debit est mutualise sur le lot : son temps appartient a l'OF de
        # debit, pas aux OF d'assemblage. Il part donc sur la nomenclature du
        # sous-ensemble debite.
        operations, missing_wc = self._bom_operations(
            men, product, skip=OPERATIONS_DEBIT)
        issues_gamme = list(missing_wc)
        issues_gamme.extend(self._sync_debit_bom(debit, men))

        # Une nomenclature de l'ancienne structure — ensemble debite en
        # composant, pas de kit — doit etre reconstruite meme si le chiffrage
        # n'a pas bouge : sans kit, le lot ne sait generer aucun OF de
        # quincaillerie. Ce n'est pas une question d'empreinte mais de forme.
        # Une nomenclature de la forme precedente doit etre reconstruite meme
        # si le chiffrage n'a pas bouge : ce n'est pas une question
        # d'empreinte mais de forme. Elle se reconnait a ce qui lui manque --
        # l'ensemble debite, ou le kit.
        ancienne_forme = bool(
            bom and bom.bom_line_ids
            and (debit not in bom.bom_line_ids.product_id
                 or kit not in bom.bom_line_ids.product_id)
        )
        if ancienne_forme and not issues:
            unchanged = False

        # Deux raisons de ne pas retoucher les COMPOSANTS d'une nomenclature
        # existante : l'empreinte du chiffrage n'a pas bouge — cinq lots d'une
        # meme menuiserie decrivent la meme chose —, ou un composant reste
        # introuvable, et une resolution incomplete ecraserait une
        # nomenclature correcte. Dans les deux cas la gamme, elle, est mise a
        # jour : c'est une autre information.
        if bom and bom.bom_line_ids and (unchanged or issues):
            bom.write({"operation_ids": [(5, 0, 0)] + operations})
            if ancienne_forme:
                issues_gamme.append(_(
                    "nomenclature %(ref)s laissee dans l'ancienne forme, faute "
                    "de pouvoir resoudre tous ses composants : il lui manque "
                    "l'ensemble debite ou le kit quincaillerie, et son OF "
                    "d'assemblage sortira incomplet",
                    ref=pivot_line.ref,
                ))
            return issues + issues_gamme

        # Les composants sont tous resolus : le kit est reconstruit avec la
        # menuiserie, sinon les deux divergeraient d'un import a l'autre.
        self._sync_quincaillerie_bom(kit, quincaillerie)

        issues.extend(issues_gamme)
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
        """Nomenclature du sous-ensemble debite : les profiles et le temps.

        Le debit appartient a la MENUISERIE et ne change jamais : le fichier
        rattache chaque coupe a sa position, exactement comme il y rattache la
        quincaillerie et le vitrage. Ce qui appartient au lot, c'est
        l'optimisation — la facon de nester ces coupes dans des barres
        entieres, qui elle varie d'un regroupement a l'autre.

        Les deux vivent donc a deux endroits, et ce n'est pas un doublon :
        ici le BESOIN par menuiserie, stable, exprime en longueur ; sur
        fma.lot.material.line les BARRES a sortir pour le lot, avec la chute
        que le nesting laisse. L'OF de debit consomme les barres (il a
        bom_id=False), jamais cette nomenclature-ci. Rien n'est compte deux
        fois.

        L'unite est le point delicat. Un profile se stocke a la barre et se
        consomme au metre : on ecrit donc la ligne en METRES quand l'unite de
        l'article appartient a la meme categorie, Odoo faisant lui-meme la
        conversion vers la barre. Quand il ne le peut pas, on ne devine pas :
        on le dit, et le manque remonte sur le lot.
        """
        operations, missing = self._bom_operations(men, debit, keep=OPERATIONS_DEBIT)
        # Encadre : le besoin de debit est une information. Le module pose en
        # principe qu'un import ne s'arrete pas sur une piece introuvable --
        # le lot et les autres positions restent valides. Une exception
        # inattendue ici ne doit pas faire exception a ce principe, et le
        # premier import sur la staging a montre ce que ca coute.
        try:
            lignes, manques = self._lignes_debit(men)
        except Exception as erreur:  # noqa: BLE001 — trace, pas de blocage
            _logger.exception(
                "Import pricer : besoin de debit de %s", men.ref)
            lignes, manques = [], [_(
                "menuiserie %(ref)s : le besoin de debit n'a pas pu etre "
                "repris (%(erreur)s)",
                ref=men.ref, erreur=erreur,
            )]
        missing = list(missing) + manques
        if not operations and not lignes:
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
            "bom_line_ids": [(5, 0, 0)] + lignes,
        }
        if bom:
            bom.write(vals)
        else:
            Bom.create(vals)
        return missing

    def _longueurs_de_barre(self, quotation):
        """Longueur de barre par (reference, teinte), en millimetres.

        Le fichier la donne sur le plan de coupe : chaque barre porte sa
        longueur. C'est la seule source fiable — l'article Odoo ne la porte
        pas toujours, et le nom de son unite (« BARRE6.50 ») n'est pas une
        donnee, c'est du texte.
        """
        longueurs = {}
        for lot in quotation.lots:
            for barre in lot.bars:
                cle = ((barre.code or "").strip(), (barre.color or "").strip())
                if barre.length_mm and cle not in longueurs:
                    longueurs[cle] = barre.length_mm
        return longueurs

    def _lignes_debit(self, men):
        """Les profiles d'une menuiserie, en lignes de nomenclature.

        Une coupe porte une longueur et une quantite ; plusieurs coupes du
        meme profile et de la meme teinte se cumulent en un seul besoin. Le
        detail des longueurs n'a pas sa place ici — une nomenclature ne sait
        pas le dire — il reste dans le plan de coupe du lot.

        Renvoie ``(lignes, manques)``.
        """
        besoin = {}
        manques = []
        for cut in men.debit:
            cle = ((cut.code or "").strip(), (cut.color or "").strip())
            besoin[cle] = besoin.get(cle, 0.0) + cut.total_mm

        lignes = []
        for (code, couleur), total_mm in besoin.items():
            if total_mm <= 0:
                continue
            produit, probleme = self._find_product(
                code, couleur, _("profile du debit"))
            if not produit:
                if probleme and probleme not in manques:
                    manques.append(probleme)
                continue
            uom, quantite, probleme = self._quantite_debit(
                produit, total_mm, (code, couleur))
            if not uom:
                if probleme not in manques:
                    manques.append(probleme)
                continue
            lignes.append((0, 0, {
                "product_id": produit.id,
                "product_qty": quantite,
                "product_uom_id": uom.id,
            }))
        return lignes, manques

    def _unites_convertibles(self, source, cible):
        """Odoo sait-il passer de l'une a l'autre ?

        On ne juge jamais une unite sur son nom : « BARRE6.50 » ne dit rien a
        personne d'autre qu'a nous. Mais la façon de poser la question a
        change de version en version.

        Jusqu'en v18, deux unites se convertissaient si elles partageaient une
        categorie. La v19 a supprime uom.category : les unites se rattachent
        desormais les unes aux autres par relative_uom_id, et c'est la racine
        commune qui fait foi. Le premier import sur la staging l'a dit sans
        detour -- « 'uom.uom' object has no attribute 'category_id' ».

        On regarde donc ce que le modele porte vraiment, plutot que de parier
        sur une version. Et si aucun des deux chemins n'existe, on repond non :
        mieux vaut signaler un profile que lui inventer une quantite.
        """
        if not source or not cible:
            return False
        if source == cible:
            return True
        champs = cible._fields
        if "category_id" in champs:
            return source.category_id == cible.category_id
        if "relative_uom_id" in champs:
            return bool(self._racine_uom(source)) and (
                self._racine_uom(source) == self._racine_uom(cible)
            )
        return False

    def _racine_uom(self, uom):
        """L'unite de reference au bout de la chaine des rattachements.

        La garde sur les identifiants deja vus n'est pas theorique : rien
        n'empeche un parametrage de refermer la chaine sur elle-meme, et on
        tournerait sans fin au milieu d'un import.
        """
        vus = set()
        courant = uom
        while courant and courant.id not in vus:
            vus.add(courant.id)
            suivant = courant.relative_uom_id
            if not suivant:
                return courant
            courant = suivant
        return courant

    def _quantite_debit(self, produit, total_mm, cle):
        """Le besoin de debit, dans une unite que l'article accepte.

        Deux chemins, et il en faut deux.

        Le metre d'abord : c'est la mesure du besoin, Odoo convertit seul vers
        la barre au moment de consommer, et la ligne se lit. Encore faut-il
        que l'unite de l'article sache se convertir en metres.

        Quand elle ne le sait pas — une unite « BARRE6.50 » posee hors de
        toute chaine de conversion, ce qui est le cas ici — on exprime le
        besoin en FRACTION DE BARRE : 1,39 m d'une barre de 6,50 m font 0,214
        barre. C'est exact, c'est achetable, et surtout c'est valorise : sans
        cette ligne, l'ensemble debite reste a 0,00 euro et le prix de revient
        de la menuiserie perd tous ses profiles.

        La longueur de barre vient du plan de coupe de l'affaire, a defaut de
        x_studio_longueur_m sur l'article. On ne l'invente jamais : sans elle,
        le profile est laisse de cote et le manque remonte sur le lot.

        Renvoie ``(uom, quantite, probleme)``.
        """
        metres = total_mm / 1000.0
        metre = self.env.ref("uom.product_uom_meter", raise_if_not_found=False)
        if metre and self._unites_convertibles(metre, produit.uom_id):
            return metre, metres, None

        longueur_mm = (self.env.context.get("fma_longueurs_barres") or {}).get(cle)
        if not longueur_mm:
            longueur_m = getattr(produit, "x_studio_longueur_m", 0.0) or 0.0
            longueur_mm = longueur_m * 1000.0
        if longueur_mm:
            return produit.uom_id, total_mm / longueur_mm, None

        return None, 0.0, _(
            "profile %(code)s : son unite « %(uom)s » ne se convertit pas en "
            "metres et sa longueur de barre est inconnue — le besoin de debit "
            "ne peut etre exprime ni en longueur ni en barres",
            code=produit.default_code or produit.display_name,
            uom=produit.uom_id.display_name,
        )

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

        # La position ne suffit pas : « A » existe dans toutes les affaires.
        # Sans ce filtre, la nomenclature se garnissait du vitrage d'une
        # AUTRE affaire — constate sur la staging, ou les vitrages de
        # A26-08-09999/1 pointaient A26-07-03112, un chiffrage anterieur du
        # meme produit. On restreint donc a l'affaire en cours, et on ne
        # retombe sur l'ensemble que si elle n'a aucun vitrage a cette
        # position.
        affaire = (self.env.context.get("fma_affaire") or "").strip().upper()
        if affaire:
            propres = candidates.filtered(
                lambda p: (p.default_code or "").strip().upper().startswith(affaire)
            )
            if propres:
                candidates = propres
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
        refs |= self._refs_position(order, project, position)
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

    def _refs_position(self, order, project, position):
        """Les references sous lesquelles l'article d'une position peut exister.

        Le connecteur nomme l'article « affaire_position », et son « affaire »
        est le NUMERO d'offre du fichier (Projects.OfferNo), pas le nom du
        chantier. C'est aussi le numero d'offre qu'on retrouve dans order.name,
        puisque l'import refuse deja un fichier chiffre pour un autre devis.

        Le moteur passait ici Projects.Name. Sur A26-00-00002 cela donnait
        « INTERNAT LA FLECHE TEST ODOO_E-MEXT-A TG », qui ne ressemble a rien
        de ce qui existe en base : les trois lignes etaient pourtant la, sous
        « A26-00-00002_E-MEXT-A TG », et le lot LOT-2026-0007 est ressorti sans
        aucune ligne, avec trois « aucune ligne de devis correspondante ».

        On essaie donc les deux origines, et les deux ecritures de la tranche :
        sans, comme le connecteur l'ecrit pour la tranche 0, et avec.
        """
        position = (position or "").strip()
        if not position:
            return set()
        tranche = order.x_tranche if "x_tranche" in order._fields else 0
        refs = set()
        for affaire in ((order.name or ""), (project or "")):
            # Une affaire lotie s'ecrit « A26-.../2 » dans le fichier ; le
            # numero de tranche est repris a part dans la reference.
            affaire = affaire.split("/")[0].strip()
            if not affaire:
                continue
            refs.add(("%s_%s" % (affaire, position)).upper())
            refs.add(("%s/%s_%s" % (affaire, tranche or 0, position)).upper())
        return refs

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
            ligne = {
                "lot_id": lot.id,
                "sale_line_id": line.id,
                "product_qty": men.qty,
            }
            # L'ensemble debite de CE repere. L'OF de debit le sort, l'OF
            # d'assemblage de la meme ligne le consomme. Sans ce lien, tout le
            # lot partageait un ensemble debite generique : les coupes d'un
            # repere devenaient interchangeables avec celles d'un autre.
            if "product_debit_id" in self.env["fma.lot.fabrication.line"]._fields:
                ligne["product_debit_id"] = self._debit_product(
                    line.product_id
                ).id
            vals.append(ligne)
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
            product, problem = self._find_product(
                code, color,
                _("barre du plan de coupe"),
            )
            if not product:
                missing[problem] = missing.get(problem, 0.0) + entry["qty"]
                continue
            # Une barre vient de la table Profiles : c'est un profile, et
            # c'est ce qui garantit que l'OF de debit n'en consomme pas
            # d'autre nature.
            self._marquer_nature(product, "profile")
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

    def _marquer_nature(self, product, nature):
        """Recopie sur l'article la table du fichier dont il vient.

        Profiles, Articles, Glass : c'est la seule distinction qui fasse foi.
        Elle n'existe que pendant la lecture du fichier, et se perdait ensuite.
        La categorie d'article ne peut pas en tenir lieu — elle se modifie a la
        main, et on l'a deja fait pour debloquer un import.

        Le connecteur la pose a la creation ; l'import la repose a chaque
        passage, ce qui rattrape tout ce qui existe deja. sudo : le commercial
        qui importe n'ecrit pas sur les articles.
        """
        if not product or "fma_nature_logikal" not in product._fields:
            return
        if product.fma_nature_logikal != nature:
            product.sudo().fma_nature_logikal = nature

    def _find_article_libre(self, comp):
        """Retrouve l'article d'un composant saisi a la main dans LOGIKAL.

        Une ligne « manuelle » (``Articles.IsManual``) n'a rien a quoi se
        raccrocher : ni code article, ni GUID, ni hashcode — tout est vide.
        Les identifiants techniques du fichier, eux, sont locaux au fichier :
        le meme volet roulant est ``AllArticleID`` 4 dans l'export du lot 1 et
        15 dans celui du chantier entier. Il n'y a donc rien de plus solide a
        chercher dans le fichier : la designation est la seule chose stable,
        et elle porte d'ailleurs la reference du chiffreur
        (« SOP A26-07-03020/1_1 VR »).

        Cote Odoo, en revanche, on ne s'appuie pas sur le NOM de l'article,
        que n'importe qui peut modifier. Le connecteur marque ces articles a la
        creation (``fma_article_libre``) et recopie leur designation dans
        ``x_studio_ref_int_logikal`` — le champ technique sur lequel TOUS les
        autres articles sont deja rattaches. La marque dit ce qu'est
        l'article, la reference dit lequel ; ni l'une ni l'autre ne bouge
        quand le commercial renomme la fiche.

        Le nom reste une deuxieme passe, pour les articles libres crees avant
        que le connecteur ne pose la reference et que la reprise n'aurait pas
        rattrapes.

        LA RECHERCHE NE SORT PAS DE L'AFFAIRE. Deux lots d'un meme chantier
        doivent bien retomber sur le meme article : c'est la meme piece, et
        c'est tout l'interet. Deux chantiers differents, non — un chiffreur
        qui tape « Lisse galva basse » sur deux affaires decrit deux pieces,
        a deux prix. La marque dit que l'article est libre, elle ne dit pas
        de quel chantier il vient ; c'est la reference qui le porte, sous la
        forme « ABC A26-00-00002_LB1 ». Cette partie-la, elle, ne bouge pas :
        seul le compteur suit le fichier deposE.
        """
        Product = self.env["product.product"]
        designation = (comp.description or "").strip()
        if not designation:
            return Product

        # Le connecteur ne garde que la partie avant la barre : une affaire
        # lotie « A26-.../1 » donne des articles libres « A26-..._LB1 ».
        affaire = (
            self.env.context.get("fma_affaire") or ""
        ).split("/")[0].strip()
        if not affaire:
            # Sans affaire, on ne sait pas circonscrire la recherche, et
            # prendre l'article libre d'un autre chantier serait pire que de
            # signaler le manque.
            return Product

        # « _ » est un joker SQL ; il joue ici en notre faveur, la reference
        # etant de toute facon suffixee par le compteur.
        libres = [("default_code", "like", "%s_LB" % affaire)]
        if "fma_article_libre" in self.env["product.template"]._fields:
            # Marque posee par le connecteur a la creation : l'article ne vient
            # d'aucun catalogue, il a ete saisi a la main dans LOGIKAL.
            libres.append(("fma_article_libre", "=", True))

        if "x_studio_ref_int_logikal" in Product._fields:
            trouve = Product.search(
                libres + [("x_studio_ref_int_logikal", "=", designation)], limit=1
            )
            if trouve:
                return trouve

        # Deux lignes manuelles de meme designation DANS LA MEME AFFAIRE
        # donnent deux articles libres distincts ; rien ne les distingue, le
        # premier fait foi.
        return Product.search(libres + [("name", "=", designation)], limit=1)

    def _libelle_composant(self, comp, men):
        """De quoi nommer un composant que le fichier ne reference pas.

        L'import de LOT-2026-0008 a sorti trois fois la meme ligne, « profile
        sans reference dans le fichier », sur laquelle il n'y avait rien a
        faire : ni de quel profile il s'agissait, ni sur quelle menuiserie.
        Le code est vide, c'est le probleme meme ; on rapporte donc tout ce
        que le fichier porte par ailleurs, de quoi retrouver la ligne dans
        LOGIKAL et lui donner sa reference.
        """
        bouts = [_("position %s", men.position or men.ref)]
        designation = (comp.description or "").strip()
        if designation:
            bouts.append('"%s"' % designation)
        teinte = (comp.color or "").strip()
        if teinte:
            bouts.append(_("teinte %s", teinte))
        if comp.qty:
            bouts.append(_("qte %s", "%g" % comp.qty))
        return ", ".join(bouts)

    def _find_product(self, code, color="", contexte=""):
        """Retrouve un article par sa reference **et sa teinte**.

        ``sqlite_connector`` cree un article par couple (reference, teinte) :
        le ``default_code`` est suffixe par la couleur, et
        ``x_studio_ref_int_logikal`` / ``x_studio_color_logikal`` portent les
        deux valeurs du pricer. Chercher sur la seule reference reviendrait a
        prendre une teinte au hasard — donc a acheter la mauvaise barre.

        Renvoie ``(article, motif)``. Le motif decrit ce qui a empeche de
        trancher quand aucun article ne convient ; il est inscrit sur le lot,
        et n'interrompt pas l'import.

        ``contexte`` nomme l'element traite. Il ne sert qu'au cas ou le fichier
        ne donne aucune reference : sans lui, le message se resume a « profile
        sans reference dans le fichier », repete autant de fois qu'il y a de
        menuiseries concernees et sans rien pour retrouver le profile dans
        LOGIKAL. Les autres motifs citent deja le code et la teinte.
        """
        Product = self.env["product.product"]
        code = (code or "").strip()
        color = (color or "").strip()
        if not code:
            return Product, _(
                "%(quoi)s : aucune reference article dans le fichier",
                quoi=contexte or _("profile"),
            )

        # « profile » etait ecrit en dur ici, quelle que soit la nature de la
        # piece. Un JEU DE CLES manquant etait annonce comme un profile
        # introuvable : on cherchait la piece dans le mauvais catalogue.
        absent = _(
            "%(quoi)s %(code)s en %(color)s : article inexistant dans Odoo",
            quoi=contexte or _("article"),
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
            "%(quoi)s %(code)s : existe en %(colors)s, mais pas en %(wanted)s",
            quoi=contexte or _("article"),
            code=code,
            colors=", ".join(
                sorted((p.x_studio_color_logikal or "?") for p in candidates)
            ),
            wanted=color or _("sans teinte"),
        )
