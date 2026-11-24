from .intake import validate
from .transaction import receive

CONFIG = {
    "title": "桐驿充电·换站批次验收",
    "team": "桐驿公共充电运维组（14 人）",
    "description": "逐站登记枪口，隔离编号冲突以及检测未过的站点，同批其他站点仍可交接。",
    "direction": "事务与锁 / 保存点",
    "mechanism": "PostgreSQL 对站点和枪口写入建立真实 SAVEPOINT，站内原子回退、批内继续。",
    "modules": ["换站交接", "站点与枪口", "分站验收", "送电核对单"],
    "unit": "验收批次",
    "max_parameter": 100000,
    "parameter_label": "绝缘读数下限（kΩ）",
    "default_parameter": 1000,
    "facts": ["通过站点", "搁置站点", "已登记枪口"],
    "palette": 3,
    "fixture": "TY-1124-站批",
}


def port(serial, insulation, interlock=True):
    return {"serial": serial, "insulation": insulation, "interlock": interlock}


def station(code, district, *ports):
    return {"station": code, "district": district, "ports": list(ports)}


FIXTURES = [
    {
        "code": "TY-1124-AC", "title": "TY-1124-站批", "description": "含跨站序列号重复及低绝缘读数。",
        "payload": {"stations": [
            station("TY-S11", "口袋公园", port("TY-P01", 1840)),
            station("TY-S12", "东客站", port("TY-P02", 1280), port("TY-P01", 1450)),
            station("TY-S13", "体育场", port("TY-P03", 620)),
            station("TY-S14", "竹园路", port("TY-P02", 1000), port("TY-P03", 1610)),
        ]},
    },
    {
        "code": "TY-1125-SV", "title": "二次送检·重验联锁", "description": "联锁失败后，站号可用于同批的复测记录。",
        "payload": {"stations": [
            station("TY-S21", "老集镇", port("TY-P21", 1800, False)),
            station("TY-S21", "老集镇", port("TY-P21", 1800)),
        ]},
    },
]


def run(payload, parameter, db):
    if type(parameter) is not int or not 1 <= parameter <= 100000:
        raise ValueError("验收下限须为 1–100000 kΩ 整数")
    validate(payload)
    rows, accepted, ports = receive(db, payload["stations"], parameter)
    held = len(rows) - accepted
    return {
        "summary": f"{len(rows)} 次分站送检，{accepted} 站通过、{held} 次搁置，登记 {ports} 个枪口。",
        "metrics": {"通过站点": accepted, "搁置站点": held, "已登记枪口": ports},
        "rows": rows,
    }
