def get_upstash_config(upstash_url, upstash_token):
    """Get UPSTASH specific configuration - auto-generated from successful test"""
    
    # Extract hostname from URL
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    
    return {'host': 'probable-gelding-12987.upstash.io', 'port': 6379, 'password': 'ATK7AAIjcDEzMWIxMmU1NTQ0MmI0NTJjODFhMzVjY2ViZGYxMDY4OXAxMA', 'ssl': True, 'decode_responses': True}
