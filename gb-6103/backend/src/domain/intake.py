import re


CODE = re.compile(r"[A-Z0-9][A-Z0-9-]{0,23}")


def _code(value, name):
    if not isinstance(value, str) or not CODE.fullmatch(value):
        raise ValueError(f"{name} 须为 1–24 位大写字母、数字或连字符")
    return value


def validate(payload):
    stations = payload.get("stations")
    if not isinstance(stations, list) or not 1 <= len(stations) <= 100:
        raise ValueError("stations 须含 1–100 条站点记录")
    for station in stations:
        if not isinstance(station, dict) or set(station) != {"station", "district", "ports"}:
            raise ValueError("站点记录须含 station、district 和 ports")
        _code(station["station"], "站号")
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
