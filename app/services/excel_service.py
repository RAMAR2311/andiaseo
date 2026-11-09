import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def aplicar_estilos_celda(celda, font=None, fill=None, alignment=None, border=None, number_format=None):
    if font: celda.font = font
    if fill: celda.fill = fill
    if alignment: celda.alignment = alignment
    if border: celda.border = border
    if number_format: celda.number_format = number_format


def generar_kardex_excel(movimientos, parametros_filtro=None):
    """
    Genera un archivo XLSX formal para auditoría del Kardex usando openpyxl.
    Retorna un objeto io.BytesIO listo para enviar como descarga HTTP.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Kardex de Movimientos"
    ws.views.sheetView[0].showGridLines = True

    # Paleta de colores corporativa (Azul marino industrial y acento verde esmeralda)
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")  # Azul marino profundo
    sub_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")     # Gris claro
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="475569")
    regular_font = Font(name="Calibri", size=10)
    bold_font = Font(name="Calibri", size=10, bold=True)
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Bloque de Título
    ws.merge_cells('A1:I1')
    ws['A1'] = "ANDIASEO - GESTIÓN INTEGRAL DE QUÍMICOS Y ASEO"
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(vertical='center')

    ws.merge_cells('A2:I2')
    ws['A2'] = f"REPORTE OFICIAL DE KARDEX Y MOVIMIENTOS | Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws['A2'].font = subtitle_font
    ws['A2'].alignment = Alignment(vertical='center')

    fila_inicio = 4
    if parametros_filtro:
        ws[f'A{fila_inicio}'] = f"Filtros aplicados: {parametros_filtro}"
        ws[f'A{fila_inicio}'].font = subtitle_font
        fila_inicio += 1

    fila_inicio += 1

    # Encabezados de tabla
    headers = [
        "ID",
        "Fecha / Hora",
        "Tipo de Movimiento",
        "Producto",
        "Presentación",
        "Lote",
        "Cant. Mov.",
        "Precio / Costo Unit.",
        "Stock Nuevo",
        "Doc. Soporte",
        "Usuario",
        "Observaciones / Motivo"
    ]

    for col_num, h_text in enumerate(headers, 1):
        c = ws.cell(row=fila_inicio, column=col_num, value=h_text)
        aplicar_estilos_celda(c, font=header_font, fill=header_fill, alignment=Alignment(horizontal="center", vertical="center"), border=thin_border)
    
    ws.row_dimensions[fila_inicio].height = 26

    # Datos
    fila_actual = fila_inicio + 1
    for m in movimientos:
        fecha_str = m.fecha.strftime('%Y-%m-%d %H:%M') if m.fecha else ""
        prod_str = f"{m.producto.codigo_referencia} - {m.producto.nombre}" if m.producto else "N/A"
        pres_str = m.presentacion.nombre_presentacion if m.presentacion else f"Granel ({m.producto.unidad_base if m.producto else ''})"
        lote_str = m.lote.numero_lote if m.lote else "N/A"
        usr_str = m.usuario.nombre if m.usuario else "N/A"
        
        cant_val = float(m.cantidad or 0)
        precio_val = float(m.precio_unitario or 0)
        stock_nuevo_val = float(m.stock_nuevo or 0)

        # Colorear según ingreso o salida
        cant_font = Font(name="Calibri", size=10, bold=True, color="047857" if cant_val > 0 else "B91C1C")

        fila_datos = [
            (m.id, regular_font, Alignment(horizontal="center")),
            (fecha_str, regular_font, Alignment(horizontal="center")),
            (m.tipo_legible, regular_font, Alignment(horizontal="left")),
            (prod_str, regular_font, Alignment(horizontal="left")),
            (pres_str, regular_font, Alignment(horizontal="left")),
            (lote_str, regular_font, Alignment(horizontal="center")),
            (cant_val, cant_font, Alignment(horizontal="right")),
            (precio_val, regular_font, Alignment(horizontal="right")),
            (stock_nuevo_val, bold_font, Alignment(horizontal="right")),
            (m.documento_soporte or "-", regular_font, Alignment(horizontal="center")),
            (usr_str, regular_font, Alignment(horizontal="left")),
            (m.motivo_observaciones or "", regular_font, Alignment(horizontal="left"))
        ]

        ws.row_dimensions[fila_actual].height = 20
        for col_num, (valor, f_style, a_style) in enumerate(fila_datos, 1):
            c = ws.cell(row=fila_actual, column=col_num, value=valor)
            aplicar_estilos_celda(c, font=f_style, alignment=a_style, border=thin_border)
            if col_num in (7, 8):
                c.number_format = '#,##0.00'

        fila_actual += 1

    # Ajuste automático del ancho de columnas
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row < fila_inicio:
                continue
            if cell.value:
                val_str = str(cell.value)
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 40)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generar_inventario_valorizado_excel(productos):
    """
    Genera el reporte oficial de Inventario Valorizado General por producto y presentación.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario Valorizado"
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")  # Verde azulado / Teal
    total_fill = PatternFill(start_color="CCFBF1", end_color="CCFBF1", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=16, bold=True, color="0F766E")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="475569")
    regular_font = Font(name="Calibri", size=10)
    bold_font = Font(name="Calibri", size=10, bold=True)
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws.merge_cells('A1:H1')
    ws['A1'] = "ANDIASEO - BALANCE DE INVENTARIO VALORIZADO"
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(vertical='center')

    ws.merge_cells('A2:J2')
    ws['A2'] = f"Corte a fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Costeo Promedio Ponderado con Discriminación de IVA (19%)"
    ws['A2'].font = subtitle_font
    ws['A2'].alignment = Alignment(vertical='center')

    fila_header = 4
    headers = [
        "Código Ref.",
        "Categoría",
        "Producto / Químico",
        "Producto / Insumo",
        "Tipo",
        "Presentación Comercial",
        "Unidad",
        "Stock Físico",
        "Costo Unit. Compra ($)",
        "Subtotal Compra ($)",
        "Costo Unidad ($)",
        "Subtotal Costo ($)",
        "IVA 19% ($)",
        "Total con IVA ($)"
        "Total con IVA ($)",
        "Precio de Venta ($)"
    ]

    for col_num, h_text in enumerate(headers, 1):
        c = ws.cell(row=fila_header, column=col_num, value=h_text)
        aplicar_estilos_celda(c, font=header_font, fill=header_fill, alignment=Alignment(horizontal="center", vertical="center"), border=thin_border)

    ws.row_dimensions[fila_header].height = 26

    fila_actual = fila_header + 1
    total_subtotal_gen = 0.0

    for prod in productos:
        cat_nombre = prod.categoria.nombre if prod.categoria else "Sin categoría"
        stock_f = float(prod.stock_actual_total or 0)
        costo_u = float(prod.costo_unitario_base or 0)
        subtotal_f = stock_f * costo_u
        iva_f = subtotal_f * 0.19
        total_f = subtotal_f + iva_f
        p_venta = float(prod.precio_venta_base or 0)
        total_subtotal_gen += subtotal_f

        fila_datos = [
            (prod.codigo_referencia, regular_font, Alignment(horizontal="center")),
            (cat_nombre, regular_font, Alignment(horizontal="left")),
            (prod.nombre, bold_font, Alignment(horizontal="left")),
            (prod.tipo_legible, regular_font, Alignment(horizontal="left")),
            (prod.unidad_legible, regular_font, Alignment(horizontal="center")),
            (stock_f, regular_font, Alignment(horizontal="right")),
            (costo_u, regular_font, Alignment(horizontal="right")),
            (subtotal_f, regular_font, Alignment(horizontal="right")),
            (iva_f, regular_font, Alignment(horizontal="right")),
            (total_f, bold_font, Alignment(horizontal="right")),
            (p_venta, bold_font, Alignment(horizontal="right"))
        ]
        ws.row_dimensions[fila_actual].height = 20
        for col_num, (valor, f_style, a_style) in enumerate(fila_datos, 1):
            c = ws.cell(row=fila_actual, column=col_num, value=valor)
            aplicar_estilos_celda(c, font=f_style, alignment=a_style, border=thin_border)
            if col_num == 6:
                c.number_format = '#,##0.00'
            elif col_num in (7, 8, 9, 10, 11):
                c.number_format = '$#,##0.00'
        fila_actual += 1

    # Fila de Totales Generales
    total_iva_gen = total_subtotal_gen * 0.19
    total_con_iva_gen = total_subtotal_gen + total_iva_gen

    ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=7)
    tot_label = ws.cell(row=fila_actual, column=1, value="TOTALES CONSOLIDADOS:")
    tot_label.alignment = Alignment(horizontal="right", vertical="center")
    tot_label.font = Font(name="Calibri", size=11, bold=True, color="1450A8")

    c_sub = ws.cell(row=fila_actual, column=8, value=total_subtotal_gen)
    c_sub.number_format = '$#,##0.00'
    c_sub.font = Font(name="Calibri", size=11, bold=True)
    c_sub.alignment = Alignment(horizontal="right", vertical="center")

    c_iva = ws.cell(row=fila_actual, column=9, value=total_iva_gen)
    c_iva.number_format = '$#,##0.00'
    c_iva.font = Font(name="Calibri", size=11, bold=True)
    c_iva.alignment = Alignment(horizontal="right", vertical="center")

    tot_val = ws.cell(row=fila_actual, column=10, value=total_con_iva_gen)
    tot_val.number_format = '$#,##0.00'
    tot_val.font = Font(name="Calibri", size=12, bold=True, color="1450A8")
    tot_val.alignment = Alignment(horizontal="right", vertical="center")
    tot_val.fill = total_fill
    
    for c_idx in range(1, 11):
        ws.cell(row=fila_actual, column=c_idx).border = thin_border

    ws.row_dimensions[fila_actual].height = 26

    # Ajuste de anchos
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row < fila_header:
                continue
            if cell.value:
                val_str = str(cell.value)
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 40)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
