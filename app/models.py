from datetime import datetime, date
from decimal import Decimal
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Modelo de Usuario para autenticación y auditoría en bodega."""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='almacenista')  # 'admin', 'almacenista', 'auditor'
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    movimientos = db.relationship('MovimientoKardex', back_populates='usuario', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def es_admin(self):
        return self.rol == 'admin'

    @property
    def es_auditor(self):
        return self.rol in ('admin', 'auditor')

    def __repr__(self):
        return f'<User {self.username} ({self.rol})>'


class Categoria(db.Model):
    """Categoría de productos químicos, insumos y herramientas."""
    __tablename__ = 'categoria'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), unique=True, nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)

    movimientos = db.relationship('MovimientoKardex', back_populates='categoria', cascade='all, delete-orphan') if hasattr(db, 'nothing') else None
    productos = db.relationship('Producto', back_populates='categoria', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Categoria {self.nombre}>'


class Tercero(db.Model):
    """Modelo para Clientes y Proveedores de Andiaseo."""
    __tablename__ = 'tercero'

    TIPOS_VALIDOS = {
        'cliente': 'Cliente',
        'proveedor': 'Proveedor',
        'ambos': 'Cliente y Proveedor'
    }

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, default='cliente') # 'cliente', 'proveedor', 'ambos'
    documento_nit = db.Column(db.String(40), unique=True, nullable=False, index=True)
    nombre_razon_social = db.Column(db.String(150), nullable=False, index=True)
    telefono = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    ciudad = db.Column(db.String(80), nullable=True)
    contacto_nombre = db.Column(db.String(120), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    movimientos = db.relationship('MovimientoKardex', back_populates='tercero', lazy='dynamic')

    @property
    def tipo_legible(self):
        return self.TIPOS_VALIDOS.get(self.tipo, self.tipo)

    @property
    def total_facturas_asociadas(self):
        """Devuelve cuántas operaciones de Kardex están vinculadas a este tercero."""
        return self.movimientos.count()

    def __repr__(self):
        return f'<Tercero {self.documento_nit} - {self.nombre_razon_social} ({self.tipo})>'


class Producto(db.Model):
    """Producto base: químico líquido/polvo a granel, insumo de empaque o accesorio."""
    __tablename__ = 'producto'

    TIPOS_VALIDOS = {
        'quimico_liquido': 'Químico Líquido',
        'quimico_polvo': 'Químico en Polvo',
        'insumo_empaque': 'Insumo de Empaque',
        'accesorio_herramienta': 'Accesorio o Herramienta'
    }

    UNIDADES_VALIDAS = {
        'litros': 'Litros (L)',
        'kilogramos': 'Kilogramos (Kg)',
        'unidades': 'Unidades (Und)'
    }

    id = db.Column(db.Integer, primary_key=True)
    codigo_referencia = db.Column(db.String(50), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(150), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    tipo_producto = db.Column(db.String(30), nullable=False, default='quimico_liquido')
    unidad_base = db.Column(db.String(20), nullable=False, default='litros')
    stock_minimo_alerta = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    stock_actual_total = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    costo_unitario_base = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    requiere_vencimiento = db.Column(db.Boolean, default=True, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    categoria = db.relationship('Categoria', back_populates='productos')
    presentaciones = db.relationship('PresentacionComercial', back_populates='producto', cascade='all, delete-orphan')
    lotes = db.relationship('Lote', back_populates='producto', cascade='all, delete-orphan', lazy='dynamic')
    movimientos = db.relationship('MovimientoKardex', back_populates='producto', lazy='dynamic')

    @property
    def en_alerta_stock(self):
        """Indica si el stock total está por debajo o igual al punto mínimo de reorden."""
        return float(self.stock_actual_total or 0) <= float(self.stock_minimo_alerta or 0)

    @property
    def stock_en_presentaciones_equivalente(self):
        """Calcula el volumen/peso total contenido en todas sus presentaciones comerciales activas."""
        total = Decimal('0.0')
        for p in self.presentaciones:
            if p.activo:
                total += Decimal(str(p.stock_actual or 0)) * Decimal(str(p.factor_conversion_base or 0))
        return total

    @property
    def valor_total_inventario(self):
        """Valor económico total sumando el inventario de todas sus presentaciones comerciales o de su stock a granel."""
        total = Decimal('0.0')
        if self.presentaciones and len([p for p in self.presentaciones if p.activo]) > 0:
            for p in self.presentaciones:
                if p.activo:
                    total += Decimal(str(p.stock_actual or 0)) * Decimal(str(p.costo_promedio_unitario or 0))
        else:
            # Producto a granel / directo
            total = Decimal(str(self.stock_actual_total or 0)) * Decimal(str(self.costo_unitario_base or 0))
        return total

    @property
    def tipo_legible(self):
        return self.TIPOS_VALIDOS.get(self.tipo_producto, self.tipo_producto)

    @property
    def unidad_legible(self):
        return self.UNIDADES_VALIDAS.get(self.unidad_base, self.unidad_base)

    def sincronizar_stock_total(self):
        """
        Sincroniza el stock_actual_total del producto:
        Si tiene presentaciones comerciales, el stock_actual_total puede reflejar la suma
        del volumen envasado + el volumen que permanezca en granel directo.
        """
        pass

    def __repr__(self):
        return f'<Producto {self.codigo_referencia} - {self.nombre}>'


class PresentacionComercial(db.Model):
    """Presentación comercial del producto (ej: Frasco 500ml, Galón 3.8L, Garrafa 20L)."""
    __tablename__ = 'presentacion_comercial'

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    nombre_presentacion = db.Column(db.String(100), nullable=False)
    factor_conversion_base = db.Column(db.Numeric(10, 4), nullable=False, default=1.0)
    codigo_barras = db.Column(db.String(64), unique=True, nullable=True, index=True)
    stock_actual = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    costo_promedio_unitario = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    precio_referencia = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    producto = db.relationship('Producto', back_populates='presentaciones')
    lotes = db.relationship('Lote', back_populates='presentacion', lazy='dynamic')
    movimientos = db.relationship('MovimientoKardex', back_populates='presentacion', lazy='dynamic')

    @property
    def equivalente_base(self):
        """Equivalente en la unidad base del producto (ej: 10 galones * 3.785 = 37.85 L)."""
        return Decimal(str(self.stock_actual or 0)) * Decimal(str(self.factor_conversion_base or 1))

    @property
    def valor_inventario(self):
        """Valorización física del stock actual de esta presentación."""
        return Decimal(str(self.stock_actual or 0)) * Decimal(str(self.costo_promedio_unitario or 0))

    def __repr__(self):
        return f'<PresentacionComercial {self.nombre_presentacion} ({self.producto.nombre if self.producto else "N/A"})>'


class Lote(db.Model):
    """Lote de producción o recepción con trazabilidad sanitaria y fecha de vencimiento (FEFO)."""
    __tablename__ = 'lote'

    ESTADOS_VALIDOS = ['ACTIVO', 'CUARENTENA', 'VENCIDO', 'AGOTADO']

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    presentacion_id = db.Column(db.Integer, db.ForeignKey('presentacion_comercial.id'), nullable=True)
    numero_lote = db.Column(db.String(60), nullable=False, index=True)
    fecha_produccion = db.Column(db.Date, nullable=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True, index=True)
    registro_sanitario = db.Column(db.String(100), nullable=True)  # Ej: INVIMA o Registro Sanitario/Ambiental
    cantidad_inicial = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    cantidad_actual = db.Column(db.Numeric(12, 2), nullable=False, default=0.0)
    estado = db.Column(db.String(20), nullable=False, default='ACTIVO')
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    producto = db.relationship('Producto', back_populates='lotes')
    presentacion = db.relationship('PresentacionComercial', back_populates='lotes')
    movimientos = db.relationship('MovimientoKardex', back_populates='lote', lazy='dynamic')

    @property
    def dias_para_vencer(self):
        """Días restantes para el vencimiento (positivo: vigente, negativo: vencido)."""
        if not self.fecha_vencimiento:
            return 9999
        hoy = date.today()
        return (self.fecha_vencimiento - hoy).days

    @property
    def semaforo_fefo(self):
        """
        Algoritmo de Semáforo FEFO:
        - 'no_aplica': sin fecha de vencimiento configurada
        - 'agotado': cantidad_actual <= 0 o estado 'AGOTADO'
        - 'cuarentena': estado 'CUARENTENA'
        - 'vencido': días < 0 o estado 'VENCIDO'
        - 'rojo': días <= 30 (riesgo inminente de vencimiento, prioridad crítica)
        - 'amarillo': 30 < días <= 180 (1 a 6 meses, prioridad de rotación preventiva)
        - 'verde': días > 180 (> 6 meses, en excelente estado)
        """
        if self.estado == 'CUARENTENA':
            return 'cuarentena'
        if float(self.cantidad_actual or 0) <= 0 or self.estado == 'AGOTADO':
            return 'agotado'
        if not self.fecha_vencimiento:
            return 'no_aplica'
        dias = self.dias_para_vencer
        if dias < 0:
            return 'vencido'
        if dias <= 30:
            return 'rojo'
        if dias <= 180:
            return 'amarillo'
        return 'verde'

    @property
    def semaforo_badge(self):
        """Devuelve diccionario con estilos y etiquetas para Jinja2."""
        sem = self.semaforo_fefo
        dias = self.dias_para_vencer
        if sem == 'no_aplica':
            return {
                'color': 'info',
                'icono': 'fa-infinity',
                'texto': 'No Perecedero',
                'alerta': 'Sin fecha de vencimiento (No aplica FEFO)'
            }
        elif sem == 'verde':
            return {
                'color': 'success',
                'icono': 'fa-check-circle',
                'texto': f'Óptimo ({dias} días)',
                'alerta': 'Vencimiento mayor a 6 meses'
            }
        elif sem == 'amarillo':
            return {
                'color': 'warning',
                'icono': 'fa-exclamation-triangle',
                'texto': f'Rotación ({dias} días)',
                'alerta': 'Vence entre 1 y 6 meses (Prioridad FEFO)'
            }
        elif sem == 'rojo':
            return {
                'color': 'danger',
                'icono': 'fa-radiation',
                'texto': f'Crítico ({dias} días)',
                'alerta': 'Vence en menos de 30 días'
            }
        elif sem == 'vencido':
            return {
                'color': 'dark',
                'icono': 'fa-skull-crossbones',
                'texto': f'Vencido ({abs(dias)} días atrás)',
                'alerta': 'LOTE VENCIDO - Salida Bloqueada'
            }
        elif sem == 'cuarentena':
            return {
                'color': 'secondary',
                'icono': 'fa-lock',
                'texto': 'En Cuarentena',
                'alerta': 'Bloqueado por inspección de calidad'
            }
        else:
            return {
                'color': 'light',
                'icono': 'fa-boxes-stacked',
                'texto': 'Agotado',
                'alerta': 'Lote sin existencias'
            }

    def __repr__(self):
        return f'<Lote {self.numero_lote} ({self.producto.nombre if self.producto else "N/A"}) - {self.cantidad_actual}>'


class MovimientoKardex(db.Model):
    """
    Registro histórico inmutable de todos los movimientos de inventario.
    Permite auditar entradas, salidas, fraccionamientos, mermas y ajustes físicos.
    """
    __tablename__ = 'movimiento_kardex'

    TIPOS_VALIDOS = {
        'ENTRADA_COMPRA': 'Entrada por Compra',
        'SALIDA_DESPACHO': 'Salida por Despacho',
        'FRACCIONAMIENTO_ORIGEN': 'Fraccionamiento (Descuento Granel/Insumo)',
        'FRACCIONAMIENTO_DESTINO': 'Fraccionamiento (Ingreso Terminado)',
        'MERMA_DERRAME': 'Merma / Derrame / Rotura',
        'AJUSTE_AUDITORIA': 'Ajuste de Auditoría'
    }

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    presentacion_id = db.Column(db.Integer, db.ForeignKey('presentacion_comercial.id'), nullable=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote.id'), nullable=True)
    tercero_id = db.Column(db.Integer, db.ForeignKey('tercero.id'), nullable=True)
    tipo_movimiento = db.Column(db.String(40), nullable=False, index=True)
    cantidad = db.Column(db.Numeric(12, 2), nullable=False)  # Puede ser positivo (ingreso) o negativo (salida)
    stock_anterior = db.Column(db.Numeric(12, 2), nullable=False)
    stock_nuevo = db.Column(db.Numeric(12, 2), nullable=False)
    motivo_observaciones = db.Column(db.Text, nullable=False)
    documento_soporte = db.Column(db.String(100), nullable=True)  # Nro factura, remisión, orden de envasado o acta
    archivo_comprobante = db.Column(db.String(255), nullable=True)  # Nombre o ruta del archivo de comprobante cargado

    usuario = db.relationship('User', back_populates='movimientos')
    producto = db.relationship('Producto', back_populates='movimientos')
    presentacion = db.relationship('PresentacionComercial', back_populates='movimientos')
    lote = db.relationship('Lote', back_populates='movimientos')
    tercero = db.relationship('Tercero', back_populates='movimientos')

    @property
    def tipo_legible(self):
        return self.TIPOS_VALIDOS.get(self.tipo_movimiento, self.tipo_movimiento)

    @property
    def es_ingreso(self):
        return self.tipo_movimiento in ('ENTRADA_COMPRA', 'FRACCIONAMIENTO_DESTINO') or (
            self.tipo_movimiento == 'AJUSTE_AUDITORIA' and self.cantidad > 0
        )

    def __repr__(self):
        return f'<Kardex {self.id} [{self.tipo_movimiento}] Prod:{self.producto_id} Cant:{self.cantidad}>'
