#!/usr/bin/env python3
"""
Migrate database schema and data from local PostgreSQL to Supabase
"""

import os
import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
from dotenv import load_dotenv
from datetime import datetime
import uuid

# Load environment variables
load_dotenv()

def test_connections():
    """Test both local and Supabase connections"""
    print("🔍 Testing database connections...")
    
    # Test local connection
    local_url = "postgresql://youtube:youtube123@localhost:5432/youtube_channels"
    try:
        local_engine = create_engine(local_url)
        with local_engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM channels"))
            local_count = result.scalar()
        print(f"✅ Local PostgreSQL: Connected ({local_count} channels)")
        local_available = True
    except Exception as e:
        print(f"⚠️  Local PostgreSQL: {e}")
        local_available = False
    
    # Test Supabase connection
    supabase_url = os.getenv('DATABASE_URL')
    try:
        supabase_engine = create_engine(supabase_url)
        with supabase_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Supabase: Connected")
        supabase_available = True
    except Exception as e:
        print(f"❌ Supabase: {e}")
        supabase_available = False
    
    return local_available, supabase_available

def migrate_schema():
    """Run schema migration on Supabase"""
    print("\n🏗️  Migrating schema to Supabase...")
    
    supabase_url = os.getenv('DATABASE_URL')
    
    try:
        engine = create_engine(supabase_url)
        
        # Read and execute init.sql
        with open('init.sql', 'r') as f:
            schema_sql = f.read()
        
        with engine.connect() as conn:
            # Split SQL into individual statements and execute
            statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements):
                try:
                    conn.execute(text(statement))
                    conn.commit()
                    print(f"  ✅ Executed statement {i+1}/{len(statements)}")
                except Exception as e:
                    # Some statements might fail if they already exist
                    if "already exists" in str(e).lower():
                        print(f"  ⚠️  Statement {i+1} (already exists): {str(e)[:100]}...")
                    else:
                        print(f"  ❌ Statement {i+1} failed: {str(e)[:100]}...")
        
        # Verify tables were created
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
        
        expected_tables = ['channels', 'videos', 'api_keys', 'processing_jobs', 'channel_discoveries']
        missing_tables = [table for table in expected_tables if table not in tables]
        
        if missing_tables:
            print(f"  ⚠️  Missing tables: {missing_tables}")
        else:
            print("  ✅ All required tables created")
        
        print(f"  📊 Tables in Supabase: {', '.join(tables)}")
        print("✅ Schema migration completed")
        return True
        
    except Exception as e:
        print(f"❌ Schema migration failed: {e}")
        return False

def migrate_data():
    """Migrate existing data from local to Supabase"""
    print("\n📦 Migrating data to Supabase...")
    
    local_url = "postgresql://youtube:youtube123@localhost:5432/youtube_channels"
    supabase_url = os.getenv('DATABASE_URL')
    
    try:
        local_engine = create_engine(local_url)
        supabase_engine = create_engine(supabase_url)
        
        # Tables to migrate (in order due to foreign key dependencies)
        tables = ['api_keys', 'channels', 'videos', 'processing_jobs', 'channel_discoveries']
        
        total_migrated = 0
        
        for table in tables:
            print(f"\n  📋 Migrating {table}...")
            
            try:
                # Get data from local database
                with local_engine.connect() as local_conn:
                    result = local_conn.execute(text(f"SELECT * FROM {table}"))
                    rows = result.fetchall()
                    columns = list(result.keys())
                
                if not rows:
                    print(f"    ℹ️  No data in {table}")
                    continue
                
                # Insert into Supabase
                with supabase_engine.connect() as supabase_conn:
                    # Clear existing data (for fresh migration)
                    supabase_conn.execute(text(f"DELETE FROM {table}"))
                    supabase_conn.commit()
                    
                    # Prepare INSERT statement
                    columns_str = ', '.join(columns)
                    placeholders = ', '.join([f':{col}' for col in columns])
                    insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
                    
                    # Insert rows in batches
                    batch_size = 100
                    for i in range(0, len(rows), batch_size):
                        batch = rows[i:i + batch_size]
                        
                        for row in batch:
                            row_dict = dict(zip(columns, row))
                            supabase_conn.execute(text(insert_sql), row_dict)
                        
                        supabase_conn.commit()
                        print(f"    ✅ Migrated {min(i + batch_size, len(rows))}/{len(rows)} rows")
                
                total_migrated += len(rows)
                print(f"    ✅ {table}: {len(rows)} rows migrated")
                
            except Exception as e:
                print(f"    ❌ Failed to migrate {table}: {e}")
                continue
        
        print(f"\n✅ Data migration completed: {total_migrated} total rows migrated")
        return True
        
    except Exception as e:
        print(f"❌ Data migration failed: {e}")
        return False

