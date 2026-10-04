# -*- coding: utf-8 -*-
"""Etiquette, scan et SAV sur un lot de deux menuiseries.

Le lot est monte a la main — une commande, une ligne de lot, un ordre
d'assemblage de 2 — puis scinde par la methode du lot elle-meme
(_scinder_assemblages_par_serie) : c'est elle qui pose un ordre et un
numero de serie par menuiserie, et c'est ce resultat que tout le module
suppose.
"""
from odoo import Command
from odoo.tests import Form, HttpCase, TransactionCase, tagged


class EtiquetteScanCommon:

    @classmethod
    def _fma_preparer(cls):
        env = cls.env
        cls.entrepot = env["stock.warehouse"].search(
            [("company_id", "=", env.company.id)], limit=1)
        cls.client = env["res.partner"].create({"name": "Menuiserie Dupont"})
        Produit = env["product.product"]
        cls.menuiserie = Produit.create({
            "name": "Fenêtre 2 vantaux",
            "default_code": "A26-00-00099_E-MEXT-C1",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
        })
        if "x_studio_largeur_mm" in Produit._fields:
            cls.menuiserie.write({
                "x_studio_largeur_mm": 1200, "x_studio_hauteur_mm": 2150})
        cls.poignee = Produit.create({
            "name": "Poignée", "default_code": "POIGNEE",
            "type": "consu", "is_storable": True,
        })
        env["stock.quant"]._update_available_quantity(
            cls.poignee, cls.entrepot.lot_stock_id, 100)
        cls.poste = env["mrp.workcenter"].create({"name": "Assemblage"})
        cls.nomenclature = env["mrp.bom"].create({
            "product_tmpl_id": cls.menuiserie.product_tmpl_id.id,
            "product_qty": 1,
            "bom_line_ids": [Command.create({
                "product_id": cls.poignee.id, "product_qty": 2})],
            "operation_ids": [
                Command.create({
                    "name": "Assemblage", "workcenter_id": cls.poste.id,
                    "time_cycle_manual": 30, "sequence": 1}),
                Command.create({
                    "name": "Vitrage", "workcenter_id": cls.poste.id,
                    "time_cycle_manual": 20, "sequence": 2}),
            ],
        })
        cls.commande = env["sale.order"].create({
            "partner_id": cls.client.id,
            "order_line": [Command.create({
                "product_id": cls.menuiserie.id, "product_uom_qty": 2})],
        })
        cls.lot = env["fma.lot.fabrication"].create({
            "line_ids": [Command.create({
                "sale_line_id": cls.commande.order_line.id,
                "product_qty": 2})],
        })
        ordre = env["mrp.production"].create({
            "product_id": cls.menuiserie.id,
            "product_qty": 2,
            "bom_id": cls.nomenclature.id,
            "lot_fabrication_id": cls.lot.id,
            "lot_line_id": cls.lot.line_ids.id,
            "lot_sale_line_id": cls.commande.order_line.id,
            "lot_production_type": "assemblage",
        })
        ordre.action_confirm()
        cls.lot._scinder_assemblages_par_serie()
        cls.lot.invalidate_recordset()
        cls.ordres = cls.lot.production_ids.filtered(
            lambda p: p.lot_production_type == "assemblage"
            and p.state != "cancel").sorted("id")
        cls.ordre1, cls.ordre2 = cls.ordres
        cls.serie1 = cls.ordre1.lot_producing_ids
        cls.serie2 = cls.ordre2.lot_producing_ids

    def _poste(self, mode="declarer", auto="aucune", lot=None):
        formulaire = Form(self.env["fma.poste.scan"].with_context(
            default_mode=mode, default_action_auto=auto,
            default_lot_fabrication_id=lot.id if lot else False))
        return formulaire


