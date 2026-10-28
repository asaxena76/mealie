from functools import cached_property

from fastapi import APIRouter, HTTPException

from mealie.routes._base import controller
from mealie.routes._base.base_controllers import BaseUserController
from mealie.schema.carrie.chat import CarrieAccepted, CarrieContext, CarrieHistory, CarrieSend, CarrieStatus
from mealie.services.household_services.carrie_service import CarrieConflict, CarrieService, CarrieUnavailable

router = APIRouter(prefix="/households/carrie", tags=["Households: Carrie"])


@controller(router)
class CarrieController(BaseUserController):
    @cached_property
    def service(self) -> CarrieService:
        return CarrieService(self.household_id)

    @router.get("/status", response_model=CarrieStatus)
    def status(self) -> CarrieStatus:
        settings = self.service.settings
        stock_enabled = bool(
            settings.CARRIE_STOCK_GATEWAY_URL and settings.CARRIE_HOUSEHOLD_ID == str(self.household_id)
        )
        return CarrieStatus(
            enabled=self.service.enabled,
            stock_path="/carrie" if stock_enabled else None,
            stock_agent_id=settings.CARRIE_AGENT_ID if stock_enabled else None,
        )

    @router.post("/history", response_model=CarrieHistory)
    async def history(self, context: CarrieContext) -> CarrieHistory:
        try:
            return await self.service.history(context)
        except CarrieUnavailable:
            raise HTTPException(503, "Carrie is unavailable. Try again shortly.") from None

    @router.post("/messages", response_model=CarrieAccepted, status_code=202)
    async def send(self, data: CarrieSend) -> CarrieAccepted:
        for diner_id in data.diner_ids:
            if not self.repos.household_diners.get_one(diner_id):
                raise HTTPException(422, "Diner does not belong to this household")
        try:
            return await self.service.send(data)
        except CarrieConflict:
            raise HTTPException(
                409, "Conversation changed or Carrie is still working. Refresh before sending."
            ) from None
        except ValueError:
            raise HTTPException(422, "Message cannot be blank") from None
        except CarrieUnavailable:
            raise HTTPException(
                503, "Message delivery could not be confirmed. Refresh the conversation before retrying."
            ) from None

    @router.post("/stop", status_code=204)
    async def stop(self, context: CarrieContext) -> None:
        try:
            await self.service.stop(context)
        except CarrieUnavailable:
            raise HTTPException(503, "Could not stop Carrie. Refresh to check progress.") from None
