import io
import re
from decimal import Decimal
from datetime import datetime, date
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.models import db, Producto, PresentacionComercial, Categoria, Tercero, Lote
from app.services.kardex_service import registrar_movimiento


def normalizar_empaque_unidad(texto_empaque):
    """
    Analiza cadenas de empaque/unidad como:
    'UND', 'KILO', 'LIBRA', 'PAQ X 10', 'GALON', 'CUÑETE', 'PAR', 'PASTA', '500GR'
    y retorna una tupla (tipo_producto, unidad_base, nombre_presentacion, factor_conversion).
    """
    if not texto_empaque or pd.isna(texto_empaque):
        return ('accesorio_herramienta', 'unidades', 'Unidad (Und)', Decimal('1.0'))
    
    txt = str(texto_empaque).strip().upper()
    txt = re.sub(r'\s+', ' ', txt)

    # 1. Líquidos en Galón o Cuñete
    if 'CUÑ' in txt or 'CUN' in txt:
        return ('quimico_liquido', 'litros', 'Cuñete (20L / 5 Gal)', Decimal('20.0'))
    if 'GAL' in txt:
        return ('quimico_liquido', 'litros', 'Galón (3.8L)', Decimal('3.785'))
    if '1000ML' in txt or '1L' in txt or 'LITRO' in txt:
        return ('quimico_liquido', 'litros', 'Litro (1000ml)', Decimal('1.0'))

    # 2. Polvos y Pesos
    if 'KIL' in txt or txt == 'KG' or 'KGS' in txt:
        return ('quimico_polvo', 'kilogramos', 'Kilo (1 Kg)', Decimal('1.0'))
    if 'LIBRA' in txt or txt == 'LB':
        return ('quimico_polvo', 'kilogramos', 'Libra (500 gr)', Decimal('0.5'))
    if '500GR' in txt or '500G' in txt or '500 GR' in txt:
        return ('quimico_polvo', 'kilogramos', 'Pote / Bolsa 500g', Decimal('0.5'))

    # 3. Paquetes (Bolsas, Toallas, etc.)
    if 'PAQ' in txt:
        return ('accesorio_herramienta', 'unidades', txt, Decimal('1.0'))

    # 4. Pares (Guantes)
    if 'PAR' in txt:
        return ('accesorio_herramienta', 'unidades', 'Par', Decimal('1.0'))

    # 5. Barras o Pastas (Jabón Rey)
    if 'PASTA' in txt or 'BARRA' in txt:
        return ('accesorio_herramienta', 'unidades', 'Pasta / Barra', Decimal('1.0'))

    # Default: Unidad
    return ('accesorio_herramienta', 'unidades', 'Unidad (Und)', Decimal('1.0'))


