from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, MovimientoKardex, Producto, PresentacionComercial, Lote, Tercero, User
from app.routes.auth import role_required

facturacion_bp = Blueprint('facturacion_bp', __name__)

def agrupar_movimientos_por_factura(movimientos):
    """
    Agrupa una lista de MovimientoKardex por su documento_soporte (Factura o Remisión)
    y calcula totales financieros, cantidades e ítems asociados.
    """
    facturas_dict = {}
    for m in movimientos:
        doc = (m.documento_soporte or '').strip()
        if not doc:
            doc = f"SOPORTE-MOV-{m.id}"

        # Usar clave única que combine documento y tipo de operación
        # para diferenciar si por alguna razón un número de documento se repite en compra y venta
        op_tipo = 'COMPRA' if m.tipo_movimiento == 'ENTRADA_COMPRA' else 'VENTA'
        clave = f"{op_tipo}_{doc}"

        if clave not in facturas_dict:
            facturas_dict[clave] = {
                'id_clave': clave,
                'documento': doc,
                'tipo_operacion': op_tipo,
                'tipo_movimiento': m.tipo_movimiento,
                'fecha': m.fecha,
                'tercero': m.tercero,
                'usuario': m.usuario,
                'archivo_comprobante': m.archivo_comprobante,
                'motivo_observaciones': m.motivo_observaciones,
                'items': [],
                'total_cantidad': Decimal('0.0'),
                'total_valor': Decimal('0.0'),
                'tiene_lotes_fefo': False
            }

        cant_abs = abs(Decimal(str(m.cantidad or 0)))
        p_unit = Decimal(str(m.precio_unitario or 0))
        subtotal = cant_abs * p_unit

        facturas_dict[clave]['items'].append({
            'movimiento': m,
            'producto': m.producto,
            'presentacion': m.presentacion,
            'lote': m.lote,
            'cantidad': cant_abs,
            'precio_unitario': p_unit,
            'subtotal': subtotal
        })

        facturas_dict[clave]['total_cantidad'] += cant_abs
        facturas_dict[clave]['total_valor'] += subtotal
        if m.lote:
            facturas_dict[clave]['tiene_lotes_fefo'] = True

        # Mantener archivo si alguno del grupo lo tiene
        if m.archivo_comprobante and not facturas_dict[clave]['archivo_comprobante']:
            facturas_dict[clave]['archivo_comprobante'] = m.archivo_comprobante

        # Mantener tercero si alguno del grupo lo tiene
        if m.tercero and not facturas_dict[clave]['tercero']:
            facturas_dict[clave]['tercero'] = m.tercero

    # Ordenar las facturas por fecha descendente
    lista_facturas = list(facturas_dict.values())
    lista_facturas.sort(key=lambda x: x['fecha'] or datetime.min, reverse=True)
    return lista_facturas


@facturacion_bp.route('/')
@login_required
def hub():
    """
    Vista principal del Módulo de Facturación: Compras y Ventas.
    Muestra tarjetas dinámicas de trazabilidad para cada factura registrada.
    """
    filtro_tipo = request.args.get('tipo', '').strip().upper() # 'COMPRA', 'VENTA', ''
    q = request.args.get('q', '').strip() # búsqueda por nro factura, producto o tercero
    tercero_id = request.args.get('tercero_id', type=int)
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')

    query = MovimientoKardex.query.filter(
        MovimientoKardex.tipo_movimiento.in_(['ENTRADA_COMPRA', 'SALIDA_DESPACHO'])
    )

    if filtro_tipo == 'COMPRA':
        query = query.filter(MovimientoKardex.tipo_movimiento == 'ENTRADA_COMPRA')
    elif filtro_tipo == 'VENTA':
        query = query.filter(MovimientoKardex.tipo_movimiento == 'SALIDA_DESPACHO')

    if tercero_id:
        query = query.filter(MovimientoKardex.tercero_id == tercero_id)

    if fecha_inicio_str:
        try:
            f_ini = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
            query = query.filter(MovimientoKardex.fecha >= f_ini)
        except Exception:
            pass

    if fecha_fin_str:
        try:
            f_fin = datetime.strptime(f"{fecha_fin_str} 23:59:59", '%Y-%m-%d %H:%M:%S')
            query = query.filter(MovimientoKardex.fecha <= f_fin)
        except Exception:
            pass

    todos_movs = query.order_by(MovimientoKardex.fecha.desc()).all()
    facturas = agrupar_movimientos_por_factura(todos_movs)

    # Filtrar por texto si q existe
    if q:
        q_lower = q.lower()
        facturas_filtradas = []
        for f in facturas:
            coincide_doc = q_lower in f['documento'].lower()
            coincide_tercero = f['tercero'] and (q_lower in f['tercero'].nombre_razon_social.lower() or q_lower in f['tercero'].documento_nit.lower())
            coincide_prod = any(q_lower in it['producto'].nombre.lower() or q_lower in it['producto'].codigo_referencia.lower() for it in f['items'])
            if coincide_doc or coincide_tercero or coincide_prod:
                facturas_filtradas.append(f)
        facturas = facturas_filtradas

    # Calcular KPIs globales
    total_compras_valor = sum(f['total_valor'] for f in facturas if f['tipo_operacion'] == 'COMPRA')
    total_ventas_valor = sum(f['total_valor'] for f in facturas if f['tipo_operacion'] == 'VENTA')
    num_compras = len([f for f in facturas if f['tipo_operacion'] == 'COMPRA'])
    num_ventas = len([f for f in facturas if f['tipo_operacion'] == 'VENTA'])
    total_items = sum(len(f['items']) for f in facturas)

    terceros = Tercero.query.filter_by(activo=True).order_by(Tercero.nombre_razon_social.asc()).all()

    return render_template(
        'facturacion/hub.html',
        facturas=facturas,
        filtro_tipo=filtro_tipo,
        q=q,
        tercero_id=tercero_id,
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        terceros=terceros,
        total_compras_valor=total_compras_valor,
        total_ventas_valor=total_ventas_valor,
        num_compras=num_compras,
        num_ventas=num_ventas,
        total_items=total_items
    )


@facturacion_bp.route('/trazabilidad/<tipo>/<path:documento>')
@login_required
def detalle_factura(tipo, documento):
    """
    Vista detallada de trazabilidad sanitaria y comercial de una Factura específica.
    Permite imprimir acta de entrega/remisión o revisar los lotes y comprobantes.
    """
    tipo_norm = tipo.upper()
    tipo_mov = 'ENTRADA_COMPRA' if tipo_norm == 'COMPRA' else 'SALIDA_DESPACHO'

    movs = MovimientoKardex.query.filter_by(
        documento_soporte=documento,
        tipo_movimiento=tipo_mov
    ).order_by(MovimientoKardex.fecha.asc()).all()

    if not movs:
        flash(f'No se encontraron movimientos registrados con el soporte "{documento}".', 'warning')
        return redirect(url_for('facturacion_bp.hub'))

    facturas_agr = agrupar_movimientos_por_factura(movs)
    factura = facturas_agr[0] if facturas_agr else None

    return render_template(
        'facturacion/detalle.html',
        factura=factura,
        tipo=tipo_norm,
        documento=documento
    )

