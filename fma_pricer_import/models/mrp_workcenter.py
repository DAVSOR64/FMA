# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpWorkcenter(models.Model):
    """Rattachement d'un poste de charge a une operation du pricer.

    Le pricer nomme ses temps « Debit », « Usinage », « Montage », « CU
    (banc) », « Vitrage ». L'atelier, lui, a plusieurs postes par operation —
    « Usinage FMA », « Usinage F2M », « Usinage 2 FMA », « Usinage Simple »,
    « Usinage Technique ». Rapprocher les deux par le nom donne cinq
    candidats et un choix arbitraire.

    Ce champ tranche : on inscrit ici le nom de l'operation du pricer sur LE
    poste qui doit la recevoir. L'import s'y fie en priorite, et ne retombe
    sur le rapprochement par nom que pour les operations non renseignees.
    """

    _inherit = "mrp.workcenter"

    pricer_operation = fields.Char(
        string="Opération pricer",
        index="btree_not_null",
        help="Nom de l'operation telle que le pricer la designe : Debit, "
        "Usinage, Montage, CU (banc), Vitrage. Renseigne sur un seul poste "
        "par operation — c'est lui qui portera le temps importe.",
    )
