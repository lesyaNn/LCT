from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


def paginate(query, page: int = 1, size: int = 20) -> tuple[list, int]:
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    return items, total
