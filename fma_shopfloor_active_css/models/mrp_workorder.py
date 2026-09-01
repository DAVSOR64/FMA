# -*- coding: utf-8 -*-
from odoo import Command, models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def button_pending(self):
        """La mise en pause n'arrete QUE le pointage de l'operateur courant.

        Odoo detache le proprietaire de la session sans verifier qu'il
        pointait :

            employee = Employee.get_session_owner()
            if employee:
                self.stop_employee([employee.id])

        `stop_employee` retire l'employe de `employee_ids` (Command.unlink),
        qu'il ait ou non un pointage ouvert. Sur une tablette partagee, la
        session appartient au dernier connecte : si A met en pause alors que B
        vient de prendre la session, Odoo detache B — qui travaillait — et
        laisse A rattache. Les deux operateurs se retrouvent dans un etat faux.

        On ne change pas QUI est arrete : chacun ne suspend que sa propre
        partie, c'est la regle voulue. On repare seulement le detachement a
        tort : apres l'appel a super(), tout operateur ayant encore un pointage
        OUVERT sur cet ordre y est rattache de nouveau. Un employe reste donc
        affiche tant qu'il travaille reellement, et disparait des qu'il a mis
        en pause — ni avant, ni a cause de quelqu'un d'autre.
        """
        res = super().button_pending()
        for wo in self:
            pointages_ouverts = wo.time_ids.filtered(lambda t: not t.date_end)
            a_retablir = pointages_ouverts.employee_id - wo.employee_ids
            if a_retablir:
                wo.employee_ids = [Command.link(emp.id) for emp in a_retablir]
        return res
