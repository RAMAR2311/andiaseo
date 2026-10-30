from decimal import Decimal
from datetime import datetime, date
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import db, Producto, PresentacionComercial, Categoria, Lote, MovimientoKardex
from app.routes.auth import role_required
from app.services.kardex_service import registrar_movimiento
from app.services.fefo_service import sugerir_lote_fefo, validar_salida_lote

basedir = Path(__file__).resolve().parent.parent.parent

inventory_bp = Blueprint('inventory_bp', __name__)

@inventory_bp.route('/')
@login_required
def list_productos():
    """Listado general de productos con vista dual (unidad base vs presentaciones) y filtros."""
    q = request.args.get('q', '').strip()
    categoria_id = request.args.get('categoria_id', type=int)
    tipo = request.args.get('tipo', '').strip()
    alerta = request.args.get('alerta', '').strip()

    query = Producto.query.filter(Producto.activo == True)

    if q:
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(f'%{q}%'),
                Producto.codigo_referencia.ilike(f'%{q}%')
            )
        )
    if categoria_id:
        query = query.filter(Producto.categoria_id == categoria_id)
    if tipo:
        query = query.filter(Producto.tipo_producto == tipo)

    productos = query.order_by(Producto.nombre.asc()).all()

    # Si se filtró por alerta de stock mínimo
    if alerta == 'bajo_stock':
        productos = [p for p in productos if p.en_alerta_stock]

    categorias = Categoria.query.order_by(Categoria.nombre.asc()).all()
    tipos_disponibles = Producto.TIPOS_VALIDOS

    return render_template(
        'inventory/list.html',
        productos=productos,
        categorias=categorias,
        tipos_disponibles=tipos_disponibles,
        filtros={'q': q, 'categoria_id': categoria_id, 'tipo': tipo, 'alerta': alerta}
    )


@inventory_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def nuevo_producto():
    """Creación de un nuevo producto químico o insumo base."""
    if request.method == 'POST':
        codigo = request.form.get('codigo_referencia', '').strip().upper()
        nombre = request.form.get('nombre', '').strip()
        categoria_id = request.form.get('categoria_id', type=int)
        tipo_producto = request.form.get('tipo_producto', 'quimico_liquido')
        unidad_base = request.form.get('unidad_base', 'litros')
        stock_minimo = request.form.get('stock_minimo_alerta', type=float) or 0.0
        descripcion = request.form.get('descripcion', '').strip()
        requiere_vencimiento = bool(request.form.get('requiere_vencimiento'))
        
        # Cantidad y lote inicial opcional (Saldo de Apertura)
        cantidad_inicial = request.form.get('cantidad_inicial', type=float) or 0.0
        numero_lote_inicial = request.form.get('numero_lote_inicial', '').strip().upper()
        fecha_venc_inicial_str = request.form.get('fecha_vencimiento_inicial', '').strip()

        if not codigo or not nombre or not categoria_id:
            flash('Código, nombre y categoría son obligatorios.', 'danger')
            return redirect(url_for('inventory_bp.nuevo_producto'))

        if Producto.query.filter_by(codigo_referencia=codigo).first():
            flash(f'Ya existe un producto con el código de referencia "{codigo}".', 'warning')
            return redirect(url_for('inventory_bp.nuevo_producto'))

        producto = Producto(
            codigo_referencia=codigo,
            nombre=nombre,
            categoria_id=categoria_id,
            tipo_producto=tipo_producto,
            unidad_base=unidad_base,
            stock_minimo_alerta=Decimal(str(stock_minimo)),
            stock_actual_total=Decimal('0.0'),
            costo_unitario_base=Decimal('0.0'),
            requiere_vencimiento=requiere_vencimiento,
            descripcion=descripcion,
            activo=True
        )
        db.session.add(producto)
        db.session.flush()

        # Si ingresó stock inicial, registrar lote y movimiento Kardex
        if cantidad_inicial > 0:
            if not numero_lote_inicial:
                numero_lote_inicial = f"LOT-INI-{datetime.now().strftime('%y%m%d')}"
            
            f_venc = None
            if requiere_vencimiento:
                if fecha_venc_inicial_str:
                    try:
                        f_venc = datetime.strptime(fecha_venc_inicial_str, '%Y-%m-%d').date()
                    except Exception:
                        f_venc = date.today().replace(year=date.today().year + 1)
                else:
                    f_venc = date.today().replace(year=date.today().year + 1)

            lote_ini = Lote(
                producto_id=producto.id,
                presentacion_id=None,
                numero_lote=numero_lote_inicial,
                fecha_produccion=date.today(),
                fecha_vencimiento=f_venc,
                cantidad_inicial=Decimal(str(cantidad_inicial)),
                cantidad_actual=Decimal('0.0'),
                estado='ACTIVO'
            )
            db.session.add(lote_ini)
            db.session.flush()

            registrar_movimiento(
                usuario_id=current_user.id,
                producto_id=producto.id,
                tipo_movimiento='ENTRADA_COMPRA',
                cantidad=Decimal(str(cantidad_inicial)),
                motivo_observaciones="Saldo inicial de apertura al registrar producto",
                presentacion_id=None,
                lote_id=lote_ini.id,
                documento_soporte="SALDO-INICIAL",
                commit=False
            )

        db.session.commit()

        if cantidad_inicial > 0:
            flash(f'Producto "{producto.nombre}" registrado exitosamente con saldo inicial de {cantidad_inicial} {producto.unidad_base} (Lote: {numero_lote_inicial}).', 'success')
        else:
            flash(f'Producto "{producto.nombre}" registrado exitosamente con saldo en 0. Puedes ingresar stock por Entrada de Compra o configurar presentaciones.', 'success')
        
        return redirect(url_for('inventory_bp.presentaciones', producto_id=producto.id))

    categorias = Categoria.query.order_by(Categoria.nombre.asc()).all()
    return render_template('inventory/form.html', producto=None, categorias=categorias)


