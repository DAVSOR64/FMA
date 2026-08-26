# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    # ================= Un seul bon de livraison par commande =================
    #
    # En 19.0, les mouvements ne se retrouvent dans un meme transfert que si
    # (references, emplacement source, emplacement destination, type
    # d'operation) sont identiques -- cf. `_key_assign_picking` du natif.
    #
    # Un produit fabrique en MTO est produit dans LRE/STOCK/PF et expedie
    # depuis PF ; les autres lignes de la meme commande partent de LRE/STOCK.
    # Sources differentes, donc deux bons de livraison pour un seul client et
    # une seule expedition -- alors que le client doit recevoir un BL unique
    # reprenant toutes les lignes.
    #
    # On retire donc l'emplacement source de la cle de regroupement, mais
    # uniquement pour les expeditions client d'une meme commande : chaque
    # mouvement garde sa propre source (la reservation continue de prendre le
    # produit fini dans PF), seul l'en-tete du transfert porte l'emplacement
    # parent commun. Les flux internes, les receptions et la chaine de
    # fabrication ne sont pas touches.

    def _grouper_par_livraison_client(self):
        """Ce mouvement doit-il rejoindre le BL client de sa commande ?

        On exige des references : sans elles le natif ne cherche aucun
        transfert existant et retombe sur le transfert d'origine de la chaine,
        comportement qu'on ne veut pas modifier.
        """
        self.ensure_one()
        return bool(self.reference_ids) and self.picking_type_id.code == "outgoing"

    def _key_assign_picking(self):
        if not self._grouper_par_livraison_client():
            return super()._key_assign_picking()
        return (self.reference_ids, self.location_dest_id, self.picking_type_id)

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        if not self._grouper_par_livraison_client():
            return domain
        # Le transfert a ete cree avec l'emplacement parent commun : chercher
        # sur la source exacte du mouvement ne le retrouverait pas.
        allege = [
            leaf for leaf in domain
            if not (isinstance(leaf, (list, tuple)) and len(leaf) == 3 and leaf[0] == "location_id")
        ]
        if len(allege) == len(domain):
            _logger.warning(
                "Regroupement des livraisons : aucune condition sur location_id dans le "
                "domaine natif, la surcharge est peut-etre devenue inutile."
            )
        return allege

    def _emplacement_source_commun(self):
        """Plus proche ancetre commun des sources des mouvements."""
        sources = self.location_id
        if len(sources) <= 1:
            return sources
        chemins = []
        for source in sources:
            chaine, courant = [], source
            while courant:
                chaine.append(courant.id)
                courant = courant.location_id
            chemins.append(chaine)
        # chemins[0] va de la source vers la racine : le premier emplacement
        # present dans toutes les chaines est le plus proche ancetre commun.
        for emplacement_id in chemins[0]:
            if all(emplacement_id in chaine for chaine in chemins[1:]):
                return self.env["stock.location"].browse(emplacement_id)
        return self.picking_type_id[:1].default_location_src_id or sources[0]

    def _get_new_picking_values(self):
        sources = self.location_id
        if len(sources) <= 1:
            return super()._get_new_picking_values()
        # Le natif fait `self.mapped('location_id').id`, qui leve sur plusieurs
        # emplacements. On lui passe donc les mouvements d'une seule source
        # pour obtenir les autres valeurs -- origine, partenaire, societe et
        # type d'operation sont identiques par construction, ce sont les
        # criteres du regroupement -- puis on pose l'ancetre commun.
        vals = super(
            StockMove, self.filtered(lambda m: m.location_id == sources[0])
        )._get_new_picking_values()
        vals["location_id"] = self._emplacement_source_commun().id
        return vals
