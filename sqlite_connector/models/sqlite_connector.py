
import sqlite3
import logging
import math
import tempfile
import base64
import re
import psycopg2

from odoo.exceptions import UserError
from odoo import Command, models, fields, registry, SUPERUSER_ID, api, _
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
    ir_log_ids = fields.One2many('ir.logging', 'connector_id')

    def export_data_from_db(self):
        articles = []
        profiles = []
        suppliers = []
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
        product_categories = self.env['product.category'].search([])
        uom_uoms = self.env['uom.uom'].search([])
        stock_picking_type = self.env['stock.picking.type'].search([])
        stock_warehouse = self.env['stock.warehouse'].search([])
        # account_analytic_tags = self.env['account.analytic.tag'].search([])
        account_analytics = self.env['account.analytic.account'].search([])
        mrp_workstations = self.env['mrp.workcenter'].search([])
        res_partners = self.env['res.partner'].search([])
        #product_templates = self.env['product.template'].search([])
        res_users = self.env['res.users'].search([])

        temp_file = tempfile.NamedTemporaryFile('wb', suffix='.sqlite', prefix='edi.mx.tmp.')
        temp_file.write(base64.b64decode(self.file))
        con = sqlite3.connect(str(temp_file.name))
        cursor = con.cursor()
        cursor1 = con.cursor()
        date_time = datetime.now()

        article_data = cursor.execute("select ArticleCode, PriceGross, PUSize, Units_Unit, ArticleCode_Supplier, ArticleCode_BaseNumber,ColorInfoInternal, Color, ArticleCode_Number, Discount from Articles")
        for row in article_data:
            refart = row[0]
            couleur = ''
            Unit = row[3]
            Unit = Unit.upper()
            UnitLog = ''
            if Unit == 'M' or Unit == 'ML':
                UnitLog = 'MTR'
            else :
                if Unit == 'PCE' or Unit == 'PAI' or Unit == 'UNIT' :
                    UnitLog = 'PCE'
                    
            fournisseur= row[4]
            fournisseur = fournisseur.upper()
            RefLogikal = row[5]
            Length = 0
            LengthLogikal = row[5]
            if fournisseur == 'TECHNAL' :
                refart = 'TEC' + ' ' + row[5]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'T' + RefLogikal
            if fournisseur == 'SAPA' :
                refart = refart.replace("RC  ","SAP ")
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'S' + RefLogikal
            if fournisseur == 'WICONA' :
                refart = 'WIC' + ' ' + row[8][1:]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    if len(str(LengthLogikal)) < 7:
                        RefLogikal = 'W' + RefLogikal.rjust(7, '0')
                    else:
                        RefLogikal = 'W' + RefLogikal
            if fournisseur == 'JANSEN' or fournisseur == 'Jansen':
                refart = 'JAN' + ' ' + row[8]
            refart = refart.replace("RYN","REY")
                
            couleur = row[6] if row[6] else ''
            if couleur == '' or couleur == 'None':
                couleur = row[7] if row[7] else ''
            if couleur == 'Sans' or couleur == 'sans' or couleur == 'RAL':
                couleur = ''
            if couleur not in ['', None, 'None']:
                refart = refart + '.' + couleur
            #_logger.warning("**********article pour MAJ********* %s " % refart )
            articles.append({
                'item': refart,
                'price': row[1],
                'Discount': row[9],
                'unit': row[2],
                'condi': row[3],
                'RefLogikal' : RefLogikal,
                'ColorLogikal' : couleur,
                'LengthLogikal' : Length,
                'UnitLogikal' : UnitLog
            })


        profile_data = cursor.execute("select Profiles.ArticleCode, Profiles.PriceGross, Profiles.ArticleCode_Number, Profiles.Color, Profiles.ArticleCode_Supplier, Profiles.ArticleCode_BaseNumber, Profiles.OuterColorInfoInternal, Profiles.InnerColorInfoInternal, Profiles.ColorInfoInternal, AllProfiles.Length, Profiles.Price from Profiles INNER JOIN AllProfiles ON AllProfiles.ArticleCode = Profiles.ArticleCode")
        for row in profile_data:
            refart = row[0]
            couleur = ''
            fournisseur = row[4]
            fournisseur = fournisseur.upper()
            RefLogikal = row[5]
            Discount = float(row[1]) / float(row[10]) if float(row[10]) != 0 else 0.0  
            Length = 0
            LengthLogikal = len(row[5])
            if fournisseur == 'TECHNAL' :
                refart = 'TEC' + ' ' + row[5]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'T' + RefLogikal
                Length= row[9]
            if fournisseur == 'SAPA' :
                refart = refart.replace("RC  ","SAP ")
                Length= row[9]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'S' + RefLogikal
            _logger.warning("**********AVANT Profile pour MAJ********* %s " % RefLogikal )
            if fournisseur == 'WICONA' :
                refart = 'WIC' + ' ' + row[2][1:]
                Length= row[9]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    if int(str(LengthLogikal)) < 7 :
                        RefLogikal = 'W' + RefLogikal.zfill(7)
                    else :
                        RefLogikal = 'W' + RefLogikal
                _logger.warning("**********APRES Profile pour MAJ********* %s " % RefLogikal )
            if fournisseur == 'JANSEN' or fournisseur == 'Jansen' :
                refart = 'JAN' + ' ' + row[2]
            refart = refart.replace("RYN","REY")
                
            couleurext = row[6] if row[6] else ''
            couleurint = row[7] if row[7] else ''
            if couleurext not in ['', None] and couleurint not in  ['', None] :
                couleur = couleurext + '/' + couleurint
            else :
                couleur = str(row[8])
                if couleur == '' or couleur == ' ' :
                    couleur = str(row[3])
                    if couleur == 'Sans' or couleur == 'sans' or couleur == 'RAL':
                        couleur = ''
            if couleur not in ['', None, 'None']:
                refart = refart + '.' + couleur
                #RefLogikal = 'T' + RefLogikal
                
            _logger.warning("**********Profile pour MAJ********* %s " % refart )
            profiles.append({
                'article': refart,
                'prix': row[1],
                'Discount' : Discount,
                'RefLogikal' : RefLogikal,
                'ColorLogikal' : couleur,
                'LengthLogikal' : Length,
                'UnitLogikal' : 'Pce'
            })

        
        name = ''
        rfrs = cursor.execute("select SupplierID,Address2 from Suppliers")
        for row in rfrs:
            name = str(row[1])
            if name in ['', None,'None'] :
                name = 'NonDef'
            #_logger.warning('fournisseur ID %s' % row[0])
            #_logger.warning('fournisseur Nom %s' % name)
            suppliers.append({
                'id': row[0],
                'name' : name
            })
           

        #To check if product already exists in odoo from articles
        for article in articles:
            product = self.env['product.product'].search([('default_code', '=', article['item'])])
            if product:
                product = product[0]
                product.x_studio_ref_int_logikal = article['RefLogikal']
                product.x_studio_color_logikal = article['ColorLogikal']
                product.x_studio_unit_logikal = article['UnitLogikal']
                product.x_studio_longueur_m = article['LengthLogikal']
                #message = _("Ref Logikal is updated for product: ") + product._get_html_link()
            #product = self.env['product.supplierinfo'].search([('default_code', '=', article['item'])])
            #if product and round(float(article['price']), 4) != round(product.supplierinfo.price, 4):
                #product.standard_price = float(article['price'])
                #message = _("Standard Price is updated for product: ") + product._get_html_link()
                #self.message_post(body=message)

        # To check if product already exists in odoo from articles
        for profile in profiles:
            #_logger.warning("**********Profile dans la MAJ********* %s " % profile['article'] )
            product = self.env['product.product'].search([('default_code', '=', profile['article'])])
            if product:
                _logger.warning("**********Profile dans la MAJ pour ref logikal********* %s " % profile['RefLogikal'] )
                product = product[0]
                product.x_studio_ref_int_logikal = profile['RefLogikal']
                product.x_studio_color_logikal = profile['ColorLogikal']
                product.x_studio_unit_logikal = profile['UnitLogikal']
                product.x_studio_longueur_m = profile['LengthLogikal']
                #message = _("Ref Logikal is updated for product: ") + product._get_html_link()
                #self.message_post(body=message)
            #if product and round(float(profile['prix']), 4) != round(product.standard_price, 4):
            #    product.standard_price = float(profile['prix'])
            #    message = _("Standard Price is updated for product: ") + product._get_html_link()
            #    self.message_post(body=message)

        # At FMA, they have a concept of tranches, that is to say that the project is didelaid into
        # several phases (they call it tranches). So I come to see if it is a project with installments or
        # not and I come to get the installment number

        Tranche = '0'
        PersonBE = ''
        project = ''
        fab = 1
        zero_delay_products = []
        fab_delay_products = []
        
        #_logger.warning("testttttt %s " % )
        
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
        #_logger.warning("Projet %s " % projet )
        user_id = res_users.filtered(lambda p: p.name == re.sub(' +', ' ', PersonBE.strip()))
        if user_id:
            user_id = user_id.id
        else:
            user_id = False
            self.log_request("Unable to find user Id.", PersonBE, 'Project Data')
        #key_vals = dict(self.env['sale.order']._fields['x_studio_bureau_etudes'].selection)
        #bureau_etudes = False
        #for key, val in key_vals.items():
        #    if key == PersonBE.strip():
        #        bureau_etudes = key
        
        account_analytic_id = account_analytics.filtered(lambda a: a.name.strip() in projet.strip())
        #_logger.warning("*****************************COMPTE ANALYTIQUE**************** %s " % account_analytic_id)
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
                fab = float(row[2])
          #if (row[0] == 'UserVars') and (row[1] == 'UserDate2') :
          #  date_time = row[2]
          #  def convert(date_time):
          #      if date_time:
          #          format = '%d/%m/%Y'  # The format
          #          datetime_str = datetime.strptime(date_time, format).strftime('%Y-%m-%d')
          #          return datetime_str
          #      return datetime.now()
          #  dateliv = convert(date_time)
        
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
        #_logger.warning("projet  2 %s " % projet)
        # account_analytic_tag_id = account_analytic_tags.filtered(lambda t: t.name == etiana)
        # if account_analytic_tag_id:
        #     account_analytic_tag_id = account_analytic_tag_id.id
        # else:
        #     account_analytic_tag_id = False
        #     self.log_request("Unable to find analytic account tag.", etiana, 'Projects Data')

        # We come to create the item which is sold

        # We recover in a parameter the type of case which is a concept from FMA. We have either
        # BPA, or BPE, or BPA-BPE. This parameter is very important because if you are in BPA, we will
        # only create purchase orders and not bills of materials.

        #BP = ''
        #resultBP = cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        #for row in resultBP :
        #    if (row[0] == 'UserVars') and (row[1] == 'UserInteger1') :
        #        if (row[2] == '1')  :
        #            BP = 'BPA'
        #        if (row[2] == '3') :
        #            BP = 'BPE'
        #        if (row[2] == '2') :
        #            BP = 'BPA-BPE'
        value = ''
        BP = ''
        resultBP = cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        rows = resultBP.fetchall()
        #_logger.warning("Nombre de lignes dans REPORTVARIABLES : %d" % len(rows))
        
        for row in rows:
           # _logger.warning("Ligne : %s" % str(row))
            if (row[0] == 'UserVars') and (row[1] == 'UserInteger1'):
                value = row[2].strip().replace(' ', '')
                _logger.warning("Valeur nettoyée : %s" % value)
                if value == '1':
                    BP = 'BPA'
                elif value == '3':
                    BP = 'BPE'
                elif value == '2':
                    BP = 'BPA-BPE'
                
        _logger.warning("Profile %s " % value )
        # If we are not in BPA, we come and create the items that we will put in the customer quote.
        # This we put in the articlesm.xlsx files

        # Now we will handle 2 cases over here as BPA and non BPA
        
        if BP != 'BPA':
            _logger.info(BP)
            cpt = 0
            elevID = ''
            cat = ''
            categorie = ''
            resultsm = cursor.execute("select Elevations.ElevationID, Elevations.Name, Elevations.Model, Elevations.Autodescription, Elevations.Height_Output, Elevations.Width_Output, Projects.OfferNo, ReportOfferTexts.TotalPrice, Elevations.Description,Elevations.Model from Elevations INNER JOIN ElevationGroups ON Elevations.ElevationGroupID = ElevationGroups.ElevationGroupID INNER JOIN Phases ON Phases.PhaseID = ElevationGroups.PhaseId INNER JOIN Projects ON Projects.ProjectID = Phases.ProjectId INNER JOIN ReportOfferTexts ON ReportOfferTexts.ElevationId = Elevations.ElevationId order by Elevations.ElevationID")

            # To get the product category as Elevations.Name will be categ_id
            for row in resultsm:
                if row[3] != 'Position texte' :
                    cpt = cpt + 1
                    Index = str(cpt)
                    refart = row[8]
                    categorie = row[2]
                    refint =  str(cpt) + '_' + projet
                    elevID = row[1]
                    idrefart = ''
                    HautNumDec = float(row[4]) if row[4] not in (None, '', ' ') else 0.0
                    largNumDec = float(row[5]) if row[5] not in (None, '', ' ') else 0.0
                    HautNum = int(HautNumDec)
                    largNum = int(largNumDec)
                
                categ = product_categories.filtered(lambda c: c.x_studio_logical_map == categorie)
                if not categ:
                    self.log_request("Unable to find product category.", categorie, 'Elevations data')
                if row[1] != 'ECO-CONTRIBUTION' and not self.env['product.product'].search([('default_code', '=', refint)]):
                    product = self.env['product.product'].create({
                        "name": refart,
                        "default_code": refint,
                        "list_price": row[7],
                        #"standard_price": row[7],
                        'categ_id': categ.id if categ else self.env.ref('product.product_category_all').id,
                        "uom_id": self.env.ref('uom.product_uom_unit').id,
                        "uom_po_id": self.env.ref('uom.product_uom_unit').id,
                        "x_studio_position": elevID,
                        "x_studio_hauteur_mm": HautNum,
                        "x_studio_largeur_mm": largNum,
                        "detailed_type": "consu",
                        "purchase_ok": False,
                        "sale_ok": True,
                        "invoice_policy":"delivery",
                    })
                    zero_delay_products.append(product.product_tmpl_id.id)
                    message = _("Product has been Created: ") + product._get_html_link()
                    self.message_post(body=message)
                    self.env.cr.commit()

        # To handle if BPA
        # We also create a final item which will be sold and on which we will put the nomenclature
        affaire = ''
        resultp = cursor.execute("select Projects.Name, Projects.OfferNo from Projects")
        for row in resultp:
            refart = str(row[1])
            categ = self.env.ref('product.product_category_all')
            affaire = row[0]
            if BP == 'BPA':
                refart = refart + '_BPA'
                refart = refart.strip()
                idrefart = ''
            p = self.env['product.product'].search([('default_code', '=', refart)])
            if not p:
                #sale_order = self.env['sale.order'].search([('name', '=', refart), ('state', 'not in', ['done', 'cancel'])], limit=1)
                #if sale_order :
                #    affaire = sale_order.x_studio_ref_affaire 
                
                #_logger.warning("**************ARTCILE NOMENCLATURE*************  2 %s " % affaire) 
                #_logger.warning("**************ARTCILE NOMENCLATURE*************  2 %s " % refart)
                
                product = self.env['product.product'].create({
                    "name": affaire,
                    "default_code": refart,
                    "list_price": 0,
                    "standard_price": 0,
                    'categ_id': categ.id,
                    "uom_id": self.env.ref('uom.product_uom_unit').id,
                    "uom_po_id": self.env.ref('uom.product_uom_unit').id,
                    "detailed_type": "product",
                    "purchase_ok": False,
                    "sale_ok": True,
                    "route_ids": [Command.link(self.env.ref('stock.route_warehouse0_mto').id), Command.link(self.env.ref('mrp.route_warehouse0_manufacture').id)],
                    # Staging before merge :"_ids": [(4, self.env.ref('stock._warehouse0_mto').id), (4,self.env.ref('__export__.stock_location__99_adb9a7a8').id)],
                    "invoice_policy":"delivery",
                })
                fab_delay_products.append(product.product_tmpl_id.id)
                message = _("Product has been Created: ") + product._get_html_link()
                self.message_post(body=message)
                self.env.cr.commit()

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

        test = stock_picking_type.filtered(lambda p: p.id == 7)

        if warehouse:
            stock_picking_type_id = stock_picking_type.filtered(lambda p: p.name == operation.strip() and p.warehouse_id.id == warehouse.id)
            if stock_picking_type_id:
                stock_picking_type_id = stock_picking_type_id[0].id
            else:
                self.log_request("Unable to find stock picking type.", operation.strip(), 'Project Data')
        else:
            self.log_request("Unable to find warehouse.", warehouse, 'Project Data')

        
        # Now to collect final data of articles

        datejourd = fields.Date.today()
        # On vient créer une fonction permettant de créer la liste des articles/profilés 
        QteArt = 0    
        delai = ''
        def creation_article(Article, refinterne, nom, unstk, categorie, fournisseur, prix,delai,UV, SaisieManuelle, Qte,RefLogikal,ColorLogikal,UnitLogikal,LengthLogikal):
            trouve = False
            for item in Article:
                # Si l'article existe déjà on ne fait rien
                if item[0] == refinterne :
                    #QteArt = float(item[9])
                    #QteArt += Qte
                    #item[9] = str(QteArt)
                    trouve = True
                    break
            # Si l 'article n'est pas trouvé, ajouter une nouvelle ligne
            if not trouve:
                Article.append([refinterne, nom, unstk, categorie, fournisseur, prix,delai,UV, SaisieManuelle, Qte,RefLogikal,ColorLogikal,UnitLogikal,LengthLogikal])
                
        # On vient créer une fonction permettant de créer les Purchase Order   
        def creation_commande(Commande, refinterne, unstk, fournisseur, prix,delai,UV, Qte):
            trouve = False
            for item in Commande:
                if item[0] == refinterne :
                    QteArt = float(item[6])
                    QteArt += float(Qte)
                    item[6] = str(QteArt)
                    trouve = True
                    break
            # Si l 'article n'est pas trouvé, ajouter une nouvelle ligne
            if not trouve:
                Commande.append([refinterne, unstk, fournisseur, prix,delai , UV, Qte])
        
        # On vient créer une fonction permettant de créer les Nomenclatures   
        def creation_nomenclature(Nomenclature, refinterne, unstk,  Qte):
            trouve = False
            for item in Nomenclature:
                # Si l'article existe déjà on ne fait rien
                if item[0] == refinterne :
                    trouve = True
                    break
            # Si l 'article n'est pas trouvé, ajouter une nouvelle ligne
            if not trouve:
                Nomenclature.append([refinterne, unstk, Qte])

        Article = []
        Commande = []
        Nomenclature = []
        Qte = 0
        QteBesoin = 0
        LstArt = ''
        CptLb = 0
        resart = cursor1.execute("select AllArticles.ArticleCode, AllArticles.ArticleCode_Supplier, AllArticles.Units_Unit, AllArticles.Description, AllArticles.Color, AllArticles.Price, AllArticles.Units, AllArticles.PUSize, AllArticles.IsManual,AllArticles.ArticleCode_BaseNumber, AllArticles.ColorInfoInternal, AllArticles.ArticleCode_Number, AllArticles.Units_Unit from AllArticles order by AllArticles.ArticleCode_Supplier")

        for row in resart :
            refart = row[0]
            #_logger.warning("**********REFART********* %s " % refart )
            fournisseur= row[1]
            fournisseur = fournisseur.upper()
            unit = row[2]
            nom = row[3]
            UV = row[7]
            SaisieManuelle = row[8]
            prix = 0
            Qte = row[6]
            RefLogikal = row[9]
            ColorLogikal = ''
            UnitLogikal = row[12]
            UnitLogikal = UnitLogikal.upper()
            LengthLogikal = 0
            LengthLogi = len(row[9])
            # dateliv = datejourd
            if fournisseur == 'TECHNAL' :
                refart = 'TEC' + ' ' + row[9]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'T' + RefLogikal
                #RefLogikal = 'T' + RefLogikal 
            if fournisseur == 'WICONA' :
                refart = 'WIC' + ' ' + row[11][1:]
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'W' + RefLogikal
                    if int(LengthLogi) < 7 :
                        RefLogikal = 'W' + RefLogikal.zfill(7)
                    else :
                        RefLogikal = 'W' + RefLogikal
            if fournisseur == 'SAPA' :
                refart = refart.replace("RC  ","SAP ")
                if RefLogikal.startswith("X") :
                    RefLogikal = RefLogikal
                else :
                    RefLogikal = 'S' + RefLogikal
            if fournisseur == 'Jansen' or fournisseur == 'Jansen' :
                refart = 'JAN' + ' ' + row[11]
            if fournisseur == 'RP-Technik' :
                refart = 'RP' + ' ' + row[9]
            if fournisseur == 'Forster' :
                refart = 'FRS' + ' ' + row[9]
                refart = refart.remplace ('.','')
            if fournisseur == 'RPT' or fournisseur == 'rpt' :
                fournisseur = 'KDI'
            
            refart = refart.replace("RYN","REY")
            refart = refart.replace("SC  ","SCH ")
            

            if fournisseur != 'HUD' :
                uom = uom_uoms.filtered(lambda u: u.x_studio_uom_logical == unit)
                if uom:
                    unit = uom.name
                #_logger.warning("**********UNITE APRES CONVERSION********* %s " % unit )
                couleur = row[10] if row[10] else ''
                if couleur == '' and couleur != 'None':
                    couleur = row[4] if row[4] else ''
                if couleur == 'Sans' or couleur == 'sans' :
                    couleur = ''
                #if eticom == 'F2M' :
                #    couleur =''
                if couleur not in ['', None, 'None']:
                    refart = refart + '.' + couleur
                ColorLogikal = couleur
                #_logger.warning("**********saisie manuelle********* %s " % str(SaisieManuelle) )  
                if str(SaisieManuelle) == 'True' or SaisieManuelle == 1 : 
                    CptLb = CptLb + 1
                    refart = nom[:3] + ' ' + projet +'_LB' + str(CptLb)
                    fournisseur = 'NONDEF'
                    
                # to get price
                for article in articles:
                    if refart == article['item']:
                        prix = article['price']
                
                categorie = '__export__.product_category_14_a5d33274'
                if not self.env['product.product'].search([('default_code', '=', refart)], limit=1):
                    creation_article(Article, refart, nom, unit, categorie ,fournisseur,prix ,delai, UV, SaisieManuelle, Qte,RefLogikal,ColorLogikal,UnitLogikal,LengthLogikal)
                else :
                    creation_commande(Commande, refart, unit, fournisseur,prix ,delai, UV, Qte)
                    
        for ligne in Article :
            # we are looking for the ID of UnMe
            idfrs = ''
            idun = ''
            unit = ligne[2]
            uom = uom_uoms.filtered(lambda u: u.name == unit)
            if uom:
                unnom = uom.name
                idun = uom.id
            # we are looking for the ID of supplier
            fournisseur = ligne[4]
            #Qte = ligne[9]
            UV = ligne[7]
            QteBesoin = float(ligne[9])
            Qte = (float(ligne[9])) / float(UV) if UV else float(ligne[9])
            x = Qte
            n = 0
            resultat = math.ceil(x * 10**n)/ 10**n
            Qte = (resultat * float(UV))
            resultat = res_partners.filtered(lambda p: p.x_studio_ref_logikal and p.x_studio_ref_logikal.upper() == fournisseur)
            if resultat:
                idfrs = resultat[0].id
            if fournisseur == 'NONDEF' :
                if LstArt == '' :
                    LstArt = refart
                else :
                    LstArt = LstArt + ' , ' + refart
                #self.log_request('Unable to find customer (x_studio_ref_logikal)', fournisseur, 'Articles Data')
            
                   
            refart = ligne[0]
            nom = ligne[1]
            prix = float (ligne[5]) if ligne[5] not in (None, '', ' ') else 0.0
            categorie = ligne[3]
            categ_id = self.env.ref(categorie)
            # Created new article
            #_logger.warning("**********Prix  Article********* %s " % str(prix) )
            _logger.warning("**********Article********* %s " % refart )
            if not self.env['product.product'].search([('default_code', '=', refart)], limit=1):
                _logger.warning("**********Creation Article********* %s " % refart )
                vals = {
                    'default_code': refart,
                    'name': nom,
                    'lst_price': prix,
                    'standard_price': prix,
                    'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                    'categ_id': categ_id.id,
                    'purchase_ok': True,
                    'sale_ok': True,
                    'detailed_type': 'product',
                    'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                    'route_ids': [Command.link(self.env.ref('stock.route_warehouse0_mto').id),Command.link(self.env.ref('__export__.stock_route_61_d1ff2535').id)],
                    'x_studio_hauteur_mm': 0,
                    'x_studio_largeur_mm': 0,
                    'x_studio_ref_int_logikal' : ligne[10],
                    'x_studio_color_logikal' : ligne[11],
                    'x_studio_unit_logikal' : ligne[12],
                    'x_studio_longueur_m' : ligne[13],
                    'x_studio_cration_auto' : True,
                    # 'x_studio_positionn': ''
                    }
                if idfrs:
                    seller = self.env['product.supplierinfo'].create({
                    'partner_id': idfrs,
                    'price': prix,
                    'delay': delai,
                    })
                    vals.update({'seller_ids': [Command.set([seller.id])]})
                product = self.env['product.product'].create(vals)
                message = _("Product has been Created: ") + product._get_html_link()
                self.message_post(body=message)
                self.env.cr.commit()
                # created nomenclature
                creation_nomenclature(Nomenclature, refart, idun, Qte)
               
        for ligne in Commande :
            idfrs = ''
            idun = ''
            unit = ligne[1]
            uom = uom_uoms.filtered(lambda u: u.name == unit)
            if uom:
                unnom = uom.name
                idun = uom.id
            # we are looking for the ID of supplier
            fournisseur = ligne[2]

            # On cherche l'article correspondant via sa référence interne
            refart = ligne[0]
            product = self.env['product.product'].search([('default_code', '=', refart)], limit=1)

            if product:
                #  On vérifie si la route MTO est présente
                mto_route = self.env.ref('stock.route_warehouse0_mto', raise_if_not_found=False)
                if mto_route and mto_route in product.route_ids:
                    _logger.info(f"L'article {refart} est configuré en MTO.")
                    UV = ligne[5]
                    Qte = (float(ligne[6])) / float(UV) if UV else float(ligne[6])
                    x = Qte
                    n = 0
                    resultat = math.ceil(x * 10**n)/ 10**n
                    Qte = (resultat * float(UV))        
                    # Tu peux faire un traitement spécifique ici
                else:
                    Qte = float(ligne[6])
                    _logger.info(f"L'article {refart} n'est PAS configuré en MTO.")
            
            #QteBesoin = float(ligne[6])
            # created nomenclature
            #_logger.warning("**********Article********* %s " % refart )
            #_logger.warning("**********Article********* %s " % str(QteBesoin) )
            creation_nomenclature(Nomenclature, refart, idun, Qte)
            
       
        # Process data for profile
        #value = ''
        #BP = ''
        #resultBP = cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        #rows = resultBP.fetchall()
        #_logger.warning("Nombre de lignes dans REPORTVARIABLES : %d" % len(rows))
        
        #for row in rows:
        #    _logger.warning("Ligne : %s" % str(row))
        #    if (row[0] == 'UserVars') and (row[1] == 'UserInteger1'):
        #        value = row[2].strip().replace(' ', '')
        #        _logger.warning("Valeur nettoyée : %s" % value)
        #        if value == '1':
        #            BP = 'BPA'
        #        elif value == '3':
        #            BP = 'BPE'
        #        elif value == '2':
        #            BP = 'BPA-BPE'
                
        #_logger.warning("Profile %s " % value )
        #BP = 'BPE'
        if BP != 'BPA-BPE':
            resultpf = cursor.execute("select AllProfiles.ArticleCode, AllProfiles.Description, AllProfiles.ArticleCode_Supplier, AllProfiles.Description, AllProfiles.Color, AllProfiles.Price, AllProfiles.Units, AllProfiles.Amount, AllProfiles.IsManual, AllProfiles.OuterColorInfoInternal, AllProfiles.InnerColorInfoInternal, AllProfiles.ColorInfoInternal, AllProfiles.ArticleCode_BaseNumber, AllProfiles.ArticleCode_Number, AllProfiles.PUSize, AllProfiles.Length  from AllProfiles order by AllProfiles.ArticleCode_Supplier")
            idun =''
            idfrs = ''
            UV = 0
            Article = []
            Commande = []
    
            for row in resultpf:
                _logger.warning("Profile %s " % row[0] )
                refart = row[0]
                refartini = row[0]
                name = row[1]
                unit = str(row[6])
                unita = ''
                prixB = float(0)
                nom = row[3]
                Qte = row[7]
                UV = row[14]
                IsManual = row[8]
                fournisseur = row[2]
                fournisseur = fournisseur.upper()
                RefLogikal = row[12]
                ColorLogikal = ''
                UnitLogikal = 'PCE'
                LengthLogikal = row[15]
                LengthLogi = len(row[12])
                if fournisseur == 'TECHNAL' :
                    refart = 'TEC' + ' ' + row[12]
                    if RefLogikal.startswith("X") :
                        RefLogikal = RefLogikal
                    else :
                        RefLogikal = 'T' + RefLogikal
                    #RefLogikal = 'T' + row[12]
                if fournisseur == 'WICONA' :
                    refart = 'WIC' + ' ' + row[13][1:]
                    if RefLogikal.startswith("X") :
                        RefLogikal = RefLogikal
                    else :
                        RefLogikal = 'W' + RefLogikal
                        if int(LengthLogi) < 7 :
                            RefLogikal = 'W' + RefLogikal.zfill(7)
                        else :
                            RefLogikal = 'W' + RefLogikal
                if fournisseur == 'SAPA' :
                    refart = refart.replace("RC  ","SAP ")
                    if RefLogikal.startswith("X") :
                        RefLogikal = RefLogikal
                    else :
                        RefLogikal = 'S' + RefLogikal
                if fournisseur == 'Jansen' or fournisseur == 'JANSEN':
                    refart = 'JAN' + ' ' + row[13]
                if fournisseur == 'RP-Technik' :
                    refart = 'RP' + ' ' + row[9]
                if fournisseur == 'Forster' :
                    refart = 'FRS' + ' ' + row[9]
                    refart = refart.replace('.','')
                couleurext = row[9] if row[9] else ''
                couleurint = row[10] if row[10] else ''
                if fournisseur == 'RPT' or fournisseur == 'rpt' :
                    fournisseur = 'KDI'
    
                if couleurext != '' and couleurext != 'None' and couleurint != '' and couleurint !='None' :
                    couleur = couleurext + '/' + couleurint
                else :
                    couleur = row[11] if row[11] else ''
                    if couleur == '' or couleur == ' '  :
                        couleur = row[4] if row[4] else ''
                        if couleur == 'Sans' or couleur == 'sans':
                            couleur = ''
                if eticom == 'F2M' :
                    couleur =''
    
                ColorLogikal = couleur
                
                
                refart = refart.replace("RYN","REY")
                refart = refart.replace("SC  ","SCH ")
                if couleur not in ['', None, 'None']:
                    refart = refart + '.' + couleur
                    refartfic = ''
                
                for profile in profiles:
                    #_logger.warning("**********Profile dans la base********* %s " % refart )
                    #_logger.warning("**********Profile dans la liste********* %s " % profile['article'] )
                    if refart == profile['article']:
                        prix = profile['prix']
                        prixB = float(prix) * float(row[6])
                        #_logger.warning("**********Profile********* %s " % refart )
                        #_logger.warning("**********Prix********* %s " % str(prix) )
                        #_logger.warning("**********Unit********* %s " % str(float(row[6])) )
                        #_logger.warning("**********Unit********* %s " % str((row[6])) )
                        #_logger.warning("**********Prix B********* %s " % str(prixB) )
                
                uom = uom_uoms.filtered(lambda u: u.x_studio_uom_logical == unit)
                if uom:
                    unit = uom.name
                
                #product_product = self.env['product.product'].search([('default_code', '=', refart)], limit=1)
                #unme = product_product.uom_id if product_product.uom_id else ""
                #if unme.name == 'BARRE6.5M' :
                #    unit = 'BARRE6.5ML'
                #else :
                #    unit = str(unme.name) if product_product.uom_id else ""
                
                trouve = 1
                tache = 0
                regle = 0
    
                #_logger.warning("**********Unite de mesure********* %s " % str(unit) )
                categorie = '__export__.product_category_19_b8423373'
                if not self.env['product.product'].search([('default_code', '=', refart)], limit=1):
                    creation_article(Article, refart, nom, unit, categorie ,fournisseur,prixB ,delai, UV, SaisieManuelle, Qte,RefLogikal,ColorLogikal,UnitLogikal,LengthLogikal)
                else :
                    _logger.warning("Profil existant %s " % refart )
                    creation_commande(Commande, refart, unit, fournisseur,prixB ,delai, UV, Qte)
            
            for ligne in Article :
                # we are looking for the ID of UnMe
                idfrs = ''
                idun = ''
                unit = ligne[2]
                #_logger.warning("**********Unite de mesure ********* %s " % unit )
                uom = uom_uoms.filtered(lambda u: u.name == unit)
                #_logger.warning("**********Unite de mesure trouve********* %s " % str(uom) )
                if uom:
                    unnom = uom.name
                    idun = uom.id
                #_logger.warning("**********Unite de mesure recuperee ********* %s " % unnom )
                #_logger.warning("**********Unite de mesure recuperee ********* %s " % str(idun) )
                # we are looking for the ID of supplier
                fournisseur = ligne[4]
                QteBesoin = ligne[9]
                UV = ligne[7]
                Qte = (float(ligne[9])) / float(UV) if UV else float(ligne[9])
                x = Qte
                n = 0
                resultat = math.ceil(x * 10**n)/ 10**n
                Qte = (resultat * float(UV))
                resultat = res_partners.filtered(lambda p: p.x_studio_ref_logikal and p.x_studio_ref_logikal.upper() == fournisseur)
                if resultat:
                    idfrs = resultat[0].id
                else:
                    self.log_request('Unable to find customer (x_studio_ref_logikal)', fournisseur, 'Articles Data')
                
                if idfrs != '':     
                    refart = ligne[0]
                    nom = ligne[1]
                    prix = float (ligne[5])
                    categorie = ligne[3]
                    categ_id = self.env.ref(categorie)
                    # Created new article
                    if not self.env['product.product'].search([('default_code', '=', refart)], limit=1):
                        vals = {
                            'default_code': refart,
                            'name': nom,
                            'lst_price': prix,
                            'standard_price': prix,
                            'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'categ_id': categ_id.id,
                            'purchase_ok': True,
                            'sale_ok': True,
                            'detailed_type': 'product',
                            'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'route_ids': [Command.link(self.env.ref('stock.route_warehouse0_mto').id),Command.link(self.env.ref('__export__.stock_route_61_d1ff2535').id)],
                            'x_studio_hauteur_mm': 0,
                            'x_studio_largeur_mm': 0,
                            'x_studio_ref_int_logikal' : ligne[10],
                            'x_studio_color_logikal' : ligne[11],
                            'x_studio_unit_logikal' : ligne[12],
                            'x_studio_longueur_m' : ligne[13],
                            'x_studio_cration_auto' : True,
                            # 'x_studio_positionn': ''
                            }
                        if idfrs:
                            seller = self.env['product.supplierinfo'].create({
                            'partner_id': idfrs,
                            'price': prix,
                            'delay':delai,
                            })
                            vals.update({'seller_ids': [Command.set([seller.id])]})
                        product = self.env['product.product'].create(vals)
                        message = _("Product has been Created: ") + product._get_html_link()
                        self.message_post(body=message)
                        self.env.cr.commit()
                        # created nomenclature
                        creation_nomenclature(Nomenclature, refart, idun, QteBesoin)
                        
            for ligne in Commande :
                idfrs = ''
                idun = ''
                unit = ligne[1]
                #_logger.warning("**********Unite de mesure recuperee dans la liste ligne de commande********* %s " % unit )
                uom = uom_uoms.filtered(lambda u: u.name == unit)
                if uom:
                    unnom = uom.name
                    idun = uom.id
                #_logger.warning("**********Unite de mesure recuperee ********* %s " % unnom )
                #_logger.warning("**********Unite de mesure recuperee ********* %s " % str(idun) )
                # we are looking for the ID of supplier
                fournisseur = ligne[2]
                UV = ligne[5]
                QteBesoin = float(ligne[6])
                Qte = float(ligne[6])
                refart = ligne[0]
                
                # created nomenclature
                creation_nomenclature(Nomenclature, refart, idun, QteBesoin)
                
        
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

            # On vient créer une fonction permettant de créer la liste des vitrages 
            
            def mettre_a_jour_ou_ajouter(Glass, fournisseur, livraison, position, nom, largeur, hauteur, prix, spacer, quantite_ajoutee,delai,type,pbname,NbHori,NbVerti,PosiHoriX,PosiVertiX,PosiHoriY,PosiVertiY,LongHori,LongVerti ):
                trouve = False
                for item in Glass:
                    # Si le vitrage existe déjà on vient mettre à jour la quantité
                    if item[0] == fournisseur and item[1] == livraison and item [2] == position and item [3] == nom and item [4] == largeur and item[5] == hauteur and item[11] == type:
                        #_logger.warning('Vitrage trouve %s' % fournisseur)
                        #_logger.warning('Vitrage trouve %s' % livraison)
                        #_logger.warning('Vitrage trouve %s' % position)
                        #_logger.warning('Vitrage trouve %s' % nom)
                        #_logger.warning('Vitrage trouve %s' % largeur)
                        #_logger.warning('Vitrage trouve %s' % hauteur)
                        item[8] = str(int(item [8]) + int(quantite_ajoutee))
                        trouve = True
                        break
            
                # Si le vitrage n'est pas trouvé, ajouter une nouvelle ligne
                if not trouve:
                    Glass.append([fournisseur, livraison, position, nom, largeur, hauteur, prix, spacer, quantite_ajoutee,delai,type,pbname,NbHori,NbVerti,PosiHoriX,PosiVertiX,PosiHoriY,PosiVertiY,LongHori,LongVerti])
                       
            Glass = []
            position = ''
            Info2 =''
            spacer = ''
            frsnomf = ''
            delai = 0
            sname = ''
            
            resultg=cursor.execute("select Glass.Info1, Glass.NameShort, Glass.Origin, Glass.Price, Glass.Width_Output, Glass.Height_Output,Glass.InsertionId,Glass.Info2,Glass.FieldNo,Elevations.Name, Elevations.Amount, Insertions.InsertionID, Insertions.ElevationId, Glass.AreaOffer, Glass.SpacerGap_Output,Glass.Name,Glass.GlassID,Glass.LK_SupplierId, Glass.ModelType from (Glass INNER JOIN Insertions ON Insertions.InsertionID = Glass.InsertionId) LEFT JOIN Elevations ON Elevations.ElevationID = Insertions.ElevationId order by Glass.LK_SupplierId, Glass.Info2, Glass.Info2, Glass.Width_Output, Glass.Height_Output, Elevations.Name ,Glass.FieldNo")
            
            for row in resultg:
                if row[13] != 'Glass' :
                    Info2 = ''
                    spacer = ''
                    delai = 21
                else :
                    Info2 = row[7]
                    spacer = row[14]
                    delai = 14
                if (row[9] is None) :
                    position = 'X'
                else :
                    position = str(row[9])
                
                Frsid = row[17]
                _logger.warning('fournisseur %s :' % str(spacer))
                type = row[18]
                if type == '0':
                    type = 'RECTANGULAIRE'
                else :
                    type = 'FORME SPECIALE'
                _logger.warning('Type %s : ' % type)
                
                res_partner = False
                for sup in suppliers :
                    if str(sup['id']).replace(" ", "") == str(Frsid).replace(" ", "") :
                        sname = sup['name']
                        
                for part in res_partners.filtered(lambda p: p.x_studio_ref_logikal):
                    if sname == (part.x_studio_ref_logikal):
                        res_partner = part
                        #_logger.warning('----- %s' % res_partner)
                if res_partner:
                    frsnomf = res_partner[0].name
                else:
                    self.log_request('Unable to find supplier with LK Supplier ID', str(Frsid), 'Glass Data')

                glass_id = row[16] 
                #Récupérer tous les petits bois associés
                cursor.execute("""
                    SELECT Name, Orientation, StartX_Output, EndX_Output, StartY_Output, EndY_Output, Length_Output, BarType
                    FROM GeorgianBars
                    WHERE GlassID = ?
                """, (glass_id,))
                pb = cursor.fetchall()
            
                if not pb:
                    continue
            
                #Séparer en barres horizontales et verticales
                horizontaux = [r for r in pb if r[1] == 'Horizontal']
                verticaux = [r for r in pb if r[1] == 'Vertical']
            
                #Fonctions de formatage
                def fmt(v):
                    try:
                        return str(int(float(v.replace(',', '.'))))
                    except:
                        return '0'
            
                def join_positions(data, i_start, i_end):
                    return " # ".join([f"{fmt(pbs[i_start])}/{fmt(pbs[i_end])}" for pbs in data])
            
                def join_longueurs(data, i_length, i_start, i_end):
                    return " # ".join([f"{fmt(pbs[i_start])}/{fmt(pbs[i_end])}" for pbs in data])

                # Sélection du type (nom du petit bois)
                type_petits_bois = pb[0]
                
                # Nombre de barres
                nb_barre_horizontale = len(horizontaux)
                nb_barre_verticale = len(verticaux)
                
                # Positions horizontales
                pos_x_barre_horizontale = join_positions(horizontaux, 2, 3)
                pos_y_barre_horizontale = join_positions(horizontaux, 4, 5)
                
                # Positions verticales
                pos_x_barre_verticale = join_positions(verticaux, 2, 3)
                pos_y_barre_verticale = join_positions(verticaux, 4, 5)
                
                # Longueurs
                longueur_barre_horizontale = join_longueurs(horizontaux, 6, 2, 3)
                longueur_barre_verticale = join_longueurs(verticaux, 6, 2, 3)
                
                mettre_a_jour_ou_ajouter(Glass,frsnomf,Info2,position,row[1],row[4],row[5],row[3],spacer,row[10],delai,type,type_petis_bois,nb_barre_horizontale,nb_barre_verticale,pos_x_barre_horizontale,pos_x_barre_verticale,pos_y_barre_horizontale,pos_y_barre_verticale,longueur_barre_horizontale,longueur_barre_verticale)
            
            fournisseur = ''
            info_livraison =''
            vitrage = ''
            data22 = ['','','','','','','']
            cpt = 0
            unnomf = 'Piece'
            HautNumDec = 0
            largNumDec = 0
            HautNum = 0
            largNum = 0
            for ligne in Glass :
                cpt = cpt + 1
                uom_uom = uom_uoms.filtered(lambda u: u.name == unnomf)
                if uom_uom:
                    idun = uom_uom.id
                res_partner = res_partners.filtered(lambda p: p.name == ligne[0])
                if res_partner:
                    idfrs = res_partner.id
                if fournisseur != ligne[0] or info_livraison != ligne[1] :
                    x_affaire = self.env['x_affaire'].search([('x_name', 'ilike', projet)], limit=1)
                   
                if vitrage != (str(ligne [2]) + " " + str(ligne[3]) + " " + str(ligne[4]) + " " + str(ligne[5])) :
                    refinterne = proj + "_" + str(cpt)
                    vitrage = ligne[3]
                    position = ligne[2]
                    prix = ligne[6]
                    Qte = ligne[8]
                    HautNumDec = float(ligne[5])
                    largNumDec = float(ligne[4])
                    HautNum = int(HautNumDec)
                    largNum = int(largNumDec)
                    spacer = ligne[7]
                    _logger.warning('Spacer %s' % spacer)
                    delai = ligne[9]
                    type = ligne[10]
                    Pbname = ligne[11]
                    NbHori = int(ligne[12])
                    NbVerti = int(ligne[13])
                    PosiHoriX = ligne[14]
                    PosiVertiX = ligne[15]
                    PosiHoriY = ligne[16]
                    PosiVertiY = ligne[17]
                    LongHori = ligne[18]
                    LongVerti = ligne[19]
                    #dateliv = datejourd + timedelta(days=)
                    categ_id = self.env.ref('__export__.product_category_23_31345211').id
                    # On vient créer l'article
                    if not self.env['product.product'].search([('default_code', '=', refinterne)], limit=1):
                        vals = {
                            'default_code': refinterne,
                            'name': vitrage,
                            'lst_price': 1,
                            'standard_price': prix,
                            'uom_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'categ_id': categ_id,
                            'purchase_ok': True,
                            'sale_ok': True,
                            'detailed_type': 'product',
                            'uom_po_id': idun if idun else self.env.ref('uom.product_uom_unit').id,
                            'route_ids': [Command.link(self.env.ref('stock.route_warehouse0_mto').id),Command.link(self.env.ref('__export__.stock_route_61_d1ff2535').id)],
                            'x_studio_hauteur_mm': HautNum,
                            'x_studio_largeur_mm': largNum,
                            'x_studio_cration_auto' : True,
                            'x_studio_spacer' : spacer,
                            'x_studio_type' : type,
                            'x_studio_type_pb' : Pbname,
                            'x_studio_nbr_pb_horizontal' : NbHori,
                            'x_studio_nbr_pb_vertical' : NbVerti,
                            'x_studio_position_en_x_pb_horizontal_1' : PosiHoriX,
                            'x_studio_position_en_x_pb_vertical_1' : PosiVertiX,
                            'x_studio_position_en_y_pb_horizontal_1' : PosiHoriY,
                            'x_studio_position_en_y_pb_vertical_1' : PosiVertiY,
                            'x_studio_longueur_pb_horizontal' : LongHori,
                            'x_studio_longueur_pb_vertical' : LongVerti,
                            # 'x_studio_positionn': Posint,
                        }
                        if idfrs:
                            seller = self.env['product.supplierinfo'].create({
                                'partner_id': idfrs,
                                'price': prix,
                                'delay': 3,
                            })
                            vals.update({'seller_ids': [Command.set([seller.id])]})
                        product = self.env['product.product'].create(vals)
                        message = _("Product has been Created: ") + product._get_html_link()
                        self.message_post(body=message)
                        self.env.cr.commit()
                   
                fournisseur = ligne[0]
                info_livraison = ligne[1]
                vitrage = (str(ligne [2]) + " " + str(ligne[3]) + " " + str(ligne[4]) + " " + str(ligne[5]))
                     

        # We then create the customer quote with delivery dates and possible discounts.
        # We come to create the quote
        address = ''
       # dateliv = date_time
        resultBP=cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultBP :
            if (row[0] == 'UserVars') and (row[1] == 'UserInteger2') :
                if (row[2] == '0')  :
                    address = 'LRE'
                if (row[2] == '1') :
                    address = 'CBM'
                if (row[2] == '2') :
                    address = 'REM'
            
        PourRem = 0
        resultrem=cursor.execute("select subNode, FieldName, SValue from REPORTVARIABLES")
        for row in resultrem:
            if (row[0] == 'Report') and (row[1] == 'QuotationDiscount1') :
                PourRem = row[2]
                PourRem = PourRem.replace(',','.')

        self.state = 'error'

        resultp = cursor.execute("select Projects.Name, Projects.OfferNo , Address.Address2, Phases.Name, Phases.Info1, Elevations.AutoDescription, Elevations.Amount, Elevations.Height_Output, ReportOfferTexts.TotalPrice, Elevations.Width_Output,Elevations.AutoDescriptionShort, Elevations.Name,  Elevations.Description, Projects.PersonInCharge from Projects LEFT JOIN Address ON Projects.LK_CustomerAddressID = Address.AddressID LEFT JOIN Phases ON Projects.ProjectID = Phases.ProjectID LEFT JOIN ElevationGroups ON Phases.PhaseId = ElevationGroups.PhaseID LEFT JOIN Elevations ON ElevationGroups.ElevationGroupId = Elevations.ElevationID LEFT JOIN ReportOfferTexts ON ReportOfferTexts.ElevationId = Elevations.ElevationId order by Elevations.ElevationId")

        clientID = ''
        PrixTot = 0
        QteTot = 0
        NbrLig = 0
        catergorie = ''
        entrepot = ''
        NumLig = 0

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
                # On vient mettre les données de l entete
                if clientID != row[2] :
                    clientID = row[2]
                    if LstArt != '' :
                        #data1 = ['',row[2], row[2],datetime.now(), projet, 'Article à commander', LstArt,'Bon de commande',deviseur,PersonBE,entrepot,eticom,dateliv]
                        data1 = ['',row[2], row[2],datetime.now(), projet, 'Article à commander', LstArt,'Bon de commande',deviseur,PersonBE,entrepot,eticom]
                    else :
                        #data1 = ['',row[2], row[2],datetime.now(), projet,'','','',deviseur,PersonBE,entrepot,eticom,dateliv]
                        data1 = ['',row[2], row[2],datetime.now(), projet,'','','',deviseur,PersonBE,entrepot,eticom]
                else :
                    #data1 =['','','','','','','','','','','','','']
                    data1 =['','','','','','','','','','','','']
                if ( row[8] == None ) :
                    PrixTot = PrixTot + 0
                else :
                    PrixTot = float(row[8]) + PrixTot
                if ( row[6] == None ) :
                    QteTot = QteTot + 0
                else :
                    QteTot = float(row[6]) + QteTot
                # En position texte on ne prend que ECO CONTRIBUTION sinon on passe tout en FRAIS DE LIVRAISON
                if row[5] == 'Position texte':
                    if row[11] == 'ECO-CONTRIBUTION' :
                        refart = 'ECO-CONTRIBUTION'
                        PourRem = 0
                        #dimension = 'ECO-CONTRIBUTION'
                    else :
                        refart = 'Frais de livraison'
                        #dimension = 'Frais de livraison'
                else :
                    if (row[9] == None or row[7] == None) :
                        dimension = ''
                        NumLig = NumLig + 1
                        refart = '[' + str(NumLig) + '_' + projet + ']'
                    else:
                        dimension = str(row[9]) + 'mm * ' + str(row[7]) + 'mm'
                        #refart = '[' + str(NbrLig) + '_' + projet + ']' + row[12]
                        refart = '[' + str(NumLig) + '_' + projet + ']'
                #data2 = [refart, row[8], row[6],dimension,etiana,PourRem]
                data2 = [refart,etiana,PourRem]
                
                if NbrLig == 1:
                    #data1 =['','','','','','','','','','','','','']
                    data1 =['','','','','','','','','','','','']
                    proj = ''
                    if Tranche != '0' :
                        proj = projet.strip() + '/' + str(Tranche)
                    else :
                        proj = projet.strip()
                    if BP == 'BPA':
                        proj = proj + '_BPA'
                    data = data1 + [proj,0, 1,proj,etiana,PourRem]
                    #_logger.warning("DESCRIPTION ARTICLE %s " % proj )
                if refart != 'ECO-CONTRIBUTION':
                    #pro_name = row[11] + '_' + projet
                    NumLig = NumLig + 1
                    pro_name = str(NumLig) + '_' + projet
                else:
                    pro_name = 'ECO-CONTRIBUTION'
                part = res_partners.filtered(lambda p: p.name == row[2])
                pro = self.env['product.product'].search([('default_code', '=', pro_name)], limit=1)
                warehouse = False
                if data1[10]:
                    warehouse = self.env.ref(data1[10]).id
                _logger.warning('Dans la creation du sale order %s' % proj)
                sale_order = self.env['sale.order'].search([('name', '=', proj), ('state', 'not in', ['done', 'cancel'])], limit=1)
                ana_acc = self.env['account.analytic.account'].search([('name', 'ilike', projet)], limit=1)
                
                if sale_order:
                    if so_data.get(sale_order.id, 0) == 0 and pro:
                        so_data[sale_order.id] = {
                        "partner_id": part.id if part else sale_order.partner_id.id,
                        "partner_shipping_id": part.id if part else sale_order.partner_shipping_id.id,
                        "partner_invoice_id": part.id if part else sale_order.partner_invoice_id.id,
                        "date_order": fields.Date.today(),
                        "order_line": [Command.create({
                                'product_id': pro.id,
                                'price_unit': float(row[8]),
                                'product_uom_qty': float(row[6]),
                                #'name': dimension,
                                'discount': PourRem,
                                'product_uom': pro.uom_id.id,
                                # "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                })],
                        }
                    else:
                        if pro and so_data[sale_order.id] and so_data[sale_order.id].get('order_line'):
                            so_data[sale_order.id].get('order_line').append(Command.create({
                                'product_id': pro.id,
                                'price_unit': float(row[8]),
                                'product_uom_qty': float(row[6]),
                                #'name': dimension,
                                'discount': PourRem,
                                'product_uom': pro.uom_id.id,
                                # "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                }))
            sale_order = self.env['sale.order'].search([('name', '=', proj), ('state', 'not in', ['done', 'cancel'])], limit=1)
            
            ana_acc = self.env['account.analytic.account'].search([('name', 'ilike', projet)], limit=1)
            proj = ''
            if Tranche != '0' :
                proj = projet + '/' + str(Tranche)
            else :
                proj = projet
            if BP == 'BPA':
                proj = proj + '_BPA'
            pro_name =proj                
            dimension = ''
            pro = self.env['product.product'].search([('default_code', '=', pro_name)], limit=1)
            if sale_order:
            # stagging before merge if sale_order and so_data:
               if pro and so_data[sale_order.id] and so_data[sale_order.id].get('order_line'):
                    so_data[sale_order.id].get('order_line').append(Command.create({
                        'product_id': pro.id,
                        'price_unit': 0,
                        'product_uom_qty': 1,
                        'name': dimension,
                        'discount': PourRem,
                        'product_uom': pro.uom_id.id,
                        # "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                        }))
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
                    part = res_partners.filtered(lambda p: p.name == row[2])
                    pro = self.env['product.product'].search([('default_code', '=', proj)], limit=1)
                    warehouse = False
                    if data1[10]:
                        warehouse = self.env.ref(data1[10]).id
                    sale_order = self.env['sale.order'].search([('name', '=', proj), ('state', 'not in', ['done', 'cancel'])], limit=1)
                    
                    ana_acc = self.env['account.analytic.account'].search([('name', 'ilike', projet)], limit=1)
                    if sale_order:
                        if so_data.get(sale_order.id, 0) == 0 and pro:
                            so_data.append({
                                "partner_id": part.id if part else sale_order.partner_id.id,
                                "partner_shipping_id": part.id if part else sale_order.partner_shipping_id.id,
                                "partner_invoice_id": part.id if part else sale_order.partner_invoice_id.id,
                                "date_order": fields.Date.today(),
                                "order_line": [Command.create({
                                    'product_id': pro[0].id if pro else False,
                                    'price_unit': float(row[8]),
                                    'product_uom_qty': float(row[6]),
                                    'name': dimension,
                                    'discount': PourRem,
                                    'product_uom': pro.uom_id.id,
                                    # "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                    })
                                ],
                            })
                        else:
                            if pro and so_data[sale_order.id].get('order_line'):
                                so_data[sale_order.id].get('order_line').append(Command.create({
                                    'product_id': pro[0].id if pro else False,
                                    'price_unit': float(row[8]),
                                    'product_uom_qty': float(row[6]),
                                    'name': dimension,
                                    'discount': PourRem,
                                    'product_uom': pro.uom_id.id,
                                    # "analytic_tag_ids": [(6, 0, [account_analytic_tag_id])] if account_analytic_tag_id else None,
                                    })
                                )
        # Now we will create nomenclatures
        datanom=[]
        cpt = 0
        elevID = ''
        nomenclatures_data = []
        self.state = 'error'
        
        proj = ''
        cpt = 0
        if Tranche != '0' :
            proj = projet + '/' + str(Tranche)
        else :
            proj = projet
        if BP == 'BPA':
            proj = proj + '_BPA'
        projet = projet.strip()
        
        for row in Nomenclature :
            refart = row[0]
            unom = row[1]
            Qte = row[2]
            cpt = cpt + 1 
            if cpt == 1 :
                datanom1= ['',proj ,'normal', '1',projet,'uom.product_uom_unit']
            else :
                datanom1 = ['','','','','','']
            
            pro = self.env['product.product'].search([('default_code', '=', refart)], limit=1)
            if datanom1[1] != '':
                pro_t = self.env['product.product'].search([('default_code', '=', datanom1[1])], limit=1)
                if not pro_t:
                    self.log_request('Unable to find product', datanom1[1], 'Nomenclatures Creation')
                else:
                    #analytic_distribution = {str(account_analytic_id): 100}
                    nomenclatures_data.append({
                    "product_tmpl_id": pro_t[0].product_tmpl_id.id,
                    "type": "normal",
                    "product_qty": int(datanom1[3]),
                    # "analytic_account_id": account_analytic_id,
                    #"analytic_distribution": analytic_distribution,
                    "product_uom_id": self.env.ref('uom.product_uom_unit').id,
                    "bom_line_ids": [Command.create({
                        'product_id': pro[0].id,
                        'product_qty': Qte,
                        'product_uom_id': pro.uom_id.id
                    })],
                    'operation_ids': []
                })
            else:
                if nomenclatures_data and pro:
                    nomenclatures_data[0].get('bom_line_ids').append(Command.create({
                    'product_id': pro[0].id,
                    'product_qty': Qte,
                    'product_uom_id': pro.uom_id.id
                }))
        

        cpt = 0
        refart = ''
        for ligne in Glass :
            cpt = cpt + 1
            refart = proj + '_' + str(cpt)
            Qte = ligne[8]
            #_logger.warning('Dans les vitrages %s', refart)
            pro = self.env['product.product'].search([('default_code', '=', refart)], limit=1)
            if pro:
                #_logger.warning('Affaire %s', proj)
                nomenclatures_data[0].get('bom_line_ids').append(Command.create({
                'product_id': pro[0].id,
                'product_qty': Qte,
                'product_uom_id': pro.uom_id.id
                }))
                
        #For operations
        # Étape 1: Lire la table SQL et agréger les données
        aggregated_data = {}

        resu = cursor.execute("SELECT * FROM LabourTimes")
        for row in resu :
            _logger.warning("Temps %s " % str(row[7]))        
        
        cursor.execute("SELECT COUNT(*) FROM LabourTimes")
        count = cursor.fetchone()[0]    
        _logger.warning("Nombre de lignes %s " % str(count) )
        
        resuOpe = []
        cursor.execute("""
            SELECT LabourTimes.TotalMinutes, LabourTimes.WhatName, LabourTimes.Name, LabourTimes.LabourTimeId 
            FROM LabourTimes 
            ORDER BY CAST(LabourTimes.LabourTimeId AS INTEGER)
        """)
        while True:
            rows = cursor.fetchmany(500)
            if not rows:
                break
            resuOpe.extend(rows)
        name = ''
        ope = ''
        temps = 0
        reference = ''
        delai_total_minutes = 0
        
        for rowOpe in resuOpe:
            temps = float(rowOpe[0]) if rowOpe[0] else 0.0
            reference = rowOpe[1].strip() if rowOpe[1] else ''
            nom_base = rowOpe[2].strip() if rowOpe[2] else ''
            #_logger.warning("**********ID********* %s " % str(rowOpe[3]) )
            if rowOpe[2] is not None and rowOpe[2] != '' :
                if rowOpe[2].strip() == 'Parcloses ALU' or rowOpe[2].strip() == 'Emballage':
                    name = 'Remontage'  + ' ' + eticom
                else :
                    if rowOpe[2].strip() == 'Prépa' :
                        name = 'Usinage'  + ' ' + eticom
                    else :
                        if rowOpe[2].strip() == 'Parcloses ACIER' :
                            name = 'Débit'  + ' ' + eticom
                        else :
                            name = rowOpe[2].strip() + ' ' + eticom
        
            if rowOpe[1] is not None and rowOpe[1] != '' : 
                ope = name
                if ope in aggregated_data:
                    aggregated_data[ope]['temps'] += temps
                else:
                    aggregated_data[ope] = {'temps': temps, 'name': name}
        
        # Trier les opérations selon x_sequence du poste de travail
        sorted_operations = sorted(
            aggregated_data.items(),
            key=lambda item: self.env['mrp.workcenter'].search([('name', '=', item[1]['name'])], limit=1).code or 999
        )
        
        # Calcul du délai global (temps total des opérations + délais inter-opérations)
        _total_minutes = 0
        previous_workcenter = None
        operation_cmds = []
        operation_links = {}  # stocke les relations de dépendance
        sequence = 1
        
        for ope, data in sorted_operations:
            workcenter = self.env['mrp.workcenter'].search([('name', '=', data['name'])], limit=1)
            if not workcenter:
                continue
        
            temps = data['temps']
            delai_total_minutes += temps
        
            # Rechercher les postes bloquants
            delay = self.env['x_delai_entre_operatio'].search([
                ('x_studio_poste_de_travail_deb', '=', previous_workcenter.id if previous_workcenter else False),
                ('x_studio_poste_de_travail_fin', '=', workcenter.id)
            ], limit=1)
        
            delay_minutes = delay.x_studio_dlai_entre_oprations if delay else 0.0
            delai_total_minutes += delay_minutes
        
            operation_data = {
                'name': ope,
                'time_cycle_manual': temps,
                'workcenter_id': workcenter.id,
                'sequence': sequence,
            }
        
            op_cmd = Command.create(operation_data)
            operation_cmds.append(op_cmd)
            operation_links[workcenter.id] = {'sequence': sequence, 'command': op_cmd, 'blockers': []}
        
            # Ajouter les postes bloquants éventuels
            if delay:
                if delay.x_studio_poste_bloquant_1:
                    operation_links[workcenter.id]['blockers'].append(delay.x_studio_poste_bloquant_1.id)
                if delay.x_studio_poste_bloquant_2:
                    operation_links[workcenter.id]['blockers'].append(delay.x_studio_poste_bloquant_2.id)
        
            previous_workcenter = workcenter
            sequence += 1
        
        # Conversion du délai total en jours (base 480 min/jour) arrondi au supérieur
        delai_jours = math.ceil(delai_total_minutes / 480)
        
        # Affecter les opérations et le délai sur la nomenclature
        if nomenclatures_data:
            nomenclatures_data[0]['operation_ids'] = operation_cmds
            nomenclatures_data[0]['ready_to_produce'] = 'asap'
            nomenclatures_data[0]['consumption'] = 'flexible'
            nomenclatures_data[0]['allow_operation_dependencies'] = True
            nomenclatures_data[0]['produce_delay'] = delai_jours
        
        # Vérifier que la nomenclature a bien un ID
        #nomenclature_dict = nomenclatures_data[0]
        #bom_id = nomenclature_dict.get('id')
        if not nomenclatures_data[0].get('id'):
            created_bom = self.env['mrp.bom'].create(nomenclatures_data[0])
            nomenclatures_data[0]['id'] = created_bom.id
        else:
            created_bom = self.env['mrp.bom'].browse(nomenclatures_data[0]['id'])
        
        # Après création effective de la nomenclature
        bom = self.env['mrp.bom'].browse(created_bom_id)
        operations = bom.operation_ids
        op_by_wc = {op.workcenter_id.id: op for op in operations}
        
        for wc_id, link_data in operation_links.items():
            op = op_by_wc.get(wc_id)
            if op and link_data['blockers']:
                blockers = []
                for bid in link_data['blockers']:
                    blocker_op = op_by_wc.get(bid)
                    if blocker_op:
                        blockers.append(blocker_op.id)
                if blockers:
                    op.write({'operation_dependency_ids': [(6, 0, blockers)]})

        cursor.close()
        temp_file.close()
        cursor1.close()
        
        #for bom_data in nomenclatures_data:
        #    product_tmpl_id = bom_data.get("product_tmpl_id")
        #    if product_tmpl_id in zero_delay_products:
        #        bom_data["produce_delay"] = 0
        #    elif product_tmpl_id in delaifab_delay_products:
        #        bom_data["produce_delay"] = delaifab

        for so in so_data:
            for so_to_update in self.env['sale.order'].browse(so):
                so_to_update.write(so_data[so])
                # so_to_update.action_confirm()
                message = _("Sales Order Updated: ") + so_to_update._get_html_link()
                self.message_post(body=message)

        for bom in self.env['mrp.bom'].create(nomenclatures_data):
            note = "Bill Of Material Created > %s" % (bom.display_name)
            message = _("Bill Of Material has been Created: ") + bom._get_html_link()
            self.message_post(body=message)
            self.env.cr.commit()

        self.state = 'done'
    
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
                                         'message': "%s" % (ref or 'Unable to find data'),
                                         'path': "%s - %s " % (path, self.description),
                                         'func': operation,
                                         'line': 1,
                                         'connector_id': self.id})
        except psycopg2.Error:
            pass
