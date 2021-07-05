import falcon

from app.hermes.models import Organisation, Channel

from .base_resource import Base


class Example(Base):
    def on_get(self, req: falcon.Request, resp: falcon.Response, id1=None, id2=None) -> None:
        print(f"id1 = {id1} and id2 = {id2}")
        resp.media = self.list_by_channel()

    def list_by_channel(self) -> list:
        result = []
        for channel in self.session.query(Channel):
            scheme_association = []
            for assoc in channel.scheme_associations:
                scheme_association.append([assoc.id, assoc.status, assoc.scheme.name, assoc.scheme.slug])
            result.append(
                [
                    channel.id,
                    channel.bundle_id,
                    channel.client_id,
                    channel.external_name,
                    {"schemes": scheme_association},
                ]
            )
        return result

    def list_by_org(self) -> list:
        result = []
        for org in self.session.query(Organisation):
            applications = []
            for apps in org.client_applications:
                channels = []
                for channel in apps.channels:
                    channels.append((channel.id, channel.bundle_id, channel.external_name))
                applications.append(
                    (
                        apps.client_id,
                        apps.name,
                        apps.organisation_id,
                        apps.secret,
                        {"channels": channels},
                    )
                )
            result.append(
                (
                    org.id,
                    org.name,
                    org.terms_and_conditions,
                    {"client_applications": applications},
                )
            )
        return result
