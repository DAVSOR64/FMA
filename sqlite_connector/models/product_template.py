# -*- coding: utf-8 -*-
from odoo import fields, models

from .. import noms_articles
from ..ref_logikal import DESTINATIONS_VITRAGE


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fma_article_libre = fields.Boolean(
        string="Article libre LOGIKAL",
        copy=False,
        index="btree_not_null",
        help="Article ne venant d'aucun catalogue fournisseur : le chiffreur "
        "l'a saisi a la main dans LOGIKAL (ligne « manuelle »). Il n'a donc "
        "pas de reference article, et le connecteur lui en fabrique une, du "
        "type « ABC A26-00-00002_LB1 ».",
    )

    fma_destination_vitrage = fields.Selection(
        DESTINATIONS_VITRAGE,
        string="Destination du vitrage",
        copy=False,
        index="btree_not_null",
        help="Lue dans Glass.Info2 du fichier LOGIKAL. « Chariot » reste a "
        "l'atelier, « Palette » part chez le client en transitant par FMA. "
        "Elle decide de la commande d'achat : les deux destinations ne "
        "peuvent pas voyager sur le meme bon, elles ne se dechargent pas au "
        "meme endroit.",
    )

    fma_conditionnement = fields.Float(
        string="Conditionnement d'achat",
        digits="Product Unit of Measure",
        copy=False,
        help="Nombre de pieces par unite de vente du fournisseur, lu dans "
        "PUSize du fichier LOGIKAL. Un article dont le conditionnement vaut "
        "100 ne s'achete que par centaines : l'import arrondit deja les "
        "quantites a l'achat, mais sans ce champ la regle n'existe nulle part "
        "dans Odoo et un reappro declenche autrement l'ignore.",
    )

    fma_nature_logikal = fields.Selection(
        [
            ("profile", "Profilé"),
            ("article", "Article / quincaillerie"),
            ("glass", "Vitrage"),
        ],
        string="Nature LOGIKAL",
        copy=False,
        index="btree_not_null",
        help="De quelle table du fichier pricer l'article provient : Profiles, "
        "Articles ou Glass. C'est la seule distinction qui fasse foi — un "
        "profile et une piece de quincaillerie peuvent porter le meme prefixe "
        "fournisseur, et la categorie d'article se modifie a la main.",
    )

    fma_nom_importe = fields.Char(
        string="Désignation importée",
        copy=False,
        readonly=True,
        help="Dernier nom que l'import LOGIKAL / pricer a ecrit sur l'article. "
        "Tant que le nom de l'article lui est egal, ou qu'il est vide, l'import "
        "le tient a jour d'apres la designation de la ligne de commande. Des "
        "qu'un utilisateur renomme l'article, les deux different et l'import "
        "n'y touche plus.",
    )

    def _fma_poser_designation(self, designation, anciens=()):
        """Nomme l'article d'apres la designation, sans ecraser un renommage.

        Renvoie 'ecrit', 'inchange', 'manuel' ou 'vide' : voir noms_articles.
        """
        self.ensure_one()
        return noms_articles.poser_designation(self, designation, anciens)