@inventory_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def editar_producto(id):
    """Edición de información del producto base."""
    producto = Producto.query.get_or_404(id)

    if request.method == 'POST':
        codigo = request.form.get('codigo_referencia', '').strip().upper()
        nombre = request.form.get('nombre', '').strip()
        categoria_id = request.form.get('categoria_id', type=int)
        tipo_producto = request.form.get('tipo_producto')
        unidad_base = request.form.get('unidad_base')
        stock_minimo = request.form.get('stock_minimo_alerta', type=float) or 0.0
        descripcion = request.form.get('descripcion', '').strip()

        # Verificar unicidad de código
        existente = Producto.query.filter_by(codigo_referencia=codigo).first()
        if existente and existente.id != producto.id:
            flash(f'El código "{codigo}" ya está asignado a otro producto.', 'danger')
            return redirect(url_for('inventory_bp.editar_producto', id=producto.id))

        producto.codigo_referencia = codigo
        producto.nombre = nombre
        producto.categoria_id = categoria_id
        producto.tipo_producto = tipo_producto
        producto.unidad_base = unidad_base
        producto.stock_minimo_alerta = Decimal(str(stock_minimo))
        producto.descripcion = descripcion

        db.session.commit()
        flash(f'Producto "{producto.nombre}" actualizado correctamente.', 'success')
        return redirect(url_for('inventory_bp.list_productos'))

    categorias = Categoria.query.order_by(Categoria.nombre.asc()).all()
    return render_template('inventory/form.html', producto=producto, categorias=categorias)


@inventory_bp.route('/<int:producto_id>/presentaciones', methods=['GET', 'POST'])
@login_required
def presentaciones(producto_id):
    """Gestión de presentaciones comerciales vinculadas a un producto."""
    producto = Producto.query.get_or_404(producto_id)

    if request.method == 'POST' and current_user.rol in ('admin', 'almacenista'):
        nombre_pres = request.form.get('nombre_presentacion', '').strip()
        factor = request.form.get('factor_conversion_base', type=float) or 1.0
        codigo_barras = request.form.get('codigo_barras', '').strip() or None
        costo_u = request.form.get('costo_promedio_unitario', type=float) or 0.0
        precio_ref = request.form.get('precio_referencia', type=float) or 0.0

        if not nombre_pres or factor <= 0:
            flash('Nombre de presentación y factor de conversión mayor a 0 son obligatorios.', 'danger')
            return redirect(url_for('inventory_bp.presentaciones', producto_id=producto.id))

        if codigo_barras and PresentacionComercial.query.filter_by(codigo_barras=codigo_barras).first():
            flash(f'El código de barras "{codigo_barras}" ya está registrado en otra presentación.', 'danger')
            return redirect(url_for('inventory_bp.presentaciones', producto_id=producto.id))

        nueva_pres = PresentacionComercial(
            producto_id=producto.id,
            nombre_presentacion=nombre_pres,
            factor_conversion_base=Decimal(str(factor)),
            codigo_barras=codigo_barras,
            stock_actual=Decimal('0.0'),
            costo_promedio_unitario=Decimal(str(costo_u)),
            precio_referencia=Decimal(str(precio_ref)),
            activo=True
        )
        db.session.add(nueva_pres)
        db.session.commit()

        flash(f'Presentación "{nueva_pres.nombre_presentacion}" agregada a {producto.nombre}.', 'success')
        return redirect(url_for('inventory_bp.presentaciones', producto_id=producto.id))

    return render_template('inventory/presentaciones.html', producto=producto)


