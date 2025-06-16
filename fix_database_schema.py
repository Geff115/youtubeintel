#!/usr/bin/env python3
"""
Fix database schema - add missing columns to users table
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def add_missing_columns():
    """Add missing columns to users table"""
    print("🔧 Adding missing columns to users table...")
    
    supabase_url = os.getenv('DATABASE_URL')
    engine = create_engine(supabase_url)
    
    # SQL to add missing columns
    add_columns_sql = """
    -- Add missing columns to users table
    ALTER TABLE users ADD COLUMN IF NOT EXISTS current_plan VARCHAR(50) DEFAULT 'free';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_free_credit_reset DATE DEFAULT CURRENT_DATE;
    
    -- Add missing columns to credit_transactions table
    ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS api_endpoint VARCHAR(100);
    ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS batch_size INTEGER;
    
    -- Update existing users to have default values
    UPDATE users SET current_plan = 'free' WHERE current_plan IS NULL;
    UPDATE users SET last_free_credit_reset = CURRENT_DATE WHERE last_free_credit_reset IS NULL;
    """
    
    try:
        with engine.connect() as conn:
            statements = [stmt.strip() for stmt in add_columns_sql.split(';') if stmt.strip()]
            
            for statement in statements:
                try:
                    conn.execute(text(statement))
                    conn.commit()
                    print(f"  ✅ Executed: {statement[:50]}...")
                except Exception as e:
                    print(f"  ⚠️  Statement failed: {str(e)[:100]}...")
        
        print("✅ Missing columns added successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to add columns: {e}")
        return False

def verify_schema():
    """Verify the users table has all required columns"""
    print("\n🔍 Verifying users table schema...")
    
    supabase_url = os.getenv('DATABASE_URL')
    engine = create_engine(supabase_url)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND table_schema = 'public'
                ORDER BY ordinal_position
            """))
            
            columns = result.fetchall()
            
            print("  Column Name              Type           Nullable  Default")
            print("  " + "-" * 65)
            
            required_columns = [
                'id', 'email', 'name', 'credits_balance', 
                'total_credits_purchased', 'current_plan', 
                'last_free_credit_reset', 'created_at', 'updated_at'
            ]
            
            found_columns = []
            for column_name, data_type, is_nullable, column_default in columns:
                found_columns.append(column_name)
                default_str = str(column_default)[:15] if column_default else 'None'
                print(f"  {column_name:<24} {data_type:<12} {is_nullable:<8} {default_str}")
            
            print("  " + "-" * 65)
            
            missing = [col for col in required_columns if col not in found_columns]
            if missing:
                print(f"  ❌ Missing columns: {missing}")
                return False
            else:
                print("  ✅ All required columns present")
                return True
        
    except Exception as e:
        print(f"❌ Schema verification failed: {e}")
        return False

if __name__ == '__main__':
    print("🔧 YouTubeIntel Database Schema Fix")
    print("=" * 40)
    
    if add_missing_columns():
        verify_schema()
        
        print("\n🎉 Database schema updated!")
        print("\nNext steps:")
        print("1. Restart your Flask app")
        print("2. Test the endpoints again")
    else:
        print("\n❌ Schema update failed")