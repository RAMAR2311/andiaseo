from datetime import date, datetime, timedelta
from decimal import Decimal
from app import create_app, db
from app.models import User, Categoria, Producto, PresentacionComercial, Lote, MovimientoKardex

def seed_database():
    app = create_app()
    with app.app_context():
        print("--> Recreando base de datos limpia...")
        db.drop_all()
        db.create_all()

        print("--> Creando usuarios de prueba...")
        admin = User(username='admin', nombre='Marlo Administrador', rol='admin', activo=True)
        admin.set_password('admin123')

        bodeguero = User(username='bodeguero', nombre='Jorge Bodeguero', rol='almacenista', activo=True)
        bodeguero.set_password('bodega123')

        auditor = User(username='auditor', nombre='Dra. Clara Calidad', rol='auditor', activo=True)
        auditor.set_password('auditor123')

        db.session.add_all([admin, bodeguero, auditor])
        db.session.flush()

        print("--> Creando categorías de aseo...")
        cat_cloro = Categoria(nombre='Clorados y Desinfectantes', descripcion='Hipocloritos, dióxido de cloro y bactericidas hospitalarios')
        cat_desen = Categoria(nombre='Desengrasantes Industriales', descripcion='Desengrasantes biodegradables, solventes y decapantes')
        cat_jabon = Categoria(nombre='Detergentes y Jabones', descripcion='Jabones de manos, detergente líquido para ropa y pisos')
        cat_empaq = Categoria(nombre='Insumos de Empaque', descripcion='Galones plásticos, garrafas, tapas, atomizadores y etiquetas')
        cat_acces = Categoria(nombre='Accesorios de Limpieza', descripcion='Cepillos industriales, escobas, jaladores y mopas')

        db.session.add_all([cat_cloro, cat_desen, cat_jabon, cat_empaq, cat_acces])
        db.session.flush()

        print("--> Creando productos base (graneles e insumos)...")
        # 1. Hipoclorito de sodio al 15% (Granel)
        prod_cloro = Producto(
            codigo_referencia='QUI-CLO-01',
            nombre='Hipoclorito de Sodio al 15% Concentrado',
            categoria_id=cat_cloro.id,
            descripcion='Desinfectante industrial clorado de alta concentración para potabilización y saneamiento',
            tipo_producto='quimico_liquido',
            unidad_base='litros',
            stock_minimo_alerta=Decimal('500.00'),
            stock_actual_total=Decimal('2800.00'),
            activo=True
        )

        # 2. Desengrasante Industrial
        prod_desen = Producto(
            codigo_referencia='QUI-DES-01',
            nombre='Desengrasante Alcalino Pesado Industrial',
            categoria_id=cat_desen.id,
            descripcion='Removedor concentrado de grasas mecánicas, aceites e hidrocarburos',
            tipo_producto='quimico_liquido',
            unidad_base='litros',
            stock_minimo_alerta=Decimal('300.00'),
            stock_actual_total=Decimal('1500.00'),
            activo=True
        )

        # 3. Jabón Líquido
        prod_jabon = Producto(
            codigo_referencia='QUI-JAB-01',
            nombre='Jabón Líquido Antibacterial Manos (Glicerinado)',
            categoria_id=cat_jabon.id,
            descripcion='Jabón dermolimpiador biodegradable con aroma a frutos cítricos',
            tipo_producto='quimico_liquido',
            unidad_base='litros',
            stock_minimo_alerta=Decimal('200.00'),
            stock_actual_total=Decimal('650.00'),
            activo=True
        )

        # 4. Envase Galón 3.8L
        prod_env_galon = Producto(
            codigo_referencia='INS-ENV-38',
            nombre='Envase Plástico Galón 3.8L Polietileno Natural',
            categoria_id=cat_empaq.id,
            descripcion='Galón rígido soplado con manija para químicos corrosivos',
            tipo_producto='insumo_empaque',
            unidad_base='unidades',
            stock_minimo_alerta=Decimal('150.00'),
            stock_actual_total=Decimal('620.00'),
            activo=True
        )

        # 5. Tapa Galón 38mm
        prod_tapa_38 = Producto(
            codigo_referencia='INS-TAP-38',
            nombre='Tapa Rosca 38mm con Liner Espumado y Sello de Seguridad',
            categoria_id=cat_empaq.id,
            descripcion='Tapa plástica estriada compatible con envase galón',
            tipo_producto='insumo_empaque',
            unidad_base='unidades',
            stock_minimo_alerta=Decimal('200.00'),
            stock_actual_total=Decimal('940.00'),
            activo=True
        )

        # 6. Frasco PET 500ml con Spray
        prod_env_spray = Producto(
            codigo_referencia='INS-BOT-50',
            nombre='Frasco PET 500ml Cilíndrico con Pistola Spray Gatillo',
            categoria_id=cat_empaq.id,
            descripcion='Botella de polietileno tereftalato transparente con atomizador',
            tipo_producto='insumo_empaque',
            unidad_base='unidades',
            stock_minimo_alerta=Decimal('80.00'),
            stock_actual_total=Decimal('280.00'),
            activo=True
        )

        # 7. Escoba Cepillo (Caso de alerta de stock bajo)
        prod_escoba = Producto(
            codigo_referencia='ACC-ESC-01',
            nombre='Escoba Cepillo Barrendero Industrial 40cm Cerdas Duras',
            categoria_id=cat_acces.id,
            descripcion='Cepillo de barrido pesado para naves de producción y patios de maniobra',
            tipo_producto='accesorio_herramienta',
            unidad_base='unidades',
            stock_minimo_alerta=Decimal('25.00'),
            stock_actual_total=Decimal('12.00'),  # BAJO MÍNIMO
            activo=True
        )

        db.session.add_all([
            prod_cloro, prod_desen, prod_jabon,
            prod_env_galon, prod_tapa_38, prod_env_spray, prod_escoba
        ])
        db.session.flush()

        print("--> Creando presentaciones comerciales...")
        # Cloro: Galón 3.8L y Garrafa 20L
        pres_cloro_galon = PresentacionComercial(
            producto_id=prod_cloro.id,
            nombre_presentacion='Galón 3.8 Litros',
            factor_conversion_base=Decimal('3.7850'),
            codigo_barras='7701234567801',
            stock_actual=Decimal('50.00'),
            costo_promedio_unitario=Decimal('14800.00'),
            precio_referencia=Decimal('22000.00'),
            activo=True
        )
        pres_cloro_garrafa = PresentacionComercial(
            producto_id=prod_cloro.id,
            nombre_presentacion='Garrafa 20 Litros',
            factor_conversion_base=Decimal('20.0000'),
            codigo_barras='7701234567802',
            stock_actual=Decimal('20.00'),
            costo_promedio_unitario=Decimal('69000.00'),
            precio_referencia=Decimal('98000.00'),
            activo=True
        )

        # Desengrasante: Frasco Spray 500ml y Galón 3.8L
        pres_desen_spray = PresentacionComercial(
            producto_id=prod_desen.id,
            nombre_presentacion='Frasco Spray 500ml',
            factor_conversion_base=Decimal('0.5000'),
            codigo_barras='7701234567803',
            stock_actual=Decimal('40.00'),
            costo_promedio_unitario=Decimal('6400.00'),
            precio_referencia=Decimal('12000.00'),
            activo=True
        )
        pres_desen_galon = PresentacionComercial(
            producto_id=prod_desen.id,
            nombre_presentacion='Galón 3.8 Litros',
            factor_conversion_base=Decimal('3.7850'),
            codigo_barras='7701234567804',
            stock_actual=Decimal('30.00'),
            costo_promedio_unitario=Decimal('29500.00'),
            precio_referencia=Decimal('45000.00'),
            activo=True
        )

        # Jabón Líquido: Galón 3.8L
        pres_jabon_galon = PresentacionComercial(
            producto_id=prod_jabon.id,
            nombre_presentacion='Galón 3.8 Litros',
            factor_conversion_base=Decimal('3.7850'),
            codigo_barras='7701234567805',
            stock_actual=Decimal('24.00'),
            costo_promedio_unitario=Decimal('21500.00'),
            precio_referencia=Decimal('34000.00'),
            activo=True
        )

        db.session.add_all([
            pres_cloro_galon, pres_cloro_garrafa,
            pres_desen_spray, pres_desen_galon,
            pres_jabon_galon
        ])
        db.session.flush()

        print("--> Creando lotes con fechas escalonadas para semáforo FEFO...")
        hoy = date.today()

        # 1. Lote Verde Óptimo (> 6 meses / vence en 280 días)
        lote_verde_cloro = Lote(
            producto_id=prod_cloro.id,
            presentacion_id=pres_cloro_galon.id,
            numero_lote='LOT-2026-CLO-01',
            fecha_produccion=hoy - timedelta(days=20),
            fecha_vencimiento=hoy + timedelta(days=280),
            registro_sanitario='INVIMA 2026-NSO-10028',
            cantidad_inicial=Decimal('50.00'),
            cantidad_actual=Decimal('35.00'),
            estado='ACTIVO'
        )

        # 2. Lote Amarillo - Rotación Preventiva (vence en 60 días)
        lote_amarillo_desen = Lote(
            producto_id=prod_desen.id,
            presentacion_id=pres_desen_galon.id,
            numero_lote='LOT-2026-DES-02',
            fecha_produccion=hoy - timedelta(days=120),
            fecha_vencimiento=hoy + timedelta(days=55),
            registro_sanitario='INVIMA 2025-NSO-7721',
            cantidad_inicial=Decimal('30.00'),
            cantidad_actual=Decimal('18.00'),
            estado='ACTIVO'
        )

        # 3. Lote Rojo - Crítico FEFO (vence en 15 días)
        lote_rojo_jabon = Lote(
            producto_id=prod_jabon.id,
            presentacion_id=pres_jabon_galon.id,
            numero_lote='LOT-2026-JAB-03',
            fecha_produccion=hoy - timedelta(days=340),
            fecha_vencimiento=hoy + timedelta(days=15),
            registro_sanitario='INVIMA 2024-NSO-4412',
            cantidad_inicial=Decimal('24.00'),
            cantidad_actual=Decimal('10.00'),
            estado='ACTIVO'
        )

        # 4. Lote Vencido (venció hace 8 días - Alerta Sanitaria)
        lote_vencido_cloro = Lote(
            producto_id=prod_cloro.id,
            presentacion_id=pres_cloro_galon.id,
            numero_lote='LOT-2025-CLO-OLD',
            fecha_produccion=hoy - timedelta(days=400),
            fecha_vencimiento=hoy - timedelta(days=8),
            registro_sanitario='INVIMA 2025-NSO-0991',
            cantidad_inicial=Decimal('15.00'),
            cantidad_actual=Decimal('5.00'),
            estado='VENCIDO'
        )

        # 5. Lote en Cuarentena por Control de Calidad
        lote_cuarentena = Lote(
            producto_id=prod_desen.id,
            presentacion_id=pres_desen_spray.id,
            numero_lote='LOT-2026-DES-CUAR',
            fecha_produccion=hoy - timedelta(days=5),
            fecha_vencimiento=hoy + timedelta(days=360),
            registro_sanitario='INVIMA 2025-NSO-7721',
            cantidad_inicial=Decimal('15.00'),
            cantidad_actual=Decimal('15.00'),
            estado='CUARENTENA'
        )

        db.session.add_all([
            lote_verde_cloro, lote_amarillo_desen,
            lote_rojo_jabon, lote_vencido_cloro, lote_cuarentena
        ])
        db.session.flush()

        print("--> Generando movimientos iniciales en Kardex...")
        # Movimiento 1: Recepción de compra cloro
        k1 = MovimientoKardex(
            fecha=datetime.utcnow() - timedelta(days=20),
            usuario_id=bodeguero.id,
            producto_id=prod_cloro.id,
            presentacion_id=pres_cloro_galon.id,
            lote_id=lote_verde_cloro.id,
            tipo_movimiento='ENTRADA_COMPRA',
            cantidad=Decimal('50.00'),
            stock_anterior=Decimal('0.00'),
            stock_nuevo=Decimal('50.00'),
            motivo_observaciones='Ingreso por compra inicial a fabricante químico',
            documento_soporte='FAC-PROV-8821'
        )

        # Movimiento 2: Despacho aplicando FEFO
        k2 = MovimientoKardex(
            fecha=datetime.utcnow() - timedelta(days=5),
            usuario_id=bodeguero.id,
            producto_id=prod_cloro.id,
            presentacion_id=pres_cloro_galon.id,
            lote_id=lote_verde_cloro.id,
            tipo_movimiento='SALIDA_DESPACHO',
            cantidad=Decimal('-15.00'),
            stock_anterior=Decimal('50.00'),
            stock_nuevo=Decimal('35.00'),
            motivo_observaciones='Despacho a distribuidora regional Centro',
            documento_soporte='REM-2026-0045'
        )

        # Movimiento 3: Merma por rotura de envase
        k3 = MovimientoKardex(
            fecha=datetime.utcnow() - timedelta(days=2),
            usuario_id=bodeguero.id,
            producto_id=prod_desen.id,
            presentacion_id=pres_desen_galon.id,
            lote_id=lote_amarillo_desen.id,
            tipo_movimiento='MERMA_DERRAME',
            cantidad=Decimal('-2.00'),
            stock_anterior=Decimal('32.00'),
            stock_nuevo=Decimal('30.00'),
            motivo_observaciones='MERMA [Rotura de envase en cargue]: Perforación de dos galones por estiba astillada',
            documento_soporte='ACTA-MERMA-2026-01'
        )

        db.session.add_all([k1, k2, k3])
        db.session.commit()

        print("\n========================================================")
        print("  ¡BASE DE DATOS ANDIASEO INICIALIZADA EXITOSAMENTE!   ")
        print("========================================================")
        print("Usuarios disponibles:")
        print("  1. admin / admin123         (Administrador General)")
        print("  2. bodeguero / bodega123    (Operario de Almacén)")
        print("  3. auditor / auditor123     (Control de Calidad)")
        print("========================================================\n")

if __name__ == '__main__':
    seed_database()