@inventory_bp.route('/presentaciones/<int:id>/editar', methods=['POST'])
@login_required
@role_required('admin', 'almacenista')
def editar_presentacion(id):
    """Edición de datos de una presentación comercial."""
    pres = PresentacionComercial.query.get_or_404(id)
    nombre_pres = request.form.get('nombre_presentacion', '').strip()
    factor = request.form.get('factor_conversion_base', type=float) or 1.0
    codigo_barras = request.form.get('codigo_barras', '').strip() or None
    costo_u = request.form.get('costo_promedio_unitario', type=float) or 0.0
    precio_ref = request.form.get('precio_referencia', type=float) or 0.0

    if codigo_barras:
        existente = PresentacionComercial.query.filter_by(codigo_barras=codigo_barras).first()
        if existente and existente.id != pres.id:
            flash(f'El código de barras "{codigo_barras}" ya pertenece a otra presentación.', 'danger')
            return redirect(url_for('inventory_bp.presentaciones', producto_id=pres.producto_id))

    pres.nombre_presentacion = nombre_pres
    pres.factor_conversion_base = Decimal(str(factor))
    pres.codigo_barras = codigo_barras
    pres.costo_promedio_unitario = Decimal(str(costo_u))
    pres.precio_referencia = Decimal(str(precio_ref))

    db.session.commit()
    flash(f'Presentación "{pres.nombre_presentacion}" actualizada.', 'success')
    return redirect(url_for('inventory_bp.presentaciones', producto_id=pres.producto_id))


@inventory_bp.route('/categorias', methods=['GET', 'POST'])
@login_required
def categorias():
    """Gestión de categorías de productos."""
    if request.method == 'POST' and current_user.rol in ('admin', 'almacenista'):
        nombre = request.form.get('nombre', '').strip()
        desc = request.form.get('descripcion', '').strip()
        if not nombre:
            flash('El nombre de la categoría es requerido.', 'danger')
            return redirect(url_for('inventory_bp.categorias'))

        if Categoria.query.filter(Categoria.nombre.ilike(nombre)).first():
            flash(f'La categoría "{nombre}" ya existe.', 'warning')
            return redirect(url_for('inventory_bp.categorias'))

        cat = Categoria(nombre=nombre, descripcion=desc)
        db.session.add(cat)
        db.session.commit()
        flash(f'Categoría "{nombre}" creada exitosamente.', 'success')
        return redirect(url_for('inventory_bp.categorias'))

    todas = Categoria.query.order_by(Categoria.nombre.asc()).all()
    return render_template('inventory/categorias.html', categorias=todas)


