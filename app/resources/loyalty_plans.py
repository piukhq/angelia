import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import LoyaltyPlanJourneyFieldsSerializer, LoyaltyPlanOverviewSerializer, LoyaltyPlanSerializer
from app.api.validators import empty_schema, validate
from app.handlers.loyalty_plan import LoyaltyPlanHandler, LoyaltyPlansHandler
from app.resources.metrics import loyalty_plan_get_counter

from .base_resource import Base


class LoyaltyPlans(Base):
    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanSerializer)
    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        handler = LoyaltyPlansHandler(user_id=user_id, channel_id=channel, db_session=self.session)
        response = handler.get_all_plans()

        resp.media = response
        resp.status = falcon.HTTP_200

        loyalty_plan_get_counter.labels(
            endpoint="/loyalty_plans", channel=channel, response_status=falcon.HTTP_200
        ).inc()

    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanSerializer)
    def on_get_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_plan_id: int) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        handler = LoyaltyPlanHandler(
            user_id=user_id, channel_id=channel, db_session=self.session, loyalty_plan_id=loyalty_plan_id
        )
        response = handler.get_plan()

        resp.media = response
        resp.status = falcon.HTTP_200

        loyalty_plan_get_counter.labels(
            endpoint="/loyalty_plans/{loyalty_plan_id}", channel=channel, response_status=falcon.HTTP_200
        ).inc()

    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanOverviewSerializer)
    def on_get_overview(self, req: falcon.Request, resp: falcon.Response, **kwargs) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        handler = LoyaltyPlansHandler(user_id=user_id, channel_id=channel, db_session=self.session)
        response = handler.get_all_plans_overview()

        resp.media = response
        resp.status = falcon.HTTP_200

        loyalty_plan_get_counter.labels(
            endpoint="/loyalty_plans_overview", channel=channel, response_status=falcon.HTTP_200
        ).inc()


class LoyaltyPlanJourneyFields(Base):
    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanJourneyFieldsSerializer)
    def on_get_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_plan_id: int) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        handler = LoyaltyPlanHandler(
            user_id=user_id, channel_id=channel, db_session=self.session, loyalty_plan_id=loyalty_plan_id
        )

        response = handler.get_journey_fields()
        response.update(loyalty_plan_id=loyalty_plan_id)

        resp.media = response
        resp.status = falcon.HTTP_200

        loyalty_plan_get_counter.labels(
            endpoint=" /loyalty_plans/{loyalty_plan_id}/journey_fields",
            channel=channel,
            response_status=falcon.HTTP_200,
        ).inc()
