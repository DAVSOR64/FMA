# -*- coding: utf-8 -*-
from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def get_employees_wo_by_employees(self, employees_ids):
        """Ajoute le chantier a chaque poste occupe du panneau operateurs.

        La methode d'origine renvoie, par employe connecte, la liste de ses
        postes en cours avec le temps pointe :

            {"id": 3, "workcenters": [{"id": 7, "name": "Usinage",
                                       "duration": 42.0, "ongoing": True}]}

        Le chef d'atelier voit donc sur quel poste travaille chacun, mais pas
        sur quelle affaire — l'information ne remonte simplement pas jusqu'au
        client. On la joint ici, sans toucher au calcul des temps.

        Le rapprochement se fait par (employe, poste) : c'est la cle que la
        methode d'origine utilise pour regrouper, et un operateur n'a qu'un
        pointage ouvert par poste.
        """
        employees = super().get_employees_wo_by_employees(employees_ids)
        if not employees_ids:
            return employees

        # Pointages ouverts : date_end vide. Ce sont eux, et eux seuls, qui
        # portent le « ongoing » des postes renvoyes par la methode d'origine.
        pointages = self.env["mrp.workcenter.productivity"].search([
            ("employee_id", "in", employees_ids),
            ("date_end", "=", False),
        ])

        chantiers = {}
        for pointage in pointages:
            of = pointage.workorder_id.production_id
            # x_studio_projet_de_la_vente est declare par le module « custom »,
            # dont celui-ci ne depend pas : on controle sa presence.
            if not of or "x_studio_projet_de_la_vente" not in of._fields:
                continue
            projet = of.x_studio_projet_de_la_vente
            if projet:
                cle = (pointage.employee_id.id, pointage.workcenter_id.id)
                chantiers.setdefault(cle, projet.display_name)

        if not chantiers:
            return employees

        for employe in employees:
            for poste in employe.get("workcenters") or []:
                chantier = chantiers.get((employe["id"], poste.get("id")))
                if chantier:
                    poste["chantier"] = chantier
        return employees
