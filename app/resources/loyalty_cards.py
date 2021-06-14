import falcon
from .base_resource import Base
from app.hermes.models import SchemeAccountUserAssociation, SchemeAccount
from sqlalchemy import select
from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.messaging.sender import send_message_to_hermes


class LoyaltyAdds(Base):

    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        post_data = req.media
        try:
            plan = post_data['loyalty_plan']
            adds = post_data['account'].get('add_fields', [])
            auths = post_data['account'].get('authorise_fields', [])
        except(KeyError, AttributeError):
            raise falcon.HTTPBadRequest("missing parameters")

        print(plan, adds, auths)

        send_message_to_hermes("add_card", {"plan": plan})
        loyalty_cards = []
        adds = []

        reply = [
            {"adds": adds},
            {"loyalty_cards": loyalty_cards},

        ]

        resp.media = reply
