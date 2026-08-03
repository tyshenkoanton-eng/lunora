from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()


def timezone_for(lat: float, lon: float) -> str | None:
    return _tf.timezone_at(lat=lat, lng=lon)
