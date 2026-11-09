from datetime import date
from app.models import Lote, db

def obtener_lotes_fefo(producto_id, presentacion_id=None, solo_disponibles=True):
    """
    Obtiene los lotes de un producto ordenados estrictamente bajo la regla FEFO
    (First Expired, First Out - Primero en Vencer, Primero en Salir).
    """
    query = Lote.query.filter(Lote.producto_id == producto_id)
    
    if presentacion_id is not None:
        query = query.filter(Lote.presentacion_id == presentacion_id)
        
    if solo_disponibles:
        query = query.filter(
            Lote.estado == 'ACTIVO',
            Lote.cantidad_actual > 0,
            db.or_(
                Lote.fecha_vencimiento.is_(None),
                Lote.fecha_vencimiento >= date.today()
            )
        )
        
    # Ordenamiento FEFO: los que tienen vencimiento próximo primero, y los no perecederos (NULL) al final
    return query.order_by(Lote.fecha_vencimiento.asc().nullslast(), Lote.fecha_produccion.asc().nullslast()).all()


def sugerir_lote_fefo(producto_id, presentacion_id=None):
    """
    Retorna el lote sugerido para despacho o consumo siguiendo FEFO.
    Excluye lotes vencidos o en cuarentena.
    """
    lotes = obtener_lotes_fefo(producto_id, presentacion_id=presentacion_id, solo_disponibles=True)
    return lotes[0] if lotes else None


def validar_salida_lote(lote):
    """
    Verifica si un lote puede ser despachado o consumido.
    Retorna (permitido: bool, motivo_error: str).
    """
    if not lote:
        return False, "El lote especificado no existe."
    if lote.estado == 'CUARENTENA':
        return False, f"El lote {lote.numero_lote} está en CUARENTENA y no puede despacharse."
    if lote.fecha_vencimiento and (lote.estado == 'VENCIDO' or lote.dias_para_vencer < 0):
        return False, f"ALERTA SANITARIA: El lote {lote.numero_lote} está VENCIDO (venció el {lote.fecha_vencimiento.strftime('%d/%m/%Y')}). Salida bloqueada."
    if float(lote.cantidad_actual or 0) <= 0:
        return False, f"El lote {lote.numero_lote} no tiene existencias disponibles."
    return True, ""


def obtener_resumen_vencimientos():
    """
    Calcula estadísticas de vencimientos de lotes en todo el inventario:
    - Vencidos (< 0 días)
    - Críticos (<= 30 días)
    - Próximos a vencer (31 a 90 días)
    - Rotación (91 a 180 días)
    - Óptimos (> 180 días)
    - No perecederos (sin fecha de vencimiento)
    """
    hoy = date.today()
    lotes_activos = Lote.query.filter(Lote.estado != 'AGOTADO', Lote.cantidad_actual > 0).all()
    
    resumen = {
        'vencidos': 0,
        'criticos_30d': 0,
        'proximos_90d': 0,
        'rotacion_180d': 0,
        'optimos': 0,
        'no_perecederos': 0,
        'total_lotes_vigentes': 0
    }
    
    for l in lotes_activos:
        if l.estado == 'CUARENTENA':
            continue
        if not l.fecha_vencimiento:
            resumen['no_perecederos'] += 1
            resumen['total_lotes_vigentes'] += 1
            continue
        dias = (l.fecha_vencimiento - hoy).days
        if dias < 0:
            resumen['vencidos'] += 1
        elif dias <= 30:
            resumen['criticos_30d'] += 1
            resumen['total_lotes_vigentes'] += 1
        elif dias <= 90:
            resumen['proximos_90d'] += 1
            resumen['total_lotes_vigentes'] += 1
        elif dias <= 180:
            resumen['rotacion_180d'] += 1
            resumen['total_lotes_vigentes'] += 1
        else:
            resumen['optimos'] += 1
            resumen['total_lotes_vigentes'] += 1
            
    return resumen
