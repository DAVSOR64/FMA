# -*- coding: utf-8 -*-
"""La menuiserie, vue depuis son numero de serie.

Le lot de fabrication cree un ordre par menuiserie et lui pose un numero de
serie « <reference>-NNN ». Ce numero est aussi celui du casier que le magasin
garnit. C'est donc lui qui porte l'etiquette, et c'est par lui que l'on
retrouve tout le reste : l'ordre, le lot, la commande, la livraison, le SAV.

Rien n'est stocke ici en dehors du jeton SAV et de l'emplacement du casier :
tout le suivi est relu a la demande sur les documents qui font foi.
"""
import base64
import re
import uuid

from markupsafe import Markup, escape

from odoo import _, api, fields, models

#: Chemin de la page SAV, tel qu'il est encode dans le QR code.
SAV_ROUTE = "/fma/sav/"

#: Une douchette reglee en QWERTY, branchee sur un poste en AZERTY, « tape »
#: d'autres caracteres que ceux de l'etiquette : les chiffres deviennent
#: « &e"'(-e_ca », le tiret devient « ) », A et Q s'echangent. Table de
#: retour : ce qui a ete tape -> ce qui etait imprime.
_AZERTY_VERS_QWERTY = str.maketrans({
    "&": "1", "é": "2", '"': "3", "'": "4", "(": "5", "-": "6", "è": "7",
    "_": "8", "ç": "9", "à": "0", ")": "-", "°": "_",
    "Q": "A", "A": "Q", "Z": "W", "W": "Z", "?": "M",
    "q": "a", "a": "q", "z": "w", "w": "z", ",": "m",
})


def fma_message(type_, message, **extra):
    """Resultat d'un scan : un niveau (success, info, warning, danger) et
    une phrase. Le poste de scan l'affiche et l'empile dans son historique."""
    return dict(type=type_, message=message, **extra)


