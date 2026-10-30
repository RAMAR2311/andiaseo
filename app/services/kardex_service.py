from datetime import datetime
from decimal import Decimal
from app.models import db, MovimientoKardex, Producto, PresentacionComercial, Lote

def registrar_movimiento(
    usuario_id,
    producto_id,
    tipo_movimiento,
    cantidad,
    motivo_observaciones,
    presentacion_id=None,
    lote_id=None,
    documento_soporte=None,
    archivo_comprobante=None,
    commit=True
):
    """
    Registra un movimiento inmutable en el Kardex y actualiza los stocks correspondientes.
    
    Parámetros:
        usuario_id (int): ID del usuario que ejecuta la acción
        producto_id (int): ID del producto afectado
        tipo_movimiento (str): Uno de los tipos válidos en MovimientoKardex
        cantidad (Decimal/float): Magnitud del cambio (+ para entradas, - para salidas)
        motivo_observaciones (str): Justificación obligatoria
        presentacion_id (int, optional): ID de la presentación comercial afectada
        lote_id (int, optional): ID del lote afectado
        documento_soporte (str, optional): Número de remisión, factura o acta
        commit (bool): Si es True realiza commit inmediato; False para transacciones compuestas
        
    Retorna:
        MovimientoKardex: La instancia del movimiento generado
    """
    producto = db.session.get(Producto, producto_id)
    if not producto:
        raise ValueError(f"El producto con ID {producto_id} no existe.")

    presentacion = db.session.get(PresentacionComercial, presentacion_id) if presentacion_id else None
    lote = db.session.get(Lote, lote_id) if lote_id else None

    cantidad_dec = Decimal(str(cantidad))

    # Determinar stock anterior y nuevo
    if presentacion:
        stock_anterior = Decimal(str(presentacion.stock_actual or 0))
        stock_nuevo = stock_anterior + cantidad_dec
        if stock_nuevo < 0:
            raise ValueError(
                f"Stock insuficiente para {producto.nombre} - {presentacion.nombre_presentacion}. "
                f"Disponible: {stock_anterior}, Solicitado: {abs(cantidad_dec)}"
            )
        presentacion.stock_actual = stock_nuevo

        # Actualizar stock consolidado del producto en unidad base
        factor = Decimal(str(presentacion.factor_conversion_base or 1))
        impacto_base = cantidad_dec * factor
        prod_anterior = Decimal(str(producto.stock_actual_total or 0))
        producto.stock_actual_total = max(Decimal('0.0'), prod_anterior + impacto_base)
    else:
        # Movimiento directo a granel / unidad base
        stock_anterior = Decimal(str(producto.stock_actual_total or 0))
        stock_nuevo = stock_anterior + cantidad_dec
        if stock_nuevo < 0:
            raise ValueError(
                f"Stock insuficiente para {producto.nombre} a granel. "
                f"Disponible: {stock_anterior} {producto.unidad_base}, Solicitado: {abs(cantidad_dec)}"
            )
        producto.stock_actual_total = stock_nuevo

    # Actualizar lote si se especificó
    if lote:
        lote_anterior = Decimal(str(lote.cantidad_actual or 0))
        lote_nuevo = lote_anterior + cantidad_dec
        if lote_nuevo < 0:
            raise ValueError(
                f"Existencias insuficientes en el Lote {lote.numero_lote}. "
                f"Disponible en lote: {lote_anterior}, Solicitado: {abs(cantidad_dec)}"
            )
        lote.cantidad_actual = lote_nuevo
        if lote.cantidad_actual == 0:
            lote.estado = 'AGOTADO'
        elif lote.estado == 'AGOTADO' and lote.cantidad_actual > 0:
            lote.estado = 'ACTIVO'

    # Crear el registro histórico del Kardex
    movimiento = MovimientoKardex(
        fecha=datetime.utcnow(),
        usuario_id=usuario_id,
        producto_id=producto.id,
        presentacion_id=presentacion.id if presentacion else None,
        lote_id=lote.id if lote else None,
        tipo_movimiento=tipo_movimiento,
        cantidad=cantidad_dec,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        motivo_observaciones=motivo_observaciones.strip(),
        documento_soporte=documento_soporte.strip() if documento_soporte else None,
        archivo_comprobante=archivo_comprobante.strip() if archivo_comprobante else None
    )
    db.session.add(movimiento)

    if commit:
        db.session.commit()

    return movimiento
