# -*- coding: utf-8 -*-
import logging

from odoo import Command, models

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def _fma_employe_de_session(self):
        """L'employe qui a pris la session, en recordset.

        get_session_owner ne renvoie PAS un recordset mais un identifiant
        entier. On normalise ici plutot qu'a chaque appel : supposer un
        recordset a fait echouer le demarrage d'un ordre de travail, et le
        garde-fou lui-meme, qui lisait un attribut sur cet entier.

        On accepte les deux formes : selon les versions, la methode peut
        renvoyer l'un ou l'autre.
        """
        proprietaire = self.env['hr.employee'].get_session_owner()
        if not proprietaire:
            return self.env['hr.employee']
        if hasattr(proprietaire, '_name'):
            return proprietaire
        return self.env['hr.employee'].browse(proprietaire)

    def button_start(self, *args, **kwargs):
        """Demarrer rattache TOUJOURS l'operateur courant, meme si un collegue
        est deja dessus.

        Sur une tablette partagee, Odoo considere l'ordre comme deja demarre
        des qu'un operateur y pointe : le second qui appuie sur « Démarrer »
        obtient bien l'ecran de travail, mais n'est pas ajoute a
        `employee_ids`. Consequences, toutes deux constatees en pre-production :
        la carte ne passe pas au vert pour lui — le vert vient de
        `o_fma_mine`, qui teste sa presence dans cette liste — et l'ordre
        n'apparait pas dans « Mes ordres de travail », qui cherche sur la meme
        liste.

        On ne change pas ce que fait Odoo : on complete apres coup. Si
        l'operateur de session n'a pas de pointage ouvert, on lui en ouvre un ;
        s'il en a un sans figurer dans `employee_ids`, on l'y rattache. Deux
        operateurs peuvent ainsi travailler sur le meme ordre en le voyant
        chacun comme le sien.
        """
        res = super().button_start(*args, **kwargs)
        employe = self._fma_employe_de_session()
        if not employe:
            return res
        for wo in self:
            # Deux gestes independants, deux gardes : l'echec de l'ouverture du
            # pointage ne doit pas empecher le rattachement, qui est ce qui
            # fait passer la carte au vert et la fait entrer dans « Mes ordres
            # de travail ». Et ni l'un ni l'autre ne doit empecher de demarrer.
            try:
                ouvert = wo.time_ids.filtered(
                    lambda t: not t.date_end and t.employee_id == employe
                )
                if not ouvert:
                    wo.start_employee(employe.id)
            except Exception:
                _logger.exception(
                    "Atelier FMA : pointage non ouvert pour l'employe %s sur "
                    "l'ordre %s.", employe.id, wo.id,
                )
            try:
                if employe not in wo.employee_ids:
                    wo.employee_ids = [Command.link(employe.id)]
            except Exception:
                _logger.exception(
                    "Atelier FMA : employe %s non rattache a l'ordre %s.",
                    employe.id, wo.id,
                )
        return res

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
        employe = self._fma_employe_de_session()
        if not employe:
            return []
        requete = self.env['mrp.workorder']._search(
            [('employee_ids', 'in', employe.ids)]
        )
        return [('id', operator, requete)]
