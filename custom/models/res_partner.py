from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_studio_mode_de_rglement_1 = fields.Selection(
        [
            ('01','ESPECES'),
            ('03','CHEQUE BANCAIRE'),
            ('11','VIREMENT BANCAIRE'),
            ('12','L.C.R. DIRECTE'),
            ('13','L.C.R. A L ACCEPTATION'),
            ('15','PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE','L.C.R. MAGNETIQUE'),
            ('18','BOR'),
            ('CARTE BANCAIRE','CARTE BANCAIRE'),
            ('CREDIT DOCUMENTAIRE','CREDIT DOCUMENTAIRE'),
        ],
        string="Mode de Règlement",
    default = 'VIREMENT BANCAIRE',)
    
    part_mode_de_reglement = fields.Selection(
        [
            ('01','ESPECES'),
            ('03','CHEQUE BANCAIRE'),
            ('11','VIREMENT BANCAIRE'),
            ('12','L.C.R. DIRECTE'),
            ('13','L.C.R. A L ACCEPTATION'),
            ('15','PRELEVEMENT'),
            ('L.C.R. MAGNETIQUE','L.C.R. MAGNETIQUE'),
            ('18','BOR'),
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
            ('Grégory GIROLLET','Grégory GIROLLET'),
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
        # Vérifie si le booléen est coché
        if vals.get('x_studio_gneration_n_compte_1', False):
            # Récupère la dernière valeur de x_studio_compte (chez les sociétés uniquement)
            last_record = self.search([('is_company', '=', True), ('x_studio_compte', '!=', False)], order='x_studio_compte desc', limit=1)
            last_code = last_record.x_studio_compte if last_record else 0
            new_code = last_code + 1

            # Attribue la nouvelle valeur de x_studio_compte
            vals['x_studio_compte'] = new_code

            # Décoche le booléen (pratique)
            vals['x_studio_gneration_n_compte_1'] = False

        # Appel de la méthode parent
        return super(ResPartner, self).create(vals)

    def write(self, vals):
        for partner in self:
            # Si la case est cochée, génère le numéro uniquement si pas déjà défini
            if vals.get('x_studio_gneration_n_compte_1', False) and not partner.x_studio_compte:
                last_record = self.search([('is_company', '=', True), ('x_studio_compte', '!=', False)], order='x_studio_compte desc', limit=1)
                last_code = last_record.x_studio_compte if last_record else 0
                new_code = last_code + 1

                partner.x_studio_compte = new_code

                # Décoche le booléen après génération
                vals['x_studio_gneration_n_compte_1'] = False

        return super(ResPartner, self).write(vals)
 
    
    def _prepare_order(self):
        order_vals = super(ResPartner, self)._prepare_order()
        order_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        return order_vals
