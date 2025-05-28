from odoo import models, fields, api

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def write(self, values):
        context = self.env.context
        res = super().write(values)

        # Ne rien faire si on est en mode manuel (ex: permutation sur poste)
        if context.get('manual_swap'):
            return res

        trigger_fields = {'date_start', 'date_finished'}
        if trigger_fields & set(values.keys()):
            for wo in self:
                delta = (wo.date_start - wo._origin.date_start) if wo._origin.date_start and wo.date_start else None
                if delta:
                    if wo.is_first_workorder():
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


