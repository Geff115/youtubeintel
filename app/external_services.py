import requests
import time
import logging
import random
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin, urlparse
from models import APIKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

logger = logging.getLogger(__name__)

class ExternalChannelDiscovery:
    def __init__(self):
        self.setup_database()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def setup_database(self):
        """Setup database connection for API key management"""
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost/youtube_channels?schema=public')
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")
        logger.info(f"Connecting to database at {DATABASE_URL}")
        # Create engine and session
        self.engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db_session = SessionLocal()
    
    def get_api_key(self, service_name: str) -> Optional[str]:
        """Get API key for external service"""
        api_key_obj = self.db_session.query(APIKey).filter(
            APIKey.service == service_name,
            APIKey.is_active == True
        ).first()
        
        if api_key_obj and api_key_obj.can_use():
            return api_key_obj.api_key
        return None
    
    def discover_channels(self, channel_id: str, method: str = 'related_channels') -> List[Dict]:
        """Main method to discover related channels using various methods"""
        try:
            if method == 'related_channels':
                return self.discover_via_socialblade(channel_id)
            elif method == 'similar_content':
                return self.discover_via_content_similarity(channel_id)
            elif method == 'noxinfluencer':
                return self.discover_via_noxinfluencer(channel_id)
            elif method == 'channelcrawler':
                return self.discover_via_channelcrawler(channel_id)
            else:
                logger.warning(f"Unknown discovery method: {method}")
                return []
        except Exception as e:
            logger.error(f"Discovery method {method} failed for channel {channel_id}: {str(e)}")
            return []
    
    def discover_via_socialblade(self, channel_id: str) -> List[Dict]:
        """Discover channels via SocialBlade similar channels"""
        try:
            url = f"https://socialblade.com/youtube/channel/{channel_id}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for similar channels section
            similar_channels = []
            
            # Find channel links in similar channels section
            channel_links = soup.find_all('a', href=re.compile(r'/youtube/channel/'))
            
            for link in channel_links[:10]:  # Limit to first 10
                href = link.get('href', '')
                match = re.search(r'/youtube/channel/([A-Za-z0-9_-]+)', href)
                if match:
                    found_channel_id = match.group(1)
                    if found_channel_id != channel_id:  # Don't include the source channel
                        title = link.get_text(strip=True)
                        
                        similar_channels.append({
                            'channel_id': found_channel_id,
                            'title': title,
                            'service': 'socialblade',
                            'confidence': 0.7,
                            'discovery_method': 'related_channels'
                        })
            
            logger.info(f"SocialBlade found {len(similar_channels)} similar channels for {channel_id}")
            return similar_channels
            
        except Exception as e:
            logger.error(f"SocialBlade discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_content_similarity(self, channel_id: str) -> List[Dict]:
        """Discover channels via content similarity using web scraping"""
        try:
            # Use YouTube's channel page to find featured/related channels
            url = f"https://www.youtube.com/channel/{channel_id}/channels"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse the page for channel data
            content = response.text
            similar_channels = []
            
            # Look for channel IDs in the page content
            channel_pattern = r'UC[a-zA-Z0-9_-]{22}'
            found_channels = re.findall(channel_pattern, content)
            
            # Remove duplicates and source channel
            unique_channels = list(set(found_channels))
            if channel_id in unique_channels:
                unique_channels.remove(channel_id)
            
            for found_channel_id in unique_channels[:8]:  # Limit results
                similar_channels.append({
                    'channel_id': found_channel_id,
                    'title': '',  # Title will be fetched later
                    'service': 'youtube_scraping',
                    'confidence': 0.6,
                    'discovery_method': 'similar_content'
                })
            
            logger.info(f"Content similarity found {len(similar_channels)} channels for {channel_id}")
            return similar_channels
            
        except Exception as e:
            logger.error(f"Content similarity discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_noxinfluencer(self, channel_id: str) -> List[Dict]:
        """Discover channels via NoxInfluencer API or scraping"""
        try:
            # Check if we have API key for NoxInfluencer
            api_key = self.get_api_key('noxinfluencer')
            
            if api_key:
                return self.discover_via_noxinfluencer_api(channel_id, api_key)
            else:
                return self.discover_via_noxinfluencer_scraping(channel_id)
                
        except Exception as e:
            logger.error(f"NoxInfluencer discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_noxinfluencer_api(self, channel_id: str, api_key: str) -> List[Dict]:
        """Use NoxInfluencer API for channel discovery"""
        try:
            # This is a placeholder - implement actual NoxInfluencer API calls
            # when you have access to their API documentation
            url = f"https://api.noxinfluencer.com/v1/youtube/similar-channels"
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'channel_id': channel_id,
                'limit': 10
            }
            
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            similar_channels = []
            
            for channel in data.get('similar_channels', []):
                similar_channels.append({
                    'channel_id': channel['channel_id'],
                    'title': channel.get('title', ''),
                    'service': 'noxinfluencer_api',
                    'confidence': channel.get('similarity_score', 0.5),
                    'discovery_method': 'related_channels'
                })
            
            return similar_channels
            
        except Exception as e:
            logger.error(f"NoxInfluencer API discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_noxinfluencer_scraping(self, channel_id: str) -> List[Dict]:
        """Scrape NoxInfluencer for similar channels"""
        try:
            url = f"https://noxinfluencer.com/youtube/channel/{channel_id}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            similar_channels = []
            
            # Look for similar channels section
            similar_section = soup.find('div', {'class': re.compile(r'similar.*channel', re.I)})
            
            if similar_section:
                channel_links = similar_section.find_all('a', href=re.compile(r'/youtube/channel/'))
                
                for link in channel_links[:8]:
                    href = link.get('href', '')
                    match = re.search(r'/youtube/channel/([A-Za-z0-9_-]+)', href)
                    if match:
                        found_channel_id = match.group(1)
                        if found_channel_id != channel_id:
                            title = link.get_text(strip=True)
                            
                            similar_channels.append({
                                'channel_id': found_channel_id,
                                'title': title,
                                'service': 'noxinfluencer_scraping',
                                'confidence': 0.6,
                                'discovery_method': 'related_channels'
                            })
            
            logger.info(f"NoxInfluencer scraping found {len(similar_channels)} channels for {channel_id}")
            return similar_channels
            
        except Exception as e:
            logger.error(f"NoxInfluencer scraping failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_channelcrawler(self, channel_id: str) -> List[Dict]:
        """Discover channels via ChannelCrawler service"""
        try:
            api_key = self.get_api_key('channelcrawler')
            
            if not api_key:
                logger.warning("No API key available for ChannelCrawler")
                return []
            
            # This is a placeholder for ChannelCrawler API
            # Replace with actual API endpoint and parameters
            url = "https://api.channelcrawler.com/v1/similar-channels"
            
            headers = {
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'channel_id': channel_id,
                'max_results': 10
            }
            
            response = self.session.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            similar_channels = []
            
            for channel in data.get('channels', []):
                similar_channels.append({
                    'channel_id': channel['id'],
                    'title': channel.get('name', ''),
                    'service': 'channelcrawler',
                    'confidence': channel.get('score', 0.5),
                    'discovery_method': 'similar_content'
                })
            
            logger.info(f"ChannelCrawler found {len(similar_channels)} channels for {channel_id}")
            return similar_channels
            
        except Exception as e:
            logger.error(f"ChannelCrawler discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_keyword_search(self, channel_id: str, keywords: List[str]) -> List[Dict]:
        """Discover channels by searching for similar keywords"""
        try:
            from youtube_service import YouTubeService
            
            youtube_service = YouTubeService()
            similar_channels = []
            
            # Use top keywords to search for similar channels
            for keyword in keywords[:3]:  # Limit to top 3 keywords
                try:
                    search_results = youtube_service.search_channels(keyword, max_results=5)
                    
                    for result in search_results:
                        if result['channel_id'] != channel_id:  # Don't include source channel
                            similar_channels.append({
                                'channel_id': result['channel_id'],
                                'title': result['title'],
                                'service': 'youtube_search',
                                'confidence': 0.4,  # Lower confidence for keyword-based discovery
                                'discovery_method': 'keyword_search',
                                'search_keyword': keyword
                            })
                    
                    # Rate limiting
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Keyword search failed for '{keyword}': {str(e)}")
                    continue
            
            # Remove duplicates
            unique_channels = {}
            for channel in similar_channels:
                channel_id_key = channel['channel_id']
                if channel_id_key not in unique_channels:
                    unique_channels[channel_id_key] = channel
            
            result = list(unique_channels.values())
            logger.info(f"Keyword search found {len(result)} unique channels")
            return result
            
        except Exception as e:
            logger.error(f"Keyword-based discovery failed for {channel_id}: {str(e)}")
            return []
    
    def rate_limit_delay(self, service_name: str):
        """Apply appropriate rate limiting for different services"""
        delays = {
            'socialblade': random.uniform(2, 4),
            'noxinfluencer': random.uniform(3, 6),
            'channelcrawler': random.uniform(1, 2),
            'youtube_scraping': random.uniform(2, 5)
        }
        
        delay = delays.get(service_name, 2)
        time.sleep(delay)
    
    def validate_external_service(self, service_name: str, api_key: str) -> bool:
        """Validate external service API key"""
        try:
            if service_name == 'noxinfluencer':
                # Test NoxInfluencer API
                url = "https://api.noxinfluencer.com/v1/test"
                headers = {'Authorization': f'Bearer {api_key}'}
                response = self.session.get(url, headers=headers, timeout=10)
                return response.status_code == 200
            
            elif service_name == 'channelcrawler':
                # Test ChannelCrawler API
                url = "https://api.channelcrawler.com/v1/status"
                headers = {'X-API-Key': api_key}
                response = self.session.get(url, headers=headers, timeout=10)
                return response.status_code == 200
            
            else:
                logger.warning(f"Validation not implemented for service: {service_name}")
                return False
                
        except Exception as e:
            logger.error(f"Service validation failed for {service_name}: {str(e)}")
            return False
    
    def close(self):
        """Close database session"""
        if hasattr(self, 'db_session'):
            self.db_session.close()
        
        if hasattr(self, 'session'):
            self.session.close()

class ContentAnalyzer:
    """Analyze channel content for similarity matching"""
    
    def __init__(self):
        pass
    
    def extract_keywords_from_description(self, description: str) -> List[str]:
        """Extract keywords from channel description"""
        if not description:
            return []
        
        # Simple keyword extraction - can be enhanced with NLP libraries
        import re
        
        # Remove common words and extract meaningful terms
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
            'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        # Extract words (letters and numbers)
        words = re.findall(r'\b[a-zA-Z]+\b', description.lower())
        
        # Filter out stop words and short words
        keywords = [word for word in words if len(word) > 3 and word not in stop_words]
        
        # Return top keywords by frequency
        from collections import Counter
        word_counts = Counter(keywords)
        
        return [word for word, count in word_counts.most_common(10)]
    
    def calculate_content_similarity(self, channel1_data: Dict, channel2_data: Dict) -> float:
        """Calculate similarity score between two channels"""
        similarity_score = 0.0
        
        # Compare categories/topics
        topics1 = set(channel1_data.get('topic_categories', []))
        topics2 = set(channel2_data.get('topic_categories', []))
        
        if topics1 and topics2:
            topic_similarity = len(topics1.intersection(topics2)) / len(topics1.union(topics2))
            similarity_score += topic_similarity * 0.4
        
        # Compare keywords
        keywords1 = set(channel1_data.get('keywords', []))
        keywords2 = set(channel2_data.get('keywords', []))
        
        if keywords1 and keywords2:
            keyword_similarity = len(keywords1.intersection(keywords2)) / len(keywords1.union(keywords2))
            similarity_score += keyword_similarity * 0.3
        
        # Compare subscriber counts (similar scale)
        subs1 = channel1_data.get('subscriber_count', 0)
        subs2 = channel2_data.get('subscriber_count', 0)
        
        if subs1 > 0 and subs2 > 0:
            # Normalize subscriber difference
            max_subs = max(subs1, subs2)
            min_subs = min(subs1, subs2)
            sub_similarity = min_subs / max_subs
            
            # Give more weight to channels with similar subscriber counts
            if sub_similarity > 0.1:  # Within an order of magnitude
                similarity_score += sub_similarity * 0.2
        
        # Compare language
        if (channel1_data.get('language') and channel2_data.get('language') and 
            channel1_data['language'] == channel2_data['language']):
            similarity_score += 0.1
        
        return min(similarity_score, 1.0)  # Cap at 1.0