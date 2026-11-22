import dataclasses


def chart_to_dict(obj) -> dict:
    if obj is None:
        return {}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: _convert(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
    return {}


def _convert(val):
    if val is None:
        return None
    if dataclasses.is_dataclass(val) and not isinstance(val, type):
        return chart_to_dict(val)
    if isinstance(val, list):
        return [_convert(v) for v in val]
    if isinstance(val, dict):
        return {k: _convert(v) for k, v in val.items()}
    if isinstance(val, tuple):
        return list(val)
    # numpy-скаляры (np.bool_/np.float64 из эфемерид) → родной Python-тип, иначе JSONB падает
    if not isinstance(val, (bool, int, float, str)) and hasattr(val, 'item'):
        return val.item()
    if hasattr(val, 'value'):
        return val.value
    return val
