from collections import defaultdict
from time import time

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from src.models.registers import (
    IN_SERVICE, RETIRED, acceptance_batch, port_registry, service_port, service_station,
)
from .acceptance_rules import StationHold, ensure_energizable


PENDING = {"status": "pending"}


def claim_batch(db, batch, parameter, payload_digest):
    """占住批号裁决台账。已有原裁决时直接返回，同批号重试不再重复入册。"""
    values = {
        "batch": batch, "parameter": parameter, "payload_digest": payload_digest,
        "result": PENDING, "created_at": int(time()),
    }
    if db.dialect.name == "postgresql":
        db.execute(pg_insert(acceptance_batch).values(**values).on_conflict_do_nothing(index_elements=["batch"]))
    else:
        db.execute(mysql_insert(acceptance_batch).values(**values).on_duplicate_key_update(
            batch=acceptance_batch.c.batch,
        ))
    # 行锁把同批号的并发重试串行化，后到者读到的就是原裁决。
    row = db.execute(
        select(acceptance_batch.c.result)
        .where(acceptance_batch.c.batch == batch).with_for_update()
    ).mappings().first()
    if row is None:
        # 占住裁决行的并发批次已经回滚，本批自行裁决。
        return None
    stored = row["result"]
    if isinstance(stored, dict) and stored.get("status") == "pending":
        return None
    # 同批号一律沿用原裁决，不再重复入册。
    return stored


def save_batch(db, batch, result):
    db.execute(update(acceptance_batch).where(acceptance_batch.c.batch == batch).values(result=result))


def _station_row(db, station):
    return db.execute(
        select(service_station).where(service_station.c.station == station).with_for_update()
    ).mappings().first()


def _try_own(db, values):
    if db.dialect.name == "postgresql":
        return db.execute(
            pg_insert(port_registry).values(**values)
            .on_conflict_do_nothing(index_elements=["serial"])
            .returning(port_registry.c.serial)
        ).first() is not None
    return db.execute(mysql_insert(port_registry).values(**values).prefix_with("IGNORE")).rowcount == 1


CONTESTED = "并发冲突"


def _claim_serial(db, serial, code, old, batch):
    """在枪号名册上占位。返回占用该枪号的其他站号；成功或沿用旧站枪号时返回 None。"""
    for _ in range(3):
        values = {"serial": serial, "holder": code, "batch": batch, "updated_at": int(time())}
        if _try_own(db, values):
            return None
        # 并发入册会阻塞在这行锁上：先提交的事务留下枪号，只准一方入册。
        holder = db.execute(
            select(port_registry.c.holder).where(port_registry.c.serial == serial).with_for_update()
        ).scalar_one_or_none()
        if holder is None:
            # 占位方已回滚，枪号重新空出，再抢一次。
            continue
        if holder == code:
            return None
        if holder == old:
            # 接替站先送检：旧站尚未退役，把枪号持枪人改到接替站。
            db.execute(update(port_registry).where(port_registry.c.serial == serial).values(
                holder=code, batch=batch, updated_at=int(time()),
            ))
            return None
        return holder
    return CONTESTED


