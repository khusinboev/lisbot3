"""
src/database.py — API response ga mos yangilangan schema.
"""
import aiosqlite
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
from settings import DB_PATH


@dataclass
class Certificate:
    id: Optional[int] = None

    # Identifikatorlar
    uuid: Optional[str] = None
    register_id: Optional[int] = None
    application_id: Optional[int] = None
    document_id: Optional[int] = None
    number: Optional[str] = None           # hujjat raqami
    register_number: Optional[str] = None  # L-XXXXXXXX

    # Tashkilot
    name: Optional[str] = None             # tashkilot nomi
    tin: Optional[str] = None              # STIR
    pin: Optional[str] = None

    # Manzil
    region_uz: Optional[str] = None
    sub_region_uz: Optional[str] = None
    address: Optional[str] = None
    activity_addresses: Optional[str] = None  # JSON array (uz matni)

    # Sanalar
    registration_date: Optional[str] = None
    expiry_date: Optional[str] = None
    revoke_date: Optional[str] = None

    # Holat
    status: Optional[str] = None           # ACTIVE / REVOKED / ...
    active: bool = True

    # Faoliyat turlari
    specializations: Optional[str] = None      # JSON array [name.uz, ...]
    specialization_ids: Optional[str] = None

    # Filtr
    is_filtered: bool = False

    # Vaqtlar
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Database:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS certificates (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid                TEXT UNIQUE NOT NULL,
                    register_id         INTEGER,
                    application_id      INTEGER,
                    document_id         INTEGER,
                    number              TEXT,
                    register_number     TEXT,
                    name                TEXT,
                    tin                 TEXT,
                    pin                 TEXT,
                    region_uz           TEXT,
                    sub_region_uz       TEXT,
                    address             TEXT,
                    activity_addresses  TEXT,
                    registration_date   TEXT,
                    expiry_date         TEXT,
                    revoke_date         TEXT,
                    status              TEXT,
                    active              INTEGER DEFAULT 1,
                    specializations     TEXT,
                    specialization_ids  TEXT,
                    is_filtered         INTEGER DEFAULT 0,
                    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for col in ("tin", "number", "status", "is_filtered", "active"):
                await db.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_cert_{col} ON certificates({col})"
                )
            await db.commit()
        await self._migrate()

    async def _migrate(self):
        """Eski bazaga yangi ustunlar qo'shish."""
        new_cols = {
            "register_id": "INTEGER", "application_id": "INTEGER",
            "register_number": "TEXT", "pin": "TEXT",
            "region_uz": "TEXT", "sub_region_uz": "TEXT",
            "activity_addresses": "TEXT", "revoke_date": "TEXT",
            "active": "INTEGER DEFAULT 1",
            "specializations": "TEXT", "specialization_ids": "TEXT",
        }
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("PRAGMA table_info(certificates)")
            existing = {r[1] for r in await cur.fetchall()}
            for col, ctype in new_cols.items():
                if col not in existing:
                    await db.execute(f"ALTER TABLE certificates ADD COLUMN {col} {ctype}")
            await db.commit()

    async def upsert_certificate(self, cert: Certificate) -> int:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                INSERT INTO certificates (
                    uuid, register_id, application_id, document_id,
                    number, register_number, name, tin, pin,
                    region_uz, sub_region_uz, address, activity_addresses,
                    registration_date, expiry_date, revoke_date,
                    status, active, specializations, specialization_ids,
                    is_filtered, created_at, updated_at
                ) VALUES (
                    :uuid, :register_id, :application_id, :document_id,
                    :number, :register_number, :name, :tin, :pin,
                    :region_uz, :sub_region_uz, :address, :activity_addresses,
                    :registration_date, :expiry_date, :revoke_date,
                    :status, :active, :specializations, :specialization_ids,
                    :is_filtered, :now, :now
                )
                ON CONFLICT(uuid) DO UPDATE SET
                    register_id        = excluded.register_id,
                    application_id     = excluded.application_id,
                    number             = excluded.number,
                    register_number    = excluded.register_number,
                    name               = excluded.name,
                    tin                = excluded.tin,
                    pin                = excluded.pin,
                    region_uz          = excluded.region_uz,
                    sub_region_uz      = excluded.sub_region_uz,
                    address            = excluded.address,
                    activity_addresses = excluded.activity_addresses,
                    registration_date  = excluded.registration_date,
                    expiry_date        = excluded.expiry_date,
                    revoke_date        = excluded.revoke_date,
                    status             = excluded.status,
                    active             = excluded.active,
                    specializations    = excluded.specializations,
                    specialization_ids = excluded.specialization_ids,
                    updated_at         = :now
            """, {
                "uuid": cert.uuid, "register_id": cert.register_id,
                "application_id": cert.application_id, "document_id": cert.document_id,
                "number": cert.number, "register_number": cert.register_number,
                "name": cert.name, "tin": str(cert.tin) if cert.tin else None,
                "pin": cert.pin, "region_uz": cert.region_uz,
                "sub_region_uz": cert.sub_region_uz, "address": cert.address,
                "activity_addresses": cert.activity_addresses,
                "registration_date": cert.registration_date,
                "expiry_date": cert.expiry_date, "revoke_date": cert.revoke_date,
                "status": cert.status, "active": 1 if cert.active else 0,
                "specializations": cert.specializations,
                "specialization_ids": cert.specialization_ids,
                "is_filtered": 1 if cert.is_filtered else 0,
                "now": now,
            })
            await db.commit()
            return cur.lastrowid

    # bot.py eski interfeysi bilan mos
    async def add_certificate(self, cert: Certificate) -> int:
        return await self.upsert_certificate(cert)

    async def add_filtered_certificate(self, cert: Certificate) -> int:
        cert.is_filtered = True
        return await self.upsert_certificate(cert)

    async def get_all_certificates(self, limit: int = 100000, offset: int = 0) -> List[Certificate]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM certificates LIMIT ? OFFSET ?", (limit, offset))
            return [self._row(r) for r in await cur.fetchall()]

    async def get_filtered_certificates(self, limit: int = 100000, offset: int = 0) -> List[Certificate]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM certificates WHERE is_filtered=1 LIMIT ? OFFSET ?", (limit, offset)
            )
            return [self._row(r) for r in await cur.fetchall()]

    async def get_certificate_by_uuid(self, uuid: str) -> Optional[Certificate]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM certificates WHERE uuid=?", (uuid,))
            row = await cur.fetchone()
            return self._row(row) if row else None

    async def count_certificates(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM certificates")
            return (await cur.fetchone())[0]

    async def count_filtered_certificates(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM certificates WHERE is_filtered=1")
            return (await cur.fetchone())[0]

    async def get_stats(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                SELECT COUNT(*),
                       SUM(CASE WHEN is_filtered=1 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN active=1 THEN 1 ELSE 0 END)
                FROM certificates
            """)
            r = await cur.fetchone()
            return {
                "total_certificates":    r[0] or 0,
                "filtered_certificates": r[1] or 0,
                "active_certificates":   r[2] or 0,
            }

    async def update_stats(self, **kwargs):
        pass  # get_stats() real hisoblaydi, bu kerak emas

    async def clear_certificates(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM certificates")
            await db.commit()

    async def clear_filtered_certificates(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE certificates SET is_filtered=0")
            await db.commit()

    @staticmethod
    def _row(row) -> Certificate:
        d = dict(row)
        return Certificate(
            id=d.get("id"), uuid=d.get("uuid"),
            register_id=d.get("register_id"), application_id=d.get("application_id"),
            document_id=d.get("document_id"), number=d.get("number"),
            register_number=d.get("register_number"), name=d.get("name"),
            tin=d.get("tin"), pin=d.get("pin"),
            region_uz=d.get("region_uz"), sub_region_uz=d.get("sub_region_uz"),
            address=d.get("address"), activity_addresses=d.get("activity_addresses"),
            registration_date=d.get("registration_date"), expiry_date=d.get("expiry_date"),
            revoke_date=d.get("revoke_date"), status=d.get("status"),
            active=bool(d.get("active", 1)), specializations=d.get("specializations"),
            specialization_ids=d.get("specialization_ids"),
            is_filtered=bool(d.get("is_filtered", 0)),
            created_at=d.get("created_at"), updated_at=d.get("updated_at"),
        )