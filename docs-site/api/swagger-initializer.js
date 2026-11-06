// Inicializa Swagger UI sobre openapi.yaml (misma carpeta, ruta relativa: funciona bajo
// cualquier URL base de GitHub Pages). Sin código en línea en la página.
window.onload = function () {
  window.ui = SwaggerUIBundle({
    url: 'openapi.yaml',
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [SwaggerUIBundle.presets.apis],
    layout: 'BaseLayout',
    // Copia estática: no hay API a la que llamar, así que se desactiva «Try it out».
    supportedSubmitMethods: [],
    tagsSorter: 'alpha',
    docExpansion: 'list',
  });
};
