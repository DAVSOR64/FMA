from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_studio_mode_de_rglement_1 = fields.Selection(
        [
            ('ESPECES','ESPECES'),
            ('CHEQUE BANCAIRE','CHEQUE BANCAIRE'),
            ('VIREMENT BANCAIRE','VIREMENT BANCAIRE'),
            ('L.C.R. DIRECTE','L.C.R. DIRECTE'),
            ('L.C.R. A L ACCEPTATION','L.C.R. A L ACCEPTATION'),
            ('PRELEVEMENT','PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE','L.C.R. MAGNETIQUE'),
            ('BOR','BOR'),
            ('CARTE BANCAIRE','CARTE BANCAIRE'),
            ('CREDIT DOCUMENTAIRE','CREDIT DOCUMENTAIRE'),
        ],
        string="Mode de Règlement",
    default = 'VIREMENT BANCAIRE',)
    
    part_mode_de_reglement = fields.Selection(
        [
            ('ESPECES','ESPECES'),
            ('CHEQUE BANCAIRE','CHEQUE BANCAIRE'),
            ('VIREMENT BANCAIRE','VIREMENT BANCAIRE'),
            ('L.C.R. DIRECTE','L.C.R. DIRECTE'),
            ('L.C.R. A L ACCEPTATION','L.C.R. A L ACCEPTATION'),
            ('PRELEVEMENT','PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE','L.C.R. MAGNETIQUE'),
            ('BOR','BOR'),
            ('CARTE BANCAIRE','CARTE BANCAIRE'),
            ('CREDIT DOCUMENTAIRE','CREDIT DOCUMENTAIRE'),
        ],
        string="Mode de Règlement",
    default = 'VIREMENT BANCAIRE',)

    part_commercial = fields.Selection(
        [
            ('A DEFINIR','A Définir'),
            ('Adrien LAISNE','Adrien LAISNE'),
            ('Alexandre BLOT','Alexandre BLOT'),
            ('Alexandre DAUDE','Alexandre DAUDE'),
            ('Alexandre DODE','Alexandre DODE'),
            ('Alexandre POILANE','Alexandre POILANE'),
            ('Cédric SEGUIN','Cédric SEGUIN'),
            ('Carlos DA TORRE','Carlos DA TORRE'),
            ('Cédric SANDRE','Cédric SANDRE'),
            ('Christian GUILLARD','Christian GUIHARD'),
            ('Cyril JACQUEMET','Cyril JACQUEMET'),
            ('David JOUGLARD','David JOUGLARD'),
            ('David CHARPENTIER','David CHARPENTIER'),
            ('Franck SARAZIN','Franck SARAZIN'),
            ('Frédéric DUCHEMIN','Frédéric DUCHEMIN'),
            ('Gregory GIROLLET','Grégory GIROLLET'),
            ('Guillaume GALLARDO','Guillaume GALLARDO'),
            ('Hubert BOURDARAIS','Hubert BOURDARIAS'),
            ('Jean JUSTAFRE','Jean JUSTAFRE'),
            ('Jérôme DECAIX','Jérôme DECAIX'),
            ('Karine HERVOUET','Karine HERVOUET'),
            ('Mathieu LACAM','Mathieu LACAM'),
            ('Mathieu LOISEAUX','Mathieu LOISEAUX'),
            ('Maxime DE SOUSA','Maxime DE SOUSA'),
            ('Mickaël DUH','Mickaël DUH'),
            ('Nicolas FONTENEAU','Nicolas FONTENEAU'),
            ('Nicolas FONTENEAU 1','Nicolas FONTENEAU 1'),
            ('Olivier PECHEUR','Olivier PECHEUR'),
            ('Pierre PINEAU','Pierre PINEAU'),
            ('Pierre ROYER','Pierre ROYER'),
            ('Quentin MOREAU','Quentin MOREAU'),
            ('Quentin MOREAU 1','Quentin MOREAU 1'),
            ('Richard ROTH','Richard ROTH'),
            ('Richard ROTH 1','Richard ROTH 1'),
            ('Richard ROTH 2','Richard ROTH 2'),
            ('Recrutement 1','Recrutement 1'),
            ('Recrutement 2','Recrutement 2'),
            ('Recrutement 3','Recrutement 3'),
            ('Recrutement 4','Recrutement 4'),
            ('Recrutement 5','Recrutement 5'),
            ('Sami ABID','Sami ABID'),
            ('Stéphane MOUSSEL','Stéphane MOUSSEL'),
            ('Vincent PERROT','Vincent PERROT'),
            ('Client Direct','Client Direct'),
            ('Sans Affectation','Sans Affectation'),
        ],
        string = "Commercial",
    default = "A DEFINIR",)

    part_civilite = fields.Selection(
        [
            ('SARL','SARL'),
            ('EURL','EURL'),
            ('EI','EI'),
            ('SAS','SAS'),
            ('SASU','SASU'),
            ('SCI','SCI'),
            ('Madame ou Monsieur','Madame ou Monsieur'),
            ('SA','SA'),
            ('SNC','SNC'),
            ('SCOP','SCOP'),
            ('SCEA','SCEA'),
            ('SELARL','SELARL'),
            ('LLC','LLC'),
            ('COLLECTIVITE','COLLECTIVITE'),
        ],string="Civilité",
    default = "SARL",)

    part_siren = fields.Char(string="SIREN")
    part_bic = fields.Char(string="BIC")
    part_iban = fields.Char(string="IBAN")
    part_affacturage = fields.Boolean(string="Affacturage")
    part_couverture = fields.Boolean(string="ALLIANZ ND COVER")
    part_date_couverture = fields.Date(string="ALLIANZ ND COVER")
    part_montant_couverture = fields.Float(string="ALLIANZ COUVERTURE EULEUR")
    part_decision = fields.Char(string="ASSURANCE-CREDIT")
    part_code_tiers = fields.Integer(string="Code Tiers")
    
    @api.model
    def create(self, vals):
        # Vérifier si le contact est une société
        if vals.get('is_company', False):
            # Récupérer la dernière valeur de 'part_code_tiers' parmi les sociétés uniquement
            last_record = self.search([('is_company', '=', True)], order='part_code_tiers desc', limit=1)
            last_code = last_record.part_code_tiers if last_record else 0
            new_code = last_code + 1
            
            # Attribuer la nouvelle valeur de 'part_code_tiers'
            vals['part_code_tiers'] = new_code
        
        # Appel de la méthode create de la super-classe avec les valeurs modifiées
        return super(ResPartner, self).create(vals)
 
    
    def _prepare_order(self):
        order_vals = super(ResPartner, self)._prepare_order()
        order_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        return order_vals
