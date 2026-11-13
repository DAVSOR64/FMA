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

from ..ref_logikal import (
    DESTINATION_CHARIOT,
    DESTINATION_PALETTE,
    DESTINATIONS_VITRAGE,
)

_logger = logging.getLogger(__name__)

#: Le commentaire de livraison du bon d'achat. Il est IMPRIME sur le bon
#: envoye au fournisseur et repris dans l'export XML sous <Remarks> : ce
#: qu'on y ecrit part chez le verrier.
CHAMP_COMMENTAIRE = "x_studio_commentaire_livraison_vitrage_"

#: La mention portee sur le bon, en toutes lettres et en majuscules — elle
#: se lit sur un document imprime, pas dans une base.
MENTION_PAR_DESTINATION = {
    DESTINATION_CHARIOT: "CHARIOT",
    DESTINATION_PALETTE: "PALETTE",
}


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

    def _fma_noter_destination(self):
        """Porte CHARIOT ou PALETTE sur le commentaire de livraison du bon.

        Le verrier a besoin de le lire sur le document, pas de le deduire :
        c'est lui qui charge, et un chariot n'est pas une palette.

        ON N'ECRASE JAMAIS UN COMMENTAIRE SAISI. Le champ est libre et sert
        deja a l'acheteur — une adresse de chantier, une consigne d'horaire.
        On n'ecrit que s'il est vide, ou s'il porte deja l'une de nos deux
        mentions, de sorte qu'une correction de destination se propage sans
        jamais effacer le travail de quelqu'un.

        Le champ vient du module « custom », qui n'est pas une dependance
        d'ici : on verifie sa presence plutot que de la supposer.
        """
        mentions = set(MENTION_PAR_DESTINATION.values())
        for achat in self:
            if CHAMP_COMMENTAIRE not in achat._fields:
                return
            destinations = set(
                achat.order_line.mapped("fma_destination_vitrage")) - {False}
            if len(destinations) != 1:
                # Pas de vitrage, ou les deux destinations encore melangees :
                # rien a affirmer au fournisseur.
                continue
            mention = MENTION_PAR_DESTINATION[destinations.pop()]
            actuel = (achat[CHAMP_COMMENTAIRE] or "").strip()
            if actuel and actuel.upper() not in mentions:
                continue
            if actuel != mention:
                achat[CHAMP_COMMENTAIRE] = mention

    # ------------------------------------------------------------------
    def _fma_scinder_vitrage(self):
        """Rassemble le vitrage de chantier sur UN bon par flux.

        Le traitement porte sur le LOT DE BONS recu, et non sur chacun pris a
        part. C'est la difference avec la premiere version : elle sortait les
        palettes bon par bon, donc creait autant de bons de palette qu'il y
        avait de bons d'origine. Une affaire qui approvisionnait en deux fois
        — la confirmation du devis, puis la generation d'un lot — recevait
        deux livraisons de chantier la ou elle n'en attend qu'une.

        Le chantier veut un bon, un camion, un dechargement. Les lignes de
        palette d'une meme affaire se rejoignent donc toutes sur le meme bon,
        tant qu'elles partagent le fournisseur, la societe, la devise et le
        type d'operation : on ne melange ni deux receptions ni deux monnaies.

        Ne touche qu'aux bons en brouillon : une fois envoye au fournisseur,
        un bon ne se recompose pas dans le dos de l'acheteur.

        Encadre : au pire les deux destinations restent sur un bon, ce qui
        est genant et visible. Une exception qui empecherait de confirmer une
        commande client le serait bien davantage.
        """
        bons = self.filtered(lambda a: a.state in ("draft", "sent"))
        palettes = bons.order_line.filtered(
            lambda l: l.fma_destination_vitrage == DESTINATION_PALETTE)
        if not palettes:
            return self.browse()

        par_flux = {}
        for ligne in palettes:
            achat = ligne.order_id
            cle = (
                achat.partner_id.id,
                achat.company_id.id,
                achat.currency_id.id,
                achat.picking_type_id.id,
            )
            par_flux.setdefault(cle, self.env["purchase.order.line"])
            par_flux[cle] |= ligne

        nouveaux = self.browse()
        for du_flux in par_flux.values():
            try:
                nouveaux |= self._fma_grouper_les_palettes(du_flux)
            except Exception as erreur:  # noqa: BLE001 — trace, pas de blocage
                _logger.exception(
                    "Regroupement du vitrage de chantier (%s lignes)",
                    len(du_flux))
                du_flux.order_id[:1].message_post(body=_(
                    "Regroupement du vitrage de chantier impossible : "
                    "%(erreur)s<br/>Ce bon porte peut-être les deux "
                    "destinations — à vérifier avant de l'envoyer.",
                    erreur=erreur,
                ))
        return nouveaux

    def _fma_vals_bon_vitrage(self):
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
        # Volontairement SANS le commentaire de livraison : le bon d'accueil
        # porte l'autre destination, recopier celui du bon d'origine
        # annoncerait l'inverse de ce qu'il contient. _fma_noter_destination
        # le pose juste apres, a partir de ses lignes.
        # Les champs Studio du referentiel FMA — le projet notamment, sans
        # lequel l'achat sortirait des ecrans de suivi de l'affaire.
        for nom in ("x_studio_projet_du_so", "fma_sale_order_id"):
            if nom in self._fields and self[nom]:
                vals[nom] = self[nom].id if hasattr(self[nom], "id") else self[nom]
        return vals

    def _fma_bon_de_palette(self, lignes):
        """Le bon qui accueille ces lignes : un bon deja tout palette, sinon un neuf.

        On prefere un bon existant qui ne porte QUE de la palette : il a deja
        ses liens d'approvisionnement, son origine et, le cas echeant, son
        numero connu de l'acheteur. En ouvrir un alors qu'il convenait
        laisserait un bon vide a nettoyer.
        """
        candidats = lignes.order_id
        for achat in candidats:
            if not (achat.order_line - lignes):
                return achat
        return self.create(candidats[0]._fma_vals_bon_vitrage())

    def _fma_grouper_les_palettes(self, lignes):
        """Pose ``lignes`` sur un bon unique et vide les bons qu'elles quittent.

        Deplacer les lignes plutot que les recreer : la ligne d'achat porte
        ses liens d'approvisionnement — le mouvement qu'elle alimente, l'ordre
        qui l'attend. Les recreer les casserait.
        """
        cible = self._fma_bon_de_palette(lignes)
        a_deplacer = lignes - cible.order_line
        if not a_deplacer:
            return self.browse() if cible in self else cible

        anciens = a_deplacer.order_id
        origines = [cible.origin or ""] + [a.origin or "" for a in anciens]
        a_deplacer.write({"order_id": cible.id})
        anciens.invalidate_recordset(["order_line"])

        # ANNULER AVANT DE SUPPRIMER : Odoo refuse de supprimer un bon
        # d'achat qui n'est pas annule.
        vides = anciens.filtered(
            lambda a: not a.order_line and a.state in ("draft", "sent"))
        if vides:
            vides.button_cancel()
            vides.unlink()

        # L'origine des bons absorbes reste sur le bon d'accueil : sans elle
        # on perdrait le lien vers la commande et vers l'OF demandeur.
        retenues = []
        for origine in origines:
            for jeton in (origine or "").split(", "):
                jeton = jeton.strip()
                if jeton and jeton not in retenues:
                    retenues.append(jeton)
        if retenues:
            cible.origin = ", ".join(retenues)

        cible.message_post(body=_(
            "%(nb)s ligne(s) de vitrage sur palette rassemblées ici : il se "
            "réceptionne et se réexpédie au chantier, il n'entre pas en stock "
            "atelier. Une seule livraison pour l'affaire.",
            nb=len(a_deplacer),
        ))
        return cible


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def fma_regrouper_vitrage_chantier(self):
        """Rassemble le vitrage sur palette de l'affaire sur un bon unique.

        PUBLIQUE A DESSEIN : le lot de fabrication l'appelle apres avoir
        regroupe SES achats, par ``hasattr`` — fma_lot_fabrication ne depend
        pas de ce module, et une methode privee appelee de l'exterieur est un
        contrat qui ne se voit pas.

        Le balayage part de l'AFFAIRE et non des bons qu'on vient de creer :
        c'est ce qui permet a un lot genere trois semaines apres la
        confirmation de rejoindre le bon de palette deja ouvert, au lieu d'en
        ouvrir un second.
        """
        for commande in self.filtered("name"):
            # LES BONS DE CETTE COMMANDE, pas tous les brouillons de la base.
            # Le lien passe par l'origine, que l'approvisionnement renseigne
            # avec le nom du devis — c'est le seul lien direct, la ligne
            # d'achat ne porte pas la commande de vente.
            achats = self.env["purchase.order"].search([
                ("state", "in", ("draft", "sent")),
                ("origin", "ilike", commande.name),
            ])
            achats = achats.filtered(
                lambda a: any(a.order_line.mapped("fma_destination_vitrage")))
            if not achats:
                continue
            nouveaux = achats._fma_scinder_vitrage()
            # Apres le regroupement seulement : avant, un bon melangeant les
            # deux destinations n'aurait rien eu a dire au fournisseur.
            restants = (achats | nouveaux).exists()
            restants._fma_noter_destination()

    def action_confirm(self):
        """Les achats naissent ici : on les regroupe dans la foulee.

        Le vitrage est a la commande (MTO) : c'est la confirmation du devis
        qui declenche son achat. C'est donc le seul moment ou l'on est sur de
        passer apres la creation des bons et avant que l'acheteur les ouvre.
        """
        resultat = super().action_confirm()
        self.fma_regrouper_vitrage_chantier()
        return resultat
