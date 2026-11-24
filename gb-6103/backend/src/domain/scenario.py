from src.utils.serial import content_digest

from .intake import validate
from .transaction import claim_batch, receive, save_batch

CONFIG = {
    "title": "桐驿充电·换站批次验收",
    "team": "桐驿公共充电运维组（14 人）",
    "description": "逐站登记枪口，跨批次保留在役站点与枪口；接替站通过后旧站才退役，同批其余站点照常交接。",
    "direction": "事务与锁 / 保存点",
    "mechanism": "PostgreSQL 用保存点逐站验收，枪号名册与批号台账行锁保证只一方入册，同批号重试沿用原裁决。",
    "modules": ["换站交接", "站点与枪口", "分站验收", "送电核对单"],
    "unit": "验收批次",
    "max_parameter": 100000,
    "parameter_label": "绝缘读数下限（kΩ）",
    "default_parameter": 1000,
    "facts": ["在役名册", "接替交接", "搁置原因"],
    "palette": 3,
    "fixture": "TY-1124-站批",
}


def port(serial, insulation, interlock=True):
    return {"serial": serial, "insulation": insulation, "interlock": interlock}


def station(code, district, *ports, replaces=None):
    record = {"station": code, "district": district, "ports": list(ports)}
    if replaces is not None:
        record["replaces"] = replaces
    return record


FIXTURES = [
    {
        "code": "TY-1124-AC", "title": "TY-1124-站批", "description": "含跨站序列号重复及低绝缘读数。",
        "payload": {"batch": "TY-1124-A", "stations": [
            station("TY-S11", "口袋公园", port("TY-P01", 1840)),
            station("TY-S12", "东客站", port("TY-P02", 1280), port("TY-P01", 1450)),
            station("TY-S13", "体育场", port("TY-P03", 620)),
            station("TY-S14", "竹园路", port("TY-P02", 1000), port("TY-P03", 1610)),
        ]},
    },
    {
        "code": "TY-1125-SV", "title": "二次送检·重验联锁", "description": "联锁失败后，站号可用于同批的复测记录。",
        "payload": {"batch": "TY-1125-A", "stations": [
            station("TY-S21", "老集镇", port("TY-P21", 1800, False)),
            station("TY-S21", "老集镇", port("TY-P21", 1800)),
        ]},
    },
    {
        "code": "TY-1126-HO", "title": "换站交接·先送接替站",
        "description": "接替站先送检，沿用旧站枪号；全部枪口通过后旧站退役。",
        "payload": {"batch": "TY-1126-A", "stations": [
            station("TY-S41", "口袋公园二期", port("TY-P01", 1900), replaces="TY-S11"),
            station("TY-S11", "口袋公园", port("TY-P01", 1840)),
        ]},
    },
]


def run(payload, parameter, db):
    if type(parameter) is not int or not 1 <= parameter <= 100000:
        raise ValueError("验收下限须为 1–100000 kΩ 整数")
    validate(payload)
    digest = content_digest(payload)
    batch = payload.get("batch") or f"AUTO-{digest[:16].upper()}"
    decisions = claim_batch(db, batch, parameter, digest)
    if decisions is not None:
        # 同批号重试：沿用原裁决，不再重复入册。
        return decisions
    result = receive(db, payload["stations"], parameter, batch)
    result["批号"] = batch
    save_batch(db, batch, result)
    return result
