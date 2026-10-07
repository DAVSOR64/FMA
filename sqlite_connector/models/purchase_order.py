# -*- coding: utf-8 -*-
"""Le vitrage de chantier ne voyage pas avec celui de l'atelier.

LOGIKAL distingue deux destinations (Glass.Info2) : le vitrage monte sur
CHARIOT reste a l'atelier, celui pose sur PALETTE part chez le client en
transitant par FMA. Les deux ne se dechargent pas au meme endroit et ne se
manutentionnent pas pareil : ils ne peuvent pas figurer sur le meme bon de
commande, sinon personne au quai ne sait ce qui est a garder.

Odoo regroupe ses achats d'approvisionnement par fournisseur, societe,
devise et type d'operation. La destination n'en fait pas partie, et ne peut
pas en faire partie : c'est une notion metier FMA. On scinde donc APRES
coup, en deplacant les lignes de palette sur un bon a elles.

Pourquoi deplacer les lignes plutot que creer les bons en amont : la ligne
d'achat porte ses liens d'approvisionnement — le mouvement qu'elle alimente,
l'ordre qui l'attend. Les recreer les casserait. Les deplacer les conserve,
exactement comme le fait deja le regroupement des achats d'un lot.
"""
import logging

from odoo import _, api, fields, models

from ..ref_logikal import DESTINATION_PALETTE, DESTINATIONS_VITRAGE

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    fma_destination_vitrage = fields.Selection(
        DESTINATIONS_VITRAGE,
        string="Destination du vitrage",
        related="product_id.fma_destination_vitrage",
        store=True,
        index="btree_not_null",
    )


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    fma_vitrage_palette = fields.Boolean(
        string="Vitrage sur palette",
        compute="_compute_fma_vitrage_palette",
        store=True,
        help="Bon qui ne porte que du vitrage destine au chantier. Il se "
        "receptionne et se reexpedie, il ne rentre pas en stock atelier.",
    )

    @api.depends("order_line.fma_destination_vitrage")
    def _compute_fma_vitrage_palette(self):
        for achat in self:
            destinations = set(
                achat.order_line.mapped("fma_destination_vitrage")) - {False}
            achat.fma_vitrage_palette = destinations == {DESTINATION_PALETTE}

    # ------------------------------------------------------------------
    def _fma_scinder_vitrage(self):
        """Sort les lignes de palette des bons qui melangent les deux.

        Ne touche qu'aux bons en brouillon : une fois envoye au fournisseur,
        un bon ne se recompose pas dans le dos de l'acheteur.

        Encadre : au pire les deux destinations restent sur un bon, ce qui
        est genant et visible. Une exception qui empecherait de confirmer une
        commande client le serait bien davantage.
        """
        nouveaux = self.browse()
        for achat in self.filtered(lambda a: a.state in ("draft", "sent")):
            try:
                nouveaux |= achat._fma_sortir_les_palettes()
            except Exception as erreur:  # noqa: BLE001
                _logger.exception(
                    "Scission du vitrage sur le bon %s", achat.name)
                achat.message_post(body=_(
                    "Séparation du vitrage de chantier impossible : "
                    "%(erreur)s<br/>Ce bon porte peut-être les deux "
                    "destinations — à vérifier avant de l'envoyer.",
                    erreur=erreur,
                ))
        return nouveaux

    def _fma_vals_bon_jumeau(self):
        """L'en-tete du bon d'accueil, recopie champ par champ.

        Et non un copy() : copier un bon de commande duplique ses lignes, et
        on veut precisement un bon vide ou deplacer les lignes existantes.
        Les champs sont donc nommes — ceux qui engagent le fournisseur et
        ceux qui pilotent la reception.
        """
        self.ensure_one()
        vals = {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "date_order": self.date_order,
            "origin": self.origin,
            "partner_ref": self.partner_ref,
            "user_id": self.user_id.id,
            "picking_type_id": self.picking_type_id.id,
            "payment_term_id": self.payment_term_id.id,
            "fiscal_position_id": self.fiscal_position_id.id,
            "dest_address_id": self.dest_address_id.id,
        }
        # Les champs Studio du referentiel FMA — le projet notamment, sans
        # lequel l'achat sortirait des ecrans de suivi de l'affaire.
        for nom in ("x_studio_projet_du_so", "fma_sale_order_id"):
            if nom in self._fields and self[nom]:
                vals[nom] = self[nom].id if hasattr(self[nom], "id") else self[nom]
        return vals

    def _fma_sortir_les_palettes(self):
        self.ensure_one()
        palettes = self.order_line.filtered(
            lambda l: l.fma_destination_vitrage == DESTINATION_PALETTE)
        autres = self.order_line - palettes
        # Rien a faire quand le bon est homogene : tout palette, ou pas de
        # palette du tout.
        if not palettes or not autres:
            return self.browse()

        cible = self.create(self._fma_vals_bon_jumeau())
        palettes.write({"order_id": cible.id})
        self.invalidate_recordset(["order_line"])
        cible.message_post(body=_(
            "Vitrage destiné au chantier, séparé de %(origine)s : il se "
            "réceptionne et se réexpédie, il n'entre pas en stock atelier.",
            origine=self.name,
        ))
        self.message_post(body=_(
            "%(nb)s ligne(s) de vitrage sur palette déplacées vers "
            "%(cible)s.", nb=len(palettes), cible=cible.name,
        ))
        return cible


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        """Les achats naissent ici : on les scinde dans la foulee.

        Le vitrage est a la commande (MTO) : c'est la confirmation du devis
        qui declenche son achat. C'est donc le seul moment ou l'on est sur de
        passer apres la creation des bons et avant que l'acheteur les ouvre.
        """
        resultat = super().action_confirm()
        # LES BONS DE CETTE COMMANDE, pas tous les brouillons de la base. Le
        # lien passe par l'origine, que l'approvisionnement renseigne avec le
        # nom du devis — c'est le seul lien direct, la ligne d'achat ne porte
        # pas la commande de vente.
        for commande in self.filtered("name"):
            achats = self.env["purchase.order"].search([
                ("state", "in", ("draft", "sent")),
                ("origin", "ilike", commande.name),
            ])
            achats = achats.filtered(
                lambda a: any(a.order_line.mapped("fma_destination_vitrage")))
            if achats:
                achats._fma_scinder_vitrage()
        return resultat
