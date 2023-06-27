import threading
from typing import Any, ClassVar, Generic, TypeVar

SinClsType = TypeVar("SinClsType", bound="Singleton")
ThSinClsType = TypeVar("ThSinClsType", bound="PerThreadSingleton")


class PerThreadSingleton(type, Generic[ThSinClsType]):
    """
    This is a multi/single thread safe singleton which should be used as metaclass to modify how a singleton class is
    built.   Consider using this class when making classes which might run with Gunicorn/WSGI with one or more threads
    and you required each thread to see a singleton independent of the other threads.
    For example storing request related data.

    Using this metaclass it is possible to create a class whose __init__ parameters are retained for the life of the
    pod or if __delattr__is called with "this_tread"   eg  delattr(MyClass, "this_tread") then the next time
    MyClass() is called the init will be run again, ideal for just global life of request storage using middleware.
    example:
    MyClass(metaclass=MultiThreadSingleton):
        def __init__(*args,*kwargs):
             only runs once

    x = MyClass(*args,*kwargs)  -   args kwargs are used only once per thread, ignored if given again.
    x.my_var = val  - store a value
    x.my_val        - read a value

    it follows from singleton
    if y = MyClass() then x.my_val == y.my_val   ie singleton

    Note MyClass can be imported and will contain values as previously set
    y = MyClass()
    if y == None:
        # gets here if  MyClass has init values and they were not set.


    This code has been tested for thread safety and correct working with Gunicorn
    """

    _instance: ClassVar[dict[int, Any]] = {}
    _lock = threading.Lock()

    def __call__(cls: ThSinClsType, *args: Any, **kwargs: Any) -> ThSinClsType | None:
        with cls._lock:
            thread_id = threading.get_native_id()
            inst_dict = cls._instance
            if not inst_dict.get(thread_id):
                try:
                    cls._instance[thread_id] = super().__call__(*args, **kwargs)
                except TypeError:
                    return None

            return inst_dict[thread_id]

    def __delattr__(cls, *args: Any, **kwargs: Any) -> None:
        """
        Deleting the fake attribute "this_thread" causes the thread instance and associated data to be destroyed.
        It was done this wat because an override of a method on type was required.
        Basically finds which thread you are in then deletes all record of it making the Singleton appear to be deleted
        in the current thread.  Other threads if present are maintained.  Works if single threaded as well.
        :param args:
        :param kwargs:
        :return:
        """
        with cls._lock:
            thread_id = threading.get_native_id()
            inst_dict = cls._instance
            if inst_dict.get(thread_id):
                if args[0] == "this_tread":
                    del inst_dict[thread_id]
                else:
                    super().__delattr__(*args, **kwargs)


class Singleton(type, Generic[SinClsType]):
    """
    This is a basic singleton metaclass which works as expected if not threaded in Python or by Gunicorn/WSGI
    If used threaded the first thread would set up the instance and other threads would get the same data.
    This would persist across threads and requests.
    NB.  We may need to add a lock for additional safety
    """

    instance: SinClsType | None = None

    def __call__(cls: SinClsType, *args: Any, **kwargs: Any) -> SinClsType:
        if cls.instance is None:
            cls.instance = super().__call__(*args, **kwargs)
        return cls.instance
