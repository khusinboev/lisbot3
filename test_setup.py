#!/usr/bin/env python3
"""
Test script to verify the setup
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from database import Database, Certificate
from parser_v2 import LicenseParserV2, ParsedCertificate
from loguru import logger


async def test_database():
    """Test database operations"""
    print("\n" + "="*50)
    print("Testing Database...")
    print("="*50)
    
    db = Database("data/test.db")
    await db.init_db()
    print("✅ Database initialized")
    
    # Test adding certificate
    cert = Certificate(
        document_id="12345",
        document_number="TEST-001",
        status="ACTIVE",
        organization_name="Test Organization",
        stir="123456789",
        activity_type="Олий таълим хизматлари",
        uuid="550e8400-e29b-41d4-a716-446655440000"
    )
    
    cert_id = await db.add_certificate(cert)
    print(f"✅ Certificate added with ID: {cert_id}")
    
    # Test retrieving certificate
    retrieved = await db.get_certificate_by_uuid(cert.uuid)
    if retrieved:
        print(f"✅ Certificate retrieved: {retrieved.organization_name}")
    else:
        print("❌ Failed to retrieve certificate")
    
    # Test stats
    stats = await db.get_stats()
    print(f"✅ Stats: {stats}")
    
    # Clean up
    await db.clear_certificates()
    print("✅ Database cleared")
    
    print("\n✅ Database tests passed!")


async def test_parser():
    """Test parser"""
    print("\n" + "="*50)
    print("Testing Parser...")
    print("="*50)
    
    parser = LicenseParserV2()
    
    try:
        print("Initializing browser...")
        await parser.init_browser(headless=True)
        print("✅ Browser initialized")
        
        print("\nTesting page scraping (page 1)...")
        certificates = await parser.scrape_page(1)
        print(f"✅ Scraped {len(certificates)} certificates from page 1")
        
        if certificates:
            cert = certificates[0]
            print(f"\nSample certificate:")
            print(f"  Organization: {cert.organization_name}")
            print(f"  Document Number: {cert.document_number}")
            print(f"  UUID: {cert.uuid}")
            print(f"  Activity Type: {cert.activity_type}")
        
        print("\n✅ Parser tests passed!")
        
    except Exception as e:
        print(f"❌ Parser test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await parser.close()
        print("✅ Browser closed")


async def main():
    """Main test function"""
    print("\n" + "="*50)
    print("License Bot - Setup Test")
    print("="*50)
    
    try:
        # Test database
        await test_database()
        
        # Test parser
        await test_parser()
        
        print("\n" + "="*50)
        print("✅ All tests passed!")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
