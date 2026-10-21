# Clarificaciones de la Especificación 001 — Flujo Editorial

**Feature**: `001-editorial-workflow`
**Fecha**: 2026-10-20
**Rol**: Analista QA Senior
**Spec fuente**: `specs/001-editorial-workflow/spec.md`
**Herramienta**: `/speckit.clarify`

Este documento registra las decisiones tomadas para resolver ambigüedades y casos límite
detectados en la especificación antes de pasar al diseño técnico. Las respuestas también se
integraron directamente en `spec.md` (sección `## Clarifications` y secciones afectadas).

## Resumen de decisiones

| # | Pregunta | Respuesta adoptada | Impacto |
|---|----------|--------------------|---------|
| 1 | ¿Qué es una "publicación"? | Sinónimo del mismo manuscrito en estado Publicado; no hay entidad aparte | Terminología + modelo de datos + catálogo |
| 2 | Manejo de múltiples autores | Un Autor principal gestiona; coautores sin permisos de gestión | Control de acceso + entidad Autoría |
| 3 | Visualización de versiones anteriores | Todas se conservan; Revisor ve solo la vigente; Autor/Editor/Administrador ven el historial | Doble ciego + versionado |
| 4 | Edición concurrente | Bloqueo optimista (rechaza copia desactualizada) | Integridad + UX de error |
| 5 | Metadatos obligatorios vs. futuros | Todos obligatorios desde el inicio (incluye DOI, ISSN, ORCID, financiamiento); ninguno diferido | Alcance + validaciones |

## Casos límite y escenarios de error identificados

1. **Concurrencia (Q4)**: dos gestores guardan el mismo manuscrito a la vez → solo el primer
   guardado válido persiste; el desactualizado se rechaza pidiendo recargar.
2. **Coautor sin permisos (Q2)**: un coautor intenta editar/entregar/dar de baja → denegado;
   solo el Autor principal gestiona.
3. **Acceso indebido a versiones (Q3)**: un Revisor intenta abrir una versión anterior →
   denegado; solo ve la versión vigente asignada (protege el doble ciego).
4. **Metadatos incompletos (Q5)**: registro sin DOI/ISSN/ORCID/financiamiento u otro campo
   obligatorio → rechazado indicando el campo faltante.
5. **Transiciones inválidas** (ya cubiertas): nueva versión fuera de "Requiere Correcciones" y
   veredicto sin evaluaciones → bloqueados.
6. **Búsqueda sin resultados / manuscrito dado de baja**: mensajes claros y bloqueo de nuevas
   transiciones sobre el manuscrito inactivo.

## Ambigüedades diferidas (no bloqueantes)

- **Tamaño máximo del PDF**: se fijará en una iteración posterior; no altera el alcance
  funcional (FR-006 ya exige rechazar archivos que excedan el límite permitido).
- **Anonimización del contenido/metadatos del PDF para doble ciego**: el detalle técnico se
  especifica aparte; aquí solo se exige que el Revisor nunca acceda a la identidad del Autor.

## Requisitos y criterios añadidos a la spec

- FR-004a (bloqueo optimista), FR-005 (metadatos obligatorios), FR-010a (historial de versiones
  por rol), FR-011 y FR-024 (terminología y gestión del Autor principal).
- SC-009 a SC-012 (denegación a coautores, acceso a versiones, concurrencia, metadatos).
