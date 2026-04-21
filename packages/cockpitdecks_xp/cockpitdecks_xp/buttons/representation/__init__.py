import sysconfig

if not sysconfig.get_config_var("Py_GIL_DISABLED"):
    from .xpweather import XPRealWeatherMetarIcon
    from .xpstationplot import XPRealWeatherStationPlot
