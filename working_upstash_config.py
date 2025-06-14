
def get_upstash_config(upstash_url, upstash_token):
    """Get UPSTASH specific configuration - working config for new database"""
    
    # Extract hostname and port from URL
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    if ':' in hostname:
        host, port = hostname.split(':')
        port = int(port)
    else:
        host = hostname
        port = 6379
    
    return {
        'host': host,
        'port': port,
        'password': upstash_token,
        'ssl': True,         'decode_responses': True
    }
