# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fma_semi_fini = fields.Selection(
        [
            ("debit", "Ensemble débité"),
            ("quincaillerie", "Kit quincaillerie"),
        ],
        string="Semi-fini de lot",
        copy=False,
        index=True,
        help="Nature d'un article intermediaire du lot de fabrication. Le lot "
        "s'y fie, et non a la reference de l'article, pour savoir quel ordre "
        "de fabrication generer : un kit quincaillerie present dans la "
        "nomenclature d'une menuiserie declenche un OF de quincaillerie.",
    )


#: Categories d'article que le connecteur LOGIKAL pose a la creation, par
#: table du pricer. Ce sont les identifiants externes qu'il emploie deja
#: (sqlite_connector : CATEGORIE_NATURE, et la categorie des vitrages) — on ne
#: cree rien, on relit la meme structure.
CATEGORIES_LOGIKAL = {
    "__export__.product_category_14_a5d33274": "quincaillerie",  # Articles
    "__export__.product_category_19_b8423373": "profile",        # Profiles
    "__export__.product_category_23_31345211": "remplissage",    # Glass
}

#: Famille d'approvisionnement (categorie, famille ou sous-famille de
#: l'article) -> ce qu'est l'article pour le magasin. Un complementaire est un
#: profile.
CLASSE_PAR_FAMILLE = {
    "profil": "profile",
    "complementaire": "profile",
    "vitrage": "remplissage",
    "panneaux": "remplissage",
}

CLASSE_PAR_NATURE = {
    "article": "quincaillerie",
    "profile": "profile",
    "glass": "remplissage",
}


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _fma_classe_matiere(self):
        """Ce qu'est l'article pour le magasin : ``"quincaillerie"``,
        ``"profile"`` ou ``"remplissage"`` (vitrage, panneau).

        C'est le CLASSEMENT EXISTANT de l'article qui decide — sa categorie,
        sa famille, sa sous-famille. Rien n'est ajoute pour cela. Dans
        l'ordre :

        1. la famille d'approvisionnement, deja portee par la sous-famille,
           la famille ou la categorie (en remontant les categories parentes) :
           Profile et Complementaire -> profile, Vitrage et Panneaux ->
           remplissage ;
        2. a defaut, la categorie elle-meme, ou l'une de ses parentes, quand
           c'est une de celles que le connecteur LOGIKAL pose : Articles ->
           quincaillerie, Profiles -> profile, Glass -> remplissage ;
        3. a defaut, tout article RANGE — une famille, ou une categorie autre
           que la racine — est de la quincaillerie : c'est ce qui reste quand
           on a ote les profiles et les remplissages ;
        4. l'article que rien ne range (categorie racine, pas de famille)
           retombe sur la table LOGIKAL d'ou il vient (fma_nature_logikal).
           C'etait la seule regle jusqu'ici ; elle ne se lit sur aucun ecran
           et ne se corrige pas, d'ou son rang de dernier recours.

        ``False`` quand rien ne permet de trancher.

        Pour corriger un classement, on change donc la CATEGORIE de l'article
        (ou son triplet famille), jamais un champ dedie.
        """
        self.ensure_one()
        modele = self.product_tmpl_id
        famille = modele._fma_famille_appro()
        if famille:
            return CLASSE_PAR_FAMILLE.get(famille, "quincaillerie")

        logikal = {}
        for xmlid, classe in CATEGORIES_LOGIKAL.items():
            categorie = self.env.ref(xmlid, raise_if_not_found=False)
            if categorie and categorie._name == "product.category":
                logikal[categorie.id] = classe
        categorie = modele.categ_id
        while categorie:
            if categorie.id in logikal:
                return logikal[categorie.id]
            categorie = categorie.parent_id

        rangee = bool(
            ("family_id" in modele._fields and modele.family_id)
            or modele.categ_id.parent_id
        )
        if rangee:
            return "quincaillerie"

        nature = (
            self.fma_nature_logikal
            if "fma_nature_logikal" in self._fields else False
        )
        return CLASSE_PAR_NATURE.get(nature, False)
