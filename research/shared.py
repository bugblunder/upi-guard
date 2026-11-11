"""Load the app's pure feature/monitoring code without initializing its Flask package.

The application __init__ imports web/database dependencies. These two leaf modules
are loaded under a private namespace so offline experiments need only scientific
Python. No application code is copied, patched or bypassed during feature creation.
"""
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
namespace = '_upi_research_shared'
if namespace not in sys.modules:
    pkg = types.ModuleType(namespace)
    pkg.__path__ = [str(ROOT / 'upi_guard')]
    sys.modules[namespace] = pkg


def load(name):
    key = f'{namespace}.{name}'
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, ROOT / 'upi_guard' / f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


features = load('features')
monitoring = load('monitoring')
