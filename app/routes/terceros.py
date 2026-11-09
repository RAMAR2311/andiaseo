from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app.models import db, Tercero, MovimientoKardex
from app.routes.auth import role_required

terceros_bp = Blueprint('terceros_bp', __name__)

@terceros_bp.route('/')
@login_required
def list_terceros():
    """Listado general de clientes y proveedores con filtros."""
    q = request.args.get('q', '').strip()
    filtro_tipo = request.args.get('tipo', '').strip() # 'cliente', 'proveedor', 'ambos'

    query = Tercero.query.filter(Tercero.activo == True)

    if q:
        query = query.filter(
            db.or_(
                Tercero.nombre_razon_social.ilike(f'%{q}%'),
                Tercero.documento_nit.ilike(f'%{q}%'),
                Tercero.ciudad.ilike(f'%{q}%'),
                Tercero.contacto_nombre.ilike(f'%{q}%')
            )
        )
    if filtro_tipo:
        if filtro_tipo == 'cliente':
            query = query.filter(Tercero.tipo.in_(['cliente', 'ambos']))
        elif filtro_tipo == 'proveedor':
            query = query.filter(Tercero.tipo.in_(['proveedor', 'ambos']))
        else:
            query = query.filter(Tercero.tipo == filtro_tipo)

    terceros = query.order_by(Tercero.nombre_razon_social.asc()).all()

    return render_template(
        'terceros/list.html',
        terceros=terceros,
        filtro_tipo=filtro_tipo,
        q=q
    )


@terceros_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def nuevo_tercero():
    """Creación de un nuevo Cliente o Proveedor."""
    tipo_sugerido = request.args.get('tipo', 'cliente')
    
    if request.method == 'POST':
        tipo = request.form.get('tipo', 'cliente')
        nit = request.form.get('documento_nit', '').strip().upper()
        nombre = request.form.get('nombre_razon_social', '').strip()
        telefono = request.form.get('telefono', '').strip()
        email = request.form.get('email', '').strip()
        direccion = request.form.get('direccion', '').strip()
        ciudad = request.form.get('ciudad', '').strip()
        contacto = request.form.get('contacto_nombre', '').strip()

        if not nit or not nombre:
            flash('El Documento/NIT y la Razón Social son campos obligatorios.', 'danger')
            return redirect(url_for('terceros_bp.nuevo_tercero', tipo=tipo))

        existente = Tercero.query.filter_by(documento_nit=nit).first()
        if existente:
            flash(f'Ya existe un registro con el Documento/NIT "{nit}" ({existente.nombre_razon_social}).', 'warning')
            return redirect(url_for('terceros_bp.nuevo_tercero', tipo=tipo))

        tercero = Tercero(
            tipo=tipo,
            documento_nit=nit,
            nombre_razon_social=nombre,
            telefono=telefono or None,
            email=email or None,
            direccion=direccion or None,
            ciudad=ciudad or None,
            contacto_nombre=contacto or None,
            activo=True
        )
        db.session.add(tercero)
        db.session.commit()

        flash(f'{tercero.tipo_legible} "{tercero.nombre_razon_social}" registrado con éxito.', 'success')
        return redirect(url_for('terceros_bp.detalle_tercero', id=tercero.id))

    return render_template('terceros/form.html', tercero=None, tipo_sugerido=tipo_sugerido)


@terceros_bp.route('/<int:id>')
@login_required
def detalle_tercero(id):
    """Perfil detallado del Cliente o Proveedor con todo su historial de facturas y movimientos."""
    tercero = Tercero.query.get_or_404(id)
    movimientos = MovimientoKardex.query.filter_by(tercero_id=tercero.id).order_by(MovimientoKardex.fecha.desc()).all()

    # Agrupar facturas únicas asociadas a este tercero
    facturas_dict = {}
    for m in movimientos:
        doc = m.documento_soporte or 'SIN-DOCUMENTO'
        if doc not in facturas_dict:
            facturas_dict[doc] = {
                'documento': doc,
                'fecha': m.fecha,
                'archivo': m.archivo_comprobante,
                'tipo_movimiento': m.tipo_legible,
                'items': []
            }
        facturas_dict[doc]['items'].append(m)

    return render_template(
        'terceros/detalle.html',
        tercero=tercero,
        movimientos=movimientos,
        facturas=list(facturas_dict.values())
    )


@terceros_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def editar_tercero(id):
    """Edición de información del Cliente o Proveedor."""
    tercero = Tercero.query.get_or_404(id)

    if request.method == 'POST':
        tipo = request.form.get('tipo', tercero.tipo)
        nit = request.form.get('documento_nit', '').strip().upper()
        nombre = request.form.get('nombre_razon_social', '').strip()
        telefono = request.form.get('telefono', '').strip()
        email = request.form.get('email', '').strip()
        direccion = request.form.get('direccion', '').strip()
        ciudad = request.form.get('ciudad', '').strip()
        contacto = request.form.get('contacto_nombre', '').strip()

        if not nit or not nombre:
            flash('El Documento/NIT y la Razón Social son obligatorios.', 'danger')
            return redirect(url_for('terceros_bp.editar_tercero', id=tercero.id))

        existente = Tercero.query.filter_by(documento_nit=nit).first()
        if existente and existente.id != tercero.id:
            flash(f'El NIT "{nit}" ya pertenece a otro registro.', 'danger')
            return redirect(url_for('terceros_bp.editar_tercero', id=tercero.id))

        tercero.tipo = tipo
        tercero.documento_nit = nit
        tercero.nombre_razon_social = nombre
        tercero.telefono = telefono or None
        tercero.email = email or None
        tercero.direccion = direccion or None
        tercero.ciudad = ciudad or None
        tercero.contacto_nombre = contacto or None

        db.session.commit()
        flash(f'{tercero.tipo_legible} "{tercero.nombre_razon_social}" actualizado correctamente.', 'success')
        return redirect(url_for('terceros_bp.detalle_tercero', id=tercero.id))

    return render_template('terceros/form.html', tercero=tercero, tipo_sugerido=tercero.tipo)

