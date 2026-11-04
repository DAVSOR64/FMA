# -*- coding: utf-8 -*-
"""La matrice : complexite x nombre de menuiseries -> cycle.

Deux entrees, comme le tableau que la production tient aujourd'hui a la main.
En ligne la complexite du lot — la PLUS HAUTE de ses menuiseries, A < B < C <
D < E —, en colonne une tranche de quantite. A leur croisement, le cycle.

La tranche est portee par deux bornes plutot que par une liste figee : les
tranches changeront, et elles doivent changer sans developpement. C'est aussi
ce qui permet d'en ajouter une au-dela du plafond actuel le jour ou les lots
grossiront.

UNE COMBINAISON ABSENTE N'EST PAS UNE TOLERANCE : la planification s'arrete.
Un lot qu'on ne sait pas dater vaut mieux qu'un lot date au hasard, parce que
c'est toute l'affaire qui se cale derriere lui.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class FmaCycleRegle(models.Model):
    _name = "fma.cycle.regle"
    _description = "Matrice complexité / quantité -> cycle"
    _order = "niveau_sequence, qte_min"
    _rec_name = "libelle"

    niveau_id = fields.Many2one(
        "fma.complexite.niveau",
        string="Complexité",
        required=True,
        ondelete="restrict",
        index=True,
        help="La complexité la plus haute portée par les menuiseries du lot.",
    )
    niveau_sequence = fields.Integer(
        related="niveau_id.sequence",
        store=True,
        index=True,
    )
    qte_min = fields.Integer(
        string="De (menuiseries)",
        required=True,
        default=1,
    )
    qte_max = fields.Integer(
        string="À (menuiseries)",
        required=True,
        default=1,
    )
    cycle_id = fields.Many2one(
        "fma.cycle",
        string="Cycle",
        required=True,
        ondelete="restrict",
    )
    active = fields.Boolean(string="Actif", default=True)
    libelle = fields.Char(
        string="Libellé",
        compute="_compute_libelle",
        store=True,
    )

    @api.depends("niveau_id.code", "qte_min", "qte_max", "cycle_id.name")
    def _compute_libelle(self):
        for regle in self:
            regle.libelle = "%s / %s-%s -> %s" % (
                regle.niveau_id.code or "-",
                regle.qte_min,
                regle.qte_max,
                regle.cycle_id.name or "-",
            )

    @api.constrains("qte_min", "qte_max")
    def _check_bornes(self):
        for regle in self:
            if regle.qte_min < 1:
                raise ValidationError(_(
                    "La borne basse d'une tranche vaut au moins 1 : un lot "
                    "sans menuiserie ne se fabrique pas."
                ))
            if regle.qte_max < regle.qte_min:
                raise ValidationError(_(
                    "La tranche %(min)s-%(max)s est a l'envers.",
                    min=regle.qte_min, max=regle.qte_max,
                ))

    @api.constrains("niveau_id", "qte_min", "qte_max", "active")
    def _check_chevauchement(self):
        """Deux tranches d'une meme complexite ne peuvent pas se recouvrir.

        Sans ce controle, un lot de 5 menuiseries en B pourrait relever de
        deux cycles a la fois, et c'est l'ordre de lecture en base qui
        trancherait — donc personne.
        """
        for regle in self:
            if not regle.active:
                continue
            voisines = self.search([
                ("id", "!=", regle.id),
                ("niveau_id", "=", regle.niveau_id.id),
                ("qte_min", "<=", regle.qte_max),
                ("qte_max", ">=", regle.qte_min),
            ])
            if voisines:
                raise ValidationError(_(
                    "La tranche %(min)s-%(max)s de la complexité %(niveau)s "
                    "recouvre une tranche déjà définie : %(autres)s.",
                    min=regle.qte_min,
                    max=regle.qte_max,
                    niveau=regle.niveau_id.code or "?",
                    autres=", ".join(voisines.mapped("libelle")),
                ))

    @api.model
    def _cycle_pour(self, niveau, nb_menuiseries):
        """Le cycle d'un lot, ou une erreur qui dit quoi corriger.

        ``niveau`` est un enregistrement ``fma.complexite.niveau`` ou un code
        (« C »). ``nb_menuiseries`` est le NOMBRE DE MENUISERIES du lot, somme
        des quantites de ses reperes — et non son nombre de reperes.
        """
        if isinstance(niveau, str):
            code = (niveau or "").strip().upper()
            niveau = self.env["fma.complexite.niveau"].search(
                [("code", "=", code)], limit=1
            )
            if not niveau:
                raise UserError(_(
                    "La complexité « %(code)s » ne figure pas dans le "
                    "référentiel des niveaux. Créez-la, ou corrigez le "
                    "chiffrage LOGIKAL.",
                    code=code,
                ))

        regle = self.search([
            ("niveau_id", "=", niveau.id),
            ("qte_min", "<=", nb_menuiseries),
            ("qte_max", ">=", nb_menuiseries),
        ], limit=1)
        if not regle:
            raise UserError(_(
                "Aucun cycle n'est défini pour la complexité %(niveau)s et "
                "%(nb)s menuiserie(s). Complétez la matrice des cycles "
                "(Fabrication > Configuration > Cycles de fabrication) avant "
                "de planifier ce lot.",
                niveau=niveau.code or niveau.display_name,
                nb=nb_menuiseries,
            ))
        return regle.cycle_id
