from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models import db, Producto, PresentacionComercial, Lote
from app.routes.auth import role_required
from app.services.kardex_service import registrar_movimiento

produccion_bp = Blueprint('produccion_bp', __name__)

@produccion_bp.route('/mermas', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'almacenista')
def mermas():
    """
    Registro y Control de Bajas, Mermas y Averías en Bodega (Rotura de envase, vencimiento, daños físicos).
    Descuenta del inventario físico justificando el motivo y acta de inspección.
    """
    MOTIVOS_MERMA = [
        'Rotura o perforación de envase durante cargue/descargue',
        'Derrame accidental o daño en bodega',
        'Vencimiento o descomposición química',
        'Defecto de fábrica o sello defectuoso',
        'Pérdida de calidad / Inutilizable'
    ]

    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        presentacion_id = request.form.get('presentacion_id', type=int) or None
        lote_id = request.form.get('lote_id', type=int) or None
        cantidad_merma = request.form.get('cantidad', type=float)
        tipo_merma = request.form.get('tipo_merma', '').strip()
        acta_soporte = request.form.get('acta_soporte', '').strip() or f"ACTA-BAJA-{datetime.now().strftime('%Y%m%d%H%M')}"
        detalle = request.form.get('detalle', '').strip()

        if not producto_id or not cantidad_merma or cantidad_merma <= 0 or not tipo_merma:
            flash('Producto, cantidad de merma/baja mayor a 0 y tipo de merma son obligatorios.', 'danger')
            return redirect(url_for('produccion_bp.mermas'))

        prod = Producto.query.get_or_404(producto_id)
        pres = db.session.get(PresentacionComercial, presentacion_id) if presentacion_id else None
        lote = db.session.get(Lote, lote_id) if lote_id else None

        motivo_completo = f"BAJA/MERMA [{tipo_merma}]: {detalle}".strip()

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
            flash(f'Baja/Merma de {cantidad_merma} unidades registrada correctamente bajo {acta_soporte}.', 'warning')
            return redirect(url_for('reportes_bp.kardex'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la baja/merma: {str(e)}', 'danger')
            return redirect(url_for('produccion_bp.mermas'))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre.asc()).all()
    return render_template(
        'produccion/mermas.html',
        productos=productos,
        motivos_merma=MOTIVOS_MERMA
    )
