import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import LoyaltyPlanJourneyFieldsSerializer
from app.api.validators import loyalty_card_add_schema, validate
from app.handlers.loyalty_plan import LoyaltyPlanHandler
from app.report import ctx, log_request_data

from .base_resource import Base


class LoyaltyPlanJourneyFields(Base):
    @validate(resp_schema=LoyaltyPlanJourneyFieldsSerializer)
    def on_get_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_plan_id: int) -> None:
        user_id = ctx.user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        handler = LoyaltyPlanHandler(user_id=user_id,
                                     channel_id=channel,
                                     db_session=self.session,
                                     loyalty_plan_id=loyalty_plan_id)

        response = handler.get_journey_fields()

        resp.media = response
        resp.status = falcon.HTTP_200