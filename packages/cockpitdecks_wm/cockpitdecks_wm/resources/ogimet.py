"""
A METAR is a weather situation at a named location, usually an airport.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import requests_cache

# these packages have better METAR/TAF collection and exposure
from avwx import Station, Metar, Taf


from cockpitdecks.resources.weather import WeatherData


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# IMPORTANT:
# Do NOT call requests_cache.install_cache() globally here.
# It monkeypatches requests process-wide and can affect xpwebapi metadata fetches.
_OGIMET_SESSION = requests_cache.CachedSession("ogimet_cache")


def round_dt(dt, delta):  # rounds date to delta after date.
    return dt + (datetime.min - dt.replace(tzinfo=None)) % delta


def normalize_dt(dt):
    dtutc = dt.astimezone(tz=timezone.utc)
    dtret = round_dt(dtutc - timedelta(minutes=30), timedelta(minutes=30))
    return dtret


# Idea:
# As time passes, fetch next time METAR.
# Use supplied time, and update by fetching new METAR
# for the next half hour or so.
# Reset base time based on current time, not requested moment.
class WeatherOGIMET(WeatherData):

    def __init__(self, icao: str, moment: datetime):
        WeatherData.__init__(self, name=icao, config={})
        self._created = datetime.now()
        self._updated: datetime

        self.moment = moment
        self.icao = icao

        self.timed_update = False
        self.update_time = 10 * 60  # secs

        # working variables
        self._raw: str

        self.init(self.moment)

    def set_station(self, station: Any):
        if type(station) is Station:
            self.station = station
            return
        newstation = Station.from_icao(ident=station)
        if newstation is not None:
            self.station = newstation
            return
        logger.warning(f"could not find station {station} ({type(station)})")

    def station_changed(self):
        logger.warning("OGIMET station never changes")

    def check_weather(self) -> bool:
        if not hasattr(self, "_weather") or self._weather is None:
            return True
        if self.timed_update:
            diff = datetime.now() - self._updated
            return diff.seconds > self.update_time
        return False

    def weather_changed(self):
        logger.warning("OGIMET weather never changes")

    def check_station(self) -> bool:
        return not hasattr(self, "_station") or self._station is None

    def init(self, moment: datetime):
        if self.check_station():
            station = Station.from_icao(ident=self.icao)
            if station is not None:
                self.station = station  # setter calls station_changed()
                if self.check_weather():
                    if self.update_weather(moment_normalized=normalize_dt(moment)):
                        self.weather_changed()
                else:
                    logger.warning("problem fetching OGIMET METAR")
            else:
                logger.warning(f"OGIMET station {self.icao} not found")
        else:
            logger.warning("OGIMET station already set, not updated")

    def update_weather(self, moment_normalized: datetime | None = None) -> bool:
        def clean_metars(metars_in):
            p = map(lambda i: i.split(), metars_in)
            metars_out = []
            for l in p:
                temp = map(lambda s: s.strip("\\n"), l)
                metars_out.append(" ".join(list(map(lambda t: t.strip("="), temp))[1:]))
            return metars_out

        def select_metar(metars):
            return metars[0]

        if moment_normalized is None:
            if hasattr(self, "_updated"):  # uopdate after some time
                diff = datetime.now() - self._updated
                if diff.seconds > self.update_time:
                    moment_normalized = self.moment + diff
                else:
                    logger.warning(f"not time to update ({diff.seconds}/{self.update_time})")
                    return False
            else:
                moment_normalized = self.moment  # first run

        # 1. Fetch
        url = f"https://www.ogimet.com/display_metars2.php?lang=en&lugar={self.icao}&tipo=ALL&ord=REV&nil=SI&fmt=txt"
        url = url + moment_normalized.strftime("&ano=%Y&mes=%m&day=%d&hora=%H&anof=%Y&mesf=%m&dayf=%d&horaf=%H&minf=59&send=send")
        logger.debug(f"url={url}")
        try:
            response = _OGIMET_SESSION.get(url, cookies={"cookieconsent_status": "dismiss"})
            text = response.text
            logger.debug(f"response: {text}")
        except:
            logger.warning("problem getting OGIMET data", exc_info=True)
            return False

        # 2. Process result (complicated)
        rex = "( (METAR|SPECI) .*?=)"
        metars = re.findall(rex, text)
        logger.debug(f"matches: {metars}")
        if len(metars) == 0:
            logger.warning("no METAR|SPECI in response")
            return False
        metars = [m[0] for m in metars]
        metars = clean_metars(metars)

        # 2. Create (historical) Metar(s)
        self._raw = select_metar(metars)
        logger.debug(f"Historical metar {self.icao} at {moment_normalized}: {self._raw}")
        try:
            metar = Metar.from_report(report=self._raw, issued=moment_normalized.date())
            if metar is not None:
                self._weather = metar
                self._updated = metar.last_updated
            return True
        except:
            logger.warning(f"problem creating Metar {self._raw}", exc_info=True)

        return False


# For testing:
# $ python cockpitdecks_wm/buttons/representation/ogimet.py
if __name__ == "__main__":
    moment = datetime(year=2023, month=10, day=8, hour=14, minute=23)
    w = WeatherOGIMET(icao="EBBR", moment=moment)
    print(w.weather.raw)
    print("\n".join(w.weather.summary.split(", ")))
    # w.update_weather()

"""
https://www.ogimet.com/display_metars2.php?lang=en&lugar=OTHH&tipo=SA&ord=REV&nil=SI&fmt=txt&ano=2019&mes=04&day=13&hora=07&anof=2019&mesf=04&dayf=13&horaf=07&minf=59&send=send      ==>


