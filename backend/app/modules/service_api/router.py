from fastapi import APIRouter, Depends, Request, Response

from app.core.permissions import require_role
from app.core.security import CurrentUser
from app.modules.service_api.schemas import ServiceApiCatalog
from app.modules.service_api.service import catalog

router = APIRouter(tags=["Service API"])
READER = require_role("user", "manager", "admin")


@router.get(
    "/service-api",
    response_model=ServiceApiCatalog,
    summary="Каталог API сервиса",
    description="Методы подключённого API, проверка доступа по роли, ограничения и коды ошибок. Доступ к конкретному объекту проверяется при вызове метода.",
)
def service_api(
    request: Request, response: Response, user: CurrentUser = Depends(READER)
) -> ServiceApiCatalog:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return catalog(request.app, user)


@router.get(
    "/openapi.json",
    response_model=dict,
    summary="Схема API в формате OpenAPI",
    description="Полная схема подключённых методов с параметрами, телами запросов, ответами и правами. Подходит для импорта в Postman и генерации клиентов.",
)
def service_openapi(
    request: Request, response: Response, _user: CurrentUser = Depends(READER)
) -> dict:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return request.app.openapi()
