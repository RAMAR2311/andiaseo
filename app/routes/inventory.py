from decimal import Decimal
from datetime import datetime, date
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import db, Producto, PresentacionComercial, Categoria, Lote, MovimientoKardex, Tercero
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
        costo_unitario = request.form.get('costo_unitario_base', type=float) or 0.0
        precio_venta_base = request.form.get('precio_venta_base', type=float) or 0.0
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
            costo_unitario_base=Decimal(str(costo_unitario)),
            precio_venta_base=Decimal(str(precio_venta_base)),
            stock_actual_total=Decimal('0.0'),
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
        costo_unitario = request.form.get('costo_unitario_base', type=float) or 0.0
        stock_minimo = request.form.get('stock_minimo_alerta', type=float) or 0.0
        precio_venta_base = request.form.get('precio_venta_base', type=float) or 0.0
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
        producto.costo_unitario_base = Decimal(str(costo_unitario))
        producto.stock_minimo_alerta = Decimal(str(stock_minimo))
        producto.precio_venta_base = Decimal(str(precio_venta_base))
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
    Ingreso de mercancía por factura de compra con soporte para múltiples ítems.
    """
    if request.method == 'POST':
        factura_remision = request.form.get('documento_soporte', '').strip()
        observaciones = request.form.get('observaciones', '').strip()
        tercero_id = request.form.get('tercero_id', type=int)

        # Obtener listas de ítems enviados
        prod_ids = request.form.getlist('item_producto_id')
        cantidades = request.form.getlist('item_cantidad')
        costos = request.form.getlist('item_costo')
        lotes = request.form.getlist('item_lote')
        vencimientos = request.form.getlist('item_vencimiento')

        if not factura_remision:
            flash('El número de factura o documento de soporte es obligatorio.', 'danger')
            return redirect(url_for('inventory_bp.entrada_compra'))

        if not prod_ids or len(prod_ids) == 0:
            flash('Debes agregar al menos un producto a la factura.', 'warning')
            return redirect(url_for('inventory_bp.entrada_compra'))

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

        cant_procesados = 0
        try:
            for idx in range(len(prod_ids)):
                p_id = int(prod_ids[idx])
                cant = float(cantidades[idx]) if idx < len(cantidades) and cantidades[idx] else 0.0
                costo_u = float(costos[idx]) if idx < len(costos) and costos[idx] else 0.0
                num_lote = lotes[idx].strip().upper() if idx < len(lotes) and lotes[idx] else f"LOT-{datetime.now().strftime('%y%m%d')}-{idx+1}"
                f_venc_str = vencimientos[idx].strip() if idx < len(vencimientos) and vencimientos[idx] else None
                pres_id = request.form.get(f'item_presentacion_id_{idx}', type=int) or None

                if cant <= 0:
                    continue

                producto = Producto.query.get(p_id)
                if not producto:
                    continue

                presentacion = db.session.get(PresentacionComercial, pres_id) if pres_id else None

                # Actualizar costo promedio ponderado
                if costo_u > 0:
                    if presentacion:
                        stock_act = float(presentacion.stock_actual or 0)
                        costo_act = float(presentacion.costo_promedio_unitario or 0)
                        nuevo_stock = stock_act + cant
                        if nuevo_stock > 0:
                            costo_ponderado = ((stock_act * costo_act) + (cant * costo_u)) / nuevo_stock
                            presentacion.costo_promedio_unitario = Decimal(str(round(costo_ponderado, 2)))
                    else:
                        stock_act = float(producto.stock_actual_total or 0)
                        costo_act = float(producto.costo_unitario_base or 0)
                        nuevo_stock = stock_act + cant
                        if nuevo_stock > 0:
                            costo_ponderado = ((stock_act * costo_act) + (cant * costo_u)) / nuevo_stock
                            producto.costo_unitario_base = Decimal(str(round(costo_ponderado, 2)))
                        else:
                            producto.costo_unitario_base = Decimal(str(costo_u))

                # Fecha de vencimiento
                f_venc = datetime.strptime(f_venc_str, '%Y-%m-%d').date() if f_venc_str else None

                # Crear o buscar lote
                lote = Lote.query.filter_by(numero_lote=num_lote, producto_id=producto.id).first()
                if not lote:
                    lote = Lote(
                        producto_id=producto.id,
                        presentacion_id=presentacion.id if presentacion else None,
                        numero_lote=num_lote,
                        fecha_produccion=date.today(),
                        fecha_vencimiento=f_venc,
                        cantidad_inicial=Decimal(str(cant)),
                        cantidad_actual=Decimal('0.0'),
                        estado='ACTIVO'
                    )
                    db.session.add(lote)
                    db.session.flush()

                motivo = f"Recepción de compra | Factura: {factura_remision}. {observaciones}".strip()
                registrar_movimiento(
                    usuario_id=current_user.id,
                    producto_id=producto.id,
                    tipo_movimiento='ENTRADA_COMPRA',
                    cantidad=Decimal(str(cant)),
                    motivo_observaciones=motivo,
                    presentacion_id=presentacion.id if presentacion else None,
                    lote_id=lote.id,
                    documento_soporte=factura_remision,
                    archivo_comprobante=nombre_archivo_guardado,
                    tercero_id=tercero_id,
                    precio_unitario=costo_u if costo_u > 0 else None,
                    commit=False
                )
                cant_procesados += 1

            db.session.commit()
            flash(f'¡Éxito! Se procesó la Factura {factura_remision} con {cant_procesados} productos ingresados a bodega.', 'success')
            return redirect(url_for('inventory_bp.list_productos'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al asentar la factura de compra: {str(e)}', 'danger')
            return redirect(url_for('inventory_bp.entrada_compra'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    proveedores = Tercero.query.filter(Tercero.tipo.in_(['proveedor', 'ambos']), Tercero.activo == True).order_by(Tercero.nombre_razon_social.asc()).all()
    return render_template('inventory/entrada.html', productos=productos, proveedores=proveedores)


@inventory_bp.route('/despacho', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def despacho():
    """
    Registro de Salida por Despacho con soporte para múltiples productos (Factura de Venta / Remisión).
    """
    if request.method == 'POST':
        documento = request.form.get('documento_soporte', '').strip()
        motivo = request.form.get('motivo_observaciones', '').strip()
        tercero_id = request.form.get('tercero_id', type=int)

        prod_ids = request.form.getlist('item_producto_id')
        cantidades = request.form.getlist('item_cantidad')
        precios_venta = request.form.getlist('item_precio_venta')

        if not documento:
            flash('El número de remisión o factura de venta es obligatorio.', 'danger')
            return redirect(url_for('inventory_bp.despacho'))

        if not prod_ids or len(prod_ids) == 0:
            flash('Debes agregar al menos un producto a la orden de despacho.', 'warning')
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

        def parsear_num(val):
            if not val:
                return 0.0
            s = str(val).replace('$', '').replace('COP', '').strip()
            if '.' in s and ',' in s:
                if s.rfind(',') > s.rfind('.'):
                    s = s.replace('.', '').replace(',', '.')
                else:
                    s = s.replace(',', '')
            elif ',' in s:
                partes = s.split(',')
                if len(partes) == 2 and len(partes[1]) == 3:
                    s = s.replace(',', '')
                else:
                    s = s.replace(',', '.')
            try:
                return float(s)
            except Exception:
                return 0.0

        cant_procesados = 0
        try:
            for idx in range(len(prod_ids)):
                p_id = int(prod_ids[idx])
                cant = parsear_num(cantidades[idx]) if idx < len(cantidades) else 0.0
                pres_id = request.form.get(f'item_presentacion_id_{idx}', type=int) or None
                lote_id = request.form.get(f'item_lote_id_{idx}', type=int)
                precio_u = parsear_num(precios_venta[idx]) if idx < len(precios_venta) and precios_venta[idx] else None

                if cant <= 0:
                    continue

                # Si el producto tiene lotes con stock, se valida lote. Si no tiene lotes creados (ej. insumos o sin lote), se permite salida a granel
                lote = db.session.get(Lote, lote_id) if lote_id else None
                if lote:
                    permitido, mensaje_error = validar_salida_lote(lote)
                    if not permitido:
                        db.session.rollback()
                        flash(f"Error en producto #{idx+1}: {mensaje_error}", 'danger')
                        return redirect(url_for('inventory_bp.despacho'))

                registrar_movimiento(
                    usuario_id=current_user.id,
                    producto_id=p_id,
                    tipo_movimiento='SALIDA_DESPACHO',
                    cantidad=Decimal(str(-cant)),  # Salida: cantidad negativa
                    motivo_observaciones=f"Despacho por Remisión/Venta: {motivo}".strip(),
                    presentacion_id=pres_id,
                    lote_id=lote.id if lote else None,
                    documento_soporte=documento,
                    archivo_comprobante=nombre_archivo_guardado,
                    tercero_id=tercero_id,
                    precio_unitario=precio_u,
                    commit=False
                )
                cant_procesados += 1

            db.session.commit()
            flash(f'¡Éxito! Despacho {documento} procesado con {cant_procesados} productos descargados del inventario.', 'success')
            return redirect(url_for('reportes_bp.kardex'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar el despacho múltiple: {str(e)}', 'danger')
            return redirect(url_for('inventory_bp.despacho'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    clientes = Tercero.query.filter(Tercero.tipo.in_(['cliente', 'ambos']), Tercero.activo == True).order_by(Tercero.nombre_razon_social.asc()).all()
    return render_template('inventory/despacho.html', productos=productos, clientes=clientes)


@inventory_bp.route('/api/presentaciones/<int:producto_id>')
@login_required
def api_presentaciones(producto_id):
    """API JSON para obtener presentaciones de un producto dinámicamente con precios y costos."""
    pres = PresentacionComercial.query.filter_by(producto_id=producto_id, activo=True).all()
    return jsonify([{
        'id': p.id,
        'nombre': p.nombre_presentacion,
        'factor': float(p.factor_conversion_base),
        'stock': float(p.stock_actual),
        'costo': float(p.costo_promedio_unitario or 0),
        'precio_venta': float(p.precio_referencia or 0)
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
            'fecha_vencimiento': l.fecha_vencimiento.strftime('%d/%m/%Y') if l.fecha_vencimiento else 'No vence',
            'dias_restantes': l.dias_para_vencer,
            'cantidad_disponible': float(l.cantidad_actual),
            'semaforo': l.semaforo_fefo,
            'es_sugerido': (l.id == (lote_sugerido.id if lote_sugerido else None))
        } for l in lotes]
    })


@inventory_bp.route('/importar-masivo', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def importar_masivo():
    """Importación masiva de productos e inventario desde Excel o CSV."""
    from app.services.carga_masiva_service import procesar_archivo_masivo_excel
    
    if request.method == 'POST':
        archivo = request.files.get('archivo_excel')
        if not archivo or not archivo.filename:
            flash('Por favor selecciona un archivo Excel (.xlsx, .xls) o CSV.', 'warning')
            return redirect(url_for('inventory_bp.importar_masivo'))
        
        try:
            resumen = procesar_archivo_masivo_excel(archivo, usuario_id=current_user.id)
            flash(
                f"Importación completada con éxito: {resumen['creados']} productos nuevos creados, "
                f"{resumen['actualizados']} actualizados, {resumen['proveedores_creados']} proveedores registrados "
                f"y stock inicial asentado en Kardex.",
                'success'
            )
            return redirect(url_for('inventory_bp.list_productos'))
        except Exception as e:
            flash(f"Ocurrió un error al procesar el archivo Excel: {str(e)}", 'danger')
            return redirect(url_for('inventory_bp.importar_masivo'))
            
    return render_template('inventory/importar_masivo.html')


@inventory_bp.route('/descargar-plantilla-masiva')
@login_required
def descargar_plantilla_masiva():
    """Descarga de la plantilla de ejemplo para carga masiva de productos."""
    from flask import send_file
    from app.services.carga_masiva_service import generar_plantilla_carga_masiva_excel
    
    excel_stream = generar_plantilla_carga_masiva_excel()
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="Plantilla_Carga_Masiva_Andiaseo.xlsx"
    )

