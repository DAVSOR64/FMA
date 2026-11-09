# -*- coding: utf-8 -*-
"""Cycles de fabrication : le calendrier remplace la recherche de creneau.

Un lot n'est plus planifie en cherchant des heures libres sur les postes, mais
en appliquant un CYCLE : une suite de decalages en jours OUVRES, comptes a
rebours depuis la fin de fabrication. Le cycle 1, par exemple, place le
vitrage la veille de la fin de fab, le montage trois jours avant, et le debit
six jours avant.

UNE OPERATION PEUT TENIR SUR PLUSIEURS JOURS. Le montage du cycle 1 commence a
J-3 et finit a J-2 : il occupe deux jours ouvres. Le cycle porte donc deux
nombres par poste, le jour ou l'operation COMMENCE et le nombre de jours
qu'elle dure, et non un decalage unique. C'est le debut qui sert a enchainer
les lots ; la duree sert a occuper le poste sur le macro-planning.

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
        help="Nombre de jours ouvrés entre le DÉBUT de la première opération "
             "du cycle et la fin de fabrication. C'est l'avance qu'il faut "
             "prendre pour tenir la date.",
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
            # Le DEBUT le plus recule, pas la fin : c'est lui qui dit quand
            # le lot doit entrer en fabrication.
            jours = cycle.operation_ids.mapped("jours_avant_fin")
            cycle.duree_jours = max(jours) if jours else 0

    def _decalages_par_poste(self):
        """Retourne {id de poste: jours ouvrés avant la fin de fab}.

        Le DEBUT de chaque operation, et lui seul. Les appelants qui datent
        un enchainement n'ont pas besoin d'autre chose ; ceux qui occupent un
        poste sur plusieurs jours passent par ``_plages_par_poste``.
        """
        self.ensure_one()
        return {
            operation.workcenter_id.id: operation.jours_avant_fin
            for operation in self.operation_ids
            if operation.workcenter_id
        }

    def _plages_par_poste(self):
        """Retourne {id de poste: (jours avant fin au début, à la fin)}.

        Une operation d'un jour rend deux fois le meme nombre. Une operation
        de deux jours qui commence a J-3 rend ``(3, 2)``.
        """
        self.ensure_one()
        return {
            operation.workcenter_id.id: (
                operation.jours_avant_fin,
                operation.jours_avant_fin_terme,
            )
            for operation in self.operation_ids
            if operation.workcenter_id
        }


class FmaCycleOperation(models.Model):
    """Une operation du cycle : quand elle commence, et combien elle dure."""

    _name = "fma.cycle.operation"
    _description = "Opération d'un cycle de fabrication"
    # Du plus tot au plus tard : le debit ouvre la liste, le vitrage la ferme.
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
        string="Début — jours ouvrés avant la fin de fab",
        required=True,
        default=0,
        help="Le jour où l'opération COMMENCE. 0 = le jour de la fin de "
             "fabrication. 6 = six jours OUVRÉS avant, week-ends, fériés et "
             "fermetures d'entreprise exclus.",
    )
    duree_jours = fields.Integer(
        string="Durée (jours ouvrés)",
        required=True,
        default=1,
        help="Nombre de jours OUVRÉS que l'opération occupe, le jour de début "
             "compris. 1 pour une opération d'une journée ; 2 pour un montage "
             "qui commence à J-3 et finit à J-2.",
    )
    jours_avant_fin_terme = fields.Integer(
        string="Fin — jours ouvrés avant la fin de fab",
        compute="_compute_jours_avant_fin_terme",
        store=True,
        help="Déduit du début et de la durée : une opération de deux jours "
             "qui commence à J-3 finit à J-2.",
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

    @api.depends("jours_avant_fin", "duree_jours")
    def _compute_jours_avant_fin_terme(self):
        for operation in self:
            duree = max(operation.duree_jours or 1, 1)
            operation.jours_avant_fin_terme = max(
                operation.jours_avant_fin - (duree - 1), 0
            )

    @api.depends("workcenter_id", "jours_avant_fin", "jours_avant_fin_terme",
                 "duree_jours")
    def _compute_libelle(self):
        def jour(decalage):
            return "J-%s" % decalage if decalage else "J"

        for operation in self:
            poste = operation.workcenter_id.display_name or "-"
            debut = jour(operation.jours_avant_fin)
            if (operation.duree_jours or 1) <= 1:
                operation.libelle = "%s — %s" % (poste, debut)
            else:
                operation.libelle = "%s — %s → %s (%s j)" % (
                    poste,
                    debut,
                    jour(operation.jours_avant_fin_terme),
                    operation.duree_jours,
                )

    @api.constrains("jours_avant_fin", "duree_jours")
    def _check_decalages(self):
        for operation in self:
            poste = operation.workcenter_id.display_name or "?"
            if operation.jours_avant_fin < 0:
                raise ValidationError(_(
                    "Le décalage de « %(poste)s » est négatif. Un cycle se "
                    "compte à rebours depuis la fin de fabrication : une "
                    "opération ne peut pas la suivre.",
                    poste=poste,
                ))
            if operation.duree_jours < 1:
                raise ValidationError(_(
                    "La durée de « %(poste)s » doit valoir au moins 1 jour : "
                    "une opération qui ne dure aucun jour ouvré n'occupe "
                    "aucune place dans le cycle.",
                    poste=poste,
                ))
            # Une operation qui deborderait la fin de fabrication n'est pas
            # une erreur de saisie anodine : elle date un ordre apres la date
            # que le cycle est cense tenir.
            if operation.duree_jours > operation.jours_avant_fin + 1:
                raise ValidationError(_(
                    "« %(poste)s » commence à J-%(debut)s et dure "
                    "%(duree)s jours ouvrés : elle finirait APRÈS la fin de "
                    "fabrication. La durée ne peut pas dépasser %(max)s jour(s) "
                    "à cette date de début.",
                    poste=poste,
                    debut=operation.jours_avant_fin,
                    duree=operation.duree_jours,
                    max=operation.jours_avant_fin + 1,
                ))