##########################################################
# Query made at 01/17/2025 14:23:26 UTC
# Time interval: from 01/17/2025 08:00  to 01/17/2025 14:59  UTC
##########################################################

##########################################################
# EDDM, Muenchen-Riem (Germany)
# WMO index: 10866. WIGOS ID: Unknown
# Latitude 48-21N. Longitude 011-47E. Altitude 453 m.
##########################################################

###################################
#  METAR/SPECI from EDDM
###################################
202501171350 METAR EDDM 171350Z AUTO 09008KT 9999 OVC007 00/M01 Q1034 NOSIG=
202501171320 METAR EDDM 171320Z AUTO 09007KT 050V110 9999 OVC007 00/M01 Q1034 NOSIG=
202501171250 METAR EDDM 171250Z AUTO 09007KT 9999 OVC007 00/M01 Q1035 NOSIG=
202501171220 METAR EDDM 171220Z AUTO 09008KT 9999 OVC007 00/M01 Q1035 NOSIG=
202501171150 METAR EDDM 171150Z AUTO 11006KT 9999 OVC006 00/M01 Q1035 NOSIG=
202501171120 METAR EDDM 171120Z AUTO 10008KT 060V130 9999 OVC006 M00/M01 Q1036 NOSIG=
202501171050 METAR EDDM 171050Z AUTO 10009KT 9999 OVC006 M00/M01 Q1036 NOSIG=
202501171020 METAR EDDM 171020Z AUTO 07007KT 9999 OVC006 M00/M01 Q1036 NOSIG=
202501170950 METAR EDDM 170950Z AUTO 09007KT 9999 OVC006 M00/M02 Q1037 NOSIG=
202501170920 METAR EDDM 170920Z AUTO 10006KT 050V130 9999 OVC006 M00/M02 Q1037 NOSIG=
202501170850 METAR EDDM 170850Z AUTO 09008KT 9999 OVC006 M00/M01 Q1036 NOSIG=
202501170820 METAR EDDM 170820Z AUTO 08008KT 040V100 9999 OVC006 M00/M02 Q1036 NOSIG=

# No short TAF reports from EDDM in databse.

###################################
#  large TAF from EDDM
###################################
202501171100 TAF EDDM 171100Z 1712/1818 08006KT 9999 OVC006
                      BECMG 1715/1717 VRB02KT
                      BECMG 1722/1724 4000 BR OVC003
                      PROB30 TEMPO 1801/1808 0600 FZFG VV001
                      BECMG 1808/1810 9999 FEW005=

----------------------------------------------------------------------------------------------------------

