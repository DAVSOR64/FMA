# -*- coding: utf-8 -*-
"""Cycles de fabrication : le calendrier remplace la recherche de creneau.

Un lot n'est plus planifie en cherchant des heures libres sur les postes, mais
en appliquant un CYCLE : une suite de decalages en jours OUVRES, comptes a
rebours depuis la fin de fabrication. Le cycle 1, par exemple, place
l'emballage la veille de la fin de fab, le vitrage l'avant-veille, et le debit
six jours avant.

Le cycle a appliquer se lit dans une matrice a deux entrees — la complexite la
plus haute du lot et son nombre de menuiseries : voir ``fma.cycle.regle``.

LES HEURES NE DISPARAISSENT PAS POUR AUTANT. Elles restent la CHARGE que le
macro-planning compare a la capacite des postes, jour par jour. Elles ne
servent simplement plus a CHOISIR les dates. C'est tout le changement : un
poste peut desormais etre en surcharge un mardi, et cela se voit au lieu de se
resoudre en decalant silencieusement le travail de trois semaines.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FmaCycle(models.Model):
    _name = "fma.cycle"
    _description = "Cycle de fabrication"
    _order = "sequence, name"

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        help="Code court du cycle, unique. Il sert aux journaux et aux "
             "messages d'erreur, ou le libelle serait trop long.",
    )
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    note = fields.Text(string="Commentaire")

    operation_ids = fields.One2many(
        "fma.cycle.operation",
        "cycle_id",
        string="Opérations",
    )
    operation_count = fields.Integer(
        string="Nb opérations",
        compute="_compute_operation_count",
    )
    duree_jours = fields.Integer(
        string="Durée (jours ouvrés)",
        compute="_compute_duree_jours",
        store=True,
        help="Nombre de jours ouvrés entre la première opération du cycle et "
             "la fin de fabrication. C'est l'avance qu'il faut prendre pour "
             "tenir la date.",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Le code d'un cycle doit être unique.",
    )

    @api.depends("operation_ids")
    def _compute_operation_count(self):
        for cycle in self:
            cycle.operation_count = len(cycle.operation_ids)

    @api.depends("operation_ids.jours_avant_fin")
    def _compute_duree_jours(self):
        for cycle in self:
            jours = cycle.operation_ids.mapped("jours_avant_fin")
            cycle.duree_jours = max(jours) if jours else 0

    def _decalages_par_poste(self):
        """Retourne {id de poste: jours ouvrés avant la fin de fab}.

        Point d'entree de la planification : elle n'a pas a connaitre la
        structure du cycle, seulement ce decalage par poste.
        """
        self.ensure_one()
        return {
            operation.workcenter_id.id: operation.jours_avant_fin
            for operation in self.operation_ids
            if operation.workcenter_id
        }


class FmaCycleOperation(models.Model):
    """Une operation du cycle, et son decalage avant la fin de fabrication."""

    _name = "fma.cycle.operation"
    _description = "Opération d'un cycle de fabrication"
    # Du plus tot au plus tard : le debit ouvre la liste, l'emballage la ferme.
    _order = "jours_avant_fin desc, id"

    cycle_id = fields.Many2one(
        "fma.cycle",
        string="Cycle",
        required=True,
        ondelete="cascade",
        index=True,
    )
    workcenter_id = fields.Many2one(
        "mrp.workcenter",
        string="Poste de charge",
        required=True,
        ondelete="restrict",
        help="Le poste dont les ordres de travail seront datés par ce "
             "décalage. Une opération que le cycle ne nomme pas n'est pas "
             "planifiée par lui.",
    )
    jours_avant_fin = fields.Integer(
        string="Jours ouvrés avant la fin de fab",
        required=True,
        default=0,
        help="0 = le jour de la fin de fabrication. 6 = six jours OUVRÉS "
             "avant, week-ends, fériés et fermetures d'entreprise exclus.",
    )
    libelle = fields.Char(
        string="Libellé",
        compute="_compute_libelle",
        store=True,
    )

    _cycle_poste_unique = models.Constraint(
        "UNIQUE(cycle_id, workcenter_id)",
        "Ce poste de charge figure déjà dans ce cycle.",
    )

    @api.depends("workcenter_id", "jours_avant_fin")
    def _compute_libelle(self):
        for operation in self:
            poste = operation.workcenter_id.display_name or "-"
            if operation.jours_avant_fin:
                operation.libelle = "%s — J-%s" % (poste, operation.jours_avant_fin)
            else:
                operation.libelle = "%s — J" % poste

    @api.constrains("jours_avant_fin")
    def _check_jours_avant_fin(self):
        for operation in self:
            if operation.jours_avant_fin < 0:
                raise ValidationError(_(
                    "Le décalage de « %(poste)s » est négatif. Un cycle se "
                    "compte à rebours depuis la fin de fabrication : une "
                    "opération ne peut pas la suivre.",
                    poste=operation.workcenter_id.display_name or "?",
                ))
