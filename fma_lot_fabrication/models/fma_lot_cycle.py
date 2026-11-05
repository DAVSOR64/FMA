# -*- coding: utf-8 -*-
"""Le moteur : du cycle aux dates d'un lot, puis d'un lot au suivant.

Ce fichier ne calcule que des DATES. Il n'ecrit rien sur les ordres : la pose
des dates et la neutralisation du planificateur natif viennent apres, et
separer les deux permet de verifier les chiffres avant qu'ils ne touchent la
production.

La regle, telle que la production l'a posee :

* le cycle d'un lot se lit dans la matrice, a l'intersection de sa complexite
  la plus haute et de son nombre de menuiseries ;
* le cycle donne, pour chaque poste, un nombre de jours OUVRES avant la fin de
  fabrication ;
* le premier lot d'une affaire se cale sur la livraison client, moins un delai
  de securite, en jours ouvres lui aussi ;
* les lots suivants ne se calent pas sur la livraison mais **les uns sur les
  autres** : le lot 2 debite un nombre parametre de jours ouvres AVANT le lot
  1, le lot 3 avant le lot 2. Leur fin de fabrication se deduit ensuite de
  leur debit, et non l'inverse ;
* un debit qui tomberait dans le passe arrete tout. Le metier calibre le lot 1
  pour que cela n'arrive pas ; si cela arrive quand meme, c'est que l'affaire
  est deja en retard, et le planning ne doit pas faire semblant.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FmaLotFabrication(models.Model):
    _inherit = "fma.lot.fabrication"

    fma_cycle_niveau_id = fields.Many2one(
        "fma.complexite.niveau",
        string="Complexité du lot",
        compute="_compute_fma_cycle",
        help="La complexité la plus haute portée par les menuiseries du lot, "
             "lue sur leur article depuis le chiffrage LOGIKAL.",
    )
    fma_cycle_nb_menuiseries = fields.Integer(
        string="Menuiseries du lot",
        compute="_compute_fma_cycle",
        help="Somme des quantités des repères du lot, et non son nombre de "
             "repères : deux repères de 8 font 16 menuiseries.",
    )
    fma_cycle_id = fields.Many2one(
        "fma.cycle",
        string="Cycle",
        compute="_compute_fma_cycle",
    )
    fma_delai_appro_semaines = fields.Integer(
        string="Délai appro — DELAPP (semaines)",
        help="Délai d'approvisionnement de la matière de ce lot, en SEMAINES, "
             "repris du tableau des délais fournisseurs. Il ne décale aucune "
             "fabrication : il sert à calculer la date limite de passage de "
             "commande de l'affaire.",
    )
    fma_cycle_apercu = fields.Text(
        string="Planning du cycle",
        compute="_compute_fma_cycle_apercu",
        help="Les dates que le cycle donne, sans rien écrire. Elles se "
             "recalculent dès que la matrice ou le chiffrage changent.",
    )

    # ------------------------------------------------------------------
    # Les deux entrees de la matrice
    # ------------------------------------------------------------------
    def _cycle_lignes_menuiserie(self):
        self.ensure_one()
        return self.line_ids.filtered("est_menuiserie")

    def _cycle_nb_menuiseries(self):
        """Le nombre de MENUISERIES du lot, pas son nombre de reperes."""
        self.ensure_one()
        total = sum(self._cycle_lignes_menuiserie().mapped("product_qty"))
        return int(round(total))

    def _cycle_niveau(self):
        """La complexite la plus haute du lot, ou un recordset vide.

        L'article porte la complexite telle que LOGIKAL l'ecrit : « A », ou
        « A*3 » quand le chiffreur y joint un nombre de reperes. Seule la
        lettre designe le niveau — le nombre ne dit pas qu'une menuiserie est
        plus compliquee, il dit qu'il y en a plusieurs.

        « Plus haute » se lit dans la sequence du referentiel, et non dans
        l'ordre alphabetique : le jour ou un niveau s'intercale, l'ecran de
        configuration suffit a le placer.
        """
        self.ensure_one()
        Niveau = self.env["fma.complexite.niveau"]
        par_code = {
            (niveau.code or "").strip().upper(): niveau
            for niveau in Niveau.search([])
            if niveau.code
        }
        retenu = Niveau
        for ligne in self._cycle_lignes_menuiserie():
            produit = ligne.product_id
            texte = produit.fma_complexite if "fma_complexite" in produit._fields else ""
            for brut in (texte or "").splitlines():
                code = brut.partition("*")[0].strip().upper()
                niveau = par_code.get(code)
                if niveau and (not retenu or niveau.sequence > retenu.sequence):
                    retenu = niveau
        return retenu

    @api.depends("line_ids.product_qty", "line_ids.est_menuiserie",
                 "line_ids.product_id")
    def _compute_fma_cycle(self):
        Regle = self.env["fma.cycle.regle"]
        for lot in self:
            lot.fma_cycle_nb_menuiseries = lot._cycle_nb_menuiseries()
            lot.fma_cycle_niveau_id = lot._cycle_niveau()
            lot.fma_cycle_id = False
            if not lot.fma_cycle_niveau_id or not lot.fma_cycle_nb_menuiseries:
                continue
            regle = Regle.search([
                ("niveau_id", "=", lot.fma_cycle_niveau_id.id),
                ("qte_min", "<=", lot.fma_cycle_nb_menuiseries),
                ("qte_max", ">=", lot.fma_cycle_nb_menuiseries),
            ], limit=1)
            lot.fma_cycle_id = regle.cycle_id

    def _cycle_ou_erreur(self):
        """Le cycle du lot, ou l'erreur qui dit quoi corriger."""
        self.ensure_one()
        niveau = self._cycle_niveau()
        if not niveau:
            raise UserError(_(
                "Le lot %(lot)s ne porte aucune complexité exploitable. Les "
                "articles de ses menuiseries doivent porter celle du "
                "chiffrage LOGIKAL (A, B, C, D ou E).",
                lot=self.display_name,
            ))
        return self.env["fma.cycle.regle"]._cycle_pour(
            niveau, self._cycle_nb_menuiseries()
        )

    # ------------------------------------------------------------------
    # Le calendrier
    # ------------------------------------------------------------------
    def _cycle_calendrier(self):
        self.ensure_one()
        return self.company_id.resource_calendar_id

    def _cycle_jours_ouvres(self, depart, jours):
        """``depart`` decale de ``jours`` jours OUVRES, positif ou negatif.

        Le calendrier de la societe porte les week-ends, les feries et les
        fermetures d'entreprise. Les conges d'un salarie n'y sont pas, et
        c'est voulu : une absence reduit la capacite d'un poste, elle ne
        deplace pas un lot, qui n'est affecte a personne.
        """
        self.ensure_one()
        depart = fields.Datetime.to_datetime(depart)
        calendrier = self._cycle_calendrier()
        if calendrier:
            cible = calendrier.plan_days(
                float(jours) if jours >= 0 else float(jours),
                depart,
                compute_leaves=True,
            )
            if cible:
                return fields.Datetime.to_datetime(cible)
        # Sans calendrier exploitable, des jours calendaires valent mieux
        # qu'une absence de date, qui laisserait le lot non planifie.
        _logger.warning(
            "Lot %s : pas de calendrier societe, decalage en jours "
            "calendaires", self.display_name,
        )
        return depart + timedelta(days=jours)

    def _cycle_jours_securite(self):
        """DELLOG : le delai de securite STANDARD d'Odoo, en jours ouvres.

        Pas de reglage FMA pour cela : ``security_lead`` existe deja sur la
        societe, pose par sale_stock, et c'est lui que le natif applique
        entre la date de livraison et la date prevue de l'expedition. En
        creer un second aurait donne deux marges a tenir a jour, et la
        certitude qu'elles divergent.

        Seule difference avec le natif : Odoo le compte en jours calendaires,
        et toute la planification par cycles se compte en jours OUVRES.
        """
        self.ensure_one()
        societe = self.company_id
        if "security_lead" not in societe._fields:
            return 0
        return int(round(societe.security_lead or 0.0))

    def _cycle_decalage_entre_lots(self):
        self.ensure_one()
        return self.company_id.fma_lot_decalage_entre_lots or 0

    # ------------------------------------------------------------------
    # Les dates d'un lot
    # ------------------------------------------------------------------
    def _cycle_dates_depuis_fin(self, fin_de_fab, cycle=None):
        """{id de poste: date} pour une fin de fabrication donnee.

        Chaque poste recule de son propre nombre de jours ouvres. La fin de
        fabrication elle-meme figure dans le resultat sous la cle ``False``,
        pour que l'appelant n'ait pas a la recalculer.
        """
        self.ensure_one()
        cycle = cycle or self._cycle_ou_erreur()
        fin = fields.Datetime.to_datetime(fin_de_fab)
        dates = {False: fin}
        for poste_id, jours in cycle._decalages_par_poste().items():
            dates[poste_id] = (
                fin if not jours else self._cycle_jours_ouvres(fin, -jours)
            )
        return dates

    def _cycle_premier_poste(self, cycle=None):
        """Le poste qui ouvre le cycle, et son decalage.

        C'est le debit dans tous les cycles d'aujourd'hui, mais on le designe
        par son RANG — le decalage le plus grand — et non par son nom : le
        jour ou une operation se place avant lui, le chainage des lots doit
        suivre sans qu'on y revienne.
        """
        self.ensure_one()
        cycle = cycle or self._cycle_ou_erreur()
        operations = cycle.operation_ids.sorted(
            lambda o: o.jours_avant_fin, reverse=True
        )
        if not operations:
            raise UserError(_(
                "Le cycle %(cycle)s ne porte aucune opération : il ne peut "
                "dater aucun lot.",
                cycle=cycle.display_name,
            ))
        return operations[0].workcenter_id, operations[0].jours_avant_fin

    # ------------------------------------------------------------------
    # L'affaire : les lots s'enchainent les uns derriere les autres
    # ------------------------------------------------------------------
    def _cycle_lots_de_l_affaire(self):
        """Les lots de la meme commande, dans l'ordre de leur NUMERO.

        Le numero d'un lot est son rang parmi ceux de sa commande, par ordre
        de creation : c'est celui que l'ecran affiche — « A26-00-00002 - Lot
        3 » — et celui dont l'atelier parle. Il n'est pas stocke, il se
        recalcule, et c'est ce qui le rend juste apres un reimport.
        """
        self.ensure_one()
        commande = self.line_ids.order_id[:1]
        if not commande:
            return self
        return self.sudo().search(
            [("line_ids.order_id", "=", commande.id),
             ("state", "!=", "cancel")],
            order="id",
        )

    def _cycle_date_livraison(self):
        """La date de livraison engagee de la commande du lot."""
        self.ensure_one()
        commande = self.line_ids.order_id[:1]
        if not commande:
            return False
        brut = (
            commande.commitment_date
            or getattr(commande, "so_date_de_livraison_prevu", False)
            or getattr(commande, "x_studio_date_de_livraison_prevu", False)
        )
        return fields.Datetime.to_datetime(brut)

    def _cycle_planifier_affaire(self, controler_passe=True):
        """Les dates de TOUS les lots de l'affaire, sans rien ecrire.

        Renvoie ``{id de lot: {id de poste ou False: date}}``, ``False``
        portant la fin de fabrication du lot.

        Le recalcul porte sur l'affaire entiere a chaque appel, et non sur le
        seul lot qui vient d'arriver. Un decalage applique au coup par coup
        derivrait : reimporter deux fois le lot 2 le reculerait deux fois.
        """
        self.ensure_one()
        lots = self._cycle_lots_de_l_affaire()
        livraison = self._cycle_date_livraison()
        if not livraison:
            raise UserError(_(
                "La commande du lot %(lot)s n'a pas de date de livraison "
                "prévue : aucun cycle ne peut être calé dessus.",
                lot=self.display_name,
            ))

        decalage = self._cycle_decalage_entre_lots()
        aujourd_hui = fields.Datetime.now()
        resultat = {}
        debit_lot_1 = False
        appro_lot_1 = 0

        for rang, lot in enumerate(lots, start=1):
            cycle = lot._cycle_ou_erreur()
            poste_debit, jours_debit = lot._cycle_premier_poste(cycle)

            if rang == 1:
                # FF_1 = LIV - DELLOG, puis DEB_1 = FF_1 - CYC_1.
                fin = lot._cycle_jours_ouvres(
                    livraison, -lot._cycle_jours_securite()
                )
                debit = lot._cycle_jours_ouvres(fin, -jours_debit)
                debit_lot_1 = debit
                appro_lot_1 = lot.fma_delai_appro_semaines or 0
            else:
                # DEB_L = DEB_1 - X * (L-1), et non DEB_(L-1) - X.
                # Le resultat est le meme tant que X ne change pas, mais la
                # formule du CDC ne derive pas : un lot reimporte au milieu
                # de la chaine ne decale plus ceux qui le suivent.
                debit = lot._cycle_jours_ouvres(
                    debit_lot_1, -decalage * (rang - 1)
                )
                # FF_L se DEDUIT du debit du lot, et non l'inverse.
                fin = lot._cycle_jours_ouvres(debit, jours_debit)

            if controler_passe and debit.date() < aujourd_hui.date():
                raise UserError(_(
                    "Le débit du lot %(lot)s tomberait le %(date)s, dans le "
                    "passé. L'affaire est en retard sur son plan : reprendre "
                    "la date de livraison, le découpage en lots, ou le "
                    "décalage entre lots (%(decalage)s jours ouvrés) avant de "
                    "planifier.",
                    lot=lot.display_name,
                    date=fields.Date.to_string(debit.date()),
                    decalage=decalage,
                ))

            resultat[lot.id] = lot._cycle_dates_depuis_fin(fin, cycle)

        # CDE = DEB_1 - DELAPP_1 - X * (N-1).
        # UNE SEULE date pour toute l'affaire : la matiere est commandee en
        # une fois, et elle doit couvrir le lot qui debite le plus tot — donc
        # le dernier, d'ou le X * (N-1).
        #
        # LE DELAI DE PREPARATION MATIERE DU CDC N'Y FIGURE PAS. Il est
        # calcule en amont et change d'une affaire a l'autre : en faire une
        # constante de societe aurait fige ce qui varie. La date rendue ici
        # est donc la limite AVANT prise en compte de cette preparation.
        if debit_lot_1:
            jours_appro = appro_lot_1 * 5
            commande = self._cycle_jours_ouvres(
                debit_lot_1,
                -(jours_appro + decalage * (len(lots) - 1)),
            )
            resultat["commande"] = commande

        return resultat

    # ------------------------------------------------------------------
    # L'apercu, pour verifier avant d'ecrire
    # ------------------------------------------------------------------
    @api.depends("fma_cycle_id", "line_ids.order_id")
    def _compute_fma_cycle_apercu(self):
        for lot in self:
            lot.fma_cycle_apercu = lot._cycle_texte_apercu()

    def _cycle_texte_apercu(self):
        self.ensure_one()
        try:
            dates = self._cycle_planifier_affaire(controler_passe=False)
        except UserError as erreur:
            return str(erreur)

        lignes = []
        for lot in self._cycle_lots_de_l_affaire():
            mes_dates = dates.get(lot.id)
            if not mes_dates:
                continue
            marque = " <<<" if lot.id == self.id else ""
            lignes.append("%s — cycle %s, %s menuiserie(s), complexité %s%s" % (
                lot.display_name,
                lot.fma_cycle_id.name or "?",
                lot.fma_cycle_nb_menuiseries,
                lot.fma_cycle_niveau_id.code or "?",
                marque,
            ))
            postes = self.env["mrp.workcenter"].browse(
                [cle for cle in mes_dates if cle]
            )
            for poste in postes.sorted(lambda p: mes_dates[p.id]):
                lignes.append("    %-28s %s" % (
                    poste.display_name,
                    fields.Date.to_string(mes_dates[poste.id].date()),
                ))
            lignes.append("    %-28s %s" % (
                "FIN DE FABRICATION",
                fields.Date.to_string(mes_dates[False].date()),
            ))
            lignes.append("")

        commande = dates.get("commande")
        if commande:
            lignes.append("DATE LIMITE DE PASSAGE DE COMMANDE (affaire) : %s"
                          % fields.Date.to_string(commande.date()))
            lignes.append("    = débit du lot 1 - délai appro"
                          " - décalage x (nb lots - 1), hors prépa matière")
        return "\n".join(lignes)