def _process(db, station, minimum, batch, planned, replaced, submitted):
    code = station["station"]
    old = station.get("replaces")
    ports = station["ports"]
    # 已被本批通过的接替站取代：旧站只登记退役，不再入册。
    if code in replaced:
        return "退役", f"接替站 {replaced[code]} 及全部枪口已通过，旧站不再入册"
    # 质量不合格的站先搁置，不占用任何枪号。
    ensure_energizable(ports, minimum)

    row = _station_row(db, code)
    if row is not None and row["status"] == RETIRED:
        return "搁置", f"站号已退役，由接替站 {row['successor'] or '—'} 接替，不再入册"
    if row is not None and row["status"] == IN_SERVICE:
        pending = planned.get(code)
        if pending:
            decision = "、".join(pending)
            return "搁置", f"接替站 {decision} 尚未全部通过，旧站继续在役"
        return "搁置", "站号已在在役名册，跨批次保留其枪口"

    if old is not None:
        if old in replaced:
            raise StationHold(f"旧站 {old} 已由接替站 {replaced[old]} 接替")
        old_row = _station_row(db, old)
        if old_row is not None and old_row["status"] == RETIRED:
            raise StationHold(f"接替关系中的旧站 {old} 已退役")
        if old_row is not None and old_row["successor"]:
            raise StationHold(f"接替关系中的旧站 {old} 已由接替站 {old_row['successor']} 接替")
        if old_row is None and old not in submitted:
            raise StationHold(f"接替关系中的旧站 {old} 既不在役也未随本批送检")

    # 先落站行，接替站改挂旧站枪号时才满足枪号名册的外键。
    db.execute(insert(service_station).values(
        station=code, district=station["district"], status=IN_SERVICE,
        replaces=old, successor=None, batch=batch, updated_at=int(time()),
    ))
    for port in sorted(ports, key=lambda item: item["serial"]):
        holder = _claim_serial(db, port["serial"], code, old, batch)
        if holder == CONTESTED:
            raise StationHold(f"枪口 {port['serial']} 正被其他批次占用，本站记录整站回滚")
        if holder is not None:
            raise StationHold(f"枪口 {port['serial']} 已由在役站 {holder} 持有，本站记录整站回滚")
    db.execute(insert(service_port), [
        {
            "station": code, "serial": port["serial"], "insulation": port["insulation"],
            "interlock": port["interlock"], "status": IN_SERVICE, "batch": batch,
        }
        for port in ports
    ])
    if old is not None:
        replaced[old] = code
        return "通过", f"接替旧站 {old}，接替站及全部枪口通过，待旧站退役后交接"
    return "通过", "站点与全部枪口已登记，进入在役名册"


def _retire(db, old, successor, batch, districts):
    """旧站退役并留在名册上；返回是否本次真正退役。"""
    row = _station_row(db, old)
    if row is None:
        # 旧站不在役但接替关系成立：保留一条退役记录，供跨批次核对交接。
        db.execute(insert(service_station).values(
            station=old, district=districts.get(old, "—"), status=RETIRED,
            replaces=None, successor=successor, batch=batch, updated_at=int(time()),
        ))
        return True
    if row["status"] != IN_SERVICE:
        return False
    db.execute(delete(port_registry).where(port_registry.c.holder == old))
    db.execute(delete(service_port).where(service_port.c.station == old))
    db.execute(update(service_station).where(service_station.c.station == old).values(
        status=RETIRED, successor=successor, batch=batch, updated_at=int(time()),
    ))
    return True


def _integrity_note(exc):
    native = exc.orig
    if getattr(native, "sqlstate", getattr(native, "pgcode", None)) != "23505":
        raise exc
    constraint = native.diag.constraint_name
    notes = {
        "service_station_pkey": "站号已在在役名册，跨批次保留",
        "service_port_station_serial": "同站枪口序列号重复，本站记录已经回滚",
        "port_registry_pkey": "枪口序列号已被其他在役站占用，本站记录已经回滚",
    }
    if constraint not in notes:
        raise exc
    return notes[constraint]


def _roster(db):
    stations = db.execute(
        select(service_station).where(service_station.c.status == IN_SERVICE)
        .order_by(service_station.c.station)
    ).mappings().all()
    ports = defaultdict(list)
    for port in db.execute(
        select(service_port.c.station, service_port.c.serial)
        .order_by(service_port.c.station, service_port.c.serial)
    ).mappings():
        ports[port["station"]].append(port["serial"])
    return [
        {
            "站号": item["station"], "片区": item["district"],
            "枪口": "、".join(ports[item["station"]]) or "—",
            "批次": item["batch"],
        }
        for item in stations
    ]


def _serial_list(stations, code):
    for station in stations:
        if station["station"] == code:
            return "、".join(sorted(port["serial"] for port in station["ports"]))
    return "—"


def _prelock(db, stations):
    """按固定顺序先占住本批涉及的站号与枪号，避免并发批次交叉占锁死锁。"""
    codes = sorted({station["station"] for station in stations}
                   | {station["replaces"] for station in stations if station.get("replaces")})
    serials = sorted({port["serial"] for station in stations for port in station["ports"]})
    if db.dialect.name == "postgresql":
        # 事务级咨询锁：即使站号或枪号尚未入册，也能按全局顺序串行化，避免新建行的交叉死锁。
        for namespace, values in (("station", codes), ("port", serials)):
            if not values:
                continue
            db.execute(text("""
                WITH ordered AS MATERIALIZED (
                    SELECT unnest(CAST(:values AS text[])) AS key ORDER BY 1
                )
                SELECT pg_advisory_xact_lock(hashtextextended(:namespace || ':' || key, 0))
                FROM ordered
            """), {"values": values, "namespace": namespace})
        return
    if codes:
        db.execute(
            select(service_station.c.station).where(service_station.c.station.in_(codes))
            .order_by(service_station.c.station).with_for_update()
        ).all()
    if serials:
        db.execute(
            select(port_registry.c.serial).where(port_registry.c.serial.in_(serials))
            .order_by(port_registry.c.serial).with_for_update()
        ).all()


