import io
import base64
from odoo import models, fields, api
import xlsxwriter

class SaleOrder(models.Model):
    _inherit = 'sale.order'  # Changez cela selon votre modèle

    state = fields.Selection(selection_add=[('out', 'OUT')])

    @api.multi
    def write(self, vals):
        result = super(SaleOrder, self).write(vals)

        if 'state' in vals and vals['state'] == 'out':
            # Appel de la fonction pour générer et attacher le fichier Excel
            self.generate_excel_attachment()

        return result

    def generate_excel_attachment(self):
        # Créez le fichier Excel en mémoire
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet()

        # Ajout de données dans le fichier Excel (exemple)
        worksheet.write('A1', 'Product')
        worksheet.write('B1', 'Quantity')

        row = 1
        for line in self.order_line:
            worksheet.write(row, 0, line.product_id.name)
            worksheet.write(row, 1, line.product_uom_qty)
            row += 1

        workbook.close()

        # Encoder le fichier en base64 pour le stocker dans Odoo
        output.seek(0)
        file_data = base64.b64encode(output.read())

        # Créer la pièce jointe
        attachment = self.env['ir.attachment'].create({
            'name': f'Sale_Order_{self.name}.xlsx',
            'type': 'binary',
            'datas': file_data,
            'store_fname': f'Sale_Order_{self.name}.xlsx',
            'res_model': 'sale.order',
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        # Lier la pièce jointe à ce document (optionnel, déjà fait par res_model/res_id)
        self.message_post(body="Excel file attached", attachment_ids=[attachment.id])
