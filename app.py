import os
from app import create_app, db

# Instancia de la aplicación Flask
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    port = int(os.environ.get('PORT', 5000))
    print("\n========================================================")
    print("      SISTEMA ANDIASEO - CONTROL DE INVENTARIO          ")
    print(f"  Servidor iniciado en: http://127.0.0.1:{port}")
    print("========================================================")
    print("Usuarios de prueba:")
    print("  - Admin:      admin / admin123")
    print("  - Bodeguero:  bodeguero / bodega123")
    print("  - Auditor:    auditor / auditor123")
    print("========================================================\n")
    app.run(host='127.0.0.1', port=port, debug=True)
