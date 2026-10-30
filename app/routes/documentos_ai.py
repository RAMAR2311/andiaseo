import json
from decimal import Decimal
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from app.models import db, Producto, PresentacionComercial, Lote, MovimientoKardex, Categoria
from app.routes.auth import role_required
from app.services.ai_service import analizar_factura_con_ai
from app.services.kardex_service import registrar_movimiento
from app.services.fefo_service import sugerir_lote_fefo, validar_salida_lote

documentos_ai_bp = Blueprint('documentos_ai_bp', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@documentos_ai_bp.route('/subir', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def subir_documento():
    """
    Pantalla principal para cargar un PDF o Imagen (Factura de Compra o Factura de Venta).
    Envía el archivo a OpenAI y almacena temporalmente la extracción para revisarla.
    """
    tipo_operacion = request.args.get('tipo', 'compra') # 'compra' o 'venta'
    
    if request.method == 'POST':
        file = request.files.get('documento')
        tipo_op = request.form.get('tipo_operacion', tipo_operacion)

        if not file or file.filename == '':
            flash('Debes seleccionar un archivo PDF o imagen.', 'warning')
            return redirect(url_for('documentos_ai_bp.subir_documento', tipo=tipo_op))

        if not allowed_file(file.filename):
            flash('Formato no permitido. Solo se admiten archivos PDF, JPG, PNG o WEBP.', 'danger')
            return redirect(url_for('documentos_ai_bp.subir_documento', tipo=tipo_op))

        try:
            file_bytes = file.read()
            resultado_ai = analizar_factura_con_ai(file_bytes, file.filename, tipo_operacion=tipo_op)
            
            # Guardamos el resultado temporal en la sesión para la revisión
            session['ai_factura_data'] = resultado_ai
            return redirect(url_for('documentos_ai_bp.revisar_documento'))
        except Exception as e:
            flash(f'Error al procesar el documento con IA: {str(e)}', 'danger')
            return redirect(url_for('documentos_ai_bp.subir_documento', tipo=tipo_op))

    return render_template('ai/subir_documento.html', tipo_operacion=tipo_operacion)


@documentos_ai_bp.route('/revisar', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def revisar_documento():
    """
    Muestra los datos extraídos por OpenAI y permite al usuario confirmar o ajustar
    las asignaciones de producto, presentaciones y lotes antes de aplicar a la BD.
    """
    factura_data = session.get('ai_factura_data')
    if not factura_data:
        flash('No hay datos pendientes de revisión. Por favor sube un documento primero.', 'info')
        return redirect(url_for('documentos_ai_bp.subir_documento'))

    tipo_operacion = factura_data.get('tipo_operacion', 'compra')
    items = factura_data.get('items', [])

    # Obtener catálogo activo para vincular en selects
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    presentaciones = PresentacionComercial.query.filter_by(activo=True).all()
    
    # Pre-emparejar ítems con productos en base de datos si coinciden nombre o código
    items_procesados = []
    for idx, it in enumerate(items):
        match_prod = None
        codigo_it = (it.get('codigo') or '').strip().upper()
        nombre_it = (it.get('nombre') or '').strip().lower()

        if codigo_it:
            match_prod = Producto.query.filter(Producto.codigo_referencia.ilike(codigo_it)).first()
        if not match_prod and nombre_it:
            # Buscar coincidencia parcial
            match_prod = Producto.query.filter(Producto.nombre.ilike(f"%{nombre_it[:15]}%")).first()

        sugerencia_lote = None
        if tipo_operacion == 'venta' and match_prod:
            sugerencia_lote = sugerir_lote_fefo(match_prod.id)

        items_procesados.append({
            'index': idx,
            'original': it,
            'match_producto_id': match_prod.id if match_prod else None,
            'match_producto_nombre': match_prod.nombre if match_prod else None,
            'sugerencia_lote_id': sugerencia_lote.id if sugerencia_lote else None,
            'sugerencia_lote_numero': sugerencia_lote.numero_lote if sugerencia_lote else None
        })

    if request.method == 'POST':
        # Procesar la confirmación y aplicar los cambios a la base de datos
        accion = request.form.get('accion')
        if accion == 'cancelar':
            session.pop('ai_factura_data', None)
            flash('Operación cancelada.', 'secondary')
            return redirect(url_for('inventory_bp.list_productos'))

        numero_factura = request.form.get('numero_factura', '').strip() or 'FAC-SIN-NUMERO'
        tercero = request.form.get('tercero', '').strip()
        observaciones_gral = request.form.get('observaciones', '').strip()
        
        cant_procesados = 0
        try:
            for idx in range(len(items)):
                prod_id = request.form.get(f'producto_id_{idx}', type=int)
                pres_id = request.form.get(f'presentacion_id_{idx}', type=int) or None
                cant = request.form.get(f'cantidad_{idx}', type=float) or 0.0
                costo_u = request.form.get(f'costo_{idx}', type=float) or 0.0
                num_lote = request.form.get(f'lote_{idx}', '').strip().upper()
                fecha_venc_str = request.form.get(f'vencimiento_{idx}', '').strip()
                lote_id_sel = request.form.get(f'lote_id_{idx}', type=int) or None

                if not prod_id or cant <= 0:
                    continue  # Si omitieron o no asociaron el producto, salta

                prod = Producto.query.get(prod_id)
                if not prod:
                    continue

                if tipo_operacion == 'compra':
                    # Operación de ENTRADA / COMPRA
                    if not num_lote:
                        num_lote = f"LOT-{datetime.now().strftime('%y%m%d')}-{idx+1}"
                    
                    if fecha_venc_str:
                        try:
                            f_venc = datetime.strptime(fecha_venc_str, '%Y-%m-%d').date()
                        except Exception:
                            f_venc = date.today() + timedelta(days=365)
                    else:
                        f_venc = date.today() + timedelta(days=365)

                    # Buscar o crear Lote
                    lote = Lote.query.filter_by(numero_lote=num_lote, producto_id=prod.id).first()
                    if not lote:
                        lote = Lote(
                            producto_id=prod.id,
                            presentacion_id=pres_id,
                            numero_lote=num_lote,
                            fecha_produccion=date.today(),
                            fecha_vencimiento=f_venc,
                            cantidad_inicial=Decimal(str(cant)),
                            cantidad_actual=Decimal('0.0'),
                            estado='ACTIVO'
                        )
                        db.session.add(lote)
                        db.session.flush()

                    # Registrar movimiento de entrada en Kardex
                    motivo = f"Entrada por Factura IA de {tercero or 'Proveedor'}. {observaciones_gral}".strip()
                    registrar_movimiento(
                        usuario_id=current_user.id,
                        producto_id=prod.id,
                        tipo_movimiento='ENTRADA_COMPRA',
                        cantidad=Decimal(str(cant)),
                        motivo_observaciones=motivo,
                        presentacion_id=pres_id,
                        lote_id=lote.id,
                        documento_soporte=numero_factura,
                        commit=False
                    )
                    cant_procesados += 1

                elif tipo_operacion == 'venta':
                    # Operación de SALIDA / FACTURA DE VENTA
                    # Seleccionar lote asignado o sugerido por FEFO
                    lote_obj = db.session.get(Lote, lote_id_sel) if lote_id_sel else sugerir_lote_fefo(prod.id, pres_id)
                    if not lote_obj:
                        # Si no hay lote disponible, busca cualquiera activo
                        lote_obj = Lote.query.filter_by(producto_id=prod.id, estado='ACTIVO').filter(Lote.cantidad_actual > 0).first()

                    lote_salida_id = lote_obj.id if lote_obj else None

                    motivo = f"Despacho por Factura de Venta IA a {tercero or 'Cliente'}. {observaciones_gral}".strip()
                    registrar_movimiento(
                        usuario_id=current_user.id,
                        producto_id=prod.id,
                        tipo_movimiento='SALIDA_DESPACHO',
                        cantidad=Decimal(str(-cant)), # Cantidad negativa para salida
                        motivo_observaciones=motivo,
                        presentacion_id=pres_id,
                        lote_id=lote_salida_id,
                        documento_soporte=numero_factura,
                        commit=False
                    )
                    cant_procesados += 1

            db.session.commit()
            session.pop('ai_factura_data', None)
            flash(f'¡Éxito! Se procesaron {cant_procesados} productos según la factura {numero_factura}. Stock y Kardex actualizados.', 'success')
            return redirect(url_for('inventory_bp.list_productos'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al asentar la operación en inventario: {str(e)}', 'danger')

    return render_template(
        'ai/revisar_documento.html',
        factura=factura_data,
        items_procesados=items_procesados,
        productos=productos,
        presentaciones=presentaciones,
        tipo_operacion=tipo_operacion
    )

