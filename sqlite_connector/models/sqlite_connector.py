
import sqlite3
import logging
import math
import tempfile
import base64
import re
import psycopg2

from odoo.exceptions import UserError
from odoo import models, fields, registry, SUPERUSER_ID, api, _
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class SqliteConnector(models.Model):
    _name = 'sqlite.connector'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'SQLite Connector'
    _rec_name = 'description'

    description = fields.Char(string='Description')
    date = fields.Date(string='Date', default=fields.Date.context_today)
    state = fields.Selection([('new', 'New'), ('done', 'Exported'), ('error', 'Errors')], string='Status', readonly=True, default='new')
    file = fields.Binary(string='SQLite file')

    def export_data_from_db(self):
        articles = []
        profiles = []
    
        articlesm = []
        articles_data = []
        po_vals = []
        po_article_vals = []
        po_profile_vals = []
        po_glass_vals = []
        so_data = {}
        nomenclatures_data = []
        operations_data = []
        articleslibre = []
        messages = []

        product_products = self.env['product.product'].search([])
        product_categories = self.env['product.category'].search([])
        uom_uoms = self.env['uom.uom'].search([])
        stock_picking_type = self.env['stock.picking.type'].search([])
        stock_warehouse = self.env['stock.warehouse'].search([])
        account_analytic_tags = self.env['account.analytic.tag'].search([])
        account_analytics = self.env['account.analytic.account'].search([])
        mrp_workstations = self.env['mrp.workcenter'].search([])
        res_partners = self.env['res.partner'].search([])
        product_templates = self.env['product.template'].search([])
        res_users = self.env['res.users'].search([])

        temp_file = tempfile.NamedTemporaryFile('wb', suffix='.sqlite', prefix='edi.mx.tmp.')
        temp_file.write(base64.b64decode(self.file))
        con = sqlite3.connect(str(temp_file.name))
        cursor = con.cursor()
        cursor1 = con.cursor()
        date_time = datetime.now()

        article_data = cursor.execute("select ArticleCode, Price, PUSize, Units_Unit from Articles")
        for row in article_data:
            articles.append({
                'item': row[0],
                'price': row[1],
                'unit': row[2],
                'condi': row[3]
            })

        profile_data = cursor.execute("select ArticleCode, Price from Profiles")
        for row in profile_data:
            profiles.append({
                'article': row[0],
                'prix': row[1]
            })

        # To check if product already exists in odoo from articles
        for article in articles:
            product = product_products.filtered(lambda p: p.default_code == article['item'] and round(float(article['price']), 4) != float(p.standard_price))
            if product:
                product.standard_price = article['price']
                refs = ["<a href=# data-oe-model=product.product data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in product.name_get()]
                message = _("Standard Price is updated for product: %s") % ','.join(refs)
                messages.append(message)

        # To check if product already exists in odoo from articles
        for profile in profiles:
            product = product_products.filtered(lambda p: p.default_code == profile['article'] and round(float(profile['prix']), 4) != float(p.standard_price))
            if product:
                product.standard_price = profile['prix']
                refs = ["<a href=# data-oe-model=product.product data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in product.name_get()]
                message = _("Standard Price is updated for product: %s") % ','.join(refs)
                messages.append(message)

        # At FMA, they have a concept of tranches, that is to say that the project is divided into
        # several phases (they call it tranches). So I come to see if it is a project with installments or
        # not and I come to get the installment number

        Tranche = '0'
        PersonBE = ''
        project = ''

        resultp = cursor.execute("select Projects.Name, Projects.OfferNo, PersonInCharge from Projects")

        for row in resultp :
            project = row[1]
            pro = project.split('/')
            nbelem = len(pro)
            PersonBE = row[2]
            if nbelem == 1 :
                projet = row[1]
            else:
                projet = project.split('/')[0]
                Tranche = project.split('/')[1]
            proj = ['', projet]
        user_id = res_users.filtered(lambda p: p.name == re.sub(' +', ' ', PersonBE.strip()))
        if user_id:
            user_id = user_id.id
        else:
            user_id = False
            self.log_request("Unable to find user Id.", PersonBE, 'Project Data')

        account_analytic_id = account_analytics.filtered(lambda a: a.name in projet)
        if account_analytic_id:
            account_analytic_id = account_analytic_id[0].id
        else:
            account_analytic_id = False
            self.log_request("Unable to find analytic account.", projet, 'Project Data')

        # In a parameter of the MDB database, I retrieve information which will allow me to give
        # the manufacturing address, the manufacturing time and the customer delivery time for
        # each item.
        address = ''

        resultBP=cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultBP :
          if (row[0] == 'UserVars') and (row[1] == 'UserInteger2') :
            if (row[2] == '0')  :
                address = 'LRE'
            if (row[2] == '1') :
                address = 'CBM'
            if (row[2] == '2') :
                address = 'REM'
          if (row[0] == 'UserVars') and (row[1] == 'UserFloat1') :
                delaifab = float(row[2])
          if (row[0] == 'UserVars') and (row[1] == 'UserDate2') :
            date_time = row[2]
            def convert(date_time):
                if date_time:
                    format = '%d/%m/%Y'  # The format
                    datetime_str = datetime.strptime(date_time, format).strftime('%Y-%m-%d')
                    return datetime_str
                return datetime.now()
            dateliv = convert(date_time)

        # Depending on the parameters of the MDB database, I create commercial and analytical labels.
        resultp=cursor.execute("select Projects.Name, Projects.OfferNo from Projects")
        etiana = ''
        for row in resultp :
            project = row[1]
            pro = project.split('/')
            nbelem = len(pro)
            if nbelem == 1 :
                if (address == 'LRE') or (address == 'CBM' ) :
                    etiana = 'ALU'
                    eticom = 'FMA'
                else :
                    etiana = 'ACI'
                    eticom = 'F2M'
            else :
                if (address == 'LRE') or (address == 'CBM' ) :
                    projet = project.split('/')[0]
                    etiana = 'ALU Tranche ' + project.split('/')[1]
                    eticom = 'FMA'
                else :
                  projet = project.split('/')[0]
                  etiana = 'ACIER Tranche ' + project.split('/')[1]
                  eticom = 'F2M'
                project = project

        account_analytic_tag_id = account_analytic_tags.filtered(lambda t: t.name == etiana)
        if account_analytic_tag_id:
            account_analytic_tag_id = account_analytic_tag_id.id
        else:
            account_analytic_tag_id = False
            self.log_request("Unable to find analytic account.", etiana, 'Projects Data')

        # We come to create the item which is sold

        # We recover in a parameter the type of case which is a concept from FMA. We have either
        # BPA, or BPE, or BPA-BPE. This parameter is very important because if you are in BPA, we will
        # only create purchase orders and not bills of materials.

        BP = ''
        resultBP = cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultBP :
            if (row[0] == 'UserVars') and (row[1] == 'UserInteger1') :
                if (row[2] == '1')  :
                    BP = 'BPA'
                if (row[2] == '3') :
                    BP = 'BPE'
                if (row[2] == '2') :
                    BP = 'BPA-BPE'

        # If we are not in BPA, we come and create the items that we will put in the customer quote.
        # This we put in the articlesm.xlsx files

        # Now we will handle 2 cases over here as BPA and non BPA

        if BP != 'BPA':
            cpt = 0
            elevID = ''
            cat = ''
            resultsm = cursor.execute("select Elevations.ElevationID, Elevations.Name, Elevations.Model, Elevations.Autodescription, Elevations.Height_Output, Elevations.Width_Output, Projects.OfferNo, ReportOfferTexts.TotalPrice, Elevations.Description,Elevations.Model from Elevations INNER JOIN ElevationGroups ON Elevations.ElevationGroupID = ElevationGroups.ElevationGroupID INNER JOIN Phases ON Phases.PhaseID = ElevationGroups.PhaseId INNER JOIN Projects ON Projects.ProjectID = Phases.ProjectId INNER JOIN ReportOfferTexts ON ReportOfferTexts.ElevationId = Elevations.ElevationId order by Elevations.ElevationID")

            # To get the product category as Elevations.Name will be categ_id
            for row in resultsm:
                if row[3] != 'Position texte' :
                    cpt = cpt + 1
                    Index = str(cpt)
                    refart = row[8]
                    categorie = row[2]
                refint =  row[1] + '_' + projet
                idrefart = ''
                
                categ = product_categories.filtered(lambda c: c.x_studio_logical_map == categorie)
                if not categ:
                    self.log_request("Unable to find product category.", categorie, 'Elevations data')
                articlesm.append({
                    "name": refart,
                    "default_code": refint,
                    "list_price": 0,
                    "standard_price": row[7],
                    'categ_id': categ.id if categ else self.env.ref('product.product_category_all').id,
                    "uom_id": self.env.ref('uom.product_uom_unit').id,
                    "uom_po_id": self.env.ref('uom.product_uom_unit').id,
                    "type": "consu",
                    "purchase_ok": "no",
                    "sale_ok": "yes",
                    'produce_delay': 0
                })

        # To handle if BPA
        # We also create a final item which will be sold and on which we will put the nomenclature
        resultp = cursor.execute("select Projects.Name, Projects.OfferNo from Projects")

        for row in resultp:
            refart = row[1]
            if BP == 'BPA':
                refart = refart + '_BPA'
                refart = refart.strip()
                idrefart = ''
                # categ = product_categories.filtered(lambda c: c.name == 'ALL')
                categ = self.env.ref('product.product_category_all')

                articlesm.append({
                    "name": refart,
                    "default_code": refart,
                    "list_price": 0,
                    "standard_price": 0,
                    'categ_id': categ.id,
                    "uom_id": self.env.ref('uom.product_uom_unit').id,
                    "uom_po_id": self.env.ref('uom.product_uom_unit').id,
                    "type": "product",
                    "purchase_ok": "no",
                    "sale_ok": "yes",
                    "route_ids": [(4, self.env.ref('stock.route_warehouse0_mto').id), (4, self.env.ref('mrp.route_warehouse0_manufacture').id)],
                    'produce_delay': delaifab
                })

        # We come to find the address for supplier deliveries
        entrepot = ''
        stock_picking_type_id = False
        if 'ALU' in etiana:
            if address == 'LRE':
                entrepot = 'LA REGRIPPIERE: Réceptions'
            else:
                entrepot = 'LA CHAPELLE B/M FMA: Réceptions'
        else:
            entrepot = 'LA REMAUDIERE: Réceptions'

        warehouse, operation = entrepot.split(":")
        warehouse = stock_warehouse.filtered(lambda w: w.name == warehouse)
        if warehouse:
            stock_picking_type_id = stock_picking_type.filtered(lambda p: p.name == operation.strip() and p.warehouse_id.id == warehouse.id)
            if stock_picking_type_id:
                stock_picking_type_id = stock_picking_type_id.id
            else:
                self.log_request("Unable to find stock picking type.", operation.strip(), 'Project Data')
        else:
            self.log_request("Unable to find warehouse.", warehouse, 'Project Data')
        # Now to collect final data of articles

        idun =''
        idfrs = ''
        ida = ''
        tache = 0
        LstArt = ''
        data22 = []
        data23 = []
        LstFrs = ''
        Qte = 0
        UV = 0
        prix = 0

        resart = cursor1.execute("select AllArticles.ArticleCode, AllArticles.ArticleCode_Supplier, AllArticles.Units_Unit, AllArticles.Description, AllArticles.Color, AllArticles.Price, AllArticles.Units, AllArticles.PUSize, AllArticles.IsManual,AllArticles.ArticleCode_BaseNumber, AllArticles.ColorInfoInternal, AllArticles.ArticleCode_Number from AllArticles order by AllArticles.ArticleCode_Supplier")

        for row in resart :
            refart = row[0]
            refartini = row[0]
            unit = row[2]
            prix = 0
            nom = row[3]
            fournisseur= row[1]
            fournisseur = fournisseur.upper()

            if fournisseur == 'TECHNAL' :
                refart = 'TEC' + ' ' + row[9]
            if fournisseur == 'WICONA' :
                refart = 'WIC' + ' ' + row[11][1:]
            if fournisseur == 'SAPA' :
                refart = refart.replace("RC  ","SAP ")
            if fournisseur == 'Jansen' :
                refart = 'JAN' + ' ' + row[9]
            if fournisseur == 'RP-Technik' :
                refart = 'RP' + ' ' + row[9]
            if fournisseur == 'Forster' :
                refart = 'FRS' + ' ' + row[9]
                refart = refart.remplace ('.','')

            UV = row[7]
            data22 = []
            SaisieManuelle = row[8]
            trouve = 1
            tache = 0
            regle = 0
            condi = ''
            consoaff = ''
            datejourd = fields.Date.today()
            # to get price
            for article in articles:
                if row[0] == article['item']:
                    prix = article['price']

            if fournisseur != 'HUD' :
                refart = refart.replace("RYN","REY")
                refart = refart.replace("SC  ","SCH ")

                uom = uom_uoms.filtered(lambda u: u.x_studio_uom_logical == unit)
                if uom:
                    unit = uom.name
                # Need to ask

                couleur = str(row[10])
                if couleur == '' :
                    couleur = str(row[4])
                if couleur == 'Sans' or couleur == 'sans' :
                    couleur = ''
                if couleur != '':
                    refart = refart + '.' + couleur

                for product in product_products.filtered(lambda p: p.default_code == refart):
                    refartodoo = product.default_code
                    delai = product.produce_delay
                    if delai == None :
                        delay = 1
                    consoaff = product.x_studio_conso_laffaire
                    if refartodoo == refart:
                        trouve = 0
                        if product.orderpoint_ids:
                            regle = 1
                        if (regle == 0) or ((regle == 1) and (consoaff == True)) :
                            idfrs = ''
                            unnom = product.uom_id
                            idun = product.uom_id.id
                            resultat = res_partners.filtered(lambda p: p.x_studio_ref_logikal == fournisseur)
                            if resultat:
                                idfrs = resultat[0].id
                            else:
                                self.log_request("Unable to find customer (x_studio_ref_logikal).", fournisseur, 'Articles Data')
                            # If the article is already in ODOO (in the article is in the BaseArticle.xlsx file) we look if it has
                            # a replenishment rule or if the article has the boolean “consumer on the deal”. IF so, we will
                            # create a purchase order for this item.
                            if idfrs == '':
                                ida = refart.replace(" ","_")
                                if ida == '' :
                                    ida = unnom.replace(" ", "_")
                                    refart = unnom
                                attached = 1
                                if LstArt == '':
                                    LstArt = refart
                                else :
                                    LstArt = LstArt + ',' + refart
                            else :
                                if LstFrs != idfrs :
                                    LstFrs = idfrs
                                    data22 = ['', projet, idfrs, stock_picking_type_id, '', datetime.now(), user_id]

                                    product_id = product_products.filtered(lambda p: p.default_code == 'affaire')
                                    if not product_id:
                                        self.log_request("Unable to find product.", 'affaire', 'Articles Data')
                                    acc = account_analytics.filtered(lambda a: a.name == projet)
                                    account_analytic_id = acc[0].id if acc else False
                                    x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                    if idfrs and stock_picking_type_id and product_id:
                                        po_article_vals.append({
                                            'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                            'partner_id': idfrs,
                                            'picking_type_id': stock_picking_type_id,
                                            'x_studio_commentaire_livraison_vitrage_': "",
                                            'date_order': datetime.now(),
                                            'user_id': user_id,
                                            'order_line': [(0, 0, {
                                                    'product_id': product_id[0].id if product_id else False,
                                                    'account_analytic_id': account_analytic_id,
                                                    'date_planned': datetime.now(),
                                                    'price_unit': 0,
                                                    'product_qty': 1,
                                                    'product_uom': product_id.uom_id.id,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': datejourd,
                                                })],                       
                                            })
                                        data22 = ['','','','','','','']
                                else :
                                    data22 = ['','','','','','','']
                                QteStk = 0
                                Qte = float(row[6])
                                if (QteStk < 0) or (consoaff == True) :
                                    Qte = (float(row[6])) / float(UV) if UV else float(row[6])
                                    x = Qte
                                    n = 0
                                    resultat = math.ceil(x * 10**n)/ 10**n
                                    Qte = (resultat * float(UV))
                                    art = refart
                                    ida = refart.replace(" ","_")
                                    projet = projet.strip()
                                    delai = int(delai)
                                    dateliv = datejourd + timedelta(days=delai)

                                    product_id = product_products.filtered(lambda p: p.default_code == art)
                                    x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                    if not product_id:
                                        self.log_request('Unable to find product.', art, 'Articles Data')
                                    for po in po_article_vals:
                                        if po.get('partner_id') == idfrs and product_id:
                                            po.get('order_line').append((0, 0, {
                                                'product_id': product_id[0].id if product_id else False,
                                                'name': product_id[0].name,
                                                'date_planned': datetime.now(),
                                                'x_studio_posit': "",
                                                'price_unit': prix,
                                                'product_qty': Qte,
                                                'product_uom': product_id.uom_id.id,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': dateliv,
                                            }))
                                else :
                                    if QteStk < Qte :
                                        Qte = (float(row[6]) - QteStk)
                                        Qte = (float(row[6]) - QteStk) / float(UV) if UV else Qte
                                        x = Qte
                                        n = 0
                                        resultat = math.ceil(x * 10**n)/ 10**n
                                        Qte = (resultat * float(UV))
                                        art = refart
                                        ida = refart.replace(" ","_")
                                        projet = projet.strip()
                                        delai = int(delai)
                                        dateliv = datejourd + timedelta(days=delai)

                                        product_id = product_products.filtered(lambda p: p.default_code == art)
                                        if not product_id:
                                            self.log_request('Unable to find product.', art, 'Articles Data')
                                        x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                        for po in po_article_vals:
                                            if po.get('partner_id') == idfrs and product_id:
                                                po.get('order_line').append((0, 0, {
                                                        'product_id': product_id[0].id if product_id else False,
                                                        'date_planned': datetime.now(),
                                                        'price_unit': prix,
                                                        'product_qty': Qte,
                                                        'product_uom': product_id.uom_id.id,
                                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                        'date_planned': dateliv,
                                                    }))
                if trouve == 1:
                    idfrs = ''
                    # we are looking for the ID of UnMe
                    uom = uom_uoms.filtered(lambda u: u.name == unit)
                    if uom:
                        unnom = uom.name
                        idun = uom.id
                    resultat = res_partners.filtered(lambda p: p.x_studio_ref_logikal and p.x_studio_ref_logikal.upper() == fournisseur)
                    if resultat:
                        idfrs = resultat[0].id
                    else:
                        self.log_request('Unable to find customer (x_studio_ref_logikal)', fournisseur, 'Articles Data')
                    if idfrs == '':
                        ida = refart.replace(" ","_")
                        if ida == '' :
                            ida = nom.replace(" ", "_")
                            refart = nom
                        tache = 1
                        if LstArt == '':
                            LstArt = refart
                        else :
                            LstArt = LstArt + ',' + refart
                        # categ_id = product_categories.filtered(lambda c: c.name == 'All / Accessoire') 
                        categ_id = self.env.ref('__export__.product_category_14_a5d33274')

                        articleslibre.append({
                            "default_code": refart,
                            "name": nom,
                            "lst_price": 10,
                            "standard_price": prix,
                            "uom_id": idun if idun else self.env.ref('uom.product_uom_unit').id,
                            "categ_id": categ_id.id,
                            "purchase_ok": "yes",
                            "sale_ok": "yes",
                            "detailed_type": "product",
                            "uom_po_id": idun if idun else self.env.ref('uom.product_uom_unit').id,
                            "route_ids": [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id)],
                            })
                    else :
                        if LstFrs != idfrs :
                            data22 = ['',projet, idfrs, stock_picking_type_id,'', datetime.now(),user_id]
                            acc = account_analytics.filtered(lambda a: a.name == projet)
                            if acc:
                                account_analytic_id = acc[0].id
                            else:
                                account_analytic_id = False
                                self.log('Unable to find analytic account.', projet)
                            product_id = product_products.filtered(lambda p: p.default_code == 'affaire')
                            x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                            if not product_id:
                                self.log_request('Unable to find Product.', 'affaire', 'Articles Data')
                            if idfrs and stock_picking_type_id and product_id:
                                po_article_vals.append({
                                    'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                    'partner_id': idfrs,
                                    'picking_type_id': stock_picking_type_id,
                                    'date_order': datetime.now(),
                                    'user_id': user_id,
                                    'order_line':[(0, 0,
                                        {
                                            'product_id': product_id[0].id,
                                            'account_analytic_id': account_analytic_id,
                                            'date_planned': datetime.now(),
                                            'price_unit': 0,
                                            'product_qty': 1,
                                            'product_uom': product_id.uom_id.id,
                                            'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                            'date_planned': datejourd,
                                        })]                        
                                    })
                                data22 = ['','','','','','','']
                                LstFrs = idfrs
                        else :
                            data22 = ['','','','','','','']
                        Qte = float(row[6]) / float(UV) if UV else float(row[6])
                        x = Qte
                        n = 0
                        resultat = math.ceil(x * 10**n)/ 10**n
                        Qte = (resultat * float(UV))
                        art = refart
                        ida = refart.replace(" ","_")
                        projet = projet.strip()
                        prixV = float(prix) * 1.5
                        delai = 14
                        dateliv = datejourd + timedelta(days=delai)
                        categ_id = self.env.ref('__export__.product_category_14_a5d33274')
                        
                        articles_data.append({
                            'default_code': art,
                            'name': nom,
                            'lst_price': prixV,
                            'standard_price': prix,
                            'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'categ_id': categ_id.id,
                            'seller_ids': [
                                (0, 0, {
                                    'name': idfrs,
                                    'delay': 56,
                                    'product_name': nom,
                                    'price': prix,
                                    'min_qty': 1,
                                    'product_code': art
                            })],
                            'purchase_ok': 'yes',
                            'sale_ok': 'yes',
                            'detailed_type': 'product',
                            'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id)],
                        })
                        pro = product_products.filtered(lambda pro: pro.default_code == art)
                        x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                        if not pro:
                            self.log_request('Unable to find product.', pro, 'Articles Data')
                        for po in po_article_vals:
                            if po.get('partner_id') == idfrs and pro:
                                po.get('order_line').append((0, 0, {
                                        'product_id': pro[0].id if pro else False,
                                        'date_planned': datetime.now(),
                                        'price_unit': prix,
                                        'product_qty': Qte,
                                        'product_uom': pro.uom_id.id,
                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                        'date_planned': dateliv,
                                    }))

        # Process data for profile
        resultBP = cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        BP = ''

        for row in resultBP:
            if (row[0] == 'UserVars') and (row[1] == 'UserInteger1') :
                if (row[2] == '1')  :
                    BP = 'BPA'
                if (row[2] == '3') :
                    BP = 'BPE'
                if (row[2] == '2') :
                    BP = 'BPA-BPE'

        if BP == 'BPA' or BP == 'BPE':
            resultpf = cursor.execute("select AllProfiles.ArticleCode, AllProfiles.Description, AllProfiles.ArticleCode_Supplier, AllProfiles.Description, AllProfiles.Color, AllProfiles.Price, AllProfiles.Units, AllProfiles.Amount, AllProfiles.IsManual, AllProfiles.OuterColorInfoInternal, AllProfiles.InnerColorInfoInternal, AllProfiles.ColorInfoInternal, AllProfiles.ArticleCode_BaseNumber, AllProfiles.ArticleCode_Number  from AllProfiles order by AllProfiles.ArticleCode_Supplier")
            idun =''
            idfrs = ''
            UV = 0
            LstFrs = ''

            for row in resultpf:
                refart = row[0]
                refartini = row[0]
                name = row[1]
                unit = str(row[6])
                unita = ''
                prixB = float(0)
                nom = row[3]
                IsManual = row[8]
                fournisseur = row[2]
                fournisseur = fournisseur.upper()
                if fournisseur == 'TECHNAL' :
                    refart = 'TEC' + ' ' + row[12]
                if fournisseur == 'WICONA' :
                    refart = 'WIC' + ' ' + row[13][1:]
                if fournisseur == 'SAPA' :
                    refart = refart.replace("RC  ","SAP ")
                if fournisseur == 'Jansen' :
                    refart = 'JAN' + ' ' + row[9]
                if fournisseur == 'RP-Technik' :
                    refart = 'RP' + ' ' + row[9]
                if fournisseur == 'Forster' :
                    refart = 'FRS' + ' ' + row[9]
                    refart = refart.replace('.','')
                couleurext = str(row[9])
                couleurint = str(row[10])

                if couleurext != '' and couleurint != '' :
                    couleur = couleurext + '/' + couleurint
                else :
                    couleur = str(row[11])
                    if couleur == '' or couleur == ' ' :
                        couleur = str(row[4])
                        if couleur == 'Sans' or couleur == 'sans':
                            couleur = ''
                for profile in profiles:
                    if row[0] == profile['article']:
                        prix = profile['prix']
                        prixB = float(prix) * float(row[6])
                refart = refart.replace("RYN","REY")
                refart = refart.replace("SC  ","SCH ")
                if couleur != '' :
                    refart = refart + '.' + couleur
                    refartfic = ''

                product_product = product_products.filtered(lambda p: p.default_code == refart)   
                unme = product_product.uom_id if product_product.uom_id else ""
                unit = unme.name if product_product.uom_id else ""

                unitcor = ''
              
                # Need to ask
                # for W in range(2,row_count7) :
                #     unitcor = sheet7.cell(row=W,column=1).value
                #     unitcor = str(unitcor)
                #     unitcor = unitcor.replace('.0','')
                #     #print ('unitcor ' , unitcor)
                #     #print ('unit ', unit)
                # if unit == unitcor :
                #     #print ('dans le if des unités')
                #     unit = sheet7.cell(row=W,column=2).value

                trouve = 1
                tache = 0
                regle = 0

                for product in product_products.filtered(lambda p: p.default_code == refart):
                    data2 = product.default_code
                    delai = product.seller_ids[0].delay if product.seller_ids else 1
                    delai = product.produce_delay
                    trouve = 0
                    order_point = self.env['stock.warehouse.orderpoint'].search([('name', 'ilike', refart)], limit=1)
                    if order_point:
                        regle =  1
                    if regle == 0:
                        unnom = product.uom_id
                        idun = product.uom_id.id

                    # Now we are looking for supplier ID
                    iduna = ''
                    unita ='ML'

                    uom = uom_uoms.filtered(lambda u: u.name == unita)
                    if uom:
                        iduna = uom.id

                    resultat = res_partners.filtered(lambda p: p.x_studio_ref_logikal and p.x_studio_ref_logikal.upper() == fournisseur)
                    if resultat:
                        idfrs = resultat[0].id
                    else:
                        self.log_request('Unable to find customer (x_studio_ref_logikal)', fournisseur, 'Articles Data')

                    # Now we come to create profiles
                    QteStk =  0
                    # Need to ask
                    # for n in range (2,row_count15+1):
                    #     refstk = '[' + str(sheet15.cell(row=n,column=1).value) + ']'
                    # if refart in refstk :
                    #     QteStk = float(sheet15.cell(row=n,column=4).value)
                    Qte = float(row[7])
                    if (QteStk <= 0):
                        Qte = float(Qte)
                        if LstFrs != idfrs :
                            LstFrs = idfrs
                            projet = projet.strip()
                            data22 = ['', projet, idfrs, stock_picking_type_id, '', datetime.now(), user_id]

                            pro = product_products.filtered(lambda p: p.default_code == 'affaire')
                            x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                            if idfrs and stock_picking_type_id and pro:
                                po_profile_vals.append({
                                    'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                    'partner_id': idfrs,
                                    'picking_type_id': stock_picking_type_id,
                                    'date_order': datetime.now(),
                                    'user_id': user_id,
                                    'order_line': [(0, 0,
                                        {
                                            'product_id': pro[0].id if pro else False,
                                            'account_analytic_id': account_analytic_id,
                                            # 'date_planned': datetime.now(),
                                            'price_unit': 0,
                                            'product_qty': 1,
                                            'product_uom': pro.uom_id.id,
                                            'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                            'date_planned': datejourd,
                                        })]
                                    })
                                data22 = ['','','','','','','']
                        else:
                            data22 = ['','','','','','','']

                        id = refart.replace(" ","_")
                        idcolor = couleur.replace(" ","_")
                        art = data2
                        projet = projet.strip()
                        delai = int(delai)
                        dateliv = datejourd + timedelta(days=delai)
                        part = res_partners.filtered(lambda p: p.name == data22[2])
                        pro = product_products.filtered(lambda p: p.default_code == art)
                        x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                        if not pro:
                            self.log_request('Unable to find product (default_code)', art, 'Articles Data')
                        for po in po_profile_vals:
                            if po.get('partner_id') == idfrs and pro:
                                po.get('order_line').append((0, 0, {
                                        'product_id': pro[0].id if pro else False,
                                        # 'date_planned': datetime.now(),
                                        'price_unit': prixB,
                                        'product_qty': Qte,
                                        'product_uom': pro.uom_id.id,
                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                        'date_planned': dateliv,
                                    }))
                    else:
                        if (QteStk < Qte) :
                            Qte = float(Qte) - QteStk
                            if LstFrs != idfrs :
                                LstFrs = idfrs
                                projet = projet.strip()
                                data22 = ['',projet,idfrs,stock_picking_type_id,'',datetime.now(),user_id]
                                pro = product_products.filtered(lambda p: p.default_code == 'affaire')
                                if not pro:
                                    self.log_request('Unable to find product (default_code)', 'affaire', 'Articles Data')
                                x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                if idfrs and stock_picking_type_id and pro:
                                    po_profile_vals.append({
                                        'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                        'partner_id': idfrs,
                                        'picking_type_id': stock_picking_type_id,
                                        'x_studio_commentaire_livraison_vitrage_': "",
                                        'date_order': datetime.now(),
                                        'user_id': user_id,
                                        'order_line': [(0, 0, {
                                                'product_id': pro[0].id if pro else False,
                                                'account_analytic_id': account_analytic_id,
                                                # 'date_planned': datetime.now(),
                                                'price_unit': 0,
                                                'product_qty': 1,
                                                'product_uom': pro.uom_id.id,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': datejourd,
                                            })]
                                        })
                                    data22 = ['','','','','','','']
                        else :
                            data22 = ['','','','','','','']
                        idcolor = couleur.replace(" ","_")
                        art = data2
                        projet = projet.strip()
                        dateliv = datejourd + timedelta(days=delai)
                        
                        part = res_partners.filtered(lambda p: p.name == data22[2])
                        prod = product_products.filtered(lambda pro: pro.default_code == art)
                        x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                        for po in po_profile_vals:
                            if po.get('partner_id') == idfrs and prod:
                                po.get('order_line').append((0, 0, {
                                        'product_id': prod[0].id if prod else False,
                                        # 'date_planned': datetime.now(),
                                        'price_unit': prixB,
                                        'product_qty': Qte,
                                        'product_uom': prod.uom_id.id,
                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                        'date_planned': dateliv,
                                    }))
                if trouve == 1 :
                    if IsManual == 'True' :
                        refart = row[1]
                        tache = 1
                        if LstArt == '':
                            LstArt = refart
                        else :
                            LstArt = LstArt + ',' + refart

                        uom = uom_uoms.filtered(lambda u: u.x_studio_uom_logical == unit)
                        if uom:
                            idun = uom.id

                        unita = 'ML'
                        uom = uom_uoms.filtered(lambda u: u.name == unita)
                        if uom:
                            iduna = uom.id
                        prixV = prixB * 1.5

                        data1 = ['',refart,refart, prixV ,prixB, idun, 'All / Profile','yes', 'yes', 'Product', idun, 'purchase_stock.route_warehouse0_buy,purchase_stock.route_warehouse0_buy', '0', '0']
                        # categ_id = product_categories.filtered(lambda c: c.name == 'All / Profile')
                        categ_id =  self.env.ref('__export__.product_category_19_b8423373')  

                        articleslibre.append({
                            "default_code": refart,
                            "name": refart,
                            "lst_price": prixV,
                            "standard_price": prixB,
                            "uom_id": idun if idun else self.env.ref('uom.product_uom_unit').id,
                            "categ_id": categ_id.id,
                            "purchase_ok": "yes",
                            "sale_ok": "yes",
                            "detailed_type": "product",
                            "uom_po_id": idun if idun else self.env.ref('uom.product_uom_unit').id,
                            "route_ids": [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id), (4, self.env.ref('purchase_stock.route_warehouse0_buy').id)],
                        })
                    else:
                        unita = 'ML'
                        uom = uom_uoms.filtered(lambda u: u.name == unita)
                        if uom:
                            iduna = uom.id

                        resultat = res_partners.filtered(lambda p: p.x_studio_ref_logikal and p.x_studio_ref_logikal.upper() == fournisseur)
                        if resultat:
                            idfrs = resultat[0].id
                        else:
                            self.log_request('Unabe to find customer (x_studio_ref_logikal)', fournisseur, 'Article Data')

                        art = refart
                        Qte = row[7]
                        prixV = prixB * 1.5
                        data10 = [art, nom, prixV ,prixB, idun, 'All / Profile', '56', idfrs, nom, prixB, '1', art, 'yes', 'yes', 'Product', idun, 'purchase_stock.route_warehouse0_buy,purchase_stock.route_warehouse0_buy', '0','0','']
                        # categ_id = product_categories.filtered(lambda c: c.name == 'All / Profile')
                        categ_id =  self.env.ref('__export__.product_category_19_b8423373') 
                        articles_data.append({
                            'default_code': art,
                            'name': nom,
                            'lst_price': prixV,
                            'standard_price': prixB,
                            'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'categ_id': categ_id.id,
                            'seller_ids': [(0, 0, {
                                'delay': 56,
                                'name': idfrs if idfrs else 1,
                                'product_name': nom,
                                'price': prixB,
                                'min_qty': 1,
                                'product_code': art
                                })
                            ],
                            'purchase_ok': 'yes',
                            'sale_ok': 'yes',
                            'detailed_type': 'product',
                            'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id), (4, self.env.ref('purchase_stock.route_warehouse0_buy').id)],
                            'x_studio_hauteur_mm': 0,
                            'x_studio_largeur_mm': 0,
                            # 'x_studio_positionn': ''
                        })
                        if LstFrs != idfrs :
                            LstFrs = idfrs
                            projet = projet.strip()
                            data22 = ['',projet,idfrs,stock_picking_type_id,'',datetime.now(),user_id]
                            pro = product_products.filtered(lambda p: p.default_code == 'affaire')
                            if not pro:
                                self.log_request('Unable to find product', 'affaire', 'Article Data')
                            x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                            if idfrs and stock_picking_type_id and pro:
                                po_profile_vals.append({
                                    'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                    'partner_id': idfrs,
                                    'picking_type_id': stock_picking_type_id,
                                    'x_studio_commentaire_livraison_vitrage_': "",
                                    'date_order': datetime.now(),
                                    'user_id': user_id,
                                    'order_line': [(0, 0, {
                                            'product_id': pro[0].id,
                                            'account_analytic_id': account_analytic_id,
                                            'date_planned': datetime.now(),
                                            'price_unit': 0,
                                            'product_qty': 1,
                                            'product_uom': pro.uom_id.id,
                                            'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                            'date_planned': datejourd,
                                        })]
                                    })
                                data22 = ['','','','','','','']
                        else :
                            data22 = ['','','','','','','']
                            delai = 35
                            dateliv = datejourd + timedelta(days=delai)
                            
                        part = res_partners.filtered(lambda p: p.name == data22[2])
                        pro = product_products.filtered(lambda p: p.default_code == art)
                        x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                        if not pro:
                            self.log_request('Unable to find product', art, 'Article Data')
                        for po in po_profile_vals and pro:
                            if po.get('partner_id') == idfrs:
                                po.get('order_line').append((0, 0, {
                                        'product_id': pro[0].id,
                                        'date_planned': datetime.now(),
                                        'price_unit': prixB,
                                        'product_qty': Qte,
                                        'product_uom': pro.uom_id.id,
                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                        'date_planned': dateliv,
                                    }))
        # To process glass data
        BP = ''
        resultBP=cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultBP :
            if (row[0] == 'UserVars') and (row[1] == 'UserInteger1') :
                if (row[2] == '1')  :
                    BP = 'BPA'
            if (row[2] == '3') :
                BP = 'BPE'
            if (row[2] == '2') :
                BP = 'BPA-BPE'

        if BP != 'BPA':
            datagnum=[]
            proj = ''
            if Tranche != '0' :
                proj = projet + '/' + str(Tranche)
            else :
                proj = projet


            resultg = cursor.execute("select Glass.Info1, Glass.NameShort, Glass.Origin, Glass.Price, Glass.Width_Output, Glass.Height_Output,Glass.InsertionId, Glass.Info2,Glass.FieldNo,Elevations.Name, Elevations.Amount, Insertions.InsertionID, Insertions.ElevationId from (Glass INNER JOIN Insertions ON Insertions.InsertionID = Glass.InsertionId) LEFT JOIN Elevations ON Elevations.ElevationID = Insertions.ElevationId order by Glass.Info2, Elevations.Name ,Glass.FieldNo")
            nbr = 0

            for row in resultg:
                nbr = nbr + 1

            resultg = cursor.execute("select Glass.Info1, Glass.NameShort, Glass.Origin, Glass.Price, Glass.Width_Output, Glass.Height_Output,Glass.InsertionId, Glass.Info2,Glass.FieldNo,Elevations.Name, Elevations.Amount, Insertions.InsertionID, Insertions.ElevationId, Glass.AreaOffer, Glass.SpacerGap_Output,Glass.Name,Glass.GlassID,Glass.LK_SupplierId from (Glass INNER JOIN Insertions ON Insertions.InsertionID = Glass.InsertionId) LEFT JOIN Elevations ON Elevations.ElevationID = Insertions.ElevationId order by Glass.Info2, Elevations.Name ,Glass.FieldNo, Glass.LK_SupplierId")

            cpt1 = 0
            PosNew = ''
            Qte = 0
            LstInfo2 = ''
            LstFrs = ''
            idfrs = ''
            refinterne= ''
            Frsid = ''
            name = ''
            frsnomf = ''

            for row in resultg:
                Info2 = row[7]
                cpt1 = cpt1 + 1
                unnomf = 'Piece'
                spacer = row[14]
                nomvit = row[15]
                Frsid = row[17]
                Qte = float(row[10])
                largNum = float(row[4])
                HautNum = float(row[5])
                largNum = round(largNum)
                HautNum = round(HautNum)

                res_partner = res_partners.filtered(lambda p: p.x_studio_lk_supplier_id_1 == int(Frsid))
                if res_partner:
                    frsnomf = res_partner[0].name
                else:
                    self.log_request('Unable to find customer with LK Supplier ID', str(Frsid), 'Glass Data')
                delay =  14

                if row[13] != 'Glass':
                    Info2 = ''
                    spacer = ''
                    delai = 21
                    trouve = '1'
                if (row[9] == None) :
                    name = 'X'
                else :
                    name = str(row[9])
                Posint = name + ' / ' + row[8]
                refart = row[1]
                if nomvit != 'Sans vitrage' :
                    if PosNew == Posint :
                        if (row[10] == None) :
                            qtech = '1'
                        else :
                            qtech = str(row[10])
                        Qte = Qte + float(qtech)
                        if cpt1 == nbr :
                            if LstFrs != idfrs :
                                LstFrs = idfrs
                                LstInfo2 = Info2
                                projet = projet.strip()
                                
                                pro = product_products.filtered(lambda p: p.default_code == 'affaire')
                                x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                if not pro:
                                    self.log_request('Unable to find product.', 'affaire', 'Glass Data')
                                if idfrs and stock_picking_type_id and pro:
                                    po_glass_vals.append({
                                        'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                        'partner_id': idfrs,
                                        'picking_type_id': stock_picking_type_id,
                                        'x_studio_commentaire_livraison_vitrage_': Info2,
                                        'date_order': datetime.now(),
                                        'user_id': user_id,
                                        'order_line':
                                            [(0, 0, {
                                                'product_id': pro[0].id if pro else False,
                                                'account_analytic_id': account_analytic_id,
                                                'date_planned': datetime.now(),
                                                'price_unit': 0,
                                                'product_qty': 1,
                                                'product_uom': pro.uom_id.id,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': datejourd,
                                            })]
                                        })
                                    data22 = ['','','','','','','']
                            else :
                                if LstInfo2 != Info2:
                                    LstInfo2 = Info2
                                    data22 = ['',projet,idfrs,stock_picking_type_id,Info2,datetime.now(),user_id]
                                else:
                                    if cpt1 != 2 :
                                        data22 = ['','','','','','','']
                                    else :
                                        data22 = ['',projet,idfrs,stock_picking_type_id,Info2,datetime.now(),user_id]

                            dateliv = datejourd + timedelta(days=delai)
                            part = res_partners.filtered(lambda p: p.name == data22[2])
                            pro = product_products.filtered(lambda p: p.default_code == refinterne)
                            if not pro:
                                self.log_request('Unable to find product.', refinterne, 'Glass Data')
                            x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                            if part:
                                if pro:
                                    po_glass_vals.append({
                                        'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                        'partner_id': idfrs,
                                        'picking_type_id': stock_picking_type_id,
                                        'x_studio_commentaire_livraison_vitrage_': Info2,
                                        'date_order': datetime.now(),
                                        'user_id': user_id,
                                        'order_line':
                                            [(0, 0, {
                                                'product_id': pro[0].id,
                                                'date_planned': datetime.now(),
                                                'x_studio_posit': Posint,
                                                'price_unit': prix,
                                                'product_qty': Qte,
                                                'product_uom': pro.uom_id.id,
                                                'x_studio_hauteur': HautNum,
                                                'x_studio_largeur': largNum,
                                                'x_studio_spacer': spacer,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': dateliv,
                                            })]
                                        })
                            else:
                                for po in po_glass_vals:
                                    if po.get('partner_id') == idfrs and po.get('x_studio_commentaire_livraison_vitrage_') == Info2 and pro:
                                        po.get('order_line').append((0, 0, {
                                                'product_id': pro[0].id,
                                                'date_planned': datetime.now(),
                                                'x_studio_posit': Posint,
                                                'price_unit': prix,
                                                'product_qty': Qte,
                                                'product_uom': pro.uom_id.id,
                                                'x_studio_hauteur': HautNum,
                                                'x_studio_largeur': largNum,
                                                'x_studio_spacer': spacer,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': dateliv,
                                            }))
                    else:
                        if PosNew != '':
                            uom = uom_uoms.filtered(lambda u: u.name == unnomf)
                            if uom:
                                idun = uom.id
                            part = res_partners.filtered(lambda p: p.name == frsnomf)

                            if part:
                                idfrs = part[0].id if part else ''
                            else:
                                self.log_request('Unable to find customer with name', frsnomf, 'Glass Data')
                            if cpt1 != nbr:
                                dateliv = datejourd + timedelta(days=delai)
                                part = res_partners.filtered(lambda p: p.id == data22[2])
                                prod = product_products.filtered(lambda pro: pro.default_code == refinterne)
                                if not prod:
                                    self.log_request('Unable to find product', refinterne, 'Glass Data')
                                x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                                if stock_picking_type_id and prod:
                                    if part:
                                        po_glass_vals.append({
                                            'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                            'partner_id': part.id,
                                            'picking_type_id': stock_picking_type_id,
                                            'x_studio_commentaire_livraison_vitrage_': data22[4],
                                            'date_order': datetime.now(),
                                            'user_id': user_id,
                                            'order_line':
                                                [(0, 0, {
                                                    'product_id': prod[0].id if prod else False,
                                                    'date_planned': datetime.now(),
                                                    'x_studio_posit': Posint,
                                                    'price_unit': prix,
                                                    'product_qty': Qte,
                                                    'product_uom': prod.uom_id.id,
                                                    'x_studio_hauteur': HautNum,
                                                    'x_studio_largeur': largNum,
                                                    'x_studio_spacer': spacer,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': dateliv,
                                                })]
                                            })
                                    else:
                                        for po in po_glass_vals:
                                            if po.get('partner_id') == idfrs:
                                                po.get('order_line').append((0, 0, {
                                                    'product_id': prod[0].id if prod else False,
                                                    'date_planned': datetime.now(),
                                                    'x_studio_posit': Posint,
                                                    'price_unit': prix,
                                                    'product_qty': Qte,
                                                    'product_uom': prod.uom_id.id,
                                                    'x_studio_hauteur': HautNum,
                                                    'x_studio_largeur': largNum,
                                                    'x_studio_spacer': spacer,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': dateliv,
                                                }))
                                if LstFrs != idfrs :
                                    LstFrs = idfrs
                                    LstInfo2 = Info2
                                    projet = projet.strip()
                                    prod = product_products.filtered(lambda pro: pro.default_code == 'affaire')
                                    x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                    if idfrs and stock_picking_type_id and prod:
                                        po_glass_vals.append({
                                            'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                            'partner_id': idfrs,
                                            'picking_type_id': stock_picking_type_id,
                                            'x_studio_commentaire_livraison_vitrage_': Info2,
                                            'date_order': datetime.now(),
                                            'user_id': user_id,
                                            'order_line':
                                                [(0, 0, {
                                                    'product_id': prod[0].id if prod else False,
                                                    'account_analytic_id': account_analytic_id,
                                                    # 'date_planned': datetime.now(),
                                                    'price_unit': 0,
                                                    'product_qty': 1,
                                                    'product_uom': prod.uom_id.id,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': datejourd,
                                                })]
                                            })
                                        data22 = ['','','','','','','']
                                else :
                                    if LstInfo2 != Info2:
                                        LstInfo2 = Info2
                                        data22 = ['',projet,idfrs,stock_picking_type_id,Info2,datetime.now(),user_id]
                                    else:
                                        data22 = ['','','','','','','']

                                prix = row[3]
                                projet = projet.strip()
                                refinterne = proj + '_' + str(cpt1)

                            if cpt1 == nbr:
                                dateliv = datejourd + timedelta(days=delai)
                                part = res_partners.filtered(lambda p: p.id == data22[2])
                                prod = product_products.filtered(lambda p: p.default_code == refinterne)
                                x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                                if stock_picking_type_id and prod:
                                    if part:
                                        po_glass_vals.append({
                                            'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                            'partner_id': idfrs,
                                            'picking_type_id': stock_picking_type_id,
                                            'x_studio_commentaire_livraison_vitrage_': Info2,
                                            'date_order': datetime.now(),
                                            'user_id': user_id,
                                            'order_line':
                                                [(0, 0, {
                                                    'product_id': prod[0].id if prod else False,
                                                    'date_planned': datetime.now(),
                                                    'x_studio_posit': PosNew,
                                                    'price_unit': prix,
                                                    'product_qty': Qte,
                                                    'product_uom': prod.uom_id.id,
                                                    'x_studio_hauteur': HautNum,
                                                    'x_studio_largeur': largNum,
                                                    'x_studio_spacer': spacer,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': dateliv,
                                                })]
                                            })
                                    else:
                                        for po in po_glass_vals:
                                            if po.get('partner_id') == idfrs:
                                                po.get('order_line').append((0, 0, {
                                                        'product_id': prod[0].id if prod else False,
                                                        'date_planned': datetime.now(),
                                                        'x_studio_posit': PosNew,
                                                        'price_unit': prix,
                                                        'product_qty': Qte,
                                                        'product_uom': prod.uom_id.id,
                                                        'x_studio_hauteur': HautNum,
                                                        'x_studio_largeur': largNum,
                                                        'x_studio_spacer': spacer,
                                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                        'date_planned': dateliv,
                                                    }))

                                prix = row[3]
                                Qte = float(row[10])
                                refinterne = proj + '_' + str(cpt1)
                                projet = projet.strip()

                                if LstFrs != idfrs :
                                    LstFrs = idfrs
                                    LstInfo2 = Info2
                                    projet = projet.strip()
                                    data22 = ['',projet,idfrs,entrepot,Info2,datetime.now(),PersonBE]
                                    
                                    prod = product_products.filtered(lambda p: p.default_code == 'affaire',)
                                    x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                    if idfrs and stock_picking_type_id and prod:
                                        po_glass_vals.append({
                                            'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                            'partner_id': idfrs,
                                            'picking_type_id': stock_picking_type_id,
                                            'x_studio_commentaire_livraison_vitrage_': Info2,
                                            'date_order': datetime.now(),
                                            'user_id': user_id,
                                            'order_line':
                                                [(0, 0, {
                                                    'product_id': prod[0].id if prod else False,
                                                    'account_analytic_id': account_analytic_id,
                                                    'date_planned': datetime.now(),
                                                    'price_unit': 0,
                                                    'product_qty': 1,
                                                    'product_uom': prod.uom_id.id,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': datejourd,
                                                })]
                                            })
                                        data22 = ['','','','','','','']
                                else :
                                    if LstInfo2 != Info2:
                                        LstInfo2 = Info2
                                        data22 = ['',account_analytic_id,idfrs,stock_picking_type_id,Info2,datetime.now(),user_id]
                                        # createion of article in order to link to the project
                                        # part = res_partners.filtered(lambda p: p.id == data22[2])
                                        prod = product_products.filtered(lambda p: p.default_code == 'affaire')
                                        x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                                        if idfrs and stock_picking_type_id and prod:
                                            po_glass_vals.append({
                                                'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                                'partner_id': idfrs,
                                                'picking_type_id': stock_picking_type_id,
                                                'x_studio_commentaire_livraison_vitrage_': data22[4],
                                                'date_order': datetime.now(),
                                                'user_id': user_id,
                                                'order_line':
                                                    [(0, 0, {
                                                        'product_id': prod[0].id if prod else False,
                                                        'account_analytic_id': account_analytic_id,
                                                        'price_unit': 0,
                                                        'product_qty': 1,
                                                        'product_uom': prod.uom_id.id,
                                                        'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                        'date_planned': datejourd,
                                                    })]
                                                })
                                            data22 = ['','','','','','','']
                                    else:
                                        data22 = ['','','','','','','']
                                dateliv = datejourd + timedelta(days=delai)
                                part = res_partners.filtered(lambda p: p.id == data22[2])
                                prod = product_product.filtered(lambda p: p.default_code == refinterne)
                                x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                                for po in po_glass_vals:
                                    if po.get('partner_id') == idfrs and prod:
                                        po.get('order_line').append((0, 0, {
                                                'product_id': prod[0].id if prod else False,
                                                'date_planned': datetime.now(),
                                                'x_studio_posit': Posint,
                                                'price_unit': prix,
                                                'product_qty': Qte,
                                                'product_uom': prod.uom_id.id,
                                                'x_studio_hauteur': HautNum,
                                                'x_studio_largeur': largNum,
                                                'x_studio_spacer': spacer,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': dateliv,
                                            }))
                                
                            prix = row[3]
                            if (row[10] == None):
                                qtech = '1'
                            else:
                                qtech = str(row[10])
                            Qte = float(qtech)
                            largNum = float(row[4])
                            HautNum = float(row[5])
                            largNum = round(largNum)
                            HautNum = round(HautNum)
                            refinterne = proj + '_' + str(cpt1)
                            idrefvit = refinterne.replace(" ","_")

                            # categ_id = product_categories.filtered(lambda c: c.name == 'All / Vitrage')
                            categ_id = self.env.ref('__export__.product_category_23_31345211').id

                            articles_data.append({
                                'default_code': refinterne,
                                'name': refart,
                                'lst_price': 1,
                                'standard_price': prix,
                                'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                                'categ_id': categ_id,
                                'seller_ids': [(0, 0, {
                                    'delay': 3,
                                    'name': idfrs if idfrs else 1,
                                    'product_name': row[1],
                                    'price': prix,
                                    'min_qty': 1,
                                    'product_code': row[0],
                                })],
                                'purchase_ok': 'yes',
                                'sale_ok': 'yes',
                                'detailed_type': 'product',
                                'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                                'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id)],
                                'x_studio_hauteur_mm': HautNum,
                                'x_studio_largeur_mm': largNum,
                                # 'x_studio_positionn': Posint,
                            })
                        else:
                            prix = row[3]
                            PosNew = Posint
                            largNum = float(row[4])
                            HautNum = float(row[5])
                            largNum = round(largNum)
                            HautNum = round(HautNum)

                            if (row[10] == None ) :
                                qtech = '1'
                            else :
                                qtech = str(row[10])

                            Qte = float(qtech)
                            refinterne = proj + '_' + str(cpt1)
                            idrefvit = refinterne.replace(" ","_")

                            uom_uom = uom_uoms.filtered(lambda u: u.name == unnomf)
                            if uom_uom:
                                idun = uom_uom.id
                            res_partner = res_partners.filtered(lambda p: p.name == frsnomf)
                            if res_partner:
                                idfrs = res_partner.id

                            # categ_id = product_categories.filtered(lambda c: c.name == 'All / Vitrage')
                            categ_id = self.env.ref('__export__.product_category_23_31345211').id
                            articles_data.append({
                                'default_code': refinterne,
                                'name': refart,
                                'lst_price': 1,
                                'standard_price': prix,
                                'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                                'categ_id': categ_id,
                                'seller_ids': [(0, 0, {
                                    'delay': 3,
                                    'name': idfrs if idfrs else 1,
                                    'product_name': row[1],
                                    'price': row[3],
                                    'min_qty': 1,
                                    'product_code': row[0],
                                })],
                                'purchase_ok': 'yes',
                                'sale_ok': 'yes',
                                'detailed_type': 'product',
                                'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                                'route_ids': [(4, self.env.ref('purchase_stock.route_warehouse0_buy').id)],
                                'x_studio_hauteur_mm': HautNum,
                                'x_studio_largeur_mm': largNum,
                                # 'x_studio_positionn': Posint,
                            })
                            if LstFrs != idfrs :
                                LstFrs = idfrs
                                LstInfo2 = Info2
                                projet = projet.strip()
                                data22 = ['',projet,idfrs,stock_picking_type_id,Info2,datetime.now(),user_id]
                                
                                prod = product_products.filtered(lambda p: p.default_code == 'affaire')
                                x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                                if idfrs and stock_picking_type_id and prod:
                                    po_glass_vals.append({
                                        'x_studio_many2one_field_LCOZX': x_affaire.id if x_affaire else False,
                                        'partner_id': idfrs,
                                        'picking_type_id': stock_picking_type_id,
                                        'x_studio_commentaire_livraison_vitrage_': Info2,
                                        'date_order': datetime.now(),
                                        'user_id': user_id,
                                        'order_line':
                                            [(0, 0, {
                                                'product_id': prod[0].id if prod else False,
                                                'account_analytic_id': account_analytic_id,
                                                'date_planned': datetime.now(),
                                                'price_unit': 0,
                                                'product_qty': 1,
                                                'product_uom': prod.uom_id.id,
                                                'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                'date_planned': datejourd,
                                            })]
                                        })
                                    data22 = ['','','','','','','']
                            else :
                                if LstInfo2 != Info2:
                                    LstInfo2 = Info2
                                    data22 = ['',projet,idfrs,stock_picking_type_id,Info2,datetime.now(),user_id]
                                else:
                                    data22 = ['','','','','','','']
                                if cpt1 == nbr :
                                    dateliv = datejourd + timedelta(days=delai)
                                    prod = product_products.filtered(lambda p: p.default_code == refinterne)
                                    part = res_partners.filtered(lambda p: p.id == data22[2])
                                    x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', data22[1])], limit=1)
                                    for po in po_glass_vals:
                                    # if part and stock_picking_type_id and prod:
                                        if po.get('partner_id') == idfrs and prod:
                                            po.get('order_line').append((0, 0, {
                                                    'product_id': prod[0].id if prod else False,
                                                    'date_planned': datetime.now(),
                                                    'x_studio_posit': Posint,
                                                    'price_unit': prix,
                                                    'product_qty': Qte,
                                                    'product_uom': prod.uom_id.id,
                                                    'x_studio_hauteur': HautNum,
                                                    'x_studio_largeur': largNum,
                                                    'x_studio_spacer': spacer,
                                                    'analytic_tag_ids': [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                                    'date_planned': dateliv,
                                                }))
                    PosNew = Posint
                    prixint = prix
                    largNumint = largNum
                    HautNumint = HautNum

        # We then create the customer quote with delivery dates and possible discounts.
        # We come to create the quote
        address = ''
        dateliv = date_time
        resultBP=cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultBP :
            if (row[0] == 'UserVars') and (row[1] == 'UserInteger2') :
                if (row[2] == '0')  :
                    address = 'LRE'
                if (row[2] == '1') :
                    address = 'CBM'
                if (row[2] == '2') :
                    address = 'REM'
            if (row[0] == 'UserVars') and (row[1] == 'UserDate2') :
                date_time = row[2]
                def convert(date_time):
                    if date_time:
                        format = '%d/%m/%Y'  # The format
                        datetime_str = datetime.strptime(date_time, format).strftime('%Y-%m-%d')
                        return datetime_str
                    else:
                        return datetime.now()
                dateliv = convert(date_time)

        PourRem = 0
        resultrem=cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultrem:
            if (row[0] == 'Report') and (row[1] == 'QuotationDiscount1') :
                PourRem = row[2]

        resultp = cursor.execute("select Projects.Name, Projects.OfferNo , Address.Address2, Phases.Name, Phases.Info1, Elevations.AutoDescription, Elevations.Amount, Elevations.Height_Output, ReportOfferTexts.TotalPrice, Elevations.Width_Output,Elevations.AutoDescriptionShort, Elevations.Name,  Elevations.Description, Projects.PersonInCharge from Projects LEFT JOIN Address ON Projects.LK_CustomerAddressID = Address.AddressID LEFT JOIN Phases ON Projects.ProjectID = Phases.ProjectID LEFT JOIN ElevationGroups ON Phases.PhaseId = ElevationGroups.PhaseID LEFT JOIN Elevations ON ElevationGroups.ElevationGroupId = Elevations.ElevationID LEFT JOIN ReportOfferTexts ON ReportOfferTexts.ElevationId = Elevations.ElevationId order by Elevations.ElevationID")

        clientID = ''
        PrixTot = 0
        QteTot = 0
        NbrLig = 0
        catergorie = ''
        entrepot = ''

        if 'ALU' in etiana :
            if address == 'LRE' :
                entrepot = '__export__.stock_warehouse_2_c81b1514'
            else :
                entrepot = '__export__.stock_warehouse_3_67750976'
        else :
            entrepot = '__export__.stock_warehouse_4_3dfdcda2'

        if BP != 'BPA' :
            for row in resultp:
                deviseur = row[13]
                NbrLig = NbrLig + 1
                if clientID != row[2] :
                    clientID = row[2]
                    if LstArt != '' :
                        data1 = ['',row[2], row[2],datetime.now(), projet, 'Article à commander', LstArt,'Bon de commande',deviseur,PersonBE,entrepot,eticom,dateliv]
                    else :
                        data1 = ['',row[2], row[2],datetime.now(), projet,'','','',deviseur,PersonBE,entrepot,eticom,dateliv]
                else :
                    data1 =['','','','','','','','','','','','','']
                if ( row[8] == None ) :
                    PrixTot = PrixTot + 0
                else :
                    PrixTot = float(row[8]) + PrixTot
                if ( row[6] == None ) :
                    QteTot = QteTot + 0
                else :
                    QteTot = float(row[6]) + QteTot
                if row[5] == 'Position texte':
                    if row[11] == 'ECO-CONTRIBUTION' :
                        refart = 'ECO-CONTRIBUTION'
                        PourRem = 0
                        dimension = 'ECO-CONTRIBUTION'
                    else :
                        refart = 'Frais de livraison'
                        dimension = 'Frais de livraison'
                else :
                    if (row[9] == None or row[7] == None) :
                        dimension = ''
                    else:
                        dimension = row[9] + 'mm * ' + row[7] + 'mm'
                        refart = '[' + row[11] + '_' + projet + ']' + row[12]
                data2 = [refart, row[8], row[6],dimension,etiana,PourRem]
                part = res_partners.filtered(lambda p: p.name == data1[1])
                part_ship = res_partners.filtered(lambda p: p.name == data1[2])
                if refart == 'ECO-CONTRIBUTION':
                    pro = product_products.filtered(lambda p: p.name == refart or p.default_code == refart)
                else:
                    pro = product_products.filtered(lambda p: "[" + p.default_code + "]" + p.name == refart if p.default_code else p.name == refart)
                warehouse = False
                if data1[10]:
                    warehouse = self.env.ref(data1[10]).id
                sale_order = self.env['sale.order'].search([('name', 'ilike', projet), ('state', 'not in', ['done', 'cancel'])], limit=1)
                    
                ana_acc = self.env['account.analytic.account'].search([('name', 'ilike', projet)], limit=1)
                if sale_order:
                    if so_data.get(sale_order.id, 0) == 0:
                        so_data[sale_order.id] = {
                        "date_order": fields.Date.today(),
                        "analytic_account_id": ana_acc.id if ana_acc else False ,
                        "activity_ids": [(0, 0, {
                            'summary': data1[6],
                            "res_model": 'sale.order',
                            'res_model_id': sale_order.id,
                            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                            'res_model_id': self.env['ir.model']._get_id('sale.order'),
                            'user_id': user_id,
                            'date_deadline': datetime.now(),
                        })],
                        "x_studio_deviseur": data1[8],
                        "x_studio_bureau_etude": data1[9],
                        "tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                        "commitment_date": dateliv,
                        "order_line": [],
                    }
                    if pro:
                        if so_data[sale_order.id] and so_data[sale_order.id].get('order_line'):
                            so_data[sale_order.id].get('order_line').append((0, 0, {
                                'product_id': pro[0].id if pro else False,
                                'price_unit': row[8],
                                'product_uom_qty': row[6],
                                'name': dimension,
                                'discount': PourRem,
                                'product_uom': pro.uom_id.id,
                                "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                }))
                        
                if NbrLig == 1:
                    data1 =['','','','','','','','','','','','','']
                    proj = ''
                    if Tranche != '0' :
                        proj = projet + '/' + str(Tranche)
                    else :
                        proj = projet
                    if BP == 'BPA':
                        proj = proj + '_BPA'
                    data = data1 + [proj,0, 1,proj,etiana,PourRem]
                    part = res_partners.filtered(lambda p: p.name == data1[1])
                    part_ship = res_partners.filtered(lambda p: p.name == data1[2])
                    pro = product_products.filtered(lambda p: "[" + p.default_code + "]" + p.name == refart if p.default_code else p.name == proj)
                    warehouse = False
                    if data1[10]:
                        warehouse = self.env.ref(data1[10]).id
                    sale_order = self.env['sale.order'].search([('name', 'ilike', projet), ('state', 'not in', ['done', 'cancel'])], limit=1)
                    ana_acc = self.env['account.analytic.account'].search([('name', 'ilike', projet)], limit=1)
                    if sale_order:
                        if so_data.get(sale_order.id, 0) == 0:
                            so_data[sale_order.id] = {
                                "date_order": fields.Date.today(),
                                "analytic_account_id": ana_acc.id if ana_acc else False ,
                                "activity_ids": [(0, 0, {
                                    'summary': data1[6],
                                    "res_model": 'sale.order',
                                    'res_model_id': sale_order.id,
                                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                                    'res_model_id': self.env['ir.model']._get_id('sale.order'),
                                    'user_id': user_id,
                                    'date_deadline': datetime.now(),
                                    })],
                                "x_studio_deviseur": data1[8],
                                "x_studio_bureau_etude": data1[9],
                                "tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                "commitment_date": dateliv,
                                "order_line": [],
                            }
                        if pro and so_data[sale_order.id].get('order_line'):
                            so_data[sale_order.id].get('order_line').append((0, 0, {
                                'product_id': pro[0].id if pro else False,
                                'price_unit': row[8],
                                'product_uom_qty': row[6],
                                'name': dimension,
                                'discount': PourRem,
                                'product_uom': pro.uom_id.id,
                                "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                })
                            )
                    else:
                        self.log_request("Unable to find Sale Order", projet, 'Elevations Data')
                        
            else:
                for row in resultp:
                    deviseur = row[13]
                    NbrLig = NbrLig + 1
                    if NbrLig == 1 :
                        clientID = row[2]
                        if LstArt != '' :
                            data1 = ['',row[2], row[2],datetime.now(), projet, 'Article à commander', LstArt,'Bon de commande',deviseur,PersonBE,entrepot,eticom,dateliv]
                        else :
                            data1 = ['',row[2], row[2],datetime.now(), projet,'','','',deviseur,PersonBE,entrepot,eticom,dateliv]
                        proj = ''
                        if Tranche != '0' :
                            proj = projet + '/' + str(Tranche)
                        else :
                            proj = projet
                        if BP == 'BPA':
                            proj = proj + '_BPA'
                        data = data1 + [proj,0, 1,proj,etiana]
                        part = res_partners.filtered(lambda p: p.name == data1[1])
                        part_ship = res_partners.filtered(lambda p: p.name == data1[2])
                        pro = product_products.filtered(lambda p: "[" + p.default_code + "]" + p.name == refart if p.default_code else p.name == proj)

                        warehouse = False
                        
                        if data1[10]:
                            warehouse = self.env.ref(data1[10]).id
                        sale_order = self.env['sale.order'].search([('name', 'ilike', projet), ('state', 'not in', ['done', 'cancel'])], limit=1)
                        ana_acc = self.env['account.analytic.account'].search([('name', 'ilike', projet)], limit=1)
                        if sale_order:
                            if so_data.get(sale_order.id, 0) == 0:
                                so_data.append({
                                    "date_order": fields.Date.today(),
                                    "analytic_account_id": ana_acc.id if ana_acc else False ,
                                    "activity_ids": [(0, 0, {
                                        'summary': data1[6],
                                        "res_model": 'sale.order',
                                        'res_model_id': sale_order.id,
                                        'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id ,
                                        'res_model_id': self.env['ir.model']._get_id('sale.order'),
                                        'user_id': user_id,
                                        'date_deadline': datetime.now(),
                                    })],
                                    "x_studio_deviseur": data1[8],
                                    "x_studio_bureau_etude": data1[9],
                                    "tag_ids": [(6, 0, data1[11])],
                                    "commitment_date": dateliv,
                                    "order_line": [],
                                })
                            if pro and so_data[sale_order.id].get('order_line'):
                                so_data[sale_order.id].get('order_line').append((0, 0, {
                                    'product_id': pro[0].id if pro else False,
                                    'price_unit': row[8],
                                    'product_uom_qty': row[6],
                                    'name': dimension,
                                    'discount': PourRem,
                                    'product_uom': pro.uom_id.id,
                                    "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                    })
                                )
        # Now we will create nomenclatures
        datanom=[]
        cpt = 0
        elevID = ''
        nomenclatures_data = []
        
        resultarticles=cursor.execute("Select ArticleCode, Description, Color, Units_Output, Units_Unit, Units,ArticleCode_Supplier, PUSize, ArticleCode_BaseNumber, ColorInfoInternal, ArticleCode_Number from AllArticles")

        UV = 0
        Cpt = 0
        consoaff = ''
        QTe = '0'
        datagnum = []
        proj = ''
        ArtOK = '0'
        if Tranche != '0' :
            proj = projet + '/' + str(Tranche)
        else :
            proj = projet
        if BP == 'BPA':
            proj = proj + '_BPA'

        for row in resultarticles :
            refarticle = row[0]
            colorarticle = str(row[9])
            if colorarticle == '' :
                colorarticle = str(row[2])
            if colorarticle == 'Sans' or colorarticle == 'sans' :
                colorarticle = ''
            fournisseur = row[6]
            fournisseur = fournisseur.upper()
            if fournisseur == 'TECHNAL' :
                refarticle = 'TEC ' + row[8]
            if fournisseur == 'WICONA' :
                refarticle = 'WIC ' + row[10][1:]
            if fournisseur == 'SAPA' :
                refarticle = refarticle.replace("RC  ","SAP ")

            UV = row[7]
            projet = projet.strip()
            if fournisseur !='HUD' :
                Cpt = Cpt + 1
                if colorarticle != '' :
                    refarticle = refarticle + '.' + colorarticle
                if Cpt == 1 :
                    datanom1= ['',proj ,'normal', '1',projet,'uom.product_uom_unit']
                else :
                    datanom1 = ['','','','','','']
                unme = row[4]
                refarticle = refarticle.replace("RYN","REY")
                refarticle = refarticle.replace("SC  ","SCH ")
                if refarticle == '' :
                    refarticle = row[1]
                product = self.env['product.product'].search([('default_code', '=', refarticle)], limit=1)
                if product:
                    consoaff = product.x_studio_conso_laffaire
                if consoaff == 'True' :
                    Qte = (float(row[5])) / float(UV)
                    x = Qte
                    n = 0
                    resultat = math.ceil(x * 10**n)/ 10**n
                    Qte = (resultat * float(UV))
                else :
                    Qte = row[5]
                ArtOK = '1'
                datanom2 = [refarticle, Qte,idun]
                datanom = datanom1 + datanom2
                pro_temp = product_templates.filtered(lambda pt: pt.default_code == '002_' + datanom1[1])
                pro = product_products.filtered(lambda p: p.default_code == refarticle)
                if pro_temp:
                    nomenclatures_data.append({
                        "product_tmpl_id": pro_temp[0].id,
                        "type": "normal",
                        "product_qty": datanom1[3],
                        "analytic_account_id": account_analytic_id,
                        "product_uom_id": self.env.ref('uom.product_uom_unit').id,
                        "bom_line_ids": [(0, 0, {
                            'product_id': pro.id,
                            'product_qty': Qte,
                            'product_uom_id': pro.uom_id.id
                        })],
                        'operation_ids': []
                    })
        
        # For profies
        resultprofiles=cursor.execute("Select ArticleCode, Description, Color, Amount, Units, OuterColorInfoInternal, InnerColorInfoInternal, ColorInfoInternal, ArticleCode_BaseNumber,ArticleCode_Supplier, ArticleCode_Number Amount from AllProfiles")
        for row in resultprofiles :
            refart = ''
            fournisseur = row[9]
            fournisseur = fournisseur.upper()
            couleurext = str(row[5])
            couleurint = str(row[6])
            if couleurext != '' and couleurint != '' :
                color = couleurext + '/' + couleurint
            else :
                color = str(row[7])
                if color == '' :
                    color = str(row[2])
            if color == 'Sans' or color =='sans' :
                color =''
            refart = row[0]
            refart = str(refart)
            refart = refart.replace (" ", "")
            if fournisseur == 'TECHNAL' :
                refart = 'TEC ' + row[8]
            if fournisseur == 'WICONA' :
                refart = 'WIC ' + row[10][1:]
            if fournisseur == 'SAPA' :
                refart = refart.replace("RC  ","SAP ")
            if color != '' :
                refart = refart + '.' + color
            refart = refart.replace("RYN","REY")
            refart = refart.replace("SC  ","SCH ")
            refart = refart.replace("SC","SCH ")
            unme = str(row[4])
        unitcor = ''
        if refart == '' :
            refart = row[1]

        product = self.env['product.product'].search([('default_code', "=", refart)], limit=1)
        if product:
            unme = product.uom_id.display_name
            unitcor = unme
        # if unitcor == '' :
        uom = uom_uoms.filtered(lambda u: u.name == unme)
        if uom:
            idun = uom[0].id
        Qte = row[3]
        datanom1= ['',proj ,'normal', '1',projet,'uom.product_uom_unit']
        # else :
        ArtOK = '1'
        pro_temp = product_templates.filtered(lambda pt: pt.default_code == '002_' + datanom1[1])
        pro = product_products.filtered(lambda p: p.default_code == refart)
        if pro_temp:
            nomenclatures_data.append({
                "product_tmpl_id": pro_temp[0].id,
                "type": "normal",
                "product_qty": datanom1[3],
                "analytic_account_id": account_analytic_id,
                "product_uom_id": self.env.ref('uom.product_uom_unit').id,
                "bom_line_ids": [(0, 0, {
                    'product_id': pro.id,
                    'product_qty': Qte,
                    'product_uom_id': pro.uom_id.id
                })],
                'operation_ids': []
            })

        # For operations
        resu=cursor.execute("select LabourTimes.TotalMinutes, LabourTimes.WhatName, LabourTimes.Name from LabourTimes")
        cpt = 0
        cpt1 = 0
        name = ''
        ope = ''
        for row in resu :
            cpt1 = cpt1 + 1
            ope = row[1]
            ope = ope.strip()
            temps = float(row[0])
            dataope = ''
            if ope == '' :
                if str(row[2]) == '' :
                    name = name.strip()
                    if name == 'Débit' :
                        ope = 'Débit profilé normaux'
                    else :
                        ope = 'par défaut'
                        if cpt == 0 :
                            cpt = cpt + 1
                            proj = '[' + proj + ']'+ ' ' + proj
                            dataope = ['',proj,temps,ope,name]
                        else :
                            dataope = ['','',temps,ope,name]
                    if dataope:
                        pro_temp = product_templates.filtered(lambda pt: pt.default_code == '002_' + proj)
                        workcenter = self.env['mrp.workcenter'].search([('name', '=', name)], limit=1)
                        if nomenclatures_data:
                            nomenclatures_data[0]['operation_ids'].append((0, 0, {
                            'name': ope,
                            'time_cycle_manual': dataope[2],
                            'name': dataope[4],
                            'workcenter_id': workcenter.id
                        }))
                else :
                    name = row[2]
                    name = name.strip()
            else:
                if cpt == 0 :
                    cpt = cpt + 1
                    dataope = ['', proj, temps, ope, name]
                else :
                    dataope = ['','',temps,ope,name]
            if dataope:
                pro_temp = product_templates.filtered(lambda pt: pt.default_code == '002_' + proj)
                workcenter = self.env['mrp.workcenter'].search([('name', '=', name)], limit=1)
                if nomenclatures_data:
                    nomenclatures_data[0]['operation_ids'].append((0, 0, {
                        'name': ope,
                        'time_cycle_manual': dataope[2],
                        'name': dataope[4],
                        'workcenter_id': workcenter.id
                    }))

        cursor.close()
        temp_file.close()
        cursor1.close()
        self.state = 'error'
        try:
            for product in product_products.create(articlesm):
                refs = ["<a href=# data-oe-model=product.product data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in product.name_get()]
                message = _("Product has been Created: %s") % ','.join(refs)
                messages.append(message)

            for product in product_products.create(articleslibre):
                refs = ["<a href=# data-oe-model=product.product data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in product.name_get()]
                message = _("Product has been Created: %s") % ','.join(refs)
                messages.append(message)
                
            for product in product_products.create(articles_data):
                refs = ["<a href=# data-oe-model=product.product data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in product.name_get()]
                message = _("Product has been Created: %s") % ','.join(refs)
                messages.append(message)
                
        except Exception as e:
            return self.log_request('Unable to create products.', str(e), 'Whole Articles Data')

        self.env.cr.commit()
        try:
            for so in so_data:
                for so_to_update in self.env['sale.order'].browse(so):
                    so_to_update.write(so_data[so])
                    so_to_update.action_confirm()
                    refs = ["<a href=# data-oe-model=sale.order data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in so_to_update.name_get()]
                    message = _("Sales Order Updated: %s") % ','.join(refs)
                    messages.append(message)

            for bom in self.env['mrp.bom'].create(nomenclatures_data):
                note = "Bill Of Material Created > %s" % (bom.display_name)
                refs = ["<a href=# data-oe-model=mrp.bom data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in bom.name_get()]
                message = _("Bill Of Material has been Created: %s") % ','.join(refs)
                messages.append(message)

            for purchase in self.env['purchase.order'].create(po_article_vals):
                refs = ["<a href=# data-oe-model=purchase.order data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in purchase.name_get()]
                message = _("Purchase Order has been created: %s") % ','.join(refs)
                messages.append(message)
                
            for purchase in self.env['purchase.order'].create(po_profile_vals):
                refs = ["<a href=# data-oe-model=purchase.order data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in purchase.name_get()]
                message = _("Purchase Order has been created: %s") % ','.join(refs)
                messages.append(message)

            for purchase in self.env['purchase.order'].create(po_glass_vals):
                refs = ["<a href=# data-oe-model=purchase.order data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in purchase.name_get()]
                message = _("Purchase Order has been created: %s") % ','.join(refs)
                messages.append(message)

        except Exception as e:
            return self.log_request('Unable to create/update SO, PO or nomenclatures', str(e), 'Whole Creation')

        self.state = 'done'
        for msg in messages:
            self.message_post(body=msg)
    
    def log_request(self, operation, ref, path, level=None):
        db_name = self.env.cr.dbname
        try:
            db_registry = registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                IrLogging = env['ir.logging']
                IrLogging.sudo().create({'name': operation,
                                         'type': 'server',
                                         'dbname': db_name,
                                         'level': level,
                                         'message': "%s" % (ref),
                                         'path': "%s - %s " % (path, self.description),
                                         'func': operation,
                                         'line': 1})
        except psycopg2.Error:
            pass
