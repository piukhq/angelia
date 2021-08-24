from dataclasses import dataclass
from app.handlers.base import BaseHandler
from app.hermes.models import Scheme, SchemeCredentialQuestion, SchemeChannelAssociation, Channel
from app.report import api_logger


@dataclass
class LoyaltyPlanHandler(BaseHandler):

    loyalty_plan_id: int

    def get_journey_fields(self):
        self.check_and_fetch_loyalty_plan()

    def check_and_fetch_loyalty_plan(self):

        plan_information = self.db_session.query(Scheme, SchemeCredentialQuestion)\
                                .join(SchemeCredentialQuestion, SchemeChannelAssociation, Channel)\
                                .filter(Scheme.id == self.loyalty_plan_id,
                                        Channel.bundle_id == self.channel_id)\
                                .all()

        api_logger.info(plan_information)

        pass
