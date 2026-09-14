from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Heures et cout de main d'oeuvre directe REELS, tires des pointages de
    # l'atelier.
    #
    # Champs ENREGISTRES et non plus calcules a l'affichage. Le calcul
    # parcourait tous les pointages de l'affaire a chaque ouverture du devis,
    # ne pouvait etre ni filtre ni regroupe, et son resultat n'existait nulle
    # part en base.
    #
    # Ils sont alimentes par _fma_recalculer_mod : a chaque pointage cree,
    # modifie ou supprime, et par le script de reprise pour l'historique.
    # Pas de calcul stocke Odoo : ses dependances traverseraient trois modeles
    # (commande, OF, pointage) dont deux declares par des modules qui chargent
    # apres celui-ci.
    so_heures_mod_reelles_odoo = fields.Float(
        string="Heures MOD réelles Odoo",
        readonly=True,
        copy=False,
    )
    so_cout_mod_reel_odoo = fields.Monetary(
        string="Coût MOD réel Odoo",
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )

    def format_amount(self, amount):
        return "{:,.2f}".format(amount).replace(",", " ").replace(".", ",")

    def _fma_employe_du_pointage(self, pointage):
        """Employe a qui imputer un pointage.

        L'employe du pointage d'abord : c'est le cas de tous les pointages
        faits depuis l'Atelier. A defaut, l'employe lie a l'utilisateur qui a
        pointe — le cas des chronos lances depuis l'OF en back-office, qui ne
        portent que l'utilisateur. Sans ce repli, leurs heures etaient
        comptees mais valorisees a zero.
        """
        employe = pointage.employee_id if "employee_id" in pointage._fields else False
        if not employe and "user_id" in pointage._fields and pointage.user_id:
            employe = pointage.user_id.employee_id
        return employe

    def _get_employee_hourly_cost_for_mod(self, employee):
        """Cout horaire de l'employe.

        hourly_cost est le seul champ de cout present sur la fiche employe.
        La version precedente essayait une liste de champs et s'arretait au
        premier qui EXISTAIT, meme vide.
        """
        if not employee or "hourly_cost" not in employee._fields:
            return 0.0
        return float(employee.hourly_cost or 0.0)

    def _fma_recalculer_mod(self):
        """Recalcule les heures et le cout MOD reels de chaque commande.

        LES OF DE LA COMMANDE, ET NON CEUX DU PROJET. Le calcul partait du
        « Projet mtn » : deux tranches d'une meme affaire partageant ce projet
        affichaient chacune le total de l'affaire, et un rapport qui les
        additionne comptait les heures deux fois. On part desormais des liens
        commande -> OF de _fma_ordres_de_fabrication (module custom), les memes
        que pour les dates de fabrication.

        LES POINTAGES SONT PRIS TELS QUELS. Un chrono oublie qui a tourne des
        jours pese de toute sa duree : c'est une decision metier, les
        anomalies se corrigent dans les pointages, pas dans ce calcul.

        Le cout retient le cout horaire ACTUEL de l'employe, comme le calcul
        d'origine : une hausse de salaire revalorise l'historique au prochain
        recalcul.
        """
        for order in self:
            ofs = order._fma_ordres_de_fabrication()
            heures = 0.0
            cout = 0.0
            if ofs and "workorder_ids" in ofs._fields:
                for pointage in ofs.workorder_ids.time_ids:
                    duree = (pointage.duration or 0.0) / 60.0
                    employe = order._fma_employe_du_pointage(pointage)
                    heures += duree
                    cout += duree * order._get_employee_hourly_cost_for_mod(employe)

            vals = {}
            if round(order.so_heures_mod_reelles_odoo or 0.0, 4) != round(heures, 4):
                vals["so_heures_mod_reelles_odoo"] = heures
            if round(order.so_cout_mod_reel_odoo or 0.0, 2) != round(cout, 2):
                vals["so_cout_mod_reel_odoo"] = cout
            if vals:
                order.write(vals)
