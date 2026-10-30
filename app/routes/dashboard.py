from datetime import date, datetime
from flask import Blueprint, render_template
from flask_login import login_required
from app.models import db, Producto, PresentacionComercial, Lote, MovimientoKardex
from app.services.fefo_service import obtener_resumen_vencimientos

dashboard_bp = Blueprint('dashboard_bp', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    """Panel principal con métricas de bodega, alertas FEFO y sugeridos de reorden."""
    productos_activos = Producto.query.filter_by(activo=True).all()

    # KPI 1: Valor total del inventario
    valor_total = sum(float(p.valor_total_inventario) for p in productos_activos)

    # KPI 2: Productos bajo stock mínimo
    productos_bajo_stock = [p for p in productos_activos if p.en_alerta_stock]

    # KPI 3: Estado de lotes FEFO
    resumen_lotes = obtener_resumen_vencimientos()

    # Tabla de Alertas de Compras / Sugeridos de Reabastecimiento
    alertas_compra = []
    for p in productos_bajo_stock:
        faltante = max(0.0, float(p.stock_minimo_alerta) - float(p.stock_actual_total))
        # Sugerencia: reponer mínimo 1.5 veces el punto de reorden o la diferencia
        sugerido = max(faltante, float(p.stock_minimo_alerta) * 0.5)
        alertas_compra.append({
            'producto': p,
            'stock_actual': float(p.stock_actual_total),
            'stock_minimo': float(p.stock_minimo_alerta),
            'faltante': faltante,
            'cantidad_sugerida': round(sugerido, 1),
            'unidad': p.unidad_legible
        })

    # Últimos 10 movimientos de Kardex
    ultimos_movimientos = MovimientoKardex.query.order_by(MovimientoKardex.fecha.desc()).limit(10).all()

    # Lotes críticos (< 30 días o vencidos) para atención inmediata (excluyendo no perecederos)
    lotes_urgentes = Lote.query.filter(
        Lote.estado == 'ACTIVO',
        Lote.cantidad_actual > 0,
        Lote.fecha_vencimiento.isnot(None),
        Lote.fecha_vencimiento <= date.today()
    ).order_by(Lote.fecha_vencimiento.asc()).limit(5).all()

    lotes_proximos = Lote.query.filter(
        Lote.estado == 'ACTIVO',
        Lote.cantidad_actual > 0,
        Lote.fecha_vencimiento.isnot(None),
        Lote.fecha_vencimiento > date.today(),
        Lote.fecha_vencimiento <= date.fromordinal(date.today().toordinal() + 30)
    ).order_by(Lote.fecha_vencimiento.asc()).limit(5).all()

    return render_template(
        'dashboard/index.html',
        valor_total=valor_total,
        total_productos=len(productos_activos),
        productos_bajo_stock=productos_bajo_stock,
        resumen_lotes=resumen_lotes,
        alertas_compra=alertas_compra,
        ultimos_movimientos=ultimos_movimientos,
        lotes_urgentes=lotes_urgentes,
        lotes_proximos=lotes_proximos
    )
