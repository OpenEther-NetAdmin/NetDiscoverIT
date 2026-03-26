"""
API routes package.

During migration, _legacy.py holds all routes not yet split into their own module.
__init__.py re-exports `router` so main.py needs no changes.
`from ._legacy import *` keeps test_device_audit.py working until devices.py is created in Task 4.
"""
from ._legacy import router       # main.py: `from app.api import routes; routes.router` still works
from ._legacy import *            # exposes list_devices, dependencies, etc. for existing tests