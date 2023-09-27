from typing import Any, cast

import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_tester_status, get_authenticated_user
from app.api.metrics import Metric
from app.api.serializers import (
    LoyaltyPlanDetailSerializer,
    LoyaltyPlanJourneyFieldsSerializer,
    LoyaltyPlanOverviewSerializer,
    LoyaltyPlanSerializer,
)
from app.api.validators import empty_schema, validate
from app.handlers.loyalty_plan import LoyaltyPlanHandler, LoyaltyPlansHandler
from app.resources.base_resource import Base


class LoyaltyPlans(Base):
    def get_handler(
        self, req: falcon.Request, loyalty_plan_id: int | None = None
    ) -> LoyaltyPlanHandler | LoyaltyPlansHandler:
        user_id = get_authenticated_user(req)
        is_tester = get_authenticated_tester_status(req)
        channel = get_authenticated_channel(req)
        handler: LoyaltyPlanHandler | LoyaltyPlansHandler

        if loyalty_plan_id:
            handler = LoyaltyPlanHandler(
                user_id=user_id,
                channel_id=channel,
                db_session=self.session,
                loyalty_plan_id=loyalty_plan_id,
                is_tester=is_tester,
            )
        else:
            handler = LoyaltyPlansHandler(
                user_id=user_id, channel_id=channel, db_session=self.session, is_tester=is_tester
            )

        return handler

    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanSerializer)
    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        handler = cast(LoyaltyPlansHandler, self.get_handler(req))
        response = handler.get_all_plans(order_by_popularity=True)

        resp.media = response
        resp.status = falcon.HTTP_200

        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanSerializer)
    def on_get_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_plan_id: int) -> None:
        handler = cast(LoyaltyPlanHandler, self.get_handler(req, loyalty_plan_id=loyalty_plan_id))
        response = handler.get_plan()

        resp.media = response
        resp.status = falcon.HTTP_200

        metric = Metric(request=req, status=resp.status, resource_id=loyalty_plan_id, resource="loyalty_plan_id")
        metric.route_metric()

    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanOverviewSerializer)
    def on_get_overview(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        handler = cast(LoyaltyPlansHandler, self.get_handler(req))
        response = handler.get_all_plans_overview()

        resp.media = response
        resp.status = falcon.HTTP_200

        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanDetailSerializer)
    def on_get_plan_details(self, req: falcon.Request, resp: falcon.Response, loyalty_plan_id: int) -> None:
        handler = cast(LoyaltyPlanHandler, self.get_handler(req, loyalty_plan_id=loyalty_plan_id))
        response = handler.get_plan_details()

        resp.media = response
        resp.status = falcon.HTTP_200

        metric = Metric(request=req, status=resp.status, resource_id=loyalty_plan_id, resource="loyalty_plan_id")
        metric.route_metric()


class LoyaltyPlanJourneyFields(Base):
    @validate(req_schema=empty_schema, resp_schema=LoyaltyPlanJourneyFieldsSerializer)
    def on_get_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_plan_id: int) -> None:
        user_id = get_authenticated_user(req)
        is_tester = get_authenticated_tester_status(req)
        channel = get_authenticated_channel(req)

        handler = LoyaltyPlanHandler(
            user_id=user_id,
            channel_id=channel,
            db_session=self.session,
            loyalty_plan_id=loyalty_plan_id,
            is_tester=is_tester,
        )

        response = handler.get_journey_fields()
        response.update(loyalty_plan_id=loyalty_plan_id)

        resp.media = response
        resp.status = falcon.HTTP_200

        metric = Metric(request=req, status=resp.status, resource_id=loyalty_plan_id, resource="loyalty_plan_id")
        metric.route_metric()
