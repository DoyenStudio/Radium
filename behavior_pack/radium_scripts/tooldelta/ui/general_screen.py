# coding=utf-8
import mod.client.extraClientApi as clientApi

from ..events.event_bus import GetMCClientEventBus
from ..events.service import EventListenerService
from ..internal import GetModName
from .elem_comp import UBaseCtrl
from .utils import Binder, UIPath

if 0>1:
    import typing

    from ._ui_typing import (
        CustomUIScreenProxy as _CustomUIControlProxy,
    )
    from ._ui_typing import ScreenNode as _ScreenNode


ScreenNode = clientApi.GetScreenNodeCls()
ScreenProxy = clientApi.GetUIScreenProxyCls()

SUPPORT_DYNA_BINDING = True


class ToolDeltaScreen(EventListenerService):
    _ATTR_EVENT_LISTENER = "_tdscreen_event_listen"
    _ATTR_EVENT_LISTENER_PRIORITY = "_tdscreen_event_listen_priority"

    _screen_cls = None  # type: type[_ScreenNode] | None
    _screen_proxy_cls = None  # type: type[_CustomUIControlProxy] | None
    _screen_key = ""  # type: str

    def __init__(self, screen_name, screen_instance, params=None):
        # type: (str, _ScreenNode | _CustomUIControlProxy, dict | None) -> None
        EventListenerService.__init__(self, GetMCClientEventBus())
        self._screen_name = screen_name
        self._screen_instance = screen_instance
        self._init_params = params or {}
        self._screen_node = self.base = (
            screen_instance
            if isinstance(screen_instance, ScreenNode)
            else getattr(screen_instance, "screenNode")
        )
        self._activated = False
        self._vars = {}
        self._dyna_bindings = {}

    def AddElement(self, ctrl_def_name, ctrl_name, force_update=True, _parent=None):
        # type: (str, str, bool, UBaseCtrl | None) -> UBaseCtrl
        return UBaseCtrl(
            self,
            self.base.CreateChildControl(
                ctrl_def_name,
                ctrl_name,
                _parent.base if _parent is not None else None,
                force_update,
            ),
        )

    def GetBaseUIControl(
        self,
        path,  # type: str | UIPath
    ):
        return self.base.GetBaseUIControl(str(path))

    def GetElement(self, path):
        # type: (str | UIPath) -> UBaseCtrl
        return UBaseCtrl(self, self.GetBaseUIControl(path))

    @classmethod
    def CreateUI(cls, params={}):
        if cls._screen_cls is None:
            raise Exception("CreateUI failed: screen %s not registered as ScreenNode")
        screen = clientApi.CreateUI(GetModName(), cls._screen_key, params)
        if not isinstance(screen, cls._screen_cls):
            raise Exception("CreateUI failed: return {} is not {}".format(screen, cls))
        self = getattr(screen, "_super_screen_ins")
        if not isinstance(self, cls):
            raise ValueError(
                "CreateUI failed: internal: return {} is not {}".format(self, cls)
            )
        return self

    @classmethod
    def PushUI(cls, params={}):
        if cls._screen_cls is None:
            raise Exception(
                "CreateUI failed: screen %s not registered as ScreenNode" % cls.__name__
            )
        screen = clientApi.PushScreen(GetModName(), cls._screen_key, params)
        if not isinstance(screen, cls._screen_cls):
            raise Exception("CreateUI failed: return {} is not {}".format(screen, cls))
        self = getattr(screen, "_super_screen_ins")
        if not isinstance(self, cls):
            raise ValueError(
                "CreateUI failed: internal: return {} is not {}".format(self, cls)
            )
        return self

    def RemoveUI(self):
        self._do_deactive()
        if self._screen_cls is not None:
            return self.base.SetRemove()
        elif self._screen_proxy_cls is not None:
            if clientApi.GetTopUINode() is self.base:
                return clientApi.PopTopUI()

    @classmethod
    def _register_as_screen(
        cls,
        screen_key,  # type: str
    ):
        cls._screen_key = screen_key

        def __init__(self, namespace, name, param=None):
            ScreenNode.__init__(self, namespace, name, param)  # type: ignore
            self._initial_params = param
            self._super_screen_ins = cls(name, self, param)

        def Create(self):
            self._super_screen_ins._on_create()

        def Destroy(self):
            self._super_screen_ins._on_destroy()

        def Update(self):
            self._super_screen_ins._on_ticking()

        def OnActive(self):
            self._super_screen_ins._on_active()

        def OnDeactive(self):
            self._super_screen_ins._on_deactive()

        attrs = {
            "__init__": __init__,
            "Create": Create,
            "Destroy": Destroy,
            "Update": Update,
            "OnActive": OnActive,
            "OnDeactive": OnDeactive,
        }
        attrs.update(cls._get_tdscreen_bindings())
        t = type(cls.__name__ + "_Base", (ScreenNode,), attrs)
        cls._screen_cls = t
        return t

    @classmethod
    def _register_as_proxy(
        cls,
        screen_name,  # type: str
        screen_key=None,  # type: str | None
    ):
        cls._screen_key = screen_key or screen_name

        def __init__(self, screenName, screenNode):
            ScreenProxy.__init__(self, screenName, screenNode)
            self._initial_params = None
            self.screenNode = screenNode
            self._super_screen_ins = cls(
                screenName,
                self,
            )

        def OnCreate(self):
            self._super_screen_ins._on_create()

        def OnDestroy(self):
            self._super_screen_ins._on_destroy()

        def OnTick(self):
            self._super_screen_ins._on_ticking()

        attrs = {
            "__init__": __init__,
            "OnCreate": OnCreate,
            "OnDestroy": OnDestroy,
            "OnTick": OnTick,
        }
        attrs.update(cls._get_tdscreen_bindings())
        t = type(cls.__name__ + "_Base", (ScreenProxy,), attrs)
        cls._screen_proxy_cls = t
        return t

    @classmethod
    def _get_tdscreen_bindings(cls):
        attrs = {}
        for key in dir(cls):
            attr = getattr(cls, key)
            if not callable(attr) or not hasattr(attr, "binding_flags"):
                continue
            if not hasattr(attr, "binding_name"):
                raise ValueError(
                    "ToolDelta binding %s.%s.%s is missing binding_name"
                    % (cls.__module__, cls.__name__, key)
                )
            if hasattr(attr, "collection_name"):

                def wrap(_func):
                    def _wrapper(self, *args):
                        return _func(self._super_screen_ins, *args)

                    return _wrapper

                custom_binding_collections_func = wrap(attr)
                custom_binding_collections_func.__module__ = attr.__module__
                new_name = custom_binding_collections_func.__name__ = (
                    key + "_bindwrapper"
                )
                attrs[new_name] = Binder.binding_collection(
                    attr.binding_flags, attr.collection_name, attr.binding_name
                )(custom_binding_collections_func)
            elif hasattr(attr, "binding_flags"):

                def wrap(_func):
                    def _wrapper(self, *args):
                        return _func(self._super_screen_ins, *args)

                    return _wrapper

                custom_binding_func = wrap(attr)
                custom_binding_func.__module__ = attr.__module__
                new_name = custom_binding_func.__name__ = key
                attrs[new_name] = Binder.binding(attr.binding_flags, attr.binding_name)(
                    custom_binding_func
                )
        return attrs

    def _do_active(self, from_create=False):
        from .pool import _addActiveToolDeltaScreen

        if self._activated:
            return
        _addActiveToolDeltaScreen(self)
        self._activated = True
        self.enable_listeners()

    def _do_deactive(self, from_destroy=False):
        from .pool import _removeActiveToolDeltaScreen

        if not self._activated:
            return
        _removeActiveToolDeltaScreen(self)
        self._activated = False
        self.disable_listeners()

    def _remove_ctrl(self, ctrl):
        # type: (UBaseCtrl) -> bool
        return self.base.RemoveChildControl(ctrl.base)

    def _on_create(self):
        self._do_active(from_create=True)
        self.OnCreate()

    def _on_destroy(self):
        self._clear_dyna_bindings()
        self._do_deactive(from_destroy=True)
        self.OnDestroy()

    def _on_active(self):
        self._do_active(from_create=False)
        self.OnActive()

    def _on_deactive(self):
        self._do_deactive(from_destroy=False)
        self.OnDeactive()

    def _on_ticking(self):
        self.OnTicking()

    __getitem__ = GetElement

    def OnCreate(self):
        "子类覆写该方法"
        pass

    def OnDestroy(self):
        "子类覆写该方法"
        pass

    def OnActive(self):
        "子类覆写该方法"
        pass

    def OnDeactive(self):
        "子类覆写该方法"
        pass

    def OnTicking(self):
        "子类覆写该方法"
        pass

    if SUPPORT_DYNA_BINDING:

        def DynaBinding(self, bind_flag, binding_name, binding_func):
            # type: (int, str, typing.Callable) -> None
            """
            动态绑定。相当于 ViewBinder.binding, 可以实时注册和反注册。
            """
            key = self._get_dyna_binding_key(bind_flag, binding_name, None)
            self._dyna_unbinding(key)
            raw_func = self._make_dyna_binding_func(binding_func, binding_name)
            Binder.binding(bind_flag, binding_name)(raw_func)
            func = self._bind_dyna_func(raw_func)
            try:
                self._screen_instance._process_default(func, self._get_dyna_screen_name())  # pyright: ignore[reportAttributeAccessIssue]
            except Exception:
                delattr(self._screen_instance, func.__name__)
                raise
            self._dyna_bindings[key] = func

        def DynaUnbinding(self, bind_flag, binding_name):
            # type: (int, str) -> None
            """
            动态反绑定。
            """
            key = self._get_dyna_binding_key(bind_flag, binding_name, None)
            self._dyna_unbinding(key)

        def DynaBindingCollection(
            self, bind_flag, collection_name, binding_name, binding_func
        ):
            # type: (int, str, str, typing.Callable) -> None
            """
            动态绑定集合。相当于 ViewBinder.binding_collection, 可以实时注册和反注册。
            """
            key = self._get_dyna_binding_key(bind_flag, binding_name, collection_name)
            self._dyna_unbinding(key)
            raw_func = self._make_dyna_binding_func(binding_func, binding_name)
            Binder.binding_collection(bind_flag, collection_name, binding_name)(
                raw_func
            )
            func = self._bind_dyna_func(raw_func)
            try:
                self._screen_instance._process_collection(  # pyright: ignore[reportAttributeAccessIssue]
                    func, self._get_dyna_screen_name()
                )
            except Exception:
                delattr(self._screen_instance, func.__name__)
                raise
            self._dyna_bindings[key] = func

        def DynaUnbindingCollection(self, bind_flag, collection_name):
            # type: (int, str) -> None
            """
            动态反绑定集合。
            """
            for key in list(self._dyna_bindings.keys()):
                key_bind_flag, _, key_collection_name = key
                if (
                    key_bind_flag == bind_flag
                    and key_collection_name == collection_name
                ):
                    self._dyna_unbinding(key)

        def _get_dyna_screen_name(self):
            # type: () -> str
            if self._screen_instance is not self._screen_node:
                get_screen_name = getattr(self._screen_instance, "GetScreenName", None)
                if get_screen_name is not None:
                    return get_screen_name()
            return self._screen_node.screen_name or self._screen_node.full_name

        @staticmethod
        def _get_dyna_binding_key(bind_flag, binding_name, collection_name):
            # type: (int, str, str | None) -> tuple[int, str, str | None]
            return (bind_flag, binding_name, collection_name)

        @staticmethod
        def _make_dyna_binding_func(binding_func, binding_name):
            # type: (typing.Callable, str) -> typing.Callable
            def _wrapper(screen_ins, *args):
                return binding_func(*args)

            return _wrapper

        def _bind_dyna_func(self, func):
            # type: (typing.Callable) -> typing.Callable
            # gui passes func.__name__ to native code, which resolves it on the
            # registered instance. Keep each wrapper discoverable and separate
            # from static methods and other bindings of the same callback.
            sequence = getattr(self, "_dyna_binding_sequence", 0) + 1
            name = "_td_dyna_binding_%s" % sequence
            while hasattr(self._screen_instance, name):
                sequence += 1
                name = "_td_dyna_binding_%s" % sequence
            self._dyna_binding_sequence = sequence
            func.__name__ = name
            bound = func.__get__(self._screen_instance, self._screen_instance.__class__)
            setattr(self._screen_instance, name, bound)
            return bound

        def _dyna_unbinding(self, key):
            # type: (tuple[int, str, str | None]) -> None
            func = self._dyna_bindings.get(key)
            if func is None:
                return
            if key[2] is None:
                self._screen_instance._process_default_unregister(  # pyright: ignore[reportAttributeAccessIssue]
                    func, self._get_dyna_screen_name()
                )
            else:
                self._screen_instance._process_collection_unregister(  # pyright: ignore[reportAttributeAccessIssue]
                    func, self._get_dyna_screen_name()
                )
            del self._dyna_bindings[key]
            delattr(self._screen_instance, func.__name__)

        def _clear_dyna_bindings(self):
            # type: () -> None
            for key in list(self._dyna_bindings.keys()):
                self._dyna_unbinding(key)
