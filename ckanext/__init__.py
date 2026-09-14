# this is a namespace package
import importlib

try:
    pkg_resources = importlib.import_module("pkg_resources")
    pkg_resources.declare_namespace(__name__)
except ImportError:
    import pkgutil

    __path__ = pkgutil.extend_path(__path__, __name__)
