# -*- coding: utf-8 -*-
"""Poste de scan : declaration de fabrication, localisation, SAV.

Un formulaire, et non un ecran JavaScript dedie. La douchette USB ou le PDA
en mode clavier « tape » le code puis Entree ; le champ change, l'onchange
traite le scan et vide le champ, pret pour le suivant. Aucun composant
navigateur a maintenir d'une version d'Odoo a l'autre, et le meme ecran
sert au clavier quand l'etiquette est abimee.

Le code est aussi capte quand le curseur n'est dans aucun champ, par le
service de code-barres standard (widget barcode_handler).
"""
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.stock_lot import fma_message

HISTORIQUE_MAX = 30

_COULEUR_ETAT = {
    "draft": "secondary", "confirmed": "info", "progress": "warning",
    "to_close": "warning", "done": "success", "cancel": "danger",
}
_COULEUR_OPERATION = {
    "blocked": "secondary", "ready": "info", "progress": "warning",
    "done": "success", "cancel": "danger",
}


class FmaPosteScan(models.TransientModel):
    _name = "fma.poste.scan"
    _description = "Poste de scan atelier"
    _inherit = ["barcodes.barcode_events_mixin"]

    # Aucun champ n'est en lecture seule ICI : le client web n'enregistre pas
    # un champ readonly, et le poste perdrait la menuiserie scannee des le
    # premier clic sur un bouton. La lecture seule est posee dans la vue,
    # avec force_save.
    mode = fields.Selection(
        [
            ("declarer", "Déclaration de fabrication"),
            ("localiser", "Localiser une menuiserie"),
            ("sav", "SAV"),
        ],
        string="Mode", required=True, default="declarer")
    action_auto = fields.Selection(
        [
            ("aucune", "Afficher la menuiserie, je valide au bouton"),
            ("operation", "Pointer l'opération (1er scan démarre, 2e termine)"),
            ("terminer", "Déclarer la menuiserie terminée"),
        ],
        string="Au scan", required=True, default="aucune",
        help="Ce que fait le poste des qu'une etiquette est lue. En mode "
        "automatique, un scan suffit : aucun clic.")
    code = fields.Char(string="Code scanné")
    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication", string="Lot de fabrication",
        help="Lot suivi par ce poste. Il se met a jour tout seul sur la "
        "menuiserie scannee.")
    serial_id = fields.Many2one(
        "stock.lot", string="Menuiserie")
    production_id = fields.Many2one(
        "mrp.production", string="Ordre de fabrication")
    production_state = fields.Selection(
        related="production_id.state", string="État de l'ordre")
    fiche = fields.Html(string="Menuiserie scannée",
                        sanitize=False)
    suivi = fields.Html(string="Suivi", sanitize=False)
    avancement = fields.Float(string="Avancement du lot")
    avancement_texte = fields.Char(string="Menuiseries terminées")
    ticket_count = fields.Integer(string="Tickets SAV")
    casier_emplacement = fields.Char(
        string="Emplacement du casier",
        help="Saisir l'emplacement puis « Ranger ici » : il est note sur "
        "la menuiserie scannee.")
    dernier_type = fields.Char(string="Type du dernier message")
    dernier_message = fields.Char(string="Dernier message")
    historique = fields.Html(string="Historique",
                             sanitize=False)

    # ------------------------------------------------------------------
    # Entrees : le champ, le service de code-barres, le bouton
    # ------------------------------------------------------------------
    @api.onchange("code")
    def _onchange_code(self):
        if self.code:
            self._fma_traiter(self.code)
            self.code = False

    def on_barcode_scanned(self, barcode):
        self._fma_traiter(barcode)

    @api.onchange("lot_fabrication_id")
    def _onchange_lot_fabrication_id(self):
        self._fma_rafraichir()

    def action_traiter(self):
        self.ensure_one()
        if self.code:
            self._fma_traiter(self.code)
            self.code = False
        return self._fma_rouvrir()

    # ------------------------------------------------------------------
    # Traitement d'un scan
    # ------------------------------------------------------------------
    def _fma_traiter(self, code):
        code = (code or "").strip()
        serie, ordre = self.env["stock.lot"]._fma_trouver(code)
        if not serie and not ordre:
            self.serial_id = False
            self.production_id = False
            resultat = fma_message("danger", _(
                "Code inconnu : %(code)s. Ni numéro de série, ni ordre de "
                "fabrication.", code=code))
            self._fma_rafraichir()
            self._fma_journaliser(resultat)
            return resultat

        self.serial_id = serie
        self.production_id = ordre
        if ordre.lot_fabrication_id:
            self.lot_fabrication_id = ordre.lot_fabrication_id

        if self.mode == "declarer":
            resultat = self._fma_scan_declarer(serie, ordre)
        elif self.mode == "sav":
            resultat = self._fma_scan_sav(serie)
        else:
            resultat = self._fma_scan_localiser(serie, ordre)
        self._fma_rafraichir()
        self._fma_journaliser(resultat)
        return resultat

    def _fma_scan_declarer(self, serie, ordre):
        nom = serie.name or ordre.name
        if not ordre:
            return fma_message("danger", _(
                "%(serie)s n'est rattaché à aucun ordre de fabrication.",
                serie=nom))
        if self.action_auto == "operation":
            return ordre.fma_scan_pointer_operation()
        if self.action_auto == "terminer":
            return ordre.fma_scan_terminer()
        blocage = ordre._fma_declarable()
        if blocage:
            return blocage
        operation = ordre._fma_prochaine_operation()
        return fma_message("info", _(
            "%(serie)s — %(of)s. %(suite)s",
            serie=nom, of=ordre.name,
            suite=_("Prochaine opération : %s.", operation.name)
            if operation else _("Gamme terminée, reste à déclarer.")))

    def _fma_scan_localiser(self, serie, ordre):
        if not serie:
            return fma_message("info", _(
                "%(of)s : ordre sans numéro de série.", of=ordre.name))
        etats = dict(self.env["mrp.production"]._fields["state"]
                     ._description_selection(self.env))
        morceaux = [serie.name]
        if ordre:
            morceaux.append(etats.get(ordre.state, ordre.state))
            if ordre.state not in ("done", "cancel") and \
                    serie.fma_operation_en_cours:
                morceaux.append(_("opération %s", serie.fma_operation_en_cours))
        if serie.fma_casier_emplacement:
            morceaux.append(_("casier en %s", serie.fma_casier_emplacement))
        morceaux.append(serie.fma_livraison or "")
        self.casier_emplacement = serie.fma_casier_emplacement
        return fma_message("info", " — ".join(m for m in morceaux if m))

    def _fma_scan_sav(self, serie):
        if not serie:
            return fma_message("danger", _(
                "Le SAV se déclare sur un numéro de série : cet ordre n'en "
                "porte pas."))
        nombre = len(serie.sudo().fma_ticket_ids)
        if nombre:
            return fma_message("warning", _(
                "%(serie)s : %(nb)s ticket(s) SAV déjà ouvert(s) sur cette "
                "menuiserie. Consultez-les ou créez-en un nouveau.",
                serie=serie.name, nb=nombre))
        return fma_message("info", _(
            "%(serie)s : aucun ticket. « Créer le ticket SAV » l'ouvre "
            "pré-rempli.", serie=serie.name))

    # ------------------------------------------------------------------
    # Affichage
    # ------------------------------------------------------------------
    def _fma_rafraichir(self):
        """Recalcule tout ce que l'ecran montre. Appele apres chaque geste :
        des champs calcules ne se rafraichiraient pas quand la meme
        menuiserie est scannee deux fois de suite."""
        serie, ordre = self.serial_id, self.production_id
        lot = self.lot_fabrication_id
        self.avancement = lot.fma_avancement if lot else 0.0
        self.avancement_texte = (
            _("%(faits)s / %(total)s menuiseries terminées — %(lot)s",
              faits=lot.fma_unites_terminees, total=lot.fma_unites_total,
              lot=lot.display_name)
            if lot else False)
        self.ticket_count = len(serie.sudo().fma_ticket_ids) if serie else 0
        self.fiche = self._fma_fiche_html(serie, ordre)
        self.suivi = serie.fma_historique if serie else False

    def _fma_fiche_html(self, serie, ordre):
        if not serie and not ordre:
            return False
        ordre = ordre.sudo()
        etats = dict(self.env["mrp.production"]._fields["state"]
                     ._description_selection(self.env))
        etats_op = dict(self.env["mrp.workorder"]._fields["state"]
                        ._description_selection(self.env))
        vals = (serie._fma_etiquette_vals(ordre or None) if serie else {
            "serie": ordre.name, "repere": "", "casier": "",
            "designation": ordre.product_id.display_name, "dimensions": "",
            "affaire": "", "commande": ordre.origin or "", "client": "",
            "chantier": "", "lot": ordre.lot_fabrication_id.display_name or "",
            "of": ordre.name,
        })
        badge = Markup("")
        if ordre:
            badge = Markup(
                "<span class='badge rounded-pill text-bg-%s ms-2'>%s</span>"
            ) % (_COULEUR_ETAT.get(ordre.state, "secondary"),
                 etats.get(ordre.state, ordre.state))
        lignes = [
            (_("Repère"), vals["repere"]),
            (_("Désignation"), vals["designation"]),
            (_("Dimensions"), vals["dimensions"]),
            (_("Affaire"), vals["affaire"]),
            (_("Commande"), vals["commande"]),
            (_("Client"), vals["client"]),
            (_("Chantier"), vals["chantier"]),
            (_("Lot de fabrication"), vals["lot"]),
            (_("Ordre de fabrication"), vals["of"]),
            (_("Emplacement du casier"),
             serie.fma_casier_emplacement if serie else ""),
            (_("Livraison"), serie.fma_livraison if serie else ""),
        ]
        tableau = Markup("").join(
            Markup("<tr><td class='text-muted pe-3'>%s</td>"
                   "<td><strong>%s</strong></td></tr>") % (cle, valeur)
            for cle, valeur in lignes if valeur)
        operations = Markup("").join(
            Markup("<span class='badge text-bg-%s me-1 mb-1'>%s : %s</span>")
            % (_COULEUR_OPERATION.get(op.state, "secondary"), op.name,
               etats_op.get(op.state, op.state))
            for op in ordre.workorder_ids)
        if operations:
            operations = Markup(
                "<div class='mt-2'><div class='text-muted'>%s</div>%s</div>"
            ) % (_("Opérations"), operations)
        return Markup(
            "<div><div class='fs-2 fw-bold'>%s%s</div>"
            "<table class='table table-sm table-borderless mb-0'>%s</table>"
            "%s</div>"
        ) % (escape(vals["serie"]), badge, tableau, operations)

    def _fma_journaliser(self, resultat):
        self.dernier_type = resultat["type"]
        self.dernier_message = resultat["message"]
        heure = fields.Datetime.context_timestamp(
            self, fields.Datetime.now()).strftime("%H:%M:%S")
        ligne = Markup('<div class="text-%s">%s — %s</div>') % (
            resultat["type"], heure, resultat["message"])
        anciennes = (str(self.historique).split("\n")
                     if self.historique else [])
        self.historique = Markup("\n").join(
            [ligne] + [Markup(l) for l in anciennes[:HISTORIQUE_MAX - 1]])

    def _fma_rouvrir(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Boutons
    # ------------------------------------------------------------------
    def _fma_ordre_requis(self):
        self.ensure_one()
        if not self.production_id:
            raise UserError(_("Scannez d'abord l'étiquette d'une menuiserie."))
        return self.production_id

    def _fma_serie_requise(self):
        self.ensure_one()
        if not self.serial_id:
            raise UserError(_("Scannez d'abord l'étiquette d'une menuiserie."))
        return self.serial_id

    def _fma_conclure(self, resultat):
        self._fma_rafraichir()
        self._fma_journaliser(resultat)
        return self._fma_rouvrir()

    def action_pointer_operation(self):
        return self._fma_conclure(
            self._fma_ordre_requis().fma_scan_pointer_operation())

    def action_terminer(self):
        return self._fma_conclure(
            self._fma_ordre_requis().fma_scan_terminer())

    def action_ranger(self):
        serie = self._fma_serie_requise()
        serie.sudo().fma_casier_emplacement = self.casier_emplacement
        return self._fma_conclure(fma_message("success", _(
            "%(serie)s : casier rangé en %(lieu)s.",
            serie=serie.name, lieu=self.casier_emplacement or "-")))

    def action_ouvrir_of(self):
        ordre = self._fma_ordre_requis()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "res_id": ordre.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_ouvrir_serie(self):
        serie = self._fma_serie_requise()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.lot",
            "res_id": serie.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_imprimer_etiquette(self):
        self.ensure_one()
        if self.serial_id:
            return self.serial_id.action_fma_imprimer_etiquette()
        return self._fma_ordre_requis().action_fma_imprimer_etiquettes()

    def action_creer_ticket(self):
        return self._fma_serie_requise().action_fma_creer_ticket()

    def action_voir_tickets(self):
        return self._fma_serie_requise().action_fma_voir_tickets()