def procesar_archivo_masivo_excel(file_storage, usuario_id):
    """
    Lee un archivo Excel/CSV cargado por el cliente y registra masivamente:
    - Categorías automáticas
    - Proveedores (Terceros)
    - Productos de inventario
    - Presentación comercial con stock inicial
    - Asiento en Kardex como saldo inicial
    """
    try:
        # Intentar leer con pandas (soporta .xlsx y .xls)
        df = pd.read_excel(file_storage)
    except Exception:
        file_storage.seek(0)
        df = pd.read_csv(file_storage)

    # Normalizar nombres de columnas a mayúsculas sin espacios
    df.columns = [str(col).strip().upper() for col in df.columns]

    # Encontrar mapeo de columnas flexible
    col_codigo = next((c for c in df.columns if any(k in c for k in ['COD', 'REFERENCIA', 'ITEM'])), None)
    col_nombre = next((c for c in df.columns if any(k in c for k in ['NOMBRE', 'DESCRIPCION', 'PRODUCTO', 'DETALLE'])), None)
    col_proveedor = next((c for c in df.columns if any(k in c for k in ['PROVEEDOR', 'TERCERO', 'DISTRIBUIDOR', 'MARCA'])), None)
    col_presentacion = next((c for c in df.columns if any(k in c for k in ['PRESENTACION', 'MEDIDA', 'UNIDAD', 'FORMATO', 'EMPAQUE'])), None)
    col_cantidad = next((c for c in df.columns if any(k in c for k in ['CANTIDAD', 'STOCK', 'EXISTENCIA', 'CANT'])), None)
    col_costo = next((c for c in df.columns if any(k in c for k in ['COSTO', 'COMPRA', 'VALOR UNITARIO', 'VALOR_UNITARIO'])), None)
    col_precio = next((c for c in df.columns if any(k in c for k in ['PRECIO', 'VENTA', 'PVP'])), None)

    # Si no tiene encabezados nombrados, inferir por orden de columna típico:
    # 0: Código, 1: Nombre, 2: Proveedor, 3: Presentación/Medida, 4: Cantidad, 5: Costo, 6: Precio
    cols_list = list(df.columns)
    if not col_codigo and len(cols_list) >= 1:
        col_codigo = cols_list[0]
    if not col_nombre and len(cols_list) >= 2:
        col_nombre = cols_list[1]
    if not col_proveedor and len(cols_list) >= 3:
        col_proveedor = cols_list[2]
    if not col_presentacion and len(cols_list) >= 4:
        col_presentacion = cols_list[3]
    if not col_cantidad and len(cols_list) >= 5:
        col_cantidad = cols_list[4]

    if not col_codigo or not col_nombre:
        raise ValueError("El archivo debe contener al menos una columna de 'Código' y una de 'Nombre' del producto.")

    # Asegurar categoría por defecto "Productos de Distribución"
    cat_distribucion = Categoria.query.filter_by(nombre="Línea General de Aseo y Distribución").first()
    if not cat_distribucion:
        cat_distribucion = Categoria(
            nombre="Línea General de Aseo y Distribución",
            descripcion="Categoría consolidada de productos empacados para distribución."
        )
        db.session.add(cat_distribucion)
        db.session.flush()

    resumen = {
        'creados': 0,
        'actualizados': 0,
        'proveedores_creados': 0,
        'omitos': 0,
        'total_filas': len(df)
    }

    proveedores_cache = {}

    for idx, row in df.iterrows():
        codigo_raw = row.get(col_codigo)
        if pd.isna(codigo_raw) or not str(codigo_raw).strip():
            resumen['omitos'] += 1
            continue

        codigo = str(codigo_raw).strip().upper()
        # Limpiar comas o decimales accidentales en códigos como COD089,5 -> COD089-5
        codigo = re.sub(r'[,]', '-', codigo)

        nombre = str(row.get(col_nombre, '')).strip()
        if not nombre or nombre.upper() in ['TOTAL', 'SUBTOTAL', 'TOTALES']:
            resumen['omitos'] += 1
            continue

        # Proveedor
        prov_nombre = str(row.get(col_proveedor, '')).strip().upper() if col_proveedor and not pd.isna(row.get(col_proveedor)) else None
        tercero_obj = None
        if prov_nombre and prov_nombre not in ['NAN', 'NONE', '-', '']:
            if prov_nombre in proveedores_cache:
                tercero_obj = proveedores_cache[prov_nombre]
            else:
                tercero_obj = Tercero.query.filter(Tercero.nombre_razon_social.ilike(f'%{prov_nombre}%')).first()
                if not tercero_obj:
                    # Crear proveedor automático
                    nit_generado = f"PROV-{prov_nombre[:10]}-{hash(prov_nombre)%1000:03d}"
                    tercero_obj = Tercero(
                        tipo='proveedor',
                        documento_nit=nit_generado,
                        nombre_razon_social=prov_nombre,
                        contacto_nombre="Contacto Comercial",
                        activo=True
                    )
                    db.session.add(tercero_obj)
                    db.session.flush()
                    resumen['proveedores_creados'] += 1
                proveedores_cache[prov_nombre] = tercero_obj

        # Presentación / Medida
        pres_raw = str(row.get(col_presentacion, 'UND')).strip() if col_presentacion and not pd.isna(row.get(col_presentacion)) else 'UND'
        tipo_prod, unidad_base, nombre_pres, factor_conv = normalizar_empaque_unidad(pres_raw)

        # Cantidad Stock Inicial
        cant_inicial = Decimal('0.0')
        if col_cantidad and not pd.isna(row.get(col_cantidad)):
            try:
                val_cant = str(row.get(col_cantidad)).replace(',', '.')
                cant_inicial = Decimal(val_cant)
                if cant_inicial < 0:
                    cant_inicial = Decimal('0.0')
            except Exception:
                cant_inicial = Decimal('0.0')

        # Costo de Compra
        costo_unit = Decimal('0.0')
        if col_costo and not pd.isna(row.get(col_costo)):
            try:
                val_costo = str(row.get(col_costo)).replace('$', '').replace(' ', '').replace('.', '').replace(',', '.')
                costo_unit = Decimal(val_costo)
            except Exception:
                costo_unit = Decimal('0.0')

        # Precio de Venta
        precio_venta = Decimal('0.0')
        if col_precio and not pd.isna(row.get(col_precio)):
            try:
                val_precio = str(row.get(col_precio)).replace('$', '').replace(' ', '').replace('.', '').replace(',', '.')
                precio_venta = Decimal(val_precio)
            except Exception:
                precio_venta = Decimal('0.0')

        # Buscar si el producto ya existe por código
        producto = Producto.query.filter_by(codigo_referencia=codigo).first()
        es_nuevo = False
        if not producto:
            producto = Producto(
                codigo_referencia=codigo,
                nombre=nombre,
                categoria_id=cat_distribucion.id,
                tipo_producto=tipo_prod,
                unidad_base=unidad_base,
                costo_unitario_base=costo_unit,
                precio_venta_base=precio_venta,
                stock_actual_total=Decimal('0.0'),
                stock_minimo_alerta=Decimal('5.0'),
                requiere_vencimiento=True if tipo_prod in ('quimico_liquido', 'quimico_polvo') else False,
                descripcion=f"Proveedor: {prov_nombre or 'General'}. Formato: {nombre_pres}",
                activo=True
            )
            db.session.add(producto)
            db.session.flush()
            es_nuevo = True
            resumen['creados'] += 1
        else:
            # Actualizar nombres y precios si estaban en 0
            if costo_unit > 0:
                producto.costo_unitario_base = costo_unit
            if precio_venta > 0:
                producto.precio_venta_base = precio_venta
            resumen['actualizados'] += 1

        # Presentación Comercial asociada
        pres_com = PresentacionComercial.query.filter_by(producto_id=producto.id, nombre_presentacion=nombre_pres).first()
        if not pres_com:
            pres_com = PresentacionComercial(
                producto_id=producto.id,
                nombre_presentacion=nombre_pres,
                factor_conversion_base=factor_conv,
                costo_promedio_unitario=costo_unit,
                precio_referencia=precio_venta,
                stock_actual=Decimal('0.0'),
                activo=True
            )
            db.session.add(pres_com)
            db.session.flush()

        # Si viene cantidad de stock inicial > 0, registrar apertura
        if cant_inicial > 0 and es_nuevo:
            lote_num = f"LOT-APERTURA-{datetime.now().strftime('%y%m%d')}"
            lote_obj = Lote.query.filter_by(producto_id=producto.id, numero_lote=lote_num).first()
            if not lote_obj:
                venc = date.today().replace(year=date.today().year + 2) if producto.requiere_vencimiento else None
                lote_obj = Lote(
                    producto_id=producto.id,
                    presentacion_id=pres_com.id,
                    numero_lote=lote_num,
                    fecha_produccion=date.today(),
                    fecha_vencimiento=venc,
                    cantidad_inicial=cant_inicial,
                    cantidad_actual=Decimal('0.0'),
                    estado='ACTIVO'
                )
                db.session.add(lote_obj)
                db.session.flush()

            # Movimiento Kardex
            registrar_movimiento(
                usuario_id=usuario_id,
                producto_id=producto.id,
                tipo_movimiento='ENTRADA_COMPRA',
                cantidad=cant_inicial,
                motivo_observaciones=f"Carga Masiva Inicial. Proveedor: {prov_nombre or 'General'}",
                precio_unitario=costo_unit,
                presentacion_id=pres_com.id,
                lote_id=lote_obj.id,
                tercero_id=tercero_obj.id if tercero_obj else None,
                documento_soporte="APERTURA-MASIVA",
                commit=False
            )

    db.session.commit()
    return resumen


