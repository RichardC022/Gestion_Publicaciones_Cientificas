"""Standard pagination for API list endpoints.

Query parameters (implementation plan, section 2.1):

* ``page``: 1-based page number. Malformed values return ``400``;
  out-of-range pages keep DRF's ``404`` semantics.
* ``page_size``: items per page. Malformed values or values above 100
  return ``400``. The server default is 20 and never exceeds 100.
"""

from __future__ import annotations

from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class StandardPagination(PageNumberPagination):
    """Page-based pagination with strict parameter validation."""

    page_size = DEFAULT_PAGE_SIZE
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE
    invalid_page_message = "La página solicitada no existe."

    def get_page_size(self, request) -> int:
        """Return the requested page size or raise a ``400`` error."""
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
        """Return a validated page number or raise a ``400`` error."""
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
