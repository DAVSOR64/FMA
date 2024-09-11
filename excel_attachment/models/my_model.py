from odoo import models, fields, api
import io
import base64
import xlsxwriter

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.multi
    def write(self, vals):
        result = super(StockPicking, self).write(vals)

        # Vérifier si le transfert de stock est complété
        if 'state' in vals and vals['state'] == 'done':
            # Appel de la fonction pour générer et attacher le fichier Excel
            self.generate_excel_attachment()

        return result

    def generate_excel_attachment(self):
        # Créez le fichier Excel en mémoire
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet()

        # Ajout des en-têtes dans le fichier Excel (par exemple)
        worksheet.write('A1', 'Product')
        worksheet.write('B1', 'Quantity')
        worksheet.write('C1', 'Source Location')
        worksheet.write('D1', 'Destination Location')

        row = 1
        # Boucler sur les lignes de mouvement de stock pour récupérer les produits et quantités
        for move_line in self.move_lines:
            worksheet.write(row, 0, move_line.product_id.name)
            worksheet.write(row, 1, move_line.product_uom_qty)
            worksheet.write(row, 2, move_line.location_id.name)
            worksheet.write(row, 3, move_line.location_dest_id.name)
            row += 1

        workbook.close()

        # Encoder le fichier en base64 pour le stocker dans Odoo
        output.seek(0)
        file_data = base64.b64encode(output.read())

        # Créer la pièce jointe
        attachment = self.env['ir.attachment'].create({
            'name': f'Stock_Picking_{self.name}.xlsx',
            'type': 'binary',
            'datas': file_data,
            'store_fname': f'Stock_Picking_{self.name}.xlsx',
            'res_model': 'stock.picking',
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        # Lier la pièce jointe à ce document
        self.message_post(body="Stock picking Excel attached", attachment_ids=[attachment.id])