@tagged("post_install", "-at_install")
class TestEtiquetteScan(EtiquetteScanCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._fma_preparer()

    # --- Le socle : un ordre et un numero par menuiserie ------------------
    def test_00_un_ordre_par_menuiserie(self):
        self.assertEqual(len(self.ordres), 2)
        self.assertEqual(self.ordres.mapped("product_qty"), [1.0, 1.0])
        self.assertEqual(
            self.serie1.name, "A26-00-00099_E-MEXT-C1-001")
        self.assertEqual(
            self.serie2.name, "A26-00-00099_E-MEXT-C1-002")
        self.assertEqual(self.serie1.fma_production_id, self.ordre1)
        self.assertEqual(self.serie1.fma_lot_fabrication_id, self.lot)
        self.assertEqual(self.serie1.fma_sale_order_id, self.commande)
        self.assertEqual(self.serie1.fma_partner_id, self.client)
        self.assertEqual(self.serie1.fma_repere, "E-MEXT-C1")
        self.assertEqual(self.serie1.fma_casier, "001")
        self.assertTrue(self.serie1.fma_est_menuiserie)
        self.assertIn(self.serie1, self.env["stock.lot"].search(
            [("fma_est_menuiserie", "=", True)]))

    # --- Etiquettes -------------------------------------------------------
    def test_10_etiquettes_du_lot(self):
        action = self.lot.action_fma_imprimer_etiquettes()
        self.assertEqual(
            action["report_name"], "fma_etiquette_scan.report_etiquette_of")
        etiquettes = self.ordres._fma_etiquettes()
        self.assertEqual(
            [e["serie"] for e in etiquettes],
            [self.serie1.name, self.serie2.name])
        premiere = etiquettes[0]
        self.assertTrue(premiere["barcode_src"].startswith(
            "data:image/png;base64,"))
        self.assertTrue(premiere["qr_src"].startswith(
            "data:image/png;base64,"))
        self.assertIn("/fma/sav/%s" % self.serie1.fma_sav_token,
                      premiere["sav_url"])
        self.assertEqual(len(self.serie1.fma_sav_token), 32)
        self.assertNotEqual(
            self.serie1.fma_sav_token, self.serie2.fma_sav_token)

        html = self.env["ir.actions.report"]._render_qweb_html(
            "fma_etiquette_scan.report_etiquette_of", self.ordres.ids
        )[0].decode()
        for attendu in (self.serie1.name, self.serie2.name,
                        "Menuiserie Dupont", self.commande.name,
                        "E-MEXT-C1", "Casier n°", self.ordre1.name):
            self.assertIn(attendu, html)
        self.assertEqual(html.count("page-break-after"), 2)

    def test_11_etiquette_de_la_serie(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "fma_etiquette_scan.report_etiquette_serie", self.serie2.ids
        )[0].decode()
        self.assertIn(self.serie2.name, html)
        self.assertNotIn(self.serie1.name, html)

    # --- Lecture du code --------------------------------------------------
    def test_20_trouver(self):
        Serie = self.env["stock.lot"]
        self.assertEqual(
            Serie._fma_trouver(self.serie1.name), (self.serie1, self.ordre1))
        self.assertEqual(
            Serie._fma_trouver(" %s \n" % self.serie1.name)[0], self.serie1)
        # Le QR code de l'etiquette : le lien SAV.
        self.assertEqual(
            Serie._fma_trouver(self.serie2._fma_url_sav()),
            (self.serie2, self.ordre2))
        # Le numero de l'ordre.
        self.assertEqual(
            Serie._fma_trouver(self.ordre2.name), (self.serie2, self.ordre2))
        # Douchette QWERTY sur un poste AZERTY :
        # A26-00-00099_E-MEXT-C1-001 est « tape » ainsi.
        from ..models.stock_lot import _AZERTY_VERS_QWERTY
        frappe = {chr(tape): imprime
                  for tape, imprime in _AZERTY_VERS_QWERTY.items()}
        aller = {imprime: tape for tape, imprime in frappe.items()}
        tape = "".join(aller.get(c, c) for c in self.serie1.name)
        self.assertNotEqual(tape, self.serie1.name)
        self.assertEqual(Serie._fma_trouver(tape)[0], self.serie1)
        self.assertFalse(Serie._fma_trouver("INCONNU")[0])

    # --- Declaration ------------------------------------------------------
    def test_30_scan_puis_bouton_terminer(self):
        formulaire = self._poste(lot=self.lot)
        formulaire.code = self.serie1.name
        self.assertFalse(formulaire.code)
        self.assertEqual(formulaire.serial_id, self.serie1)
        self.assertEqual(formulaire.production_id, self.ordre1)
        self.assertEqual(formulaire.dernier_type, "info")
        # Lecture seule : un scan sans action automatique ne declare rien.
        self.assertNotEqual(self.ordre1.state, "done")
        poste = formulaire.save()
        poste.action_terminer()

        self.assertEqual(poste.dernier_type, "success", poste.dernier_message)
        self.assertEqual(self.ordre1.state, "done")
        self.assertEqual(self.ordre1.lot_producing_ids, self.serie1)
        self.assertEqual(
            set(self.ordre1.workorder_ids.mapped("state")), {"done"})
        # Les operations jamais chronometrees prennent leur duree prevue.
        self.assertEqual(
            self.ordre1.workorder_ids.mapped("duration"), [30.0, 20.0])
        # La menuiserie est en stock, sous SON numero.
        stock = self.env["stock.quant"].search([
            ("lot_id", "=", self.serie1.id),
            ("location_id.usage", "=", "internal")])
        self.assertEqual(sum(stock.mapped("quantity")), 1.0)
        # Aucun reliquat : l'autre menuiserie a deja son ordre.
        self.assertEqual(self.lot._fma_assemblages(), self.ordres)
        self.assertNotEqual(self.ordre2.state, "done")
        # Avancement du lot.
        self.assertEqual(self.lot.fma_unites_terminees, 1)
        self.assertEqual(self.lot.fma_unites_total, 2)
        self.assertEqual(self.lot.fma_avancement, 50.0)
        self.assertEqual(poste.avancement, 50.0)
        self.assertIn("1 / 2", poste.avancement_texte)

    def test_31_scan_automatique(self):
        formulaire = self._poste(auto="terminer")
        formulaire.code = self.serie1.name
        self.assertEqual(formulaire.dernier_type, "success",
                         formulaire.dernier_message)
        self.assertEqual(self.ordre1.state, "done")
        self.assertEqual(formulaire.lot_fabrication_id, self.lot)
        formulaire.code = self.serie2.name
        self.assertEqual(self.ordre2.state, "done")
        self.assertEqual(formulaire.avancement, 100.0)
        # Rescanner une menuiserie terminee ne casse rien.
        formulaire.code = self.serie2.name
        self.assertEqual(formulaire.dernier_type, "info")

    def test_32_pointage_operation(self):
        formulaire = self._poste(auto="operation")
        assemblage, vitrage = self.ordre1.workorder_ids.sorted("sequence")
        formulaire.code = self.serie1.name
        self.assertEqual(assemblage.state, "progress")
        self.assertEqual(formulaire.dernier_type, "success",
                         formulaire.dernier_message)
        formulaire.code = self.serie1.name
        self.assertEqual(assemblage.state, "done")
        self.assertNotEqual(vitrage.state, "done")
        formulaire.code = self.serie1.name
        self.assertEqual(vitrage.state, "progress")
        formulaire.code = self.serie1.name
        self.assertEqual(vitrage.state, "done")
        formulaire.code = self.serie1.name
        self.assertEqual(formulaire.dernier_type, "info")
        self.assertNotEqual(self.ordre1.state, "done")

    def test_33_refus_odoo_sans_plantage(self):
        """Un composant suivi par lot, sans lot en stock : Odoo refuse la
        cloture. Le poste l'affiche et l'ordre en garde la trace."""
        joint = self.env["product.product"].create({
            "name": "Joint suivi", "type": "consu", "is_storable": True,
            "tracking": "lot",
        })
        self.ordre2.write({"move_raw_ids": [Command.create({
            "product_id": joint.id, "product_uom_qty": 1,
            "product_uom": joint.uom_id.id})]})
        avant = len(self.ordre2.message_ids)
        formulaire = self._poste(auto="terminer")
        formulaire.code = self.serie2.name
        self.assertEqual(formulaire.dernier_type, "danger",
                         formulaire.dernier_message)
        self.assertNotEqual(self.ordre2.state, "done")
        # Rien n'est reste a moitie fait.
        self.assertNotIn("done", self.ordre2.workorder_ids.mapped("state"))
        self.assertGreater(len(self.ordre2.message_ids), avant)
        self.assertIn("refusé", self.ordre2.message_ids[0].body)

    def test_34_code_inconnu(self):
        formulaire = self._poste()
        formulaire.code = "N-EXISTE-PAS"
        self.assertEqual(formulaire.dernier_type, "danger")
        self.assertFalse(formulaire.serial_id)

    # --- Localisation -----------------------------------------------------
    def test_40_localiser_et_ranger(self):
        formulaire = self._poste(mode="localiser")
        formulaire.code = self.serie1.name
        self.assertEqual(formulaire.dernier_type, "info")
        self.assertIn(self.serie1.name, formulaire.dernier_message)
        formulaire.casier_emplacement = "Travée B"
        poste = formulaire.save()
        poste.action_ranger()
        self.assertEqual(self.serie1.fma_casier_emplacement, "Travée B")
        self.assertIn("Assemblage", self.serie1.fma_historique)

    # --- SAV --------------------------------------------------------------
    def test_50_ticket_sav(self):
        ticket = self.serie1._fma_creer_ticket("Vitrage fêlé", "Angle bas")
        self.assertEqual(ticket.fma_serial_id, self.serie1)
        self.assertEqual(ticket.fma_production_id, self.ordre1)
        self.assertEqual(ticket.fma_lot_fabrication_id, self.lot)
        self.assertEqual(ticket.fma_sale_order_id, self.commande)
        self.assertEqual(ticket.fma_product_id, self.menuiserie)
        self.assertIn(self.serie1.name, ticket.name)
        self.assertIn("Angle bas", ticket.description)
        self.assertIn(self.commande.name, ticket.description)
        self.serie1.invalidate_recordset()
        self.assertEqual(self.serie1.fma_ticket_count, 1)
        self.assertEqual(self.serie2.fma_ticket_count, 0)
        self.assertIn("Ticket SAV", self.serie1.fma_historique)

        formulaire = self._poste(mode="sav")
        formulaire.code = self.serie1.name
        self.assertEqual(formulaire.dernier_type, "warning")
        self.assertEqual(formulaire.ticket_count, 1)
        poste = formulaire.save()
        action = poste.action_creer_ticket()
        self.assertEqual(action["res_model"], "helpdesk.ticket")
        self.assertEqual(
            action["context"]["default_fma_serial_id"], self.serie1.id)
        self.assertEqual(
            action["context"]["default_partner_id"], self.client.id)
        self.assertEqual(
            poste.action_voir_tickets()["domain"],
            [("fma_serial_id", "=", self.serie1.id)])


@tagged("post_install", "-at_install")
class TestSavPage(EtiquetteScanCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._fma_preparer()
        cls.serie1._fma_assurer_jeton()

    def _jeton_csrf(self, page):
        import re
        return re.search(
            r'name="csrf_token" value="([^"]+)"', page).group(1)

    def test_page_publique_et_declaration(self):
        url = "/fma/sav/%s" % self.serie1.fma_sav_token
        reponse = self.url_open(url)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn(self.serie1.name, reponse.text)
        # Sans connexion : ni client ni commande.
        self.assertNotIn("Menuiserie Dupont", reponse.text)
        self.assertNotIn(self.commande.name, reponse.text)

        reponse = self.url_open(url + "/declarer", data={
            "csrf_token": self._jeton_csrf(reponse.text),
            "objet": "Poignée cassée",
            "description": "La poignée tourne dans le vide.",
            "nom": "Jean Poseur",
            "email": "jean@example.com",
            "telephone": "0600000000",
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Demande enregistrée", reponse.text)
        ticket = self.env["helpdesk.ticket"].search(
            [("fma_serial_id", "=", self.serie1.id)])
        self.assertEqual(len(ticket), 1)
        self.assertIn("Poignée cassée", ticket.name)
        self.assertIn("Jean Poseur", ticket.description)
        self.assertEqual(ticket.fma_production_id, self.ordre1)

    def test_formulaire_incomplet(self):
        url = "/fma/sav/%s" % self.serie1.fma_sav_token
        reponse = self.url_open(url)
        reponse = self.url_open(url + "/declarer", data={
            "csrf_token": self._jeton_csrf(reponse.text),
            "description": "Sans coordonnées",
        })
        self.assertIn("laissez votre nom", reponse.text)
        self.assertFalse(self.env["helpdesk.ticket"].search(
            [("fma_serial_id", "=", self.serie1.id)]))

    def test_jeton_inconnu(self):
        reponse = self.url_open("/fma/sav/%s" % ("0" * 32))
        self.assertEqual(reponse.status_code, 404)

    def test_acces_public_ferme(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "fma_etiquette_scan.sav_public", "0")
        reponse = self.url_open(
            "/fma/sav/%s" % self.serie1.fma_sav_token, allow_redirects=False)
        self.assertEqual(reponse.status_code, 303)
        self.assertIn("/web/login", reponse.headers["Location"])

    def test_page_interne(self):
        self.authenticate("admin", "admin")
        reponse = self.url_open("/fma/sav/%s" % self.serie1.fma_sav_token)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Menuiserie Dupont", reponse.text)
        self.assertIn(self.commande.name, reponse.text)
