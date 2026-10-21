## SPEC-001: Autenticación con credenciales institucionales válidas

- **ID:** SPEC-001
- **Tipo:** Regla obligatoria
- **Objeto:** `dossier/dossier_requisitos.md` / Proceso de autenticación
- **Descripción:** Basado en RF-01, el sistema debe autenticar únicamente con credenciales institucionales válidas y cuentas activas.

### Criterios de Validación
- **AUTH-03.1:** Debe validar las credenciales institucionales contra el repositorio de usuarios.
- **AUTH-03.2:** Debe verificar que la cuenta del usuario se encuentre activa.
- **AUTH-03.3:** El acceso solo debe concederse si ambas condiciones (credenciales válidas y cuenta activa) se cumplen.
- **AUTH-03.4:** En caso de credenciales inválidas o cuenta inactiva, el sistema debe rechazar el acceso con el código HTTP apropiado.

**Severidad:** Crítica  
**Resultado esperado:** Solo usuarios con credenciales institucionales válidas y cuentas activas pueden autenticarse.


## SPEC-002: Registro de manuscrito con metadatos obligatorios y PDF válido

- **ID:** SPEC-002
- **Tipo:** Regla obligatoria
- **Objeto:** `dossier/dossier_requisitos.md` / Registro de manuscritos
- **Descripción:** Basado en RF-02, el registro de manuscritos debe exigir metadatos obligatorios y un archivo PDF válido.

### Criterios de Validación
- **REG-04.1:** Deben estar presentes todos los metadatos obligatorios definidos por el proyecto antes de permitir el envío.
- **REG-04.2:** Debe exigirse obligatoriamente la adjunción de un documento en formato PDF.
- **REG-04.3:** El sistema debe validar que el archivo sea efectivamente PDF y cumpla con las restricciones técnicas aplicables.
- **REG-04.4:** El proceso editorial solo debe iniciarse cuando se cumplen tanto los metadatos obligatorios como la validación del PDF.

**Severidad:** Crítica  
**Resultado esperado:** Los manuscritos se registran únicamente con metadatos completos y archivos PDF válidos.
