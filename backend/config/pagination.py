"""Paginación estándar de los endpoints de lista de la API.

Parámetros de consulta (plan de implementación, sección 2.1):

* ``page``: número de página, desde 1. Un valor mal formado responde ``400``; una página
  fuera de rango conserva la semántica ``404`` de DRF.
* ``page_size``: elementos por página. Un valor mal formado o mayor que 100 responde
  ``400``. Por defecto son 20 y nunca pasan de 100.

La respuesta no usa el formato de DRF: el renderer mueve ``count``, ``next`` y ``previous``
a ``meta.pagination`` (ver ``config.renderers``).
"""

from __future__ import annotations

from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from config.openapi import PAGINATED
from config.renderers import PaginatedPayload

# Elementos por página cuando el cliente no pide un tamaño, y tope que nadie puede superar.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class StandardPagination(PageNumberPagination):
    """Paginación por páginas con validación estricta de los parámetros.

    A diferencia de DRF, que ignora en silencio un ``page_size`` inválido, aquí cualquier
    valor mal formado es un error ``400`` con el detalle del parámetro.
    """

    page_size = DEFAULT_PAGE_SIZE
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE
    invalid_page_message = "La página solicitada no existe."

    def get_paginated_response_schema(self, schema):
        """Schema de una página: la lista de elementos, marcada para el hook OpenAPI."""
        return {"type": "array", "items": schema, PAGINATED: True}

    def get_paginated_response(self, data):
        """Devuelve la página marcada (``PaginatedPayload``) para que el renderer mueva los contadores a ``meta``.

        Dentro del proceso, ``response.data`` conserva ``count``, ``next``, ``previous`` y
        ``results``; el cambio de forma ocurre solo al serializar la respuesta.
        """
        return Response(
            PaginatedPayload(
                count=self.page.paginator.count,
                next=self.get_next_link(),
                previous=self.get_previous_link(),
                results=data,
            )
        )

    def get_page_size(self, request) -> int:
        """Devuelve el tamaño de página pedido o lanza un error ``400`` si no es un entero de 1 a 100."""
        raw = request.query_params.get(self.page_size_query_param)
        if raw is None:
            return self.page_size
        try:
            size = int(str(raw).strip())
        except (TypeError, ValueError):
            raise self._param_error(
                self.page_size_query_param,
                "El parámetro page_size debe ser un entero entre 1 y 100.",
            ) from None
        if not 1 <= size <= self.max_page_size:
            raise self._param_error(
                self.page_size_query_param,
                "El parámetro page_size debe ser un entero entre 1 y 100.",
            )
        return size

    def get_page_number(self, request, paginator) -> int:
        """Devuelve un número de página válido o lanza un error ``400``.

        Acepta ``last`` como alias de la última página.
        """
        raw = request.query_params.get(self.page_query_param) or 1
        if raw in self.last_page_strings:
            return paginator.num_pages
        try:
            number = int(str(raw).strip())
        except (TypeError, ValueError):
            raise self._param_error(
                self.page_query_param,
                "El parámetro page debe ser un entero mayor o igual que 1.",
            ) from None
        if number < 1:
            raise self._param_error(
                self.page_query_param,
                "El parámetro page debe ser un entero mayor o igual que 1.",
            )
        return number

    @staticmethod
    def _param_error(param: str, message: str) -> exceptions.ValidationError:
        return exceptions.ValidationError({param: [message]})
