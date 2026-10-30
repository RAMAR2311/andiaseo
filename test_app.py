import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
from openpyxl import load_workbook
from app import create_app, db
from app.models import User, Categoria, Producto, PresentacionComercial, Lote, MovimientoKardex
from app.services.fefo_service import obtener_lotes_fefo, sugerir_lote_fefo, validar_salida_lote
from app.services.kardex_service import registrar_movimiento
from app.services.excel_service import generar_kardex_excel, generar_inventario_valorizado_excel

class TestAndiaseoInventory(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Crear datos de prueba
        self.usuario = User(username='test_bodega', nombre='Operario Test', rol='almacenista')
        self.usuario.set_password('pass123')
        db.session.add(self.usuario)

        self.cat = Categoria(nombre='Clorados Test')
        db.session.add(self.cat)
        db.session.flush()

        self.prod_granel = Producto(
            codigo_referencia='CLO-TEST',
            nombre='Cloro Concentrado Test',
            categoria_id=self.cat.id,
            tipo_producto='quimico_liquido',
            unidad_base='litros',
            stock_minimo_alerta=Decimal('100.00'),
            stock_actual_total=Decimal('500.00')
        )
        self.prod_envase = Producto(
            codigo_referencia='ENV-TEST',
            nombre='Galón Vacío 3.8L',
            categoria_id=self.cat.id,
            tipo_producto='insumo_empaque',
            unidad_base='unidades',
            stock_minimo_alerta=Decimal('50.00'),
            stock_actual_total=Decimal('100.00')
        )
        db.session.add_all([self.prod_granel, self.prod_envase])
        db.session.flush()

        self.pres_galon = PresentacionComercial(
            producto_id=self.prod_granel.id,
            nombre_presentacion='Galón 3.8L Test',
            factor_conversion_base=Decimal('3.7850'),
            stock_actual=Decimal('10.00'),
            costo_promedio_unitario=Decimal('15000.00')
        )
        db.session.add(self.pres_galon)
        db.session.flush()

        hoy = date.today()
        # Lote 1: Vence en 300 días
        self.lote_verde = Lote(
            producto_id=self.prod_granel.id,
            presentacion_id=self.pres_galon.id,
            numero_lote='LOT-VERDE-01',
            fecha_produccion=hoy,
            fecha_vencimiento=hoy + timedelta(days=300),
            cantidad_inicial=Decimal('10.00'),
            cantidad_actual=Decimal('10.00'),
            estado='ACTIVO'
        )
        # Lote 2: Vence en 45 días (más próximo a vencer, debe ser el sugerido FEFO)
        self.lote_amarillo = Lote(
            producto_id=self.prod_granel.id,
            presentacion_id=self.pres_galon.id,
            numero_lote='LOT-AMARILLO-02',
            fecha_produccion=hoy,
            fecha_vencimiento=hoy + timedelta(days=45),
            cantidad_inicial=Decimal('5.00'),
            cantidad_actual=Decimal('5.00'),
            estado='ACTIVO'
        )
        # Lote 3: Vencido
        self.lote_vencido = Lote(
            producto_id=self.prod_granel.id,
            presentacion_id=self.pres_galon.id,
            numero_lote='LOT-VENCIDO-03',
            fecha_produccion=hoy - timedelta(days=60),
            fecha_vencimiento=hoy - timedelta(days=5),
            cantidad_inicial=Decimal('2.00'),
            cantidad_actual=Decimal('2.00'),
            estado='VENCIDO'
        )
        # Lote 4: Cuarentena
        self.lote_cuarentena = Lote(
            producto_id=self.prod_granel.id,
            presentacion_id=self.pres_galon.id,
            numero_lote='LOT-CUARENTENA-04',
            fecha_produccion=hoy,
            fecha_vencimiento=hoy + timedelta(days=200),
            cantidad_inicial=Decimal('4.00'),
            cantidad_actual=Decimal('4.00'),
            estado='CUARENTENA'
        )

        db.session.add_all([self.lote_verde, self.lote_amarillo, self.lote_vencido, self.lote_cuarentena])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_autenticacion_usuario(self):
        """Verifica hash y autenticación de contraseña."""
        self.assertTrue(self.usuario.check_password('pass123'))
        self.assertFalse(self.usuario.check_password('wrongpass'))

    def test_algoritmo_fefo_sugerencia(self):
        """Verifica que el lote sugerido sea el más próximo a vencer y no vencido."""
        lotes_fefo = obtener_lotes_fefo(self.prod_granel.id, presentacion_id=self.pres_galon.id)
        self.assertEqual(len(lotes_fefo), 2)  # Excluye vencido y cuarentena
        # El primero debe ser el amarillo (vence en 45 días) antes que el verde (300 días)
        self.assertEqual(lotes_fefo[0].id, self.lote_amarillo.id)

        sugerido = sugerir_lote_fefo(self.prod_granel.id, presentacion_id=self.pres_galon.id)
        self.assertEqual(sugerido.id, self.lote_amarillo.id)

    def test_bloqueo_sanitario_lote(self):
        """Verifica que un lote vencido o en cuarentena no pueda salir por despacho."""
        permitido, error = validar_salida_lote(self.lote_vencido)
        self.assertFalse(permitido)
        self.assertIn("VENCIDO", error)

        permitido_cuar, error_cuar = validar_salida_lote(self.lote_cuarentena)
        self.assertFalse(permitido_cuar)
        self.assertIn("CUARENTENA", error_cuar)

    def test_transaccion_fraccionamiento_atomico(self):
        """Prueba fraccionamiento: descuenta granel + empaque y genera producto terminado."""
        granel_inicial = self.prod_granel.stock_actual_total
        envase_inicial = self.prod_envase.stock_actual_total
        pres_inicial = self.pres_galon.stock_actual

        litros_fraccionar = Decimal('37.85')
        envases_usar = Decimal('10.00')
        unidades_generadas = Decimal('10.00')

        # Ejecutar transacción atómica de fraccionamiento
        # 1. Descuenta granel
        registrar_movimiento(
            usuario_id=self.usuario.id,
            producto_id=self.prod_granel.id,
            tipo_movimiento='FRACCIONAMIENTO_ORIGEN',
            cantidad=-litros_fraccionar,
            motivo_observaciones="Fraccionamiento a galones",
            commit=False
        )
        # 2. Descuenta envases
        registrar_movimiento(
            usuario_id=self.usuario.id,
            producto_id=self.prod_envase.id,
            tipo_movimiento='FRACCIONAMIENTO_ORIGEN',
            cantidad=-envases_usar,
            motivo_observaciones="Consumo de envases",
            commit=False
        )
        # 3. Ingresa terminados
        registrar_movimiento(
            usuario_id=self.usuario.id,
            producto_id=self.prod_granel.id,
            tipo_movimiento='FRACCIONAMIENTO_DESTINO',
            cantidad=unidades_generadas,
            motivo_observaciones="Ingreso de galones terminados",
            presentacion_id=self.pres_galon.id,
            commit=False
        )
        db.session.commit()

        # Verificaciones
        self.assertEqual(self.prod_granel.stock_actual_total, granel_inicial - litros_fraccionar + (unidades_generadas * self.pres_galon.factor_conversion_base))
        self.assertEqual(self.prod_envase.stock_actual_total, envase_inicial - envases_usar)
        self.assertEqual(self.pres_galon.stock_actual, pres_inicial + unidades_generadas)

        # Verificar que se crearon 3 registros en Kardex
        kardex_count = MovimientoKardex.query.count()
        self.assertEqual(kardex_count, 3)

    def test_registro_merma(self):
        """Prueba registro de merma operativa."""
        pres_inicial = self.pres_galon.stock_actual
        merma_cant = Decimal('2.00')

        registrar_movimiento(
            usuario_id=self.usuario.id,
            producto_id=self.prod_granel.id,
            tipo_movimiento='MERMA_DERRAME',
            cantidad=-merma_cant,
            motivo_observaciones="MERMA [Rotura]: Envase roto por golpe",
            presentacion_id=self.pres_galon.id,
            commit=True
        )

        self.assertEqual(self.pres_galon.stock_actual, pres_inicial - merma_cant)
        ultimo_kardex = MovimientoKardex.query.order_by(MovimientoKardex.id.desc()).first()
        self.assertEqual(ultimo_kardex.tipo_movimiento, 'MERMA_DERRAME')

    def test_generacion_excel_kardex_y_valorizado(self):
        """Prueba que los servicios OpenPyXL generen archivos válidos en memoria."""
        # Generar un movimiento para el kardex
        registrar_movimiento(
            usuario_id=self.usuario.id,
            producto_id=self.prod_granel.id,
            tipo_movimiento='ENTRADA_COMPRA',
            cantidad=Decimal('5.00'),
            motivo_observaciones="Compra de prueba",
            presentacion_id=self.pres_galon.id
        )

        movimientos = MovimientoKardex.query.all()
        excel_kardex = generar_kardex_excel(movimientos, "Filtro de prueba")
        self.assertIsInstance(excel_kardex, io.BytesIO)
        
        # Cargar el archivo generado con openpyxl para verificar integridad
        wb_k = load_workbook(excel_kardex)
        self.assertIn("Kardex de Movimientos", wb_k.sheetnames)

        # Generar inventario valorizado
        productos = Producto.query.all()
        excel_val = generar_inventario_valorizado_excel(productos)
        self.assertIsInstance(excel_val, io.BytesIO)
        wb_v = load_workbook(excel_val)
        self.assertIn("Inventario Valorizado", wb_v.sheetnames)

if __name__ == '__main__':
    unittest.main()
