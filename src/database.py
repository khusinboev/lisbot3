"""
src/database.py — API response ga mos yangilangan schema.
"""
import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
from settings import DB_PATH


_CYR_TO_LAT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "",
    "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "қ": "q", "ғ": "g", "ў": "o", "ҳ": "h",
})


def _normalize_activity_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    value = str(text).strip().lower()
    if not value:
        return ""

    # Apostrofning turli unicode variantlarini bir xil ko'rinishga keltiramiz.
    for ch in ("’", "`", "ʻ", "ʼ", "ʹ", "´", "‘"):
        value = value.replace(ch, "'")

    value = value.translate(_CYR_TO_LAT)

    # Apostrof va bo'shliqlardan mustaqil qidiruv.
    cleaned = []
    for ch in value:
        if ch.isalnum():
            cleaned.append(ch)
    return "".join(cleaned)


def _specializations_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(v) for v in parsed if v is not None]
        return [str(parsed)]
    except Exception:
        return [str(raw)]


def _activity_matches(activity_type: str, specializations_raw: Optional[str]) -> bool:
    target = _normalize_activity_text(activity_type)
    if not target:
        return False

    for specialization in _specializations_list(specializations_raw):
        norm_spec = _normalize_activity_text(specialization)
        if not norm_spec:
            continue
        if target in norm_spec or norm_spec in target:
            return True
    return False


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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS filtered_certificates (
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
                    is_filtered         INTEGER DEFAULT 1,
                    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for col in ("tin", "number", "status", "is_filtered", "active"):
                await db.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_cert_{col} ON certificates({col})"
                )
                await db.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_fcert_{col} ON filtered_certificates({col})"
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

            await db.execute("""
                CREATE TABLE IF NOT EXISTS filtered_certificates (
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
                    is_filtered         INTEGER DEFAULT 1,
                    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    @staticmethod
    def _params_for_upsert(cert: Certificate, now: str) -> Dict[str, Any]:
        return {
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
        }

    @staticmethod
    async def _upsert_into_table(db: aiosqlite.Connection, table_name: str, cert: Certificate, now: str):
        await db.execute(f"""
            INSERT INTO {table_name} (
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
                is_filtered        = excluded.is_filtered,
                updated_at         = :now
        """, Database._params_for_upsert(cert, now))

    async def upsert_certificate(self, cert: Certificate) -> int:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT id FROM certificates WHERE uuid=?", (cert.uuid,))
            prev = await cur.fetchone()

            await self._upsert_into_table(db, "certificates", cert, now)
            if cert.is_filtered:
                await self._upsert_into_table(db, "filtered_certificates", cert, now)
            else:
                await db.execute("DELETE FROM filtered_certificates WHERE uuid=?", (cert.uuid,))

            await db.commit()
            if prev:
                return prev[0]

            cur = await db.execute("SELECT id FROM certificates WHERE uuid=?", (cert.uuid,))
            row = await cur.fetchone()
            return row[0] if row else 0

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
                "SELECT * FROM filtered_certificates LIMIT ? OFFSET ?", (limit, offset)
            )
            return [self._row(r) for r in await cur.fetchall()]

    async def get_certificate_by_uuid(self, uuid: str) -> Optional[Certificate]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM certificates WHERE uuid=?", (uuid,))
            row = await cur.fetchone()
            return self._row(row) if row else None

    async def get_certificate_by_number(self, number: str) -> Optional[Certificate]:
        normalized = str(number).strip()
        if not normalized:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT *
                FROM certificates
                WHERE number = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (normalized,),
            )
            row = await cur.fetchone()
            return self._row(row) if row else None

    async def count_certificates(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM certificates")
            return (await cur.fetchone())[0]

    async def count_filtered_certificates(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM filtered_certificates")
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

    async def get_stats_by_activity(self, activity_type: str) -> Dict[str, Any]:
        """
        certificates jadvalidan faoliyat turi bo'yicha dinamik statistika.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT specializations, active FROM certificates")
            rows = await cur.fetchall()

            total = len(rows)
            active_total = sum(1 for r in rows if int(r["active"] or 0) == 1)

            filtered_count = 0
            active_filtered = 0
            for row in rows:
                if _activity_matches(activity_type, row["specializations"]):
                    filtered_count += 1
                    if int(row["active"] or 0) == 1:
                        active_filtered += 1

            return {
                "total_certificates": total,
                "filtered_certificates": filtered_count,
                "active_certificates": active_total,
                "active_filtered_certificates": active_filtered,
            }

    async def sync_filtered_by_activity(self, activity_type: str) -> int:
        """
        certificates jadvalidagi activity_type ga mos yozuvlarni
        filtered_certificates jadvaliga to'liq sinxronlaydi.
        """
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM certificates")
            all_rows = await cur.fetchall()

            matched_rows = [r for r in all_rows if _activity_matches(activity_type, r["specializations"])]

            await db.execute("DELETE FROM filtered_certificates")

            if matched_rows:
                await db.executemany(
                    """
                    INSERT INTO filtered_certificates (
                        uuid, register_id, application_id, document_id,
                        number, register_number, name, tin, pin,
                        region_uz, sub_region_uz, address, activity_addresses,
                        registration_date, expiry_date, revoke_date,
                        status, active, specializations, specialization_ids,
                        is_filtered, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        1, ?, ?
                    )
                    """,
                    [
                        (
                            row["uuid"], row["register_id"], row["application_id"], row["document_id"],
                            row["number"], row["register_number"], row["name"], row["tin"], row["pin"],
                            row["region_uz"], row["sub_region_uz"], row["address"], row["activity_addresses"],
                            row["registration_date"], row["expiry_date"], row["revoke_date"],
                            row["status"], row["active"], row["specializations"], row["specialization_ids"],
                            row["created_at"] or now, now,
                        )
                        for row in matched_rows
                        if row["uuid"]
                    ],
                )

            await db.execute(
                """
                UPDATE certificates
                SET is_filtered = 0,
                    updated_at = ?
                """,
                (now,),
            )

            if matched_rows:
                await db.executemany(
                    "UPDATE certificates SET is_filtered = 1, updated_at = ? WHERE uuid = ?",
                    [(now, row["uuid"]) for row in matched_rows if row["uuid"]],
                )

            await db.commit()

            cur = await db.execute("SELECT COUNT(*) FROM filtered_certificates")
            return (await cur.fetchone())[0] or 0

    async def update_stats(self, **kwargs):
        pass  # get_stats() real hisoblaydi, bu kerak emas

    async def clear_certificates(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM certificates")
            await db.commit()

    async def clear_filtered_certificates(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE certificates SET is_filtered=0")
            await db.execute("DELETE FROM filtered_certificates")
            await db.commit()

    async def get_existing_numbers_set(self) -> set[str]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT number FROM certificates WHERE number IS NOT NULL AND TRIM(number) != ''")
            rows = await cur.fetchall()

        result: set[str] = set()
        for (number,) in rows:
            raw = str(number).strip()
            if not raw:
                continue
            try:
                result.add(str(int(raw)))
            except (TypeError, ValueError):
                result.add(raw)
        return result

    async def get_filtered_numbers_set(self) -> set[str]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT number FROM filtered_certificates WHERE number IS NOT NULL AND TRIM(number) != ''"
            )
            rows = await cur.fetchall()

        result: set[str] = set()
        for (number,) in rows:
            raw = str(number).strip()
            if not raw:
                continue
            try:
                result.add(str(int(raw)))
            except (TypeError, ValueError):
                result.add(raw)
        return result

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