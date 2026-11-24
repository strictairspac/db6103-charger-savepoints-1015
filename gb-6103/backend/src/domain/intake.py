import re


CODE = re.compile(r"[A-Z0-9][A-Z0-9-]{0,23}")

STATION_KEYS = {"station", "district", "ports"}
STATION_KEYS_WITH_REPLACEMENT = STATION_KEYS | {"replaces"}


def _code(value, name):
    if not isinstance(value, str) or not CODE.fullmatch(value):
        raise ValueError(f"{name} 须为 1–24 位大写字母、数字或连字符")
    return value


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("业务资料须为 JSON 对象")
    if set(payload) not in ({"batch", "stations"}, {"stations"}):
        raise ValueError("业务资料须含 stations，可选 batch 批号")
    if "batch" in payload:
        _code(payload["batch"], "批号")
    stations = payload.get("stations")
    if not isinstance(stations, list) or not 1 <= len(stations) <= 100:
        raise ValueError("stations 须含 1–100 条站点记录")
    successors = {station["station"] for station in stations
                  if isinstance(station, dict) and isinstance(station.get("replaces"), str)}
    replaces = {station["replaces"] for station in stations
                if isinstance(station, dict) and isinstance(station.get("replaces"), str)}
    if successors & replaces:
        raise ValueError("同批不能串接接替关系：接替站不能再被另一站接替")
    for station in stations:
        if not isinstance(station, dict) or set(station) not in (STATION_KEYS, STATION_KEYS_WITH_REPLACEMENT):
            raise ValueError("站点记录须含 station、district、ports，可选 replaces")
        _code(station["station"], "站号")
        if "replaces" in station:
            _code(station["replaces"], "接替旧站号")
            if station["replaces"] == station["station"]:
                raise ValueError("接替站号不能与旧站号相同")
        district = station["district"]
        if not isinstance(district, str) or not 1 <= len(district.strip()) <= 40 or len(district) > 40:
            raise ValueError("片区名称须为 1–40 字符")
        ports = station["ports"]
        if not isinstance(ports, list) or not 1 <= len(ports) <= 32:
            raise ValueError("同站须提交 1–32 个枪口")
        for port in ports:
            if not isinstance(port, dict) or set(port) != {"serial", "insulation", "interlock"}:
                raise ValueError("枪口记录须含 serial、insulation 和 interlock")
            _code(port["serial"], "枪口序列号")
            if type(port["insulation"]) is not int or not 0 <= port["insulation"] <= 100000:
                raise ValueError("绝缘读数须为 0–100000 kΩ 整数")
            if type(port["interlock"]) is not bool:
                raise ValueError("联锁检测必须是布尔值")
