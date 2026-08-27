from weasyprint import HTML
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(base_dir, 'documentacao_luft.html')
pdf_path = os.path.join(base_dir, 'Documentacao_Luft_Logistics_Keyrus.pdf')

HTML(filename=html_path).write_pdf(pdf_path)
print(f'PDF gerado: {pdf_path}')