def verify_migration():
    """Verify the migration was successful"""
    print("\n🔍 Verifying migration...")
    
    local_url = "postgresql://youtube:youtube123@localhost:5432/youtube_channels"
    supabase_url = os.getenv('DATABASE_URL')
    
    try:
        local_engine = create_engine(local_url)
        supabase_engine = create_engine(supabase_url)
        
        tables = ['api_keys', 'channels', 'videos', 'processing_jobs', 'channel_discoveries']
        
        print("  📊 Row count comparison:")
        print("  " + "-" * 50)
        print("  Table               Local    Supabase")
        print("  " + "-" * 50)
        
        all_match = True
        
        for table in tables:
            try:
                # Local count
                with local_engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    local_count = result.scalar()
            except:
                local_count = 0
            
            try:
                # Supabase count
                with supabase_engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    supabase_count = result.scalar()
            except:
                supabase_count = 0
            
            match = "✅" if local_count == supabase_count else "❌"
            if local_count != supabase_count:
                all_match = False
            
            print(f"  {table:<17} {local_count:>7} {supabase_count:>9} {match}")
        
        print("  " + "-" * 50)
        
        if all_match:
            print("  ✅ All tables match perfectly!")
        else:
            print("  ⚠️  Some discrepancies found")
        
        return all_match
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def add_new_columns():
    """Add new columns for credit system and user management"""
    print("\n🆕 Adding new columns for credit system...")
    
    supabase_url = os.getenv('DATABASE_URL')
    
    try:
        engine = create_engine(supabase_url)
        
        # SQL for new tables and columns
        new_schema_sql = """
        -- Users table for credit system
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255),
            credits_balance INTEGER DEFAULT 25,
            total_credits_purchased INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Credit transactions table
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            transaction_type VARCHAR(20) NOT NULL,
            credits_amount INTEGER NOT NULL,
            payment_reference VARCHAR(255),
            amount_usd FLOAT,
            description VARCHAR(500),
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON credit_transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_credit_transactions_reference ON credit_transactions(payment_reference);
        CREATE INDEX IF NOT EXISTS idx_credit_transactions_status ON credit_transactions(status);

        -- Update trigger for users table
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';

        CREATE TRIGGER IF NOT EXISTS update_users_updated_at 
        BEFORE UPDATE ON users 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
        
        with engine.connect() as conn:
            statements = [stmt.strip() for stmt in new_schema_sql.split(';') if stmt.strip()]
            
            for statement in statements:
                try:
                    conn.execute(text(statement))
                    conn.commit()
                except Exception as e:
                    if "already exists" in str(e).lower():
                        continue
                    else:
                        print(f"  ⚠️  Error: {str(e)[:100]}...")
        
        print("  ✅ Credit system tables created")
        return True
        
    except Exception as e:
        print(f"❌ Failed to add new tables: {e}")
        return False

def main():
    """Main migration function"""
    print("🚀 YouTubeIntel Database Migration to Supabase")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Step 1: Test connections
    local_available, supabase_available = test_connections()
    
    if not supabase_available:
        print("\n❌ Cannot proceed without Supabase connection")
        sys.exit(1)
    
    # Step 2: Migrate schema
    if migrate_schema():
        # Step 3: Add new tables for credit system
        add_new_columns()
        
        # Step 4: Migrate data (only if local is available)
        if local_available:
            if migrate_data():
                # Step 5: Verify migration
                verify_migration()
            else:
                print("\n⚠️  Data migration failed, but schema is ready")
        else:
            print("\n⚠️  No local database found - schema created, no data to migrate")
    else:
        print("\n❌ Schema migration failed")
        sys.exit(1)
    
    print(f"\n🎉 Migration completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n📋 Next steps:")
    print("1. Update app configuration to use Supabase")
    print("2. Test API endpoints: python -m pytest tests/")
    print("3. Start the application: ./start_production.sh")
    print("4. Test a few API calls to verify everything works")

if __name__ == '__main__':
    main()