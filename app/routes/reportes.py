from datetime import datetime, date
from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from app.models import db, MovimientoKardex, Producto, PresentacionComercial, Lote, User
from app.services.excel_service import generar_kardex_excel, generar_inventario_valorizado_excel

reportes_bp = Blueprint('reportes_bp', __name__)

@reportes_bp.route('/kardex')
@login_required
def kardex():
    """Consulta interactiva de movimientos de inventario con filtros avanzados."""
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    producto_id = request.args.get('producto_id', type=int)
    tipo_movimiento = request.args.get('tipo_movimiento', '').strip()
    usuario_id = request.args.get('usuario_id', type=int)

    query = MovimientoKardex.query.join(Producto).order_by(MovimientoKardex.fecha.desc())

    if fecha_inicio_str:
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        query = query.filter(MovimientoKardex.fecha >= fecha_inicio)
    if fecha_fin_str:
        fecha_fin = datetime.strptime(f"{fecha_fin_str} 23:59:59", '%Y-%m-%d %H:%M:%S')
        query = query.filter(MovimientoKardex.fecha <= fecha_fin)
    if producto_id:
        query = query.filter(MovimientoKardex.producto_id == producto_id)
    if tipo_movimiento:
        query = query.filter(MovimientoKardex.tipo_movimiento == tipo_movimiento)
    if usuario_id:
        query = query.filter(MovimientoKardex.usuario_id == usuario_id)

    movimientos = query.limit(500).all()

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    usuarios = User.query.filter_by(activo=True).order_by(User.nombre.asc()).all()
    tipos_movimiento = MovimientoKardex.TIPOS_VALIDOS

    return render_template(
        'reportes/kardex.html',
        movimientos=movimientos,
        productos=productos,
        usuarios=usuarios,
        tipos_movimiento=tipos_movimiento,
        filtros={
            'fecha_inicio': fecha_inicio_str,
            'fecha_fin': fecha_fin_str,
            'producto_id': producto_id,
            'tipo_movimiento': tipo_movimiento,
            'usuario_id': usuario_id
        }
    )


@reportes_bp.route('/kardex/exportar')
@login_required
def exportar_kardex():
    """Descarga de Kardex filtrado en formato Excel (.xlsx) estilizado."""
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    producto_id = request.args.get('producto_id', type=int)
    tipo_movimiento = request.args.get('tipo_movimiento', '').strip()
    usuario_id = request.args.get('usuario_id', type=int)

    query = MovimientoKardex.query.join(Producto).order_by(MovimientoKardex.fecha.desc())

    filtros_resumen = []
    if fecha_inicio_str:
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        query = query.filter(MovimientoKardex.fecha >= fecha_inicio)
        filtros_resumen.append(f"Desde: {fecha_inicio_str}")
    if fecha_fin_str:
        fecha_fin = datetime.strptime(f"{fecha_fin_str} 23:59:59", '%Y-%m-%d %H:%M:%S')
        query = query.filter(MovimientoKardex.fecha <= fecha_fin)
        filtros_resumen.append(f"Hasta: {fecha_fin_str}")
    if producto_id:
        query = query.filter(MovimientoKardex.producto_id == producto_id)
        prod = db.session.get(Producto, producto_id)
        if prod:
            filtros_resumen.append(f"Producto: {prod.nombre}")
    if tipo_movimiento:
        query = query.filter(MovimientoKardex.tipo_movimiento == tipo_movimiento)
        filtros_resumen.append(f"Tipo: {tipo_movimiento}")
    if usuario_id:
        query = query.filter(MovimientoKardex.usuario_id == usuario_id)
        usr = db.session.get(User, usuario_id)
        if usr:
            filtros_resumen.append(f"Usuario: {usr.nombre}")

    movimientos = query.all()
    resumen_str = " | ".join(filtros_resumen) if filtros_resumen else "Todos los registros"

    excel_file = generar_kardex_excel(movimientos, parametros_filtro=resumen_str)
    nombre_descarga = f"Kardex_Andiaseo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    return send_file(
        excel_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nombre_descarga
    )


@reportes_bp.route('/valorizado')
@login_required
def inventario_valorizado():
    """Vista del Inventario General Valorizado con costo de compra, IVA (19%) y subtotal."""
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    
    total_subtotal = 0.0
    for p in productos:
        if p.presentaciones:
            for pres in p.presentaciones:
                stock_f = float(pres.stock_actual or 0)
                costo_u = float(pres.costo_promedio_unitario or 0)
                total_subtotal += (stock_f * costo_u)
        else:
            # Productos directos sin presentación comercial
            total_subtotal += 0.0

    total_iva = total_subtotal * 0.19
    total_con_iva = total_subtotal + total_iva

    return render_template(
        'reportes/valorizado.html',
        productos=productos,
        total_subtotal=total_subtotal,
        total_iva=total_iva,
        total_con_iva=total_con_iva
    )


@reportes_bp.route('/valorizado/exportar')
@login_required
def exportar_valorizado():
    """Descarga de Inventario Valorizado en formato Excel (.xlsx)."""
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    excel_file = generar_inventario_valorizado_excel(productos)
    nombre_descarga = f"Inventario_Valorizado_Andiaseo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    return send_file(
        excel_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nombre_descarga
    )
