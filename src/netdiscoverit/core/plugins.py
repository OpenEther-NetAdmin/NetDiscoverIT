"""
Plugin management: Load modules dynamically.
Example: Future AI plugin via hookimpl.
"""

from pluggy import PluginManager
import importlib

def load_builtins(pm: PluginManager):
    # Load core modules
    from netdiscoverit.scanner import ScannerPlugin
    from netdiscoverit.identifier import IdentifierPlugin
    # ... add others
    pm.register(ScannerPlugin())
    # pm.hook.add_config("netdiscoverit", pm)  # For hook specs