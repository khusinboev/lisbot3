"""
Database module for SQLite3 operations
"""
import sqlite3
import aiosqlite
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Certificate:
    """Certificate data class"""
    id: Optional[int] = None
    document_id: Optional[str] = None
    document_number: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None
    inserted_date: Optional[str] = None
    organization_name: Optional[str] = None
    address: Optional[str] = None
    stir: Optional[str] = None
    expiry_date: Optional[str] = None
    activity_type: Optional[str] = None
    uuid: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_filtered: bool = False


class Database:
    """SQLite database manager"""
    
    def __init__(self, db_path: str = "data/certificates.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        """Initialize database with tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Main certificates table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS certificates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT,
                    document_number TEXT,
                    status TEXT,
                    issue_date TEXT,
                    inserted_date TEXT,
                    organization_name TEXT,
                    address TEXT,
                    stir TEXT,
                    expiry_date TEXT,
                    activity_type TEXT,
                    uuid TEXT UNIQUE,
                    pdf_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_filtered INTEGER DEFAULT 0
                )
            """)
            
            # Filtered certificates table (for "Олий таълим хизматлари")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS filtered_certificates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    certificate_id INTEGER UNIQUE,
                    document_id TEXT,
                    document_number TEXT,
                    status TEXT,
                    issue_date TEXT,
                    inserted_date TEXT,
                    organization_name TEXT,
                    address TEXT,
                    stir TEXT,
                    expiry_date TEXT,
                    activity_type TEXT,
                    uuid TEXT UNIQUE,
                    pdf_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (certificate_id) REFERENCES certificates(id)
                )
            """)
            
            # Statistics table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scraping_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_certificates INTEGER DEFAULT 0,
                    filtered_certificates INTEGER DEFAULT 0,
                    last_scraped_at TEXT,
                    last_filtered_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_certificates_uuid 
                ON certificates(uuid)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_certificates_activity_type 
                ON certificates(activity_type)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_certificates_document_id 
                ON certificates(document_id)
            """)
            
            await db.commit()
    
    async def add_certificate(self, cert: Certificate) -> int:
        """Add or update a certificate"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT OR REPLACE INTO certificates 
                (document_id, document_number, status, issue_date, inserted_date,
                 organization_name, address, stir, expiry_date, activity_type,
                 uuid, pdf_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cert.document_id, cert.document_number, cert.status,
                cert.issue_date, cert.inserted_date, cert.organization_name,
                cert.address, cert.stir, cert.expiry_date, cert.activity_type,
                cert.uuid, cert.pdf_url, datetime.now().isoformat()
            ))
            await db.commit()
            return cursor.lastrowid
    
    async def add_filtered_certificate(self, cert: Certificate) -> int:
        """Add certificate to filtered table"""
        async with aiosqlite.connect(self.db_path) as db:
            # First get the certificate id from main table
            cursor = await db.execute(
                "SELECT id FROM certificates WHERE uuid = ?",
                (cert.uuid,)
            )
            row = await cursor.fetchone()
            
            if row:
                cert_id = row[0]
                cursor = await db.execute("""
                    INSERT OR REPLACE INTO filtered_certificates 
                    (certificate_id, document_id, document_number, status, issue_date,
                     inserted_date, organization_name, address, stir, expiry_date,
                     activity_type, uuid, pdf_url, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cert_id, cert.document_id, cert.document_number, cert.status,
                    cert.issue_date, cert.inserted_date, cert.organization_name,
                    cert.address, cert.stir, cert.expiry_date, cert.activity_type,
                    cert.uuid, cert.pdf_url, datetime.now().isoformat()
                ))
                await db.commit()
                
                # Update is_filtered flag in main table
                await db.execute(
                    "UPDATE certificates SET is_filtered = 1 WHERE id = ?",
                    (cert_id,)
                )
                await db.commit()
                
                return cursor.lastrowid
            return 0
    
    async def get_certificate_by_uuid(self, uuid: str) -> Optional[Certificate]:
        """Get certificate by UUID"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM certificates WHERE uuid = ?",
                (uuid,)
            )
            row = await cursor.fetchone()
            
            if row:
                return Certificate(
                    id=row[0],
                    document_id=row[1],
                    document_number=row[2],
                    status=row[3],
                    issue_date=row[4],
                    inserted_date=row[5],
                    organization_name=row[6],
                    address=row[7],
                    stir=row[8],
                    expiry_date=row[9],
                    activity_type=row[10],
                    uuid=row[11],
                    pdf_url=row[12],
                    created_at=row[13],
                    updated_at=row[14],
                    is_filtered=bool(row[15])
                )
            return None
    
    async def get_all_certificates(self, limit: int = 100, offset: int = 0) -> List[Certificate]:
        """Get all certificates with pagination"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM certificates LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = await cursor.fetchall()
            
            certificates = []
            for row in rows:
                certificates.append(Certificate(
                    id=row[0],
                    document_id=row[1],
                    document_number=row[2],
                    status=row[3],
                    issue_date=row[4],
                    inserted_date=row[5],
                    organization_name=row[6],
                    address=row[7],
                    stir=row[8],
                    expiry_date=row[9],
                    activity_type=row[10],
                    uuid=row[11],
                    pdf_url=row[12],
                    created_at=row[13],
                    updated_at=row[14],
                    is_filtered=bool(row[15])
                ))
            return certificates
    
    async def get_filtered_certificates(self, limit: int = 100, offset: int = 0) -> List[Certificate]:
        """Get filtered certificates"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM filtered_certificates LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = await cursor.fetchall()
            
            certificates = []
            for row in rows:
                certificates.append(Certificate(
                    id=row[0],
                    document_id=row[2],
                    document_number=row[3],
                    status=row[4],
                    issue_date=row[5],
                    inserted_date=row[6],
                    organization_name=row[7],
                    address=row[8],
                    stir=row[9],
                    expiry_date=row[10],
                    activity_type=row[11],
                    uuid=row[12],
                    pdf_url=row[13],
                    created_at=row[14],
                    updated_at=row[15]
                ))
            return certificates
    
    async def get_certificates_by_activity_type(self, activity_type: str) -> List[Certificate]:
        """Get certificates by activity type"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM certificates WHERE activity_type LIKE ?",
                (f"%{activity_type}%",)
            )
            rows = await cursor.fetchall()
            
            certificates = []
            for row in rows:
                certificates.append(Certificate(
                    id=row[0],
                    document_id=row[1],
                    document_number=row[2],
                    status=row[3],
                    issue_date=row[4],
                    inserted_date=row[5],
                    organization_name=row[6],
                    address=row[7],
                    stir=row[8],
                    expiry_date=row[9],
                    activity_type=row[10],
                    uuid=row[11],
                    pdf_url=row[12],
                    created_at=row[13],
                    updated_at=row[14],
                    is_filtered=bool(row[15])
                ))
            return certificates
    
    async def count_certificates(self) -> int:
        """Count total certificates"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM certificates")
            row = await cursor.fetchone()
            return row[0]
    
    async def count_filtered_certificates(self) -> int:
        """Count filtered certificates"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM filtered_certificates")
            row = await cursor.fetchone()
            return row[0]
    
    async def update_stats(self, total: int = None, filtered: int = None):
        """Update scraping statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            if total is not None:
                await db.execute("""
                    INSERT INTO scraping_stats (total_certificates, last_scraped_at)
                    VALUES (?, ?)
                """, (total, datetime.now().isoformat()))
            
            if filtered is not None:
                await db.execute("""
                    INSERT INTO scraping_stats (filtered_certificates, last_filtered_at)
                    VALUES (?, ?)
                """, (filtered, datetime.now().isoformat()))
            
            await db.commit()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get scraping statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_filtered = 1 THEN 1 ELSE 0 END) as filtered
                FROM certificates
            """)
            row = await cursor.fetchone()
            
            return {
                'total_certificates': row[0] or 0,
                'filtered_certificates': row[1] or 0
            }
    
    async def clear_certificates(self):
        """Clear all certificates"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM certificates")
            await db.execute("DELETE FROM filtered_certificates")
            await db.commit()
    
    async def clear_filtered_certificates(self):
        """Clear filtered certificates"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM filtered_certificates")
            await db.execute("UPDATE certificates SET is_filtered = 0")
            await db.commit()
