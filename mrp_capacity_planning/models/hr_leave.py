# -*- coding: utf-8 -*-
from odoo import models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    # mrp.capacity.week._compute_absences() ne peut pas dépendre nativement
    # d'un hr.leave (champ calculé basé sur une recherche, pas une relation
    # directe) -- seul un cron quotidien recalculait les semaines, et
    # uniquement celles à venir (week_date >= aujourd'hui). Une semaine déjà
    # passée au moment de la création du congé ne se corrigeait donc jamais,
    # et même les semaines courantes/futures avaient jusqu'à 24h de retard.
    # Retour métier EMIDAV (2026-07-16) : "la capa n'est pas correctement
    # retirée quand on pose un congé" -- confirmé en direct (calcul rejoué
    # manuellement correct, valeur stockée jamais rafraîchie). On déclenche
    # donc le recalcul immédiatement à la création/modification/suppression
    # d'un congé.
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._fma_recompute_capacity_weeks()
        return leaves

    def write(self, vals):
        res = super().write(vals)
        if vals.keys() & {"date_from", "date_to", "state", "employee_id", "holiday_status_id"}:
            self._fma_recompute_capacity_weeks()
        return res

    def unlink(self):
        employee_ids = self.employee_id.ids
        date_froms = [d for d in self.mapped("date_from") if d]
        date_tos = [d for d in self.mapped("date_to") if d]
        res = super().unlink()
        if employee_ids and date_froms and date_tos:
            weeks = self.env["mrp.capacity.week"].search([
                ("employee_id", "in", employee_ids),
                ("week_date", "<=", max(date_tos).date()),
                ("week_end_date", ">=", min(date_froms).date()),
            ])
            weeks._compute_absences()
            weeks._compute_capacity_net()
        return res

    def _fma_recompute_capacity_weeks(self):
        for leave in self:
            if not leave.employee_id or not leave.date_from or not leave.date_to:
                continue
            weeks = self.env["mrp.capacity.week"].search([
                ("employee_id", "=", leave.employee_id.id),
                ("week_date", "<=", leave.date_to.date()),
                ("week_end_date", ">=", leave.date_from.date()),
            ])
            if weeks:
                weeks._compute_absences()
                weeks._compute_capacity_net()
