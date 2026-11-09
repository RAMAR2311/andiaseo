/**
 * Scripts principales de Andiaseo - Control de Inventario Químico
 */

document.addEventListener('DOMContentLoaded', function () {
    // Toggle de sidebar en dispositivos móviles
    const toggleBtn = document.getElementById('sidebarToggle');
    const sidebar = document.querySelector('.app-sidebar');
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', function () {
            sidebar.classList.toggle('show');
        });
    }

    // Inicialización de DataTables con traducción al español
    if (typeof $.fn.DataTable !== 'undefined') {
        // Desactivar alertas modales invasivas (alert) de DataTables y registrar en consola
        $.fn.dataTable.ext.errMode = function (settings, helpPage, message) {
            console.warn('DataTables warning:', message);
        };

        $('.datatable-custom').each(function () {
            const table = $(this);
            // Si la tabla solo contiene la fila de "No se encontraron registros" o está vacía, no inicializar DataTables
            const hasDataRows = table.find('tbody tr').length > 0 && !table.find('tbody tr td[colspan]').length;
            if (hasDataRows) {
                // Verificar que el conteo de th coincida con el primer tr de tbody
                const thCount = table.find('thead tr:first th').length;
                const tdCount = table.find('tbody tr:first td').length;
                if (thCount === tdCount) {
                    table.DataTable({
                        language: {
                            url: 'https://cdn.datatables.net/plug-ins/1.13.6/i18n/es-ES.json'
                        },
                        responsive: true,
                        pageLength: 25,
                        order: []
                    });
                } else {
                    console.warn(`DataTables omitido en tabla porque el número de columnas de cabecera (${thCount}) no coincide con el cuerpo (${tdCount}).`);
                }
            }
        });
    }

    // Inicializar tooltips de Bootstrap
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Helper de confirmación con SweetAlert2 para acciones de bodega
function confirmarAccion(event, titulo, texto, botonConfirmar = 'Sí, continuar') {
    event.preventDefault();
    const form = event.target.closest('form');

    Swal.fire({
        title: titulo || '¿Estás seguro?',
        text: texto || 'Esta acción afectará los registros de inventario.',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#0f766e',
        cancelButtonColor: '#64748b',
        confirmButtonText: botonConfirmar,
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed) {
            form.submit();
        }
    });
}
