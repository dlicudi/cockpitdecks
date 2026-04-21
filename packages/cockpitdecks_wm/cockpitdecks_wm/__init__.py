#
# COCKPITDECKS EXTENSIONS
#
__path__ = __import__("pkgutil").extend_path(__path__, __name__)  # Aum
from datetime import datetime

__NAME__ = "cockpitdecks_wm"
__COPYRIGHT__ = f"© 2022-{datetime.now().strftime('%Y')} Pierre M <pierre@devleaks.be>"

__version__ = "2.3.2"
