// =====================================================
// =================== INICIALIZACIÓN ==================
// =====================================================

// Verificación básica para confirmar que el archivo JS
// se cargó correctamente en el navegador
console.log("✅ Script cargado correctamente");


// =====================================================
// =================== RELOJ UTC =======================
// =====================================================

/**
 * Función que actualiza la hora UTC en pantalla
 * Busca un elemento con id="relojUTC"
 * y escribe la hora actual en formato UTC
 */
function actualizarHoraUTC() {

    // Fecha actual del sistema
    const now = new Date();

    // Convertir la hora local a UTC (formato estándar)
    const utc = now.toUTCString();

    // Buscar el elemento donde se mostrará el reloj
    const reloj = document.getElementById("relojUTC");

    // Verificar que el elemento exista antes de escribir
    if (reloj) {
        reloj.innerText = utc;
    }
}

// Ejecuta la función cada 1000 ms (1 segundo)
setInterval(actualizarHoraUTC, 1000);

// Ejecuta una vez inmediatamente al cargar la página
actualizarHoraUTC();


// =====================================================
// ============ DESCARGAR INFORME COMO IMAGEN ===========
// =====================================================

/**
 * Captura el informe completo en pantalla y lo descarga
 * como imagen PNG usando html2canvas
 */
function descargarInforme() {

    // Elemento a capturar:
    // Puedes cambiar document.body por un div específico
    // ejemplo: document.getElementById("informe")
    const elemento = document.body;

    // Captura del HTML a canvas
    html2canvas(elemento, {
        scale: 2,            // Mejora la resolución de la imagen
        useCORS: true        // Permite imágenes externas (NOAA / NASA)
    }).then(canvas => {

        // Crear enlace de descarga
        const link = document.createElement("a");

        // Nombre del archivo
        link.download = "informe_clima_espacial.png";

        // Convertir canvas a imagen PNG
        link.href = canvas.toDataURL("image/png");

        // Simular clic para descargar
        link.click();
    }).catch(error => {

        // Manejo básico de errores
        console.error("❌ Error al generar la imagen:", error);
    });
}
