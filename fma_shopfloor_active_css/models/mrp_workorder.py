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

    def search_is_assigned_to_connected(self, operator, value):
        """« Mes ordres de travail » = ceux ou JE POINTE, pas ceux qui me sont
        assignes.

        Odoo cherche sur `employee_assigned_ids`, l'affectation :

            search_query = self.env['mrp.workorder']._search(
                [('employee_assigned_ids', '=', main_employee_connected)])

        L'operateur y voyait donc tout ce qu'on lui a attribue, y compris ce
        qu'il n'a pas commence et ce qu'il a deja mis en pause. On cherche
        desormais sur `employee_ids`, la liste des operateurs reellement
        pointes : le filtre ne montre que le travail en cours, celui de la
        personne selectionnee dans le panneau de gauche.

        Consequence a connaitre : pour DEMARRER un ordre qui lui est assigne
        mais pas encore commence, l'operateur doit desactiver ce filtre. C'est
        le prix du « je ne vois que ce sur quoi je travaille ».
        """
        employe = self.env['hr.employee'].get_session_owner()
        if not employe:
            return []
        requete = self.env['mrp.workorder']._search([('employee_ids', 'in', employe)])
        return [('id', operator, requete)]
