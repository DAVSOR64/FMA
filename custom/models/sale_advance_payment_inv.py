from odoo import models, api
from odoo.exceptions import UserError

class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def create_invoices(self):
        for wizard in self:
            sales = self.env['sale.order'].browse(self._context.get('active_ids', []))
            for sale in sales:
                partner = sale.partner_id

                # Vérifie si le client a l'étiquette "Entreprise Générale"
                if partner.category_id.filtered(lambda c: c.name == "Entreprise Générale"):
                    # Remplace 'x_studio_champ' par le nom technique exact de ton champ Studio à vérifier
                    if not sale.so_commande_client:
                        raise UserError(
                            f"Le champ requis n'est pas rempli pour le client {partner.name}. Impossible de créer la facture."
                        )

        # Si tout est OK, on appelle la méthode standard
        return super(SaleAdvancePaymentInv, self).create_invoices()
