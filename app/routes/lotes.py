from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app.models import db, Lote, Producto
from app.routes.auth import role_required
from app.services.fefo_service import obtener_resumen_vencimientos

lotes_bp = Blueprint('lotes_bp', __name__)

@lotes_bp.route('/')
@login_required
def list_lotes():
    """Monitor y semáforo de lotes de inventario bajo estándar FEFO."""
    filtro_semaforo = request.args.get('semaforo', '').strip()
    producto_id = request.args.get('producto_id', type=int)
    estado = request.args.get('estado', '').strip()

    query = Lote.query.join(Producto)

    if producto_id:
        query = query.filter(Lote.producto_id == producto_id)
    if estado:
        query = query.filter(Lote.estado == estado)

    # Orden predeterminado FEFO: los que están más próximos a vencer primero
    lotes_todos = query.order_by(Lote.fecha_vencimiento.asc()).all()

    # Filtrar por semáforo si se especificó
    if filtro_semaforo:
        lotes_filtrados = [l for l in lotes_todos if l.semaforo_fefo == filtro_semaforo]
    else:
        lotes_filtrados = lotes_todos

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    resumen = obtener_resumen_vencimientos()

    return render_template(
        'lotes/list.html',
        lotes=lotes_filtrados,
        productos=productos,
        resumen=resumen,
        filtros={'semaforo': filtro_semaforo, 'producto_id': producto_id, 'estado': estado}
    )


@lotes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def nuevo_lote():
    """Registro explícito de un lote con su ficha sanitaria y vencimiento."""
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        presentacion_id = request.form.get('presentacion_id', type=int) or None
        numero_lote = request.form.get('numero_lote', '').strip().upper()
        fecha_prod_str = request.form.get('fecha_produccion')
        fecha_venc_str = request.form.get('fecha_vencimiento')
        registro_sanitario = request.form.get('registro_sanitario', '').strip() or None
        cantidad_inicial = request.form.get('cantidad_inicial', type=float) or 0.0

        if not producto_id or not numero_lote or not fecha_prod_str or not fecha_venc_str:
            flash('Producto, número de lote y fechas son obligatorios.', 'danger')
            return redirect(url_for('lotes_bp.nuevo_lote'))

        fecha_prod = datetime.strptime(fecha_prod_str, '%Y-%m-%d').date()
        fecha_venc = datetime.strptime(fecha_venc_str, '%Y-%m-%d').date()

        if fecha_venc <= fecha_prod:
            flash('La fecha de vencimiento debe ser posterior a la fecha de producción.', 'danger')
            return redirect(url_for('lotes_bp.nuevo_lote'))

        lote_existente = Lote.query.filter_by(numero_lote=numero_lote, producto_id=producto_id).first()
        if lote_existente:
            flash(f'El lote {numero_lote} ya está registrado para este producto.', 'warning')
            return redirect(url_for('lotes_bp.nuevo_lote'))

        lote = Lote(
            producto_id=producto_id,
            presentacion_id=presentacion_id,
            numero_lote=numero_lote,
            fecha_produccion=fecha_prod,
            fecha_vencimiento=fecha_venc,
            registro_sanitario=registro_sanitario,
            cantidad_inicial=Decimal(str(cantidad_inicial)),
            cantidad_actual=Decimal(str(cantidad_inicial)),
            estado='ACTIVO'
        )
        db.session.add(lote)
        db.session.commit()

        flash(f'Lote {lote.numero_lote} creado exitosamente con semáforo FEFO asignado.', 'success')
        return redirect(url_for('lotes_bp.list_lotes'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    return render_template('lotes/form.html', productos=productos)


@lotes_bp.route('/<int:id>/cambiar-estado', methods=['POST'])
@login_required
@role_required('admin', 'auditor')
def cambiar_estado(id):
    """Pone un lote en CUARENTENA o lo REACTIVA tras inspección técnica."""
    lote = Lote.query.get_or_404(id)
    nuevo_estado = request.form.get('nuevo_estado', '').strip().upper()
    motivo = request.form.get('motivo', '').strip()

    if nuevo_estado in Lote.ESTADOS_VALIDOS:
        estado_ant = lote.estado
        lote.estado = nuevo_estado
        db.session.commit()
        flash(f'El lote {lote.numero_lote} cambió de {estado_ant} a {nuevo_estado}. Motivo: {motivo}', 'info')
    else:
        flash('Estado no válido.', 'danger')

    return redirect(url_for('lotes_bp.list_lotes'))
