from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import db, Producto, PresentacionComercial, Lote, MovimientoKardex
from app.routes.auth import role_required
from app.services.kardex_service import registrar_movimiento
from app.services.fefo_service import sugerir_lote_fefo, validar_salida_lote

produccion_bp = Blueprint('produccion_bp', __name__)

@produccion_bp.route('/envasado', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def envasado():
    """
    Módulo de Fraccionamiento / Envasado (Granel ➔ Producto Terminado).
    Ejecuta una transacción atómica que:
    1. Descuenta el químico base a granel (ej: 100 L)
    2. Descuenta los envases y tapas requeridos (insumos de empaque)
    3. Incrementa el stock de la presentación comercial envasada con nuevo lote
    4. Registra los movimientos respectivos en el Kardex
    """
    if request.method == 'POST':
        granel_id = request.form.get('granel_id', type=int)
        lote_granel_id = request.form.get('lote_granel_id', type=int) or None
        litros_fraccionar = request.form.get('litros_fraccionar', type=float)
        
        presentacion_destino_id = request.form.get('presentacion_destino_id', type=int)
        unidades_producidas = request.form.get('unidades_producidas', type=float)
        
        # Insumos de empaque seleccionados (IDs y cantidades)
        insumo_envase_id = request.form.get('insumo_envase_id', type=int) or None
        cant_envases = request.form.get('cant_envases', type=float) or 0.0
        
        insumo_tapa_id = request.form.get('insumo_tapa_id', type=int) or None
        cant_tapas = request.form.get('cant_tapas', type=float) or 0.0
        
        # Datos del nuevo lote terminado
        numero_lote_nuevo = request.form.get('numero_lote_nuevo', '').strip().upper()
        fecha_venc_str = request.form.get('fecha_vencimiento_terminado')
        orden_envasado = request.form.get('orden_envasado', '').strip() or f"ORD-ENV-{datetime.now().strftime('%Y%m%d%H%M')}"
        observaciones = request.form.get('observaciones', '').strip()

        # Validaciones de integridad
        if not granel_id or not litros_fraccionar or litros_fraccionar <= 0:
            flash('Debes especificar el químico a granel y la cantidad válida a fraccionar.', 'danger')
            return redirect(url_for('produccion_bp.envasado'))

        if not presentacion_destino_id or not unidades_producidas or unidades_producidas <= 0:
            flash('Debes especificar la presentación comercial destino y las unidades terminadas.', 'danger')
            return redirect(url_for('produccion_bp.envasado'))

        if not numero_lote_nuevo or not fecha_venc_str:
            flash('El número de lote terminado y su fecha de vencimiento son requeridos.', 'danger')
            return redirect(url_for('produccion_bp.envasado'))

        fecha_venc_terminado = datetime.strptime(fecha_venc_str, '%Y-%m-%d').date()
        fecha_prod_terminado = date.today()

        granel_prod = Producto.query.get_or_404(granel_id)
        pres_destino = PresentacionComercial.query.get_or_404(presentacion_destino_id)

        # Transacción Atómica
        try:
            # 1. Descontar químico a granel
            obs_origen = f"Fraccionamiento a {pres_destino.nombre_presentacion} ({unidades_producidas} und). {observaciones}".strip()
            registrar_movimiento(
                usuario_id=current_user.id,
                producto_id=granel_prod.id,
                tipo_movimiento='FRACCIONAMIENTO_ORIGEN',
                cantidad=Decimal(str(-litros_fraccionar)),
                motivo_observaciones=obs_origen,
                presentacion_id=None,
                lote_id=lote_granel_id,
                documento_soporte=orden_envasado,
                commit=False
            )

            # 2. Descontar envases si se especificaron
            if insumo_envase_id and cant_envases > 0:
                envase_prod = db.session.get(Producto, insumo_envase_id)
                if envase_prod:
                    registrar_movimiento(
                        usuario_id=current_user.id,
                        producto_id=envase_prod.id,
                        tipo_movimiento='FRACCIONAMIENTO_ORIGEN',
                        cantidad=Decimal(str(-cant_envases)),
                        motivo_observaciones=f"Envases consumidos en orden {orden_envasado}",
                        presentacion_id=None,
                        documento_soporte=orden_envasado,
                        commit=False
                    )

            # 3. Descontar tapas/sellos si se especificaron
            if insumo_tapa_id and cant_tapas > 0:
                tapa_prod = db.session.get(Producto, insumo_tapa_id)
                if tapa_prod:
                    registrar_movimiento(
                        usuario_id=current_user.id,
                        producto_id=tapa_prod.id,
                        tipo_movimiento='FRACCIONAMIENTO_ORIGEN',
                        cantidad=Decimal(str(-cant_tapas)),
                        motivo_observaciones=f"Tapas/accesorios consumidos en orden {orden_envasado}",
                        presentacion_id=None,
                        documento_soporte=orden_envasado,
                        commit=False
                    )

            # 4. Crear o buscar lote para el producto terminado
            lote_terminado = Lote.query.filter_by(
                numero_lote=numero_lote_nuevo,
                producto_id=pres_destino.producto_id
            ).first()

            if not lote_terminado:
                lote_terminado = Lote(
                    producto_id=pres_destino.producto_id,
                    presentacion_id=pres_destino.id,
                    numero_lote=numero_lote_nuevo,
                    fecha_produccion=fecha_prod_terminado,
                    fecha_vencimiento=fecha_venc_terminado,
                    registro_sanitario=granel_prod.lotes.first().registro_sanitario if granel_prod.lotes.first() else None,
                    cantidad_inicial=Decimal(str(unidades_producidas)),
                    cantidad_actual=Decimal('0.0'),
                    estado='ACTIVO'
                )
                db.session.add(lote_terminado)
                db.session.flush()

            # 5. Incrementar stock de la presentación comercial terminada
            obs_destino = f"Ingreso por Envasado de {litros_fraccionar} {granel_prod.unidad_base} de {granel_prod.nombre}".strip()
            registrar_movimiento(
                usuario_id=current_user.id,
                producto_id=pres_destino.producto_id,
                tipo_movimiento='FRACCIONAMIENTO_DESTINO',
                cantidad=Decimal(str(unidades_producidas)),
                motivo_observaciones=obs_destino,
                presentacion_id=pres_destino.id,
                lote_id=lote_terminado.id,
                documento_soporte=orden_envasado,
                commit=False
            )

            # Confirmar toda la transacción atómica
            db.session.commit()
            flash(
                f"¡Envasado exitoso! Se generaron {unidades_producidas} unidades de {pres_destino.nombre_presentacion} "
                f"asociadas al Lote {lote_terminado.numero_lote}.",
                'success'
            )
            return redirect(url_for('reportes_bp.kardex'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error durante el proceso de envasado: {str(e)}", 'danger')
            return redirect(url_for('produccion_bp.envasado'))

    # Datos para los selectores del formulario
    quimicos_granel = Producto.query.filter(
        Producto.activo == True,
        Producto.tipo_producto.in_(['quimico_liquido', 'quimico_polvo'])
    ).order_by(Producto.nombre.asc()).all()

    insumos_empaque = Producto.query.filter(
        Producto.activo == True,
        Producto.tipo_producto == 'insumo_empaque'
    ).order_by(Producto.nombre.asc()).all()

    return render_template(
        'produccion/envasado.html',
        quimicos_granel=quimicos_granel,
        insumos_empaque=insumos_empaque
    )


@produccion_bp.route('/mermas', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def mermas():
    """
    Registro y Control de Mermas, Derrames, Evaporación y Daños Químicos.
    Descuenta del inventario físico justificando el motivo y acta de inspección.
    """
    MOTIVOS_MERMA = [
        'Evaporación natural de químicos volátiles',
        'Rotura o perforación de envase durante cargue/descargue',
        'Derrame accidental en bodega o trasvase',
        'Vencimiento o descomposición química',
        'Contaminación cruzada / Pérdida de calidad'
    ]

    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        presentacion_id = request.form.get('presentacion_id', type=int) or None
        lote_id = request.form.get('lote_id', type=int) or None
        cantidad_merma = request.form.get('cantidad', type=float)
        tipo_merma = request.form.get('tipo_merma', '').strip()
        acta_soporte = request.form.get('acta_soporte', '').strip() or f"ACTA-MERMA-{datetime.now().strftime('%Y%m%d%H%M')}"
        detalle = request.form.get('detalle', '').strip()

        if not producto_id or not cantidad_merma or cantidad_merma <= 0 or not tipo_merma:
            flash('Producto, cantidad de merma mayor a 0 y tipo de merma son obligatorios.', 'danger')
            return redirect(url_for('produccion_bp.mermas'))

        prod = Producto.query.get_or_404(producto_id)
        pres = db.session.get(PresentacionComercial, presentacion_id) if presentacion_id else None
        lote = db.session.get(Lote, lote_id) if lote_id else None

        motivo_completo = f"MERMA [{tipo_merma}]: {detalle}".strip()

        try:
            registrar_movimiento(
                usuario_id=current_user.id,
                producto_id=prod.id,
                tipo_movimiento='MERMA_DERRAME',
                cantidad=Decimal(str(-cantidad_merma)),  # Pérdida: valor negativo
                motivo_observaciones=motivo_completo,
                presentacion_id=pres.id if pres else None,
                lote_id=lote.id if lote else None,
                documento_soporte=acta_soporte,
                commit=True
            )
            flash(f'Pérdida/Merma de {cantidad_merma} registrada correctamente bajo {acta_soporte}.', 'warning')
            return redirect(url_for('reportes_bp.kardex'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la merma: {str(e)}', 'danger')
            return redirect(url_for('produccion_bp.mermas'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    return render_template(
        'produccion/mermas.html',
        productos=productos,
        motivos_merma=MOTIVOS_MERMA
    )
