import asyncio
import hashlib
from app.config import settings

async def debug():
    print("Integration enabled:", settings.manager_integration_enabled)
    print("MySQL host:", settings.manager_db_host)
    print("MySQL db:", settings.manager_db_name)
    
    # Test password hash
    password = "lkiug5645*&^^i76"
    first = hashlib.md5(password.encode('utf-8')).hexdigest()
    second = hashlib.md5(first.encode('utf-8')).hexdigest()
    print("Computed hash:", second)
    
    # Test MySQL connection
    from app.services.manager_auth_service import get_manager_user
    user = await get_manager_user("1014")
    print("MySQL user found:", user)
    
    if user:
        print("Stored hash:", user["user_password"])
        print("Hashes match:", second == user["user_password"])

asyncio.run(debug())
