class StationHold(ValueError):
    pass


def ensure_energizable(ports, minimum):
    reasons = []
    for port in ports:
        code = port["serial"]
        measured = port["insulation"]
        if measured < minimum:
            reasons.append(f"{code} 绝缘 {measured} kΩ 低于 {minimum} kΩ")
        if not port["interlock"]:
            reasons.append(f"{code} 联锁试验未通过")
    if reasons:
        raise StationHold("；".join(reasons))