def receive(db, stations, minimum, batch):
    _prelock(db, stations)
    submitted = {station["station"] for station in stations}
    districts = {station["station"]: station["district"] for station in stations}
    planned = defaultdict(list)
    for station in stations:
        if station.get("replaces"):
            planned[station["replaces"]].append(station["station"])
    replaced = {}
    evidence = []

    for position, station in enumerate(stations, 1):
        try:
            with db.begin_nested():
                outcome, detail = _process(
                    db, station, minimum, batch, planned, replaced, submitted,
                )
        except StationHold as exc:
            outcome, detail = "搁置", str(exc)
        except IntegrityError as exc:
            outcome, detail = "搁置", _integrity_note(exc)
        evidence.append({
            "顺序": position, "站号": station["station"], "片区": station["district"],
            "送检枪口": len(station["ports"]), "决定": outcome, "原因": detail,
        })

    # 接替站及全部枪口通过后旧站才退役；接替站搁置时旧站继续在役。
    by_station = {row["站号"]: row for row in evidence}
    attempts = [
        (station["station"], station["replaces"], by_station[station["station"]])
        for station in stations if station.get("replaces")
    ]
    handovers = []
    retired = set()
    for successor, old, row in attempts:
        if row["决定"] != "通过" or replaced.get(old) != successor:
            continue
        try:
            with db.begin_nested():
                done = _retire(db, old, successor, batch, districts)
        except IntegrityError as exc:
            row["决定"] = "搁置"
            row["原因"] = f"接替站已通过，但旧站 {old} 退役失败：{_integrity_note(exc)}"
            continue
        if not done:
            continue
        retired.add(old)
        row["原因"] = f"接替旧站 {old}，接替站及全部枪口通过，旧站已退役"
        note = f"接替站 {successor} 及全部枪口通过后退役"
        if old in by_station:
            by_station[old]["决定"] = "退役"
            by_station[old]["原因"] = note
        else:
            evidence.append({
                "顺序": None, "站号": old, "片区": districts.get(old, "—"),
                "送检枪口": 0, "决定": "退役", "原因": note,
            })

    for successor, old, row in attempts:
        if old in retired and replaced.get(old) == successor and row["决定"] == "通过":
            handovers.append({
                "旧站": old, "新站": successor, "旧站片区": districts.get(old, "—"),
                "新站枪口": _serial_list(stations, successor), "交接": "已生效",
                "说明": f"接替站 {successor} 及全部枪口通过，旧站 {old} 退役",
            })
        elif old in retired:
            handovers.append({
                "旧站": old, "新站": successor, "旧站片区": districts.get(old, "—"),
                "新站枪口": _serial_list(stations, successor), "交接": "未生效",
                "说明": f"旧站 {old} 已由接替站 {replaced.get(old)} 退役；本站未入册：{row['原因']}",
            })
        else:
            handovers.append({
                "旧站": old, "新站": successor, "旧站片区": districts.get(old, "—"),
                "新站枪口": _serial_list(stations, successor), "交接": "未生效",
                "说明": f"接替站 {successor} 未通过：{row['原因']}；旧站继续在役",
            })

    held = [row for row in evidence if row["决定"] == "搁置"]
    accepted = sum(1 for row in evidence if row["决定"] == "通过")
    retired = sum(1 for row in evidence if row["决定"] == "退役")
    roster = _roster(db)
    live_ports = db.execute(select(service_port.c.id)).scalars().all()
    return {
        "summary": (
            f"{len(stations)} 次分站送检，{accepted} 站通过、{len(held)} 次搁置、"
            f"{retired} 站退役；在役名册 {len(roster)} 个站点、{len(live_ports)} 个枪口。"
        ),
        "metrics": {
            "通过站点": accepted, "搁置站点": len(held), "退役站点": retired,
            "在役站点": len(roster), "在役枪口": len(live_ports),
        },
        "rows": evidence,
        "handovers": handovers,
        "in_service": roster,
    }
