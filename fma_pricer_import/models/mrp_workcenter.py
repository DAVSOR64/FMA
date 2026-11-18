# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpWorkcenter(models.Model):
    """Rattachement d'un poste de charge a une operation du pricer.

    Le pricer nomme ses temps « Debit », « Usinage », « Montage », « CU
    (banc) », « Vitrage ». L'atelier, lui, a plusieurs postes par operation —
    « Usinage FMA », « Usinage F2M », « Usinage 2 FMA », « Usinage Simple »,
    « Usinage Technique ». Rapprocher les deux par le nom donne cinq
    candidats et un choix arbitraire.

    L'import resout dans cet ordre :

    1. le rattachement declare ici, qui fait foi ;
    2. le **code** du poste, qui vaut la sequence de l'operation — 10 Debit,
       20 CU (banc), 30 Usinage, 40 Montage, 50 Vitrage, 60 Emballage. C'est
       la convention deja en place dans l'atelier, et elle ecarte d'elle-meme
       les postes secondaires, qui n'ont pas de code ;
    3. a defaut, le debut du nom, en preferant le site du fichier.

    Les champs ci-dessous ne servent donc qu'aux cas que le code ne couvre
    pas.
    """

    _inherit = "mrp.workcenter"

    pricer_operation = fields.Char(
        string="Opération pricer",
        index="btree_not_null",
        help="Nom de l'operation telle que le pricer la designe : Debit, "
        "Usinage, Montage, CU (banc), Vitrage.",
    )

    pricer_site = fields.Char(
        string="Site pricer",
        help="Site qui chiffre, tel que LOGIKAL l'inscrit dans ses parametres "
        "(REPORTVARIABLES / Addresses / OwnAddress01) : FMA ou F2M. Il "
        "departage les postes homonymes des deux ateliers. Laisser vide fait "
        "de ce poste le choix par defaut pour son operation.",
    )