class StockLot(models.Model):
    _inherit = "stock.lot"

    # --- Stocke -------------------------------------------------------------
    fma_sav_token = fields.Char(
        string="Jeton SAV",
        copy=False,
        index="btree_not_null",
        readonly=True,
        help="Jeton aleatoire porte par le QR code de l'etiquette. Le lien "
        "SAV ne s'appuie pas sur le numero de serie, qui se devine.",
    )
    fma_casier_emplacement = fields.Char(
        string="Emplacement du casier",
        copy=False,
        help="Ou se trouve le casier (ou la menuiserie) dans l'atelier : "
        "travee, chariot, quai. Saisie libre, modifiable au poste de scan.",
    )

    # --- Relu a la demande --------------------------------------------------
    fma_sav_url = fields.Char(string="Lien SAV", compute="_compute_fma_suivi")
    fma_est_menuiserie = fields.Boolean(
        string="Menuiserie d'un lot",
        compute="_compute_fma_suivi",
        search="_search_fma_est_menuiserie",
    )
    fma_production_id = fields.Many2one(
        "mrp.production", string="Ordre de fabrication",
        compute="_compute_fma_suivi")
    # Calcule, et non related : fma_production_id n'est pas stocke, et un
    # related ferait chercher a Odoo, a chaque changement d'etat d'un ordre,
    # les numeros de serie concernes — en SQL, sur un champ sans colonne.
    fma_etat_fabrication = fields.Selection(
        selection=lambda self: self.env["mrp.production"]._fields[
            "state"]._description_selection(self.env),
        string="État de fabrication", compute="_compute_fma_suivi")
    fma_lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication", string="Lot de fabrication",
        compute="_compute_fma_suivi")
    fma_sale_order_id = fields.Many2one(
        "sale.order", string="Commande", compute="_compute_fma_suivi")
    fma_partner_id = fields.Many2one(
        "res.partner", string="Client", compute="_compute_fma_suivi")
    fma_affaire = fields.Char(string="Affaire", compute="_compute_fma_suivi")
    fma_chantier = fields.Char(string="Chantier", compute="_compute_fma_suivi")
    fma_repere = fields.Char(string="Repère", compute="_compute_fma_suivi")
    fma_casier = fields.Char(
        string="Casier n°", compute="_compute_fma_suivi",
        help="Rang de la menuiserie : la fin du numero de serie.")
    fma_dimensions = fields.Char(
        string="Dimensions", compute="_compute_fma_suivi")
    fma_operation_en_cours = fields.Char(
        string="Opération en cours", compute="_compute_fma_suivi")
    fma_date_fabrication = fields.Datetime(
        string="Fabriquée le", compute="_compute_fma_suivi")
    fma_picking_id = fields.Many2one(
        "stock.picking", string="Livraison", compute="_compute_fma_suivi")
    fma_date_livraison = fields.Datetime(
        string="Livrée le", compute="_compute_fma_suivi")
    fma_livraison = fields.Char(
        string="État de livraison", compute="_compute_fma_suivi")
    fma_ticket_ids = fields.One2many(
        "helpdesk.ticket", "fma_serial_id", string="Liste des tickets SAV")
    fma_ticket_count = fields.Integer(
        string="Tickets SAV", compute="_compute_fma_ticket_count")
    fma_historique = fields.Html(
        string="Historique", compute="_compute_fma_suivi", sanitize=False)

    # ------------------------------------------------------------------
    # Contexte : de la serie a tout ce qui l'entoure
    # ------------------------------------------------------------------
    def _fma_productions(self):
        """{id de serie: ordre qui la produit}.

        L'assemblage du lot l'emporte, puis le plus recent. Un ordre annule
        ne compte pas : apres une regeneration, c'est l'ordre vivant qui
        porte la menuiserie.
        """
        resultat = {}
        ids = self._origin.ids
        if not ids:
            return resultat
        ordres = self.env["mrp.production"].sudo().search(
            [("lot_producing_ids", "in", ids), ("state", "!=", "cancel")],
            order="id")
        for ordre in ordres:
            for serie in ordre.lot_producing_ids:
                actuel = resultat.get(serie.id)
                if (
                    not actuel
                    or ordre.lot_production_type == "assemblage"
                    or actuel.lot_production_type != "assemblage"
                ):
                    resultat[serie.id] = ordre
        return resultat

    def _fma_contexte(self, ordre=None):
        """Tout ce que l'on sait d'une menuiserie, en enregistrements."""
        self.ensure_one()
        serie = self.sudo()
        if ordre is None:
            ordre = serie._fma_productions().get(serie._origin.id)
        ordre = (ordre or self.env["mrp.production"]).sudo()
        ligne_lot = ordre.lot_line_id
        ligne = ordre.lot_sale_line_id or ligne_lot.sale_line_id
        commande = ligne.order_id or ordre.lot_sale_order_id
        if not commande and "fma_sale_order_id" in ordre._fields:
            commande = ordre.fma_sale_order_id
        projet = self.env["project.project"].sudo()
        if ordre and "x_studio_projet_de_la_vente" in ordre._fields:
            projet = ordre.x_studio_projet_de_la_vente
        if not projet and commande and "x_studio_projet" in commande._fields:
            projet = commande.x_studio_projet
        return {
            "ordre": ordre,
            "lot": ordre.lot_fabrication_id or ligne_lot.lot_id,
            "ligne": ligne,
            "commande": commande,
            "client": commande.partner_id,
            "projet": projet,
        }

    def _fma_repere(self):
        """La POSITION seule — « E-MEXT-C1 » —, comme sur la liste de
        quincaillerie : le prefixe de la reference est l'affaire, deja
        imprimee ailleurs sur l'etiquette."""
        self.ensure_one()
        produit = self.product_id
        if "x_studio_position" in produit._fields and produit.x_studio_position:
            return produit.x_studio_position
        code = produit.default_code or ""
        return code.rpartition("_")[2] or code or produit.name or ""

    def _fma_dimensions(self):
        self.ensure_one()
        produit = self.product_id
        largeur = (
            produit.x_studio_largeur_mm
            if "x_studio_largeur_mm" in produit._fields else 0)
        hauteur = (
            produit.x_studio_hauteur_mm
            if "x_studio_hauteur_mm" in produit._fields else 0)
        if largeur and hauteur:
            return "L %s x H %s mm" % (largeur, hauteur)
        return ""

    def _fma_rang(self):
        """« 002 » pour « A26-00-00002_E-MEXT-C1-002 »."""
        self.ensure_one()
        fin = (self.name or "").rpartition("-")[2]
        return fin if fin.isdigit() else ""

    def _fma_livraison(self, ligne):
        """(bon de livraison, date de livraison effective, libelle).

        La ligne de mouvement qui porte CE numero de serie fait foi : c'est
        cette menuiserie-la qui est partie. A defaut, le bon de livraison
        de la ligne de commande dit ce qui est prevu.
        """
        self.ensure_one()
        Picking = self.env["stock.picking"].sudo()
        mouvement = self.env["stock.move.line"].sudo().search(
            [
                ("lot_id", "=", self._origin.id),
                ("picking_id.picking_type_code", "=", "outgoing"),
                ("state", "!=", "cancel"),
            ],
            order="id desc", limit=1,
        ) if self._origin.id else self.env["stock.move.line"]
        bon = mouvement.picking_id
        if bon and bon.state == "done":
            return bon, bon.date_done, _(
                "Livrée le %(date)s (%(bon)s)",
                date=fields.Date.to_string(bon.date_done), bon=bon.name)
        if not bon and ligne:
            bons = ligne.sudo().move_ids.picking_id.filtered(
                lambda p: p.picking_type_code == "outgoing"
                and p.state != "cancel")
            bon = bons.filtered(lambda p: p.state != "done")[:1] or bons[:1]
        if bon:
            if bon.state == "done":
                return bon, False, _(
                    "Livraison %(bon)s faite — cette menuiserie n'y figure "
                    "pas au numéro de série", bon=bon.name)
            return bon, False, _(
                "Livraison prévue le %(date)s (%(bon)s)",
                date=fields.Date.to_string(bon.scheduled_date) or "?",
                bon=bon.name)
        return Picking, False, _("Pas encore de livraison")

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    def _fma_base_url(self):
        return (self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url") or "").rstrip("/")

    @api.depends("name", "product_id")
    def _compute_fma_suivi(self):
        ordres = self._fma_productions()
        base = self._fma_base_url()
        for serie in self:
            ordre = ordres.get(serie._origin.id)
            ctx = serie._fma_contexte(ordre or self.env["mrp.production"])
            ordre = ctx["ordre"]
            commande = ctx["commande"]
            bon, date_livraison, libelle = serie._fma_livraison(ctx["ligne"])
            en_cours = ordre.workorder_ids.filtered(
                lambda w: w.state == "progress")[:1] or (
                ordre._fma_prochaine_operation() if ordre else ordre.workorder_ids)

            serie.fma_production_id = ordre
            serie.fma_etat_fabrication = ordre.state or False
            serie.fma_est_menuiserie = bool(ordre.lot_fabrication_id)
            serie.fma_lot_fabrication_id = ctx["lot"]
            serie.fma_sale_order_id = commande
            serie.fma_partner_id = ctx["client"]
            serie.fma_affaire = (
                commande.x_studio_ref_affaire
                if commande and "x_studio_ref_affaire" in commande._fields
                else False) or False
            serie.fma_chantier = ctx["projet"].display_name or False
            serie.fma_repere = serie._fma_repere() if serie.product_id else False
            serie.fma_casier = serie._fma_rang() or False
            serie.fma_dimensions = (
                serie._fma_dimensions() if serie.product_id else False)
            serie.fma_operation_en_cours = en_cours.name or False
            serie.fma_date_fabrication = (
                ordre.date_finished if ordre.state == "done" else False)
            serie.fma_picking_id = bon
            serie.fma_date_livraison = date_livraison
            serie.fma_livraison = libelle
            serie.fma_sav_url = (
                "%s%s%s" % (base, SAV_ROUTE, serie.fma_sav_token)
                if serie.fma_sav_token else False)
            serie.fma_historique = serie._fma_historique_html(
                ctx, bon, libelle)

    @api.depends("fma_ticket_ids")
    def _compute_fma_ticket_count(self):
        for serie in self:
            serie.fma_ticket_count = len(serie.sudo().fma_ticket_ids)

    def _search_fma_est_menuiserie(self, operator, value):
        if operator not in ("in", "not in", "=", "!="):
            return NotImplemented
        if isinstance(value, (list, tuple, set, frozenset)):
            vrai = any(value)
        else:
            vrai = bool(value)
        positif = (operator in ("in", "=")) == vrai
        series = self.env["mrp.production"].sudo().search([
            ("lot_fabrication_id", "!=", False),
            ("state", "!=", "cancel"),
            ("lot_producing_ids", "!=", False),
        ]).lot_producing_ids
        return [("id", "in" if positif else "not in", series.ids)]

    def _fma_historique_html(self, ctx, bon, libelle_livraison):
        """La vie de la menuiserie, dans l'ordre : fabrication, livraison,
        SAV. Une liste, lisible telle quelle sur un PDA."""
        self.ensure_one()
        ordre = ctx["ordre"]
        etats_of = dict(
            self.env["mrp.production"]._fields["state"]
            ._description_selection(self.env))
        etats_op = dict(
            self.env["mrp.workorder"]._fields["state"]
            ._description_selection(self.env))

        def jour(valeur):
            if not valeur:
                return ""
            return fields.Datetime.context_timestamp(
                self, valeur).strftime("%d/%m/%Y %H:%M")

        lignes = []
        if self.create_date:
            lignes.append((jour(self.create_date), _(
                "Numéro de série créé (casier préparé par le magasin)")))
        if ordre:
            lignes.append((jour(ordre.create_date), _(
                "Ordre %(of)s — lot %(lot)s — %(etat)s",
                of=ordre.name,
                lot=ctx["lot"].display_name or "-",
                etat=etats_of.get(ordre.state, ordre.state))))
            for op in ordre.workorder_ids:
                lignes.append((
                    jour(op.date_finished if op.state == "done"
                         else op.date_start if op.state == "progress"
                         else False),
                    _("Opération %(op)s : %(etat)s%(duree)s",
                      op=op.name,
                      etat=etats_op.get(op.state, op.state),
                      duree=(" (%d min)" % round(op.duration)
                             if op.state == "done" else "")),
                ))
            if ordre.state == "done":
                lignes.append((jour(ordre.date_finished), _(
                    "Menuiserie déclarée terminée")))
        lignes.append((jour(bon.date_done) if bon.state == "done" else "",
                       libelle_livraison))
        for ticket in self.sudo().fma_ticket_ids.sorted("id"):
            lignes.append((jour(ticket.create_date), _(
                "Ticket SAV : %(nom)s", nom=ticket.display_name)))

        corps = Markup("").join(
            Markup("<tr><td class='text-muted pe-3' style='white-space:"
                   "nowrap;'>%s</td><td>%s</td></tr>") % (date, texte)
            for date, texte in lignes)
        return Markup(
            "<table class='table table-sm table-borderless mb-0'>%s</table>"
        ) % corps

    # ------------------------------------------------------------------
    # Jeton et lien SAV
    # ------------------------------------------------------------------
    def _fma_assurer_jeton(self):
        """Pose le jeton SAV des series qui n'en ont pas encore.

        A la demande et non a la creation : les numeros existent deja en
        base, et seules les menuiseries etiquetees en ont besoin.
        """
        for serie in self.sudo().filtered(lambda s: not s.fma_sav_token):
            serie.fma_sav_token = uuid.uuid4().hex
        return True

    def _fma_url_sav(self):
        self.ensure_one()
        self._fma_assurer_jeton()
        return "%s%s%s" % (
            self._fma_base_url(), SAV_ROUTE, self.sudo().fma_sav_token)

    # ------------------------------------------------------------------
    # Lecture d'un code scanne
    # ------------------------------------------------------------------
    @api.model
    def _fma_trouver(self, code):
        """(numero de serie, ordre) designes par un code scanne.

        Trois codes sont acceptes : le Code128 de l'etiquette (le numero de
        serie), son QR code (le lien SAV), et le numero d'un ordre de
        fabrication — pour une menuiserie qui ne serait pas suivie au numero
        de serie.
        """
        Ordre = self.env["mrp.production"].sudo()
        code = (code or "").strip()
        if not code:
            return self.browse(), Ordre

        jeton = re.search(r"/fma/sav/([0-9a-fA-F]{16,64})", code)
        if jeton:
            serie = self.sudo().search(
                [("fma_sav_token", "=", jeton.group(1).lower())], limit=1)
            if serie:
                return (self.browse(serie.id),
                        serie._fma_productions().get(serie.id, Ordre))

        candidats = [code]
        if code.upper() != code:
            candidats.append(code.upper())
        retour = code.translate(_AZERTY_VERS_QWERTY)
        if retour != code:
            candidats.append(retour)

        for candidat in candidats:
            series = self.sudo().search([("name", "=", candidat)])
            if series:
                ordres = series._fma_productions()
                # Deux articles peuvent porter le meme numero : celui qui est
                # rattache a un ordre est la menuiserie.
                serie = series.filtered(lambda s: s.id in ordres)[:1] or series[:1]
                return self.browse(serie.id), ordres.get(serie.id, Ordre)
            ordre = Ordre.search([("name", "=", candidat)], limit=1)
            if ordre:
                return self.browse(ordre.lot_producing_ids[:1].id), ordre
        return self.browse(), Ordre

    # ------------------------------------------------------------------
    # Etiquette
    # ------------------------------------------------------------------
    def _fma_image(self, type_code, valeur, **options):
        """Le code en image embarquee. Le PDF ne depend ainsi d'aucun appel
        HTTP de wkhtmltopdf vers Odoo — c'est ce qui casse le plus souvent
        une etiquette, quand l'adresse du serveur n'est pas joignable."""
        if not valeur:
            return ""
        try:
            png = self.env["ir.actions.report"].barcode(
                type_code, valeur, **options)
        except (ValueError, AttributeError):
            return ""
        return "data:image/png;base64,%s" % base64.b64encode(png).decode()

    def _fma_etiquette_vals(self, ordre=None):
        """Le contenu d'une etiquette, pret a imprimer."""
        self.ensure_one()
        ctx = self._fma_contexte(ordre)
        ordre = ctx["ordre"]
        commande = ctx["commande"]
        ligne = ctx["ligne"]
        produit = self.product_id
        url = self._fma_url_sav()
        designation = (ligne.name or produit.display_name or "").strip()
        return {
            "serie": self.name,
            "casier": self._fma_rang(),
            "repere": self._fma_repere(),
            "designation": designation.split("\n")[0][:90],
            "dimensions": self._fma_dimensions(),
            "affaire": (
                commande.x_studio_ref_affaire
                if commande and "x_studio_ref_affaire" in commande._fields
                else "") or "",
            "commande": commande.name or ordre.origin or "",
            "client": ctx["client"].display_name or "",
            "chantier": ctx["projet"].display_name or "",
            "lot": ctx["lot"].display_name or "",
            "of": ordre.name or "",
            "societe": (self.company_id or ordre.company_id
                        or self.env.company).name,
            "sav_url": url,
            # CODE128 NE SAIT PAS ECRIRE UN ACCENT. Il ne couvre que l'ASCII,
            # et les numeros de serie reprennent le nom de la ligne de
            # commande : « A26-10-07831_Repère A - Entrée-001 » le faisait
            # echouer. L'echec etait avale par _fma_image et le t-if du
            # modele masquait simplement le code — l'etiquette sortait sans
            # code-barres de serie, sans rien dire. Le QR, lui, accepte
            # l'UTF-8 : il prend le relais plutot que de laisser un trou.
            "barcode_src": self._fma_image(
                "Code128", self.name, width=900, height=140, quiet=1),
            "serie_qr_src": "" if self._fma_image(
                "Code128", self.name, width=900, height=140, quiet=1
            ) else self._fma_image(
                "QR", self.name, width=260, height=260, barLevel="M"),
            # Le numero d'ORDRE, en code-barres lui aussi. L'etiquette ne
            # portait que le numero de serie : il designe la menuiserie, mais
            # l'ecran Atelier s'ouvre sur un ordre. L'operateur lisait donc le
            # numero d'OF en clair et le tapait. Les deux codes coexistent —
            # le serie pour la tracabilite et le SAV, l'ordre pour l'atelier.
            "of_barcode_src": self._fma_image(
                "Code128", ordre.name, width=900, height=100, quiet=1
            ) if ordre.name else "",
            "qr_src": self._fma_image(
                "QR", url, width=300, height=300, barLevel="M"),
        }

    def _fma_etiquettes(self):
        return [serie._fma_etiquette_vals() for serie in self]

    def action_fma_imprimer_etiquette(self):
        return self.env.ref(
            "fma_etiquette_scan.action_report_etiquette_serie"
        ).report_action(self, config=False)

    # ------------------------------------------------------------------
    # SAV
    # ------------------------------------------------------------------
    def _fma_valeurs_ticket(self, objet=None, description=None):
        """Valeurs d'un ticket SAV pre-rempli pour cette menuiserie."""
        self.ensure_one()
        Ticket = self.env["helpdesk.ticket"]
        ctx = self._fma_contexte()
        ordre, commande = ctx["ordre"], ctx["commande"]
        lignes = [
            (_("Numéro de série"), self.name),
            (_("Menuiserie"), self.product_id.display_name),
            (_("Repère"), self._fma_repere()),
            (_("Dimensions"), self._fma_dimensions()),
            (_("Affaire"),
             commande.x_studio_ref_affaire
             if commande and "x_studio_ref_affaire" in commande._fields
             else ""),
            (_("Commande"), commande.name),
            (_("Client"), ctx["client"].display_name),
            (_("Chantier"), ctx["projet"].display_name),
            (_("Lot de fabrication"), ctx["lot"].display_name),
            (_("Ordre de fabrication"), ordre.name),
        ]
        fiche = Markup("<ul>%s</ul>") % Markup("").join(
            Markup("<li><strong>%s</strong> : %s</li>") % (cle, valeur)
            for cle, valeur in lignes if valeur)
        corps = Markup("")
        if description:
            corps = Markup("<p>%s</p>") % Markup("<br/>").join(
                escape(l) for l in description.splitlines())
        vals = {
            "name": _("SAV %(serie)s%(objet)s",
                      serie=self.name,
                      objet=" - %s" % objet if objet else ""),
            "fma_serial_id": self.id,
            "description": corps + fiche,
        }
        if "company_id" in Ticket._fields and self.company_id:
            vals["company_id"] = self.company_id.id
        return vals

    def _fma_creer_ticket(self, objet=None, description=None, extra=None):
        """Cree le ticket SAV de cette menuiserie."""
        self.ensure_one()
        vals = self._fma_valeurs_ticket(objet, description)
        vals.update(extra or {})
        return self.env["helpdesk.ticket"].create(vals)

    def action_fma_creer_ticket(self):
        """Ouvre un ticket pre-rempli : rien n'est cree tant que
        l'utilisateur n'enregistre pas."""
        self.ensure_one()
        vals = self._fma_valeurs_ticket()
        client = self._fma_contexte()["client"]
        if client:
            vals["partner_id"] = client.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Ticket SAV"),
            "res_model": "helpdesk.ticket",
            "view_mode": "form",
            "target": "current",
            "context": {"default_%s" % cle: valeur
                        for cle, valeur in vals.items()},
        }

    def action_fma_voir_tickets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "fma_etiquette_scan.action_fma_ticket_sav")
        action["domain"] = [("fma_serial_id", "=", self.id)]
        action["context"] = {"default_fma_serial_id": self.id}
        return action

    def action_fma_voir_of(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "res_id": self.fma_production_id.id,
            "view_mode": "form",
            "target": "current",
        }
