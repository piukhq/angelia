import falcon


class HealthZ:
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"ok": True}


def health_urls(app, prefix):
    app.add_route(f"{prefix}/healthz", HealthZ())
