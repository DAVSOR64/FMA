# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rules migrated from Odoo Studio automations.

Origin (Studio):
- base.automation "MTN : Propagation du compte analytique SO sur PO" and its
  exact duplicate "MTN : Propagation du compte analytique MO sur PO" (merged
  here into a single method).
- base.automation "DSA Reference compute PO" (also fixes a latent bug in the
  original code: it looped `for po in records` but read/wrote `record`
  instead of `po`, so it only behaved correctly for single-record triggers).
- base.automation "DSA : Mise à jour du responsable PO par le responsable
  PROJECT" (le portage s'écarte volontairement de l'original : il ne remet
  plus l'acheteur à vide quand la commande n'a pas de projet -- voir
  `_sync_responsible_from_project`).
See STUDIO_AUDIT.md at the repo root for the full inventory.

Ce fichier porte aussi le RATTACHEMENT D'UN ACHAT A UNE COMMANDE CLIENT
(champ « Commande client »), dont depend le calcul du prix de revient : voir
la classe PurchaseOrderLine en fin de fichier.
"""
import re

from lxml import etree

from odoo import api, fields, models

#: Separateurs d'un champ « origine » : Odoo y cumule les documents sources
#: avec des virgules, le lot y ecrit « <lot> - <commande> ».
ORIGINE_SEPARATEURS = re.compile(r"[,;\s]+")

#: Champs dont l'ecriture peut reveler la commande d'un achat.
DECLENCHEURS_EN_TETE = {"order_line", "origin", "x_studio_projet_du_so", "state"}
DECLENCHEURS_LIGNE = {"fma_sale_line_id", "lot_fabrication_id", "move_dest_ids"}


def commandes_des_of(ordres):
    """Commandes client servies par des ordres de fabrication.

    Par tous les liens connus, chacun n'etant suivi que si son champ existe :
    ce module charge avant ceux qui en declarent plusieurs (lots, custom).
    """
    commandes = ordres.env["sale.order"]
    if not ordres:
        return commandes
    champs = ordres._fields
    if "lot_sale_order_id" in champs:
        commandes |= ordres.lot_sale_order_id
    if "sale_line_id" in champs:
        commandes |= ordres.sale_line_id.order_id
    if "x_studio_mtn_mrp_sale_order" in champs:
        commandes |= ordres.x_studio_mtn_mrp_sale_order
    if not commandes and "lot_fabrication_id" in champs:
        # L'OF de debit : il sert le lot entier, donc ses commandes.
        commandes |= ordres.lot_fabrication_id.sale_order_ids
    if not commandes:
        # Dernier recours : l'origine de l'OF cite le numero de la commande.
        jetons = set()
        for ordre in ordres:
            jetons.update(
                j for j in ORIGINE_SEPARATEURS.split(ordre.origin or "") if len(j) > 1)
        if jetons:
            commandes = commandes.search([("name", "in", list(jetons))])
    return commandes


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        """Affiche « Projet » sur le formulaire quand aucune vue ne le fait.

        Le champ x_studio_projet_du_so n'est pose a l'ecran que par une vue
        Studio de la base. La ou elle existe, on n'y touche pas ; la ou elle
        manque, le projet de l'achat etait invisible. On l'insere alors juste
        avant « Commande client » : les deux axes d'imputation cote a cote.
        """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form" and "x_studio_projet_du_so" in self._fields:
            hors_lignes = "[not(ancestor::field)]"
            deja = arch.xpath("//field[@name='x_studio_projet_du_so']" + hors_lignes)
            commande = arch.xpath("//field[@name='fma_sale_order_id']" + hors_lignes)
            if commande and not deja:
                commande[0].addprevious(
                    etree.Element("field", name="x_studio_projet_du_so"))
            elif commande and deja:
                # Le Projet est deja a l'ecran : « Commande client » se range
                # juste dessous, ou qu'une autre vue ait pose le Projet.
                deja[0].addnext(commande[0])
        return arch, view

    # « Commande client » de l'achat. Avec « Projet du SO » (l'affaire), c'est
    # le second axe d'imputation : une affaire a tranches porte plusieurs
    # commandes, et le projet seul ne dit pas laquelle paie l'achat. Les deux
    # champs d'en-tete — Affaire, Commande — sont ceux que les plans
    # analytiques a venir reprendront.
    #
    # Champ ordinaire, et non calcul stocke : le lien se revele en plusieurs
    # temps (la ligne nait avant que l'OF ne rejoigne son lot), et un calcul
    # stocke fige ce qu'il a vu a la naissance. Il est donc POSE par
    # _fma_rattacher_commande, rejoue aux moments utiles, et ne remplace
    # jamais une saisie.
    fma_sale_order_id = fields.Many2one(
        "sale.order",
        string="Commande client",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
        tracking=True,
        domain="fma_sale_order_domain",
        help="Commande client a laquelle cet achat est impute dans le calcul "
        "du prix de revient. Remplie automatiquement quand l'achat vient "
        "d'un lot ou d'un ordre de fabrication de la commande, ou quand le "
        "projet n'a qu'une commande confirmee. A saisir sur une affaire a "
        "tranches pour un achat fait a la main. S'applique a toutes les "
        "lignes, sauf celles qui designent une ligne de commande.",
    )
    fma_sale_order_domain = fields.Binary(
        compute="_compute_fma_sale_order_domain",
        help="Commandes proposees : celles du projet de l'achat s'il en a un.",
    )

    @api.model
    def default_get(self, fields_list):
        """L'acheteur par defaut de la societe, quand Odoo n'en met pas.

        Odoo propose l'utilisateur qui saisit. Sur un bon ne d'un
        approvisionnement, personne ne saisit : le champ reste vide, le bon
        n'apparait dans la liste « Mes commandes » d'aucun acheteur et il
        attend que quelqu'un tombe dessus. On pose donc le responsable que
        la societe designe.
        """
        valeurs = super().default_get(fields_list)
        defaut = self.env.company.fma_acheteur_defaut_id
        if "user_id" in fields_list and defaut:
            valeurs["user_id"] = defaut.id
        return valeurs


    @api.depends("x_studio_projet_du_so")
    def _compute_fma_sale_order_domain(self):
        Commande = self.env["sale.order"]
        for achat in self:
            domaine = [("state", "in", ("sale", "done"))]
            if achat.x_studio_projet_du_so:
                domaine += Commande._fma_domaine_projet(achat.x_studio_projet_du_so)
            achat.fma_sale_order_domain = domaine

    def _fma_appliquer_commande_aux_lignes(self):
        """L'en-tete fait foi pour ses lignes.

        Saisir la commande en en-tete l'applique a toutes les lignes — y
        compris celles qu'un rattachement automatique avait deja servies :
        c'est une correction, elle doit porter. Seule une ligne qui designe
        une LIGNE DE COMMANDE garde la sienne, ce choix etant plus precis.
        """
        for achat in self:
            lignes = achat.order_line.filtered(
                lambda l: not l.display_type and not l.fma_sale_line_id
                and l.fma_sale_order_id != achat.fma_sale_order_id)
            if lignes:
                lignes.with_context(fma_rattachement_auto=True).write(
                    {"fma_sale_order_id": achat.fma_sale_order_id.id})

    def create(self, vals_list):
        # L'ACHETEUR PAR DEFAUT, ICI AUSSI. default_get ne passe que par
        # l'interface ; l'approvisionnement appelle create() avec ses propres
        # valeurs — et c'est precisement le cas qui laissait les bons sans
        # responsable, donc dans la liste « Mes commandes » de personne.
        defaut = self.env.company.fma_acheteur_defaut_id
        if defaut:
            for vals in vals_list:
                if not vals.get("user_id"):
                    vals["user_id"] = defaut.id
        orders = super().create(vals_list)
        orders.with_context(skip_studio_sync=True)._apply_studio_automations()
        orders.order_line._fma_rattacher_commande()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_studio_sync"):
            self.with_context(skip_studio_sync=True)._apply_studio_automations(vals)
        if not self.env.context.get("fma_rattachement_auto"):
            if "fma_sale_order_id" in vals:
                self._fma_appliquer_commande_aux_lignes()
            elif DECLENCHEURS_EN_TETE & set(vals):
                self.order_line._fma_rattacher_commande()
        return res

    def _apply_studio_automations(self, vals=None):
        self._propagate_analytic_from_sale_order()
        self._compute_studio_reference()
        # L'acheteur ne se resynchronise QU'A la creation et lorsque le projet
        # change. Le rejouer a chaque ecriture rendait le champ impossible a
        # corriger : l'utilisateur choisissait un acheteur, enregistrait, et
        # write() remettait aussitot celui du projet. Le symptome etait le plus
        # visible sur les commandes generees a la confirmation d'un devis,
        # celles qui portent toujours un projet.
        #
        # Meme regle que la propagation analytique juste au-dessus : ne jamais
        # ecraser silencieusement une saisie manuelle.
        if vals is None or "x_studio_projet_du_so" in vals:
            self._sync_responsible_from_project()

    def _propagate_analytic_from_sale_order(self):
        # Ne touche jamais une ligne qui a déjà une répartition analytique
        # (saisie manuelle ou propagation précédente) -- même règle que pour
        # "Projet du SO" (custom/models/purchase_order.py). Sans cette
        # garde, `write()` réappliquerait la répartition du devis à
        # *toutes* les lignes à chaque sauvegarde, effaçant silencieusement
        # toute correction manuelle.
        #
        # Cas particulier : une ligne ajoutée à la main sur une commande
        # déjà générée depuis la fabrication ne récupère rien de la source
        # ci-dessous seule. Cause : les lignes déjà présentes sur ce type de
        # commande héritent leur répartition analytique directement via la
        # chaîne d'approvisionnement standard (OF -> commande), sans qu'elle
        # soit jamais recopiée sur la ligne de devis -- la source lue
        # ci-dessous (`sale_order.order_line`) est donc vide, alors que la
        # commande elle-même a déjà la bonne valeur sur ses autres lignes.
        # On élargit donc la source de repli à ces lignes-sœurs déjà
        # renseignées sur la même commande.
        for po in self:
            analytic_dist = {}
            for line in po.order_line:
                if line.analytic_distribution:
                    analytic_dist = line.analytic_distribution
                    break
            if not analytic_dist and po.sale_order_count:
                sale_order = po._get_sale_orders()[:1]
                for sol in sale_order.order_line:
                    if sol.analytic_distribution:
                        analytic_dist = sol.analytic_distribution
                        break
            if not analytic_dist:
                continue
            lines_without_dist = po.order_line.filtered(lambda l: not l.analytic_distribution)
            if lines_without_dist:
                lines_without_dist.write({"analytic_distribution": analytic_dist})

    def _compute_studio_reference(self):
        for po in self:
            function = po.user_id.function or ""
            affaire = po.x_studio_many2one_field_LCOZX
            projet = po.x_studio_projet_du_so
            if projet:
                po.x_studio_rfrence = f"{function} - {projet.name} - {po.name}"
            elif affaire.x_name:
                po.x_studio_rfrence = f"{function} - {affaire.x_name} - {po.name}"
            else:
                po.x_studio_rfrence = f"{function} - {po.name}"

    def _sync_responsible_from_project(self):
        """Reprend l'acheteur du projet. Appele a la creation, et au seul
        changement de projet ensuite : voir _apply_studio_automations.
        """
        for po in self:
            responsible = po.x_studio_projet_du_so.user_id
            if responsible and po.user_id != responsible:
                po.user_id = responsible


class PurchaseOrderLine(models.Model):
    """Rattachement d'une ligne d'achat a une commande client.

    Le lien vit sur la LIGNE, comme celui du lot : un bon de commande regroupe
    les besoins d'un fournisseur pour un projet, donc eventuellement ceux de
    deux tranches. L'en-tete porte la commande quand toutes ses lignes en ont
    une seule, et sert de saisie rapide.

    Ordre de resolution d'une ligne sans commande :

    1. le lot de fabrication de la ligne ;
    2. la chaine d'approvisionnement : ce que l'achat alimente — un composant
       d'OF, une livraison — jusqu'a rencontrer une commande ;
    3. la ligne de vente native (achat ne d'une vente de service) ;
    4. l'origine du bon : numero de commande, d'OF ou de lot ;
    5. la commande saisie en en-tete ;
    6. le projet, s'il ne porte qu'UNE commande confirmee.

    Des que deux commandes sont possibles, rien n'est pose : le calcul du prix
    de revient signale l'achat comme « non rattache » et c'est a
    l'utilisateur de trancher. Ajouter d'office un achat a toutes les tranches
    d'une affaire est exactement ce qu'on veut eviter.
    """

    _inherit = "purchase.order.line"

    #: Nombre de maillons remontes le long des mouvements de stock.
    FMA_PROFONDEUR_CHAINE = 6

    fma_sale_order_id = fields.Many2one(
        "sale.order",
        string="Commande client",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
        help="Commande client qui porte le cout de cette ligne. Vide : "
        "l'achat n'est compte dans aucun prix de revient.",
    )
    fma_sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de commande",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
        domain="[('order_id', '=?', fma_sale_order_id), ('display_type', '=', False)]",
        help="Facultatif. Ligne de commande qui porte cet achat quand aucun "
        "ordre de fabrication ne le consomme (achat hors nomenclature). Un "
        "article consomme par les ordres de fabrication est reparti selon "
        "leur consommation, quoi que dise ce champ.",
    )

    @api.onchange("fma_sale_line_id")
    def _onchange_fma_sale_line_id(self):
        for ligne in self:
            if ligne.fma_sale_line_id:
                ligne.fma_sale_order_id = ligne.fma_sale_line_id.order_id

    @api.model_create_multi
    def create(self, vals_list):
        lignes = super().create(vals_list)
        if not self.env.context.get("fma_rattachement_auto"):
            lignes._fma_rattacher_commande()
        return lignes

    def write(self, vals):
        res = super().write(vals)
        if (DECLENCHEURS_LIGNE & set(vals)
                and not self.env.context.get("fma_rattachement_auto")):
            self._fma_rattacher_commande()
        return res

    def _fma_commandes_fortes(self):
        """Commandes que la ligne sert, par un lien materiel (etapes 1 a 4)."""
        self.ensure_one()
        Commande = self.env["sale.order"]
        champs = self._fields

        # 1. Le lot.
        if "lot_fabrication_id" in champs and self.lot_fabrication_id:
            commandes = self.lot_fabrication_id.sale_order_ids
            if commandes:
                return commandes

        # 2. La chaine : reception -> collecte des composants -> composant
        #    d'OF, ou reception -> livraison. On descend sans presumer du
        #    nombre d'etapes de l'entrepot.
        Move = self.env["stock.move"]
        moves = Move
        if "move_dest_ids" in champs:
            moves |= self.move_dest_ids
        if "move_ids" in champs:
            moves |= self.move_ids.move_dest_ids
        vus = set()
        for _niveau in range(self.FMA_PROFONDEUR_CHAINE):
            moves = moves.filtered(lambda m: m.id not in vus)
            if not moves:
                break
            vus |= set(moves.ids)
            commandes = Commande
            if "sale_line_id" in Move._fields:
                commandes |= moves.sale_line_id.order_id
            ordres = moves.raw_material_production_id
            commandes |= commandes_des_of(ordres)
            if commandes:
                return commandes
            moves = moves.move_dest_ids | ordres.move_finished_ids.move_dest_ids

        # 2 bis. La sous-traitance commandee pour un OF (laquage).
        if "laquage_production_id" in champs and self.laquage_production_id:
            commandes = commandes_des_of(self.laquage_production_id)
            if commandes:
                return commandes

        # 3. La ligne de vente native.
        if "sale_line_id" in champs and self.sale_line_id:
            return self.sale_line_id.order_id

        # 4. L'origine du bon. Comparaison par JETON entier : « A26-01 » ne
        #    doit pas reconnaitre « A26-01/2 », la tranche suivante.
        jetons = [j for j in ORIGINE_SEPARATEURS.split(self.order_id.origin or "")
                  if len(j) > 1]
        if jetons:
            societe = self.order_id.company_id.id
            commandes = Commande.search(
                [("name", "in", jetons), ("company_id", "=", societe)])
            if not commandes:
                ordres = self.env["mrp.production"].search(
                    [("name", "in", jetons), ("company_id", "=", societe)])
                commandes = commandes_des_of(ordres)
            if not commandes and "fma.lot.fabrication" in self.env:
                lots = self.env["fma.lot.fabrication"].search(
                    [("name", "in", jetons), ("company_id", "=", societe)])
                commandes = lots.sale_order_ids
            if commandes:
                return commandes
        return Commande

    def _fma_rattacher_commande(self):
        """Pose la commande client sur les lignes qui n'en ont pas.

        Ne remplace jamais une valeur presente. Rejouee a la creation, a
        certaines ecritures, et par le calcul du prix de revient — c'est lui
        qui rattrape les achats nes avant ce champ.
        """
        Commande = self.env["sale.order"]
        lignes = self.sudo().with_context(
            fma_rattachement_auto=True, skip_studio_sync=True)
        par_projet = {}
        for ligne in lignes:
            if ligne.display_type or not ligne.product_id:
                continue
            if ligne.fma_sale_line_id:
                if ligne.fma_sale_order_id != ligne.fma_sale_line_id.order_id:
                    ligne.fma_sale_order_id = ligne.fma_sale_line_id.order_id
                continue
            if ligne.fma_sale_order_id:
                continue
            commandes = ligne._fma_commandes_fortes()
            if not commandes:
                # 5. L'en-tete.
                commandes = ligne.order_id.fma_sale_order_id
            if not commandes:
                # 6. Le projet a une seule commande confirmee.
                projet = ligne.order_id.x_studio_projet_du_so
                if projet:
                    if projet.id not in par_projet:
                        par_projet[projet.id] = Commande.search(
                            [("state", "in", ("sale", "done"))]
                            + Commande._fma_domaine_projet(projet))
                    commandes = par_projet[projet.id]
            if len(commandes) == 1:
                ligne.fma_sale_order_id = commandes.id

        # L'en-tete suit quand toutes les lignes s'accordent.
        for achat in lignes.order_id:
            if achat.fma_sale_order_id:
                continue
            articles = achat.order_line.filtered(
                lambda l: not l.display_type and l.product_id)
            commandes = articles.fma_sale_order_id
            if (articles and len(commandes) == 1
                    and all(l.fma_sale_order_id for l in articles)):
                achat.fma_sale_order_id = commandes.id
        return True