##########################################################
# Query made at 01/17/2025 14:24:12 UTC
# Time interval: from 01/17/2025 08:00  to 01/17/2025 14:59  UTC
##########################################################

##########################################################
# EBBR, Bruxelles National (Belgium)
# WMO index: 06451. WIGOS ID: 0-20000-0-06451
# Latitude 50-53-47N. Longitude 004-31-37E. Altitude 56 m.
##########################################################

###################################
#  METAR/SPECI from EBBR
###################################
202501171350 METAR EBBR 171350Z VRB01KT 0600 R25L/1800D R25R/1900N R01/1900U FG OVC002 01/01 Q1036 NOSIG=
202501171320 METAR EBBR 171320Z VRB01KT 0450 R25L/1500N R25R/1700D R01/0800U FG OVC002 01/01 Q1036 NOSIG=
202501171250 METAR EBBR 171250Z VRB02KT 0350 R25L/0550N R25R/1500D R01/1200U FG OVC002 01/01 Q1036 NOSIG=
202501171220 METAR EBBR 171220Z 00000KT 0350 R25L/0650N R25R/1400N R01/0600U FG OVC001 01/01 Q1037 NOSIG=
202501171150 METAR EBBR 171150Z VRB02KT 0350 R25L/0500N R25R/1400D R01/0550N FG OVC001 00/00 Q1037 NOSIG=
202501171120 METAR EBBR 171120Z VRB02KT 0350 R25L/0500N R25R/0800N R01/0550N FG OVC001 00/00 Q1038 NOSIG=
202501171050 METAR COR EBBR 171050Z VRB01KT 0350 R25L/0600N R25R/0800N R01/0500N FG OVC001 00/00 Q1038 NOSIG=
202501171020 METAR EBBR 171020Z VRB01KT 0200 R25L/0450N R25R/0800U R01/0400N FG OVC001 00/00 Q1038 NOSIG=
202501170950 METAR EBBR 170950Z 13003KT 090V150 0200 R25L/0350N R25R/0550U R01/0400N FG OVC001 00/00 Q1038 NOSIG=
202501170920 METAR COR EBBR 170920Z 12003KT 090V150 0200 R25L/0375N R25R/0650D R01/0400N FG OVC001 00/00 Q1038 NOSIG=
202501170850 METAR EBBR 170850Z 13002KT 0300 R25L/0375N R25R/0600N R01/0450N FG OVC001 00/00 Q1038 NOSIG=
202501170820 METAR EBBR 170820Z 10002KT 0350 R25L/0400N R25R/0600N R01/0750D FG OVC001 00/00 Q1037 TEMPO OVC002=

# No short TAF reports from EBBR in databse.

###################################
#  large TAF from EBBR
###################################
202501171110 TAF EBBR 171110Z 1712/1818 06003KT 0300 FG BKN001
                      PROB30 TEMPO 1712/1718 3500 BR BKN006
                      BECMG 1721/1724 FZFG
                      PROB30 TEMPO 1812/1818 6000 NSW SCT006=

----------------------------------------------------------------------------------------------------------

##########################################################
# Query made at 01/17/2025 14:25:42 UTC
# Time interval: from 10/08/2024 12:00  to 10/08/2024 13:59  UTC
##########################################################

##########################################################
# EBBR, Bruxelles National (Belgium)
# WMO index: 06451. WIGOS ID: 0-20000-0-06451
# Latitude 50-53-47N. Longitude 004-31-37E. Altitude 56 m.
##########################################################

###################################
#  METAR/SPECI from EBBR
###################################
202410081350 METAR EBBR 081350Z 20008KT 170V230 9999 SCT031 18/13 Q0999 NOSIG=
202410081320 METAR EBBR 081320Z 20009KT 9999 BKN030 18/13 Q0999 NOSIG=
202410081250 METAR EBBR 081250Z 20010KT 9999 BKN038 18/13 Q0999 NOSIG=
202410081220 METAR EBBR 081220Z 19010KT 9999 BKN032 17/13 Q0999 NOSIG=

# No short TAF reports from EBBR in databse.

# No large TAF reports from EBBR in databse.


"""