def generar_plantilla_carga_masiva_excel():
    """Genera un archivo Excel de ejemplo con el formato listo para que el usuario complete."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Carga Masiva Productos"
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color="1450A8", end_color="1450A8", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = [
        "CODIGO",
        "NOMBRE_PRODUCTO",
        "PROVEEDOR",
        "PRESENTACION_EMPAQUE",
        "CANTIDAD_STOCK",
        "COSTO_COMPRA",
        "PRECIO_VENTA"
    ]

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # Filas de ejemplo basadas en la imagen real
    ejemplos = [
        ("COD011", "BAYETILLA BLANCA METRO", "IMPERIO", "UND", 3, 7742, 9193),
        ("COD013", "BLANQUEADOR 5,25%", "ORION", "CUÑETE", 14, 32836, 52751),
        ("COD005", "AMBIENTADOR", "ORION", "GALON", 18, 14918, 23966),
        ("COD016", "BOLSA JUMBO NEGRA", "SURTIPLAST", "PAQ X 10", 92, 6100, 9800),
        ("COD034", "DETERGENTE EN POLVO", "ARA", "KILO", 27, 3990, 6410),
        ("COD045", "GUANTES IND CALIBRE 35 TALLA 8", "IMPERIO", "PAR", 12, 3833, 6158),
        ("COD052", "JABON REY X 300 GRS", "DISTRIGUILA", "PASTA", 14, 2440, 3920),
        ("COD047", "LAVALOZA CREMA 500 GR", "JUMBO", "500GR", 23, 2880, 4627)
    ]

    for row_idx, fila in enumerate(ejemplos, 2):
        for col_idx, val in enumerate(fila, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if col_idx in (5,):
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '#,##0'
            elif col_idx in (6, 7):
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '$#,##0'
            elif col_idx in (1, 4):
                cell.alignment = Alignment(horizontal="center")

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 24

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
