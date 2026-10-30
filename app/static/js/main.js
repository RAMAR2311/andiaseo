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
        $('.datatable-custom').DataTable({
            language: {
                url: 'https://cdn.datatables.net/plug-ins/1.13.6/i18n/es-ES.json'
            },
            responsive: true,
            pageLength: 25,
            order: []
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