@inventory_bp.route('/entrada', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def entrada_compra():
    """
    Ingreso de mercancía por compra:
    Crea o alimenta lote, actualiza stock físico y genera Kardex ENTRADA_COMPRA.
    """
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        presentacion_id = request.form.get('presentacion_id', type=int) or None
        cantidad = request.form.get('cantidad', type=float)
        costo_unitario = request.form.get('costo_unitario', type=float) or 0.0
        numero_lote = request.form.get('numero_lote', '').strip()
        fecha_prod_str = request.form.get('fecha_produccion')
        fecha_venc_str = request.form.get('fecha_vencimiento')
        registro_sanitario = request.form.get('registro_sanitario', '').strip() or None
        factura_remision = request.form.get('documento_soporte', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        producto = Producto.query.get_or_404(producto_id)
        presentacion = db.session.get(PresentacionComercial, presentacion_id) if presentacion_id else None

        if not producto_id or not cantidad or cantidad <= 0 or not numero_lote:
            flash('Producto, cantidad y número de lote son requeridos.', 'danger')
            return redirect(url_for('inventory_bp.entrada_compra'))

        if producto.requiere_vencimiento and not fecha_venc_str:
            flash(f'El producto "{producto.nombre}" tiene control sanitario activado. La fecha de vencimiento es requerida.', 'danger')
            return redirect(url_for('inventory_bp.entrada_compra'))

        fecha_prod = datetime.strptime(fecha_prod_str, '%Y-%m-%d').date() if fecha_prod_str else date.today()
        fecha_venc = datetime.strptime(fecha_venc_str, '%Y-%m-%d').date() if fecha_venc_str else None

        # Actualizar costo promedio ponderado
        if costo_unitario > 0:
            if presentacion:
                stock_act = float(presentacion.stock_actual or 0)
                costo_act = float(presentacion.costo_promedio_unitario or 0)
                nuevo_stock = stock_act + cantidad
                if nuevo_stock > 0:
                    costo_ponderado = ((stock_act * costo_act) + (cantidad * costo_unitario)) / nuevo_stock
                    presentacion.costo_promedio_unitario = Decimal(str(round(costo_ponderado, 2)))
            else:
                # Producto a granel / unidad base directa
                stock_act = float(producto.stock_actual_total or 0)
                costo_act = float(producto.costo_unitario_base or 0)
                nuevo_stock = stock_act + cantidad
                if nuevo_stock > 0:
                    costo_ponderado = ((stock_act * costo_act) + (cantidad * costo_unitario)) / nuevo_stock
                    producto.costo_unitario_base = Decimal(str(round(costo_ponderado, 2)))
                else:
                    producto.costo_unitario_base = Decimal(str(costo_unitario))

        # Manejo de Comprobante / Archivo adjunto
        archivo_adjunto = request.files.get('archivo_comprobante')
        nombre_archivo_guardado = None
        if archivo_adjunto and archivo_adjunto.filename != '':
            ext = archivo_adjunto.filename.rsplit('.', 1)[-1].lower()
            if ext in {'pdf', 'png', 'jpg', 'jpeg', 'webp'}:
                from werkzeug.utils import secure_filename
                import os
                nombre_seguro = f"COMP_ENT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(archivo_adjunto.filename)}"
                upload_folder = os.path.join(basedir, 'app', 'static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                archivo_adjunto.save(os.path.join(upload_folder, nombre_seguro))
                nombre_archivo_guardado = nombre_seguro

        # Buscar o crear lote
        lote = Lote.query.filter_by(numero_lote=numero_lote, producto_id=producto.id).first()
        if not lote:
            lote = Lote(
                producto_id=producto.id,
                presentacion_id=presentacion.id if presentacion else None,
                numero_lote=numero_lote,
                fecha_produccion=fecha_prod,
                fecha_vencimiento=fecha_venc,
                registro_sanitario=registro_sanitario,
                cantidad_inicial=Decimal(str(cantidad)),
                cantidad_actual=Decimal('0.0'),
                estado='ACTIVO'
            )
            db.session.add(lote)
            db.session.flush()

        try:
            motivo = f"Recepción de compra | Factura/Remisión: {factura_remision or 'S/N'}. {observaciones}".strip()
            registrar_movimiento(
                usuario_id=current_user.id,
                producto_id=producto.id,
                tipo_movimiento='ENTRADA_COMPRA',
                cantidad=Decimal(str(cantidad)),
                motivo_observaciones=motivo,
                presentacion_id=presentacion.id if presentacion else None,
                lote_id=lote.id,
                documento_soporte=factura_remision,
                archivo_comprobante=nombre_archivo_guardado,
                commit=True
            )
            flash(f'Entrada de mercancía procesada correctamente. Lote {lote.numero_lote} registrado en Kardex.', 'success')
            return redirect(url_for('inventory_bp.list_productos'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la entrada: {str(e)}', 'danger')
            return redirect(url_for('inventory_bp.entrada_compra'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    return render_template('inventory/entrada.html', productos=productos)


@inventory_bp.route('/despacho', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def despacho():
    """
    Registro de Salida por Despacho con sugerencia FEFO automática.
    """
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        presentacion_id = request.form.get('presentacion_id', type=int) or None
        lote_id = request.form.get('lote_id', type=int)
        cantidad = request.form.get('cantidad', type=float)
        documento = request.form.get('documento_soporte', '').strip()
        motivo = request.form.get('motivo_observaciones', '').strip()

        if not producto_id or not lote_id or not cantidad or cantidad <= 0:
            flash('Producto, lote y cantidad mayor a 0 son obligatorios.', 'danger')
            return redirect(url_for('inventory_bp.despacho'))

        lote = db.session.get(Lote, lote_id)
        permitido, mensaje_error = validar_salida_lote(lote)
        if not permitido:
            flash(mensaje_error, 'danger')
            return redirect(url_for('inventory_bp.despacho'))

        # Manejo de Comprobante / Guía de despacho adjunta
        archivo_adjunto = request.files.get('archivo_comprobante')
        nombre_archivo_guardado = None
        if archivo_adjunto and archivo_adjunto.filename != '':
            ext = archivo_adjunto.filename.rsplit('.', 1)[-1].lower()
            if ext in {'pdf', 'png', 'jpg', 'jpeg', 'webp'}:
                from werkzeug.utils import secure_filename
                import os
                nombre_seguro = f"COMP_DESP_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(archivo_adjunto.filename)}"
                upload_folder = os.path.join(basedir, 'app', 'static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                archivo_adjunto.save(os.path.join(upload_folder, nombre_seguro))
                nombre_archivo_guardado = nombre_seguro

        try:
            registrar_movimiento(
                usuario_id=current_user.id,
                producto_id=producto_id,
                tipo_movimiento='SALIDA_DESPACHO',
                cantidad=Decimal(str(-cantidad)),  # Salida: cantidad negativa
                motivo_observaciones=f"Despacho a bodega/cliente: {motivo}".strip(),
                presentacion_id=presentacion_id,
                lote_id=lote_id,
                documento_soporte=documento,
                archivo_comprobante=nombre_archivo_guardado,
                commit=True
            )
            flash(f'Despacho de {cantidad} unidades del Lote {lote.numero_lote} registrado exitosamente.', 'success')
            return redirect(url_for('reportes_bp.kardex'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar el despacho: {str(e)}', 'danger')
            return redirect(url_for('inventory_bp.despacho'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    return render_template('inventory/despacho.html', productos=productos)


@inventory_bp.route('/api/presentaciones/<int:producto_id>')
@login_required
def api_presentaciones(producto_id):
    """API JSON para obtener presentaciones de un producto dinámicamente."""
    pres = PresentacionComercial.query.filter_by(producto_id=producto_id, activo=True).all()
    return jsonify([{
        'id': p.id,
        'nombre': p.nombre_presentacion,
        'factor': float(p.factor_conversion_base),
        'stock': float(p.stock_actual),
        'costo': float(p.costo_promedio_unitario)
    } for p in pres])


@inventory_bp.route('/api/lotes-fefo/<int:producto_id>')
@login_required
def api_lotes_fefo(producto_id):
    """API JSON para obtener los lotes ordenados por FEFO con sugerencia automática."""
    pres_id = request.args.get('presentacion_id', type=int)
    from app.services.fefo_service import obtener_lotes_fefo, sugerir_lote_fefo
    
    lotes = obtener_lotes_fefo(producto_id, presentacion_id=pres_id, solo_disponibles=True)
    lote_sugerido = sugerir_lote_fefo(producto_id, presentacion_id=pres_id)
    
    return jsonify({
        'sugerido_id': lote_sugerido.id if lote_sugerido else None,
        'lotes': [{
            'id': l.id,
            'numero_lote': l.numero_lote,
            'fecha_vencimiento': l.fecha_vencimiento.strftime('%d/%m/%Y'),
            'dias_restantes': l.dias_para_vencer,
            'cantidad_disponible': float(l.cantidad_actual),
            'semaforo': l.semaforo_fefo,
            'es_sugerido': (l.id == (lote_sugerido.id if lote_sugerido else None))
        } for l in lotes]
    })
