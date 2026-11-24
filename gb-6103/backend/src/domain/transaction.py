from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .acceptance_rules import StationHold, ensure_energizable


def _stage_tables(db):
    db.execute(text("""
        CREATE TEMP TABLE acceptance_station (
            station VARCHAR(24), district VARCHAR(40) NOT NULL,
            CONSTRAINT acceptance_station_code PRIMARY KEY (station)
        ) ON COMMIT DROP
    """))
    db.execute(text("""
        CREATE TEMP TABLE acceptance_port (
            serial VARCHAR(24), station VARCHAR(24) NOT NULL REFERENCES acceptance_station,
            insulation INTEGER NOT NULL, interlock BOOLEAN NOT NULL,
            CONSTRAINT acceptance_port_serial PRIMARY KEY (serial)
        ) ON COMMIT DROP
    """))


def _record_station(db, station, minimum):
    db.execute(
        text("INSERT INTO acceptance_station (station, district) VALUES (:station, :district)"),
        {"station": station["station"], "district": station["district"]},
    )
    db.execute(text("""
        INSERT INTO acceptance_port (serial, station, insulation, interlock)
        VALUES (:serial, :station, :insulation, :interlock)
    """), [{**port, "station": station["station"]} for port in station["ports"]])
    ensure_energizable(station["ports"], minimum)


def _integrity_note(exc):
    native = exc.orig
    if getattr(native, "sqlstate", getattr(native, "pgcode", None)) != "23505":
        raise exc
    constraint = native.diag.constraint_name
    if constraint == "acceptance_station_code":
        return "站号已被本批次的通过记录占用"
    if constraint == "acceptance_port_serial":
        return "枪口序列号重复，枪口与所属站记录已经回滚"
    raise exc


def receive(db, stations, minimum):
    _stage_tables(db)
    evidence = []
    for position, station in enumerate(stations, 1):
        try:
            with db.begin_nested():
                _record_station(db, station, minimum)
        except StationHold as exc:
            outcome, detail = "搁置", str(exc)
        except IntegrityError as exc:
            outcome, detail = "搁置", _integrity_note(exc)
        else:
            outcome, detail = "通过", "站点与全部枪口已登记"
        evidence.append({
            "顺序": position, "站号": station["station"], "片区": station["district"],
            "送检枪口": len(station["ports"]), "决定": outcome, "原因": detail,
        })
    accepted = db.execute(text("SELECT COUNT(*) FROM acceptance_station")).scalar_one()
    ports = db.execute(text("SELECT COUNT(*) FROM acceptance_port")).scalar_one()
    db.execute(text("DROP TABLE acceptance_port, acceptance_station"))
    return evidence, accepted, ports
