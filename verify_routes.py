from app import create_app

def test_routes():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    print("--> Probando pantalla de Login...")
    res = client.get('/auth/login')
    assert res.status_code == 200, f"Error en login: {res.status_code}"
    assert b'ANDIASEO' in res.data
    print("    [OK] Login responde correctamente.")

    print("--> Probando autenticación de 'admin'...")
    res_login = client.post('/auth/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res_login.status_code == 200
    assert b'Control de Inventario y Bodega' in res_login.data
    print("    [OK] Login exitoso y redirección a Dashboard.")

    rutas = [
        ('/', 'Dashboard Principal'),
        ('/inventario/', 'Catálogo de Químicos'),
        ('/inventario/nuevo', 'Nuevo Producto'),
        ('/inventario/categorias', 'Gestión de Categorías'),
        ('/inventario/entrada', 'Entrada de Mercancía'),
        ('/inventario/despacho', 'Salida por Despacho'),
        ('/lotes/', 'Monitor FEFO de Lotes'),
        ('/lotes/nuevo', 'Nuevo Lote'),
        ('/terceros/', 'Gestión de Terceros'),
        ('/facturacion/', 'Módulo de Compras y Ventas'),
        ('/produccion/mermas', 'Bajas y Averías de Bodega'),
        ('/reportes/kardex', 'Kardex Histórico'),
        ('/reportes/valorizado', 'Inventario Valorizado'),
        ('/auth/usuarios', 'Gestión de Usuarios')
    ]

    for ruta, nombre in rutas:
        print(f"--> Verificando {nombre} ({ruta})...")
        r = client.get(ruta)
        assert r.status_code == 200, f"Error al cargar {ruta}: status {r.status_code}"
        print(f"    [OK] {nombre} respondió HTTP 200.")

    print("--> Probando exportación Excel de Kardex...")
    r_kardex_xl = client.get('/reportes/kardex/exportar')
    assert r_kardex_xl.status_code == 200
    assert 'spreadsheetml' in r_kardex_xl.content_type
    print("    [OK] Kardex XLSX exportado correctamente.")

    print("--> Probando exportación Excel de Inventario Valorizado...")
    r_val_xl = client.get('/reportes/valorizado/exportar')
    assert r_val_xl.status_code == 200
    assert 'spreadsheetml' in r_val_xl.content_type
    print("    [OK] Inventario Valorizado XLSX exportado correctamente.")

    print("\nTODAS LAS RUTAS Y PLANTILLAS FUNCIONAN DE MANERA IMPECABLE.")

if __name__ == '__main__':
    test_routes()
