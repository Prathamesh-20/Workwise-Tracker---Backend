import asyncio
import asyncpg
import sys
import json

# Database URL provided by user
DB_URL = "postgresql://postgres:PUxQEEpdqaNmkNUWstZmfQkonciOrTBb@metro.proxy.rlwy.net:38403/railway"

# SQL Query provided by user
QUERY = """
SELECT 
    is_idle,
    COUNT(*) as snapshot_count,
    COUNT(*) * 5 as total_seconds,
    COUNT(*) * 5 / 60 as total_minutes
FROM desktop_activity_logs 
WHERE user_id = (SELECT id FROM users WHERE email = 'dhurba@autonex.com')
AND timestamp::date = CURRENT_DATE
GROUP BY is_idle;
"""

async def run_query():
    try:
        # Connect to the database
        conn = await asyncpg.connect(DB_URL)
        
        # Execute query
        rows = await conn.fetch(QUERY)
        await conn.close()
        
        results = []
        for row in rows:
            # Convert row to dict and handle non-serializable types if any (though here they are simple)
            results.append(dict(row))
            
        # Write to file
        with open("query_results.json", "w") as f:
            # Convert Decimal/Date to string for JSON serialization if needed
            # Here we have bool, int, int, numeric (Decimal?)
            # Helper for JSON serialization
            def default_serializer(obj):
                import decimal
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                return str(obj)
                
            json.dump(results, f, indent=2, default=default_serializer)
            
        # Print to stdout for verify
        print(json.dumps(results, indent=2, default=default_serializer))

    except Exception as e:
        print(f"Error executing query: {e}")
        with open("query_error.txt", "w") as f:
            f.write(str(e))

if __name__ == "__main__":
    asyncio.run(run_query())
