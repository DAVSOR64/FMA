from odoo import models

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def write(self, values):
        context = self.env.context

        # Calculer le delta AVANT d'écrire
        deltas = {}
        for wo in self:
            old_date = wo.date_start
            new_date = values.get('date_start', old_date)
            if old_date and new_date and old_date != new_date:
                delta = new_date - old_date
                deltas[wo.id] = delta

        # Appeler l'écriture standard
        res = super().write(values)

        # Après l'écriture, appliquer la logique
        for wo in self:
            delta = deltas.get(wo.id)
            if delta:
                if wo.is_first_workorder() or context.get('from_gantt'):
                    wo._shift_entire_of_and_dependents(delta)
                else:
                    wo._shift_partial_of(delta)
        return res


    def is_first_workorder(self):
        self.ensure_one()
        return self == self.order_id.workorder_ids.sorted('sequence')[0]

    def _shift_entire_of_and_dependents(self, delta):
        """Décale tout l'OF + les OFs suivants."""
        # Décaler tous les WOs de l'OF courant
        for wo in self.order_id.workorder_ids:
            if wo.date_start:
                wo.date_start += delta
            if wo.date_finished:
                wo.date_finished += delta

        # Décaler les OFs suivants (via les dépendances)
        for wo in self:
            for next_wo in wo.needed_by_workorder_ids:
                next_wo.date_start += delta
                next_wo.date_finished += delta
                next_wo._shift_entire_of_and_dependents(delta)

    def _shift_partial_of(self, delta):
        """Décale ce WO et les suivants dans l'OF."""
        wos_to_shift = self.order_id.workorder_ids.filtered(lambda w: w.sequence >= self.sequence)
        for wo in wos_to_shift:
            if wo.date_start:
                wo.date_start += delta
            if wo.date_finished:
                wo.date_finished += delta

    def manual_swap(self, other_wo):
        """Permuter cet ordre de travail avec un autre sur le même poste."""
        if self.workcenter_id != other_wo.workcenter_id:
            raise ValueError("Les ordres de travail ne sont pas sur le même poste.")
        # Inverser les séquences (ou dates) des WOs
        self_sequence = self.sequence
        other_sequence = other_wo.sequence
        self.with_context(manual_swap=True).write({'sequence': other_sequence})
        other_wo.with_context(manual_swap=True).write({'sequence': self_sequence})


