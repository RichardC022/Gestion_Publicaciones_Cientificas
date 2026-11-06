// Visor del diagrama BPMN. Sin código en línea: se carga como archivo del mismo origen.
(function () {
  'use strict';

  var viewer = new BpmnJS({ container: '#canvas' });
  var canvas = function () {
    return viewer.get('canvas');
  };

  function showError(message) {
    var box = document.getElementById('error');
    box.textContent = message;
    box.hidden = false;
  }

  fetch('proceso-editorial.bpmn')
    .then(function (response) {
      if (!response.ok) {
        throw new Error('No se pudo cargar el diagrama (HTTP ' + response.status + ').');
      }
      return response.text();
    })
    .then(function (xml) {
      return viewer.importXML(xml);
    })
    .then(function () {
      canvas().zoom('fit-viewport', 'auto');
    })
    .catch(function (error) {
      showError(error && error.message ? error.message : String(error));
    });

  document.getElementById('zoom-in').addEventListener('click', function () {
    canvas().zoom(canvas().zoom() * 1.2);
  });
  document.getElementById('zoom-out').addEventListener('click', function () {
    canvas().zoom(canvas().zoom() / 1.2);
  });
  document.getElementById('zoom-fit').addEventListener('click', function () {
    canvas().zoom('fit-viewport', 'auto');
  });
  window.addEventListener('resize', function () {
    canvas().zoom('fit-viewport', 'auto');
  });
})();
