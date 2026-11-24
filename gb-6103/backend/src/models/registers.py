from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, ForeignKey, Integer, String, Table, UniqueConstraint,
)
from .base import metadata


IN_SERVICE = "in_service"
RETIRED = "retired"

# 跨批次保留的在役站点名册。站号是名册主键，退役记录留在册上作为交接依据。
service_station = Table(
    "service_station", metadata,
    Column("station", String(24), primary_key=True),
    Column("district", String(40), nullable=False),
    Column("status", String(16), nullable=False, index=True),
    Column("replaces", String(24), nullable=True),
    Column("successor", String(24), nullable=True),
    Column("batch", String(64), nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)

# 在役枪口按站保留。接替站可以沿用旧站枪号，所以唯一键是（站号，枪号）。
service_port = Table(
    "service_port", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("station", String(24), ForeignKey("service_station.station"), nullable=False, index=True),
    Column("serial", String(24), nullable=False),
    Column("insulation", Integer, nullable=False),
    Column("interlock", Boolean, nullable=False),
    Column("status", String(16), nullable=False),
    Column("batch", String(64), nullable=False),
    UniqueConstraint("station", "serial", name="service_port_station_serial"),
)

# 一个枪号在同一时刻只指向一个在役持枪站；并发争抢在此行锁上串行，只准一方入册。
port_registry = Table(
    "port_registry", metadata,
    Column("serial", String(24), primary_key=True),
    Column("holder", String(24), ForeignKey("service_station.station"), nullable=False),
    Column("batch", String(64), nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)

# 批次号的裁决台账。同批号重试直接沿用这里的原裁决，不再重复入册。
acceptance_batch = Table(
    "acceptance_batch", metadata,
    Column("batch", String(64), primary_key=True),
    Column("parameter", Integer, nullable=False),
    Column("payload_digest", String(64), nullable=True),
    Column("result", JSON(none_as_null=True), nullable=False),
    Column("created_at", BigInteger, nullable=False),
)
