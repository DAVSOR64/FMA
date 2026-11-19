# -*- coding: utf-8 -*-
"""Declaration de fabrication au scan, ordre par ordre.

Le lot a deja scinde les assemblages : un ordre = une menuiserie = un numero
de serie. Declarer au scan revient donc a terminer UN ordre, en entier, avec
le numero qu'il porte deja — sans reliquat, sans ecran des numeros de serie.

Tout passe par les methodes standard (button_start, button_finish,
button_mark_done). Si Odoo refuse — composant suivi sans numero, controle
qualite en attente, operateur non identifie —, le refus est affiche au poste
et note dans le fil de l'ordre. Rien n'est force.
"""
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

from .stock_lot import (
    fma_complexite_etiquette,
    fma_entete_affaire,
    fma_lot_court,
    fma_message,
)

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # ------------------------------------------------------------------
    # L'en-tete de l'etiquette : le meme pour tout le lot
    # ------------------------------------------------------------------
    #: Les champs ou la commande peut se trouver sur un ordre, du plus sur au
    #: plus lointain. lot_sale_line_id n'existe que sur un ordre PAR LIGNE —
    #: assemblage, quincaillerie. Le DEBIT n'en a pas, et c'est voulu : y
    #: poser une ligne de vente ferait croire a l'approvisionnement que le
    #: besoin de la ligne est couvert, et l'ordre d'assemblage ne naitrait
    #: plus (cf. _common_production_vals).
    FMA_CHAMPS_COMMANDE = (
        "lot_sale_order_id",
        "x_studio_mtn_mrp_sale_order",
        "fma_sale_order_id",
    )

    #: Ou le chantier se trouve sur la commande, selon les modules installes.
    FMA_CHAMPS_PROJET = (
        "project_id", "x_studio_projet", "x_studio_projet_de_la_vente")

    def _fma_commande_etiquette(self):
        """La commande que l'etiquette doit nommer.

        Le LOT est le dernier recours, et il suffit la ou les champs d'ordre
        sont vides : un lot ne se monte que sur des lignes de vente.

        En sudo, comme tout ce que l'etiquette imprime : elle sort au poste
        de scan, et un operateur d'atelier ne lit pas les commandes.
        """
        self.ensure_one()
        ordre = self.sudo()
        for nom in self.FMA_CHAMPS_COMMANDE:
            if nom in ordre._fields and ordre[nom]:
                return ordre[nom]
        return ordre.lot_fabrication_id.sale_order_ids.sorted("id")[:1]

    def _fma_projet_etiquette(self, commande=None):
        """Le chantier a imprimer : celui de l'ordre, sinon celui de sa
        commande."""
        self.ensure_one()
        ordre = self.sudo()
        champ = "x_studio_projet_de_la_vente"
        if champ in ordre._fields and ordre[champ]:
            return ordre[champ]
        if commande is None:
            commande = ordre._fma_commande_etiquette()
        for nom in self.FMA_CHAMPS_PROJET:
            if commande and nom in commande._fields and commande[nom]:
                return commande[nom]
        return self.env["project.project"]

    # ------------------------------------------------------------------
    # Lecture d'une etiquette depuis l'ecran Atelier
    # ------------------------------------------------------------------
    @api.model
    def fma_ordre_du_code(self, code):
        """Le nom de l'ordre designe par un code scanne, ou une chaine vide.

        L'ecran Atelier ne sait chercher qu'un NUMERO D'ORDRE. L'etiquette
        d'une menuiserie, elle, porte son NUMERO DE SERIE — c'est la
        menuiserie que l'etiquette designe, pas le document qui la fabrique.
        Le scan ne trouvait donc rien, et l'operateur en concluait que la
        douchette etait cassee. L'etiquette de debit, qui n'a pas de numero
        de serie et porte celui de son ordre, marchait : d'ou l'impression
        que seule une des deux etiquettes etait lisible.

        PUBLIQUE A DESSEIN : l'ecran l'appelle par RPC, et le protocole
        refuse les methodes privees. Elle ne rend qu'un nom d'ordre.
        """
        _serie, ordre = self.env["stock.lot"]._fma_trouver(code)
        return ordre.name or ""

    # ------------------------------------------------------------------
    # Etiquettes
    # ------------------------------------------------------------------
    def _fma_ordre_etiquettes(self):
        """Dans l'ordre de la liste de quincaillerie : ligne de lot, puis
        rang de l'ordre. Le paquet d'etiquettes se pose ainsi sur les
        casiers sans avoir a chercher."""
        return self.sorted(lambda mo: (
            mo.lot_fabrication_id.id or 0,
            mo.lot_line_id.sequence or 0,
            mo.lot_line_id.id or 0,
            mo.id,
        ))

    def _fma_etiquettes(self):
        """Une etiquette par menuiserie. Un ordre sans numero de serie —
        article non suivi — recoit une etiquette a son propre numero : le
        poste de scan sait aussi le lire."""
        etiquettes = []
        for ordre in self._fma_ordre_etiquettes():
            if ordre.state == "cancel":
                continue
            if ordre.lot_producing_ids:
                for serie in ordre.lot_producing_ids:
                    etiquettes.append(serie._fma_etiquette_vals(ordre))
                continue
            produit = ordre.product_id
            Serie = self.env["stock.lot"]
            # L'EN-TETE EST CELUI DE L'ETIQUETTE D'ASSEMBLAGE, au mot pres :
            # les deux etiquettes se posent cote a cote sur le meme casier,
            # et l'atelier doit y lire la meme affaire.
            #
            # L'ordre de debit n'a pas de ligne de vente : lot_sale_order_id
            # etait vide, la premiere ligne retombait sur « origin » — qui
            # vaut « <lot> - <commande> » —, le lot s'y repetait et le client
            # manquait. On resout donc la commande comme pour une menuiserie.
            commande = ordre._fma_commande_etiquette()
            projet_rec = ordre._fma_projet_etiquette(commande)
            projet = projet_rec.display_name or ""
            etiquettes.append({
                "serie": ordre.name,
                "casier": "",
                # Un ordre sans numero de serie n'a pas d'exemplaires
                # numerotes : c'est un habillage, pas une menuiserie.
                "exemplaire": "",
                "affaire_ligne": fma_entete_affaire(
                    commande.name or ordre.origin or "", projet),
                "lot_court": fma_lot_court(
                    ordre.lot_fabrication_id.display_name or "",
                    commande.name or ""),
                # L'OF de debit ne porte pas de repere : il les coupe tous.
                # Son article s'appelle « <affaire>_DEB », dont la regle
                # generale tirerait « DEB » — un sigle qui ne dit rien de loin
                # sur un casier. On ecrit le mot.
                "repere": _("DÉBIT")
                if ordre.lot_production_type == "debit"
                else ((produit.default_code or "").rpartition("_")[2]
                      or produit.default_code or ""),
                # Le debit ne porte pas de complexite : il coupe pour
                # tout le lot, pas pour une menuiserie.
                "complexite": "" if ordre.lot_production_type == "debit"
                else fma_complexite_etiquette(ordre, produit),
                "designation": (produit.display_name or "")[:90],
                "dimensions": "",
                "affaire": (
                    commande.x_studio_ref_affaire
                    if commande and "x_studio_ref_affaire" in commande._fields
                    else "") or "",
                "commande": commande.name or ordre.origin or "",
                "client": commande.partner_id.display_name or "",
                "chantier": projet,
                "lot": ordre.lot_fabrication_id.display_name or "",
                "of": ordre.name,
                "societe": ordre.company_id.name,
                # Faute de numero de serie — un habillage n'en porte pas —,
                # le code-barres prend le numero de l'ordre : le poste de
                # scan sait le lire aussi, et c'est le seul identifiant que
                # cette etiquette-la puisse porter.
                "barcode_src": Serie._fma_image(
                    "Code128", ordre.name, width=900, height=140, quiet=1),
                # Pas de repli en QR : un numero d'ordre est de l'ASCII,
                # Code128 l'ecrit toujours. Le repli n'existe que pour les
                # numeros de serie accentues.
                "serie_qr_src": "",
            })
        return etiquettes

    def action_fma_imprimer_etiquettes(self):
        return self.env.ref(
            "fma_etiquette_scan.action_report_etiquette_of"
        ).report_action(self._fma_ordre_etiquettes(), config=False)

    # ------------------------------------------------------------------
    # Declaration
    # ------------------------------------------------------------------
    def _fma_prochaine_operation(self):
        """La premiere operation qui reste a faire, dans l'ordre de la
        gamme."""
        self.ensure_one()
        return self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel"))[:1]

    def _fma_refus(self, erreur, geste):
        """Odoo a refuse : on le dit au poste, et on le note sur l'ordre.

        La note est posee APRES le retour au point de sauvegarde, elle ne
        disparait donc pas avec ce qui a ete annule.
        """
        self.ensure_one()
        texte = str(erreur.args[0]) if erreur.args else str(erreur)
        try:
            self.message_post(body=_(
                "Scan atelier — %(geste)s refusé : %(erreur)s",
                geste=geste, erreur=texte))
        except Exception:  # noqa: BLE001 — la note ne doit jamais bloquer
            _logger.exception("Note de refus sur %s", self.display_name)
        return fma_message("danger", _(
            "%(of)s : %(erreur)s", of=self.name, erreur=texte))

    def _fma_declarable(self):
        """Un message si l'ordre ne peut pas etre declare, sinon rien."""
        self.ensure_one()
        if self.state == "done":
            return fma_message("info", _(
                "%(of)s est déjà terminé.", of=self.name))
        if self.state == "cancel":
            return fma_message("danger", _(
                "%(of)s est annulé.", of=self.name))
        if self.state == "draft":
            return fma_message("danger", _(
                "%(of)s est encore en brouillon : confirmez-le d'abord.",
                of=self.name))
        return None

    def fma_scan_pointer_operation(self):
        """Fait avancer la gamme d'un cran.

        Premier scan : l'operation suivante demarre, le chronometre standard
        tourne. Second scan : elle se termine, avec la duree reellement
        ecoulee. C'est un pointage, pas une saisie de temps.
        """
        self.ensure_one()
        blocage = self._fma_declarable()
        if blocage:
            return blocage
        operation = self._fma_prochaine_operation()
        if not operation:
            return fma_message("info", _(
                "%(of)s : toutes les opérations sont terminées. Déclarez "
                "la menuiserie terminée.", of=self.name))
        try:
            with self.env.cr.savepoint():
                if operation.state == "progress":
                    operation.button_finish()
                    suivante = self._fma_prochaine_operation()
                    return fma_message("success", _(
                        "%(op)s terminée (%(duree)d min)%(suite)s",
                        op=operation.name,
                        duree=round(operation.duration),
                        suite=_(" — reste : %s", suivante.name)
                        if suivante else _(" — gamme terminée")))
                operation.button_start()
                return fma_message("success", _(
                    "%(op)s démarrée sur %(of)s.",
                    op=operation.name, of=self.name))
        except UserError as erreur:
            return self._fma_refus(erreur, _("pointage de l'opération"))

    def fma_scan_terminer(self):
        """Declare la menuiserie terminee.

        Les operations restantes sont soldees par la methode standard
        « marquer comme fait » : une operation chronometree garde son temps
        reel, une operation jamais demarree prend sa duree prevue. Puis
        l'ordre est cloture avec le numero de serie qu'il porte deja.
        """
        self.ensure_one()
        blocage = self._fma_declarable()
        if blocage:
            return blocage
        if self.product_tracking == "serial" and not self.lot_producing_ids:
            return fma_message("danger", _(
                "%(of)s n'a pas de numéro de série : relancez « Compléter "
                "les OF » sur le lot.", of=self.name))
        try:
            with self.env.cr.savepoint():
                self.workorder_ids.filtered(
                    lambda w: w.state not in ("done", "cancel")
                ).action_mark_as_done()
                self.qty_producing = self.product_qty
                self._set_qty_producing()
                retour = self.button_mark_done()
                if self.state != "done":
                    # Odoo n'a pas refuse : il demande une confirmation dans
                    # un assistant (ecart de consommation, reliquat). Au
                    # poste de scan personne ne la donnera : on annule et on
                    # renvoie vers l'ordre.
                    nom = (retour.get("name") if isinstance(retour, dict)
                           else "") or _("confirmation")
                    raise UserError(_(
                        "Odoo demande une validation manuelle (%(nom)s). "
                        "Ouvrez l'ordre pour la donner.", nom=nom))
        except UserError as erreur:
            return self._fma_refus(erreur, _("déclaration de fin"))
        serie = self.lot_producing_ids[:1].name or self.name
        return fma_message("success", _(
            "Menuiserie %(serie)s déclarée terminée (%(of)s).",
            serie=serie, of=self.name))
