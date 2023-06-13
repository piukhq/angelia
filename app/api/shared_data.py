import falcon

from app.lib.singletons import PerThreadSingleton


class SharedData(metaclass=PerThreadSingleton):
    """This is a singleton class to shared data in a single or multi-thread context.
    Note it uses MultiThreadSingleton as a metaclass ie this class does not inherit from it
    This metaclass changes the behaviour of a class (Django Models are an example) so the following
    use must be adhered to:

    On first use in a request ie in middleware:
            sd = SharedData(req, resp, resource, params)   # this only works as expected
                                                           # because we delete at end of request

            then in rest of code:

             sd = SharedData()    can be used to access variables such as
             sd.request

    To avoid leaking between requests in middle ware and to allow init to work on next request:
            SharedData().delete_thread_vars()

    if we did not delete at end of request then the init method would never run again.
    By removing the thread instance we ensure that threads can never build up if the webserver decides to create
    new threads. However, Gunicorn tends to re-use the same thread.

    It is possible to add data by setting self.new_data_item to none in the __init__  and then  setting the value
    later using  SharedData().new_data_item = my_value

    """

    def __init__(self, req: falcon.Request, resp: falcon.Response, resource: object, params: dict) -> None:
        self.request = req
        self.params = params
        self.resource = resource
        self.response = resp

    @staticmethod
    def delete_thread_vars() -> None:
        delattr(SharedData, "this_tread")
