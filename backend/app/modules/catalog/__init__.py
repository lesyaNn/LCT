"""P1-03: catalog HTTP CRUD (universities, directions, programs, products,
vendors, responsibles).

Layering: router -> service -> repository -> SQLAlchemy model (``app.models``).
DTOs reuse ``app.schemas`` Create/Update contracts; Read/Detail DTOs are
defined in ``app.modules.catalog.schemas``.
"""
