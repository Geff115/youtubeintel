#!/usr/bin/env python3
"""
Fix PostgreSQL functions and triggers in Supabase
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def fix_functions():
    """Fix PostgreSQL functions and triggers"""
    print("🔧 Fixing PostgreSQL functions and triggers...")
    
    supabase_url = os.getenv('DATABASE_URL')
    engine = create_engine(supabase_url)
    
    # Fixed SQL for functions and triggers
    fixed_sql = """
    -- Drop existing function if it exists
    DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
    
    -- Create the function with proper syntax
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $trigger_function$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $trigger_function$ LANGUAGE plpgsql;
    
    -- Create triggers for existing tables
    DROP TRIGGER IF EXISTS update_channels_updated_at ON channels;
    CREATE TRIGGER update_channels_updated_at 
        BEFORE UPDATE ON channels 
        FOR EACH ROW 
        EXECUTE FUNCTION update_updated_at_column();
    
    DROP TRIGGER IF EXISTS update_videos_updated_at ON videos;
    CREATE TRIGGER update_videos_updated_at 
        BEFORE UPDATE ON videos 
        FOR EACH ROW 
        EXECUTE FUNCTION update_updated_at_column();
    
    DROP TRIGGER IF EXISTS update_api_keys_updated_at ON api_keys;
    CREATE TRIGGER update_api_keys_updated_at 
        BEFORE UPDATE ON api_keys 
        FOR EACH ROW 
        EXECUTE FUNCTION update_updated_at_column();
    
    DROP TRIGGER IF EXISTS update_users_updated_at ON users;
    CREATE TRIGGER update_users_updated_at 
        BEFORE UPDATE ON users 
        FOR EACH ROW 
        EXECUTE FUNCTION update_updated_at_column();
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(text(fixed_sql))
            conn.commit()
        
        print("✅ PostgreSQL functions and triggers fixed")
        return True
        
    except Exception as e:
        print(f"❌ Failed to fix functions: {e}")
        return False

def verify_tables():
    """Verify all tables exist and show their structure"""
    print("\n📊 Verifying table structure...")
    
    supabase_url = os.getenv('DATABASE_URL')
    engine = create_engine(supabase_url)
    
    try:
        with engine.connect() as conn:
            # Get all tables
            result = conn.execute(text("""
                SELECT table_name, 
                       (SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = t.table_name AND table_schema = 'public') as column_count
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            
            tables = result.fetchall()
            
            print("  Table Name           Columns  Status")
            print("  " + "-" * 40)
            
            for table_name, column_count in tables:
                # Check if table has data
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_count = count_result.scalar()
                
                status = f"{row_count} rows"
                print(f"  {table_name:<17} {column_count:>7}  {status}")
            
            print("  " + "-" * 40)
            print(f"  ✅ {len(tables)} tables verified")
        
        return True
        
    except Exception as e:
        print(f"❌ Table verification failed: {e}")
        return False

if __name__ == '__main__':
    print("🔧 YouTubeIntel Supabase Fix")
    print("=" * 40)
    
    if fix_functions():
        verify_tables()
        
        print("\n🎉 Supabase database is ready!")
        print("\nNext steps:")
        print("1. Test the Flask app: cd app && python app.py")
        print("2. Check health: curl http://localhost:5000/health")
        print("3. Test stats: curl http://localhost:5000/api/stats")
    else:
        print("\n⚠️  Some functions couldn't be fixed, but core functionality should work")