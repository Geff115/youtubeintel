import requests
import time
import logging
import random
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin, urlparse
from app.models import APIKey
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
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/youtube_channels')
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
            elif method == 'youtube_featured':
                return self.discover_via_youtube_featured_channels(channel_id)
            elif method == 'youtube_collaborations':
                return self.discover_via_youtube_collaborations(channel_id)
            elif method == 'keyword_search':
                # This requires additional context, so we'll get keywords from the channel first
                return self.discover_via_smart_keyword_search(channel_id)
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
        """Discover channels via NoxInfluencer scraping only (no public API available)"""
        try:
            return self.discover_via_noxinfluencer_scraping(channel_id)
                
        except Exception as e:
            logger.error(f"NoxInfluencer discovery failed for {channel_id}: {str(e)}")
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
        """ChannelCrawler service doesn't have public API - use alternative methods"""
        try:
            # Since ChannelCrawler doesn't offer public API, we'll use 
            # YouTube's own featured channels and community tab
            return self.discover_via_youtube_featured_channels(channel_id)
            
        except Exception as e:
            logger.error(f"Alternative channel discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_keyword_search(self, channel_id: str, keywords: List[str]) -> List[Dict]:
        """Discover channels by searching for similar keywords"""
        try:
            from app.youtube_service import YouTubeService
            
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
    
    def discover_via_youtube_featured_channels(self, channel_id: str) -> List[Dict]:
        """Discover channels via YouTube's featured channels section"""
        try:
            from app.youtube_service import YouTubeService
            youtube_service = YouTubeService()
            
            # Get featured channels using YouTube API
            featured_channels = youtube_service.get_related_channels(channel_id)
            
            similar_channels = []
            for featured_channel_id in featured_channels:
                if featured_channel_id != channel_id:
                    similar_channels.append({
                        'channel_id': featured_channel_id,
                        'title': '',  # Will be filled later
                        'service': 'youtube_featured',
                        'confidence': 0.8,  # High confidence for featured channels
                        'discovery_method': 'youtube_featured'
                    })
            
            logger.info(f"YouTube featured channels found {len(similar_channels)} channels for {channel_id}")
            return similar_channels
            
        except Exception as e:
            logger.error(f"YouTube featured channels discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_youtube_collaborations(self, channel_id: str) -> List[Dict]:
        """Discover channels by analyzing video collaborations and mentions"""
        try:
            from app.youtube_service import YouTubeService
            youtube_service = YouTubeService()
            
            # Get recent videos for the channel
            videos = youtube_service.get_channel_videos(channel_id, max_results=20)
            
            collaboration_channels = []
            channel_pattern = r'UC[a-zA-Z0-9_-]{22}'
            
            for video in videos:
                # Look for channel mentions in video descriptions
                description = video.get('description', '')
                if description:
                    # Find channel IDs in description
                    found_channels = re.findall(channel_pattern, description)
                    for found_channel_id in found_channels:
                        if found_channel_id != channel_id:
                            collaboration_channels.append({
                                'channel_id': found_channel_id,
                                'title': '',
                                'service': 'youtube_collaboration',
                                'confidence': 0.6,
                                'discovery_method': 'youtube_collaborations',
                                'source_video': video.get('video_id', '')
                            })
                
                # Look for @mentions in titles and descriptions
                mention_pattern = r'@([a-zA-Z0-9_-]+)'
                text = f"{video.get('title', '')} {description}"
                mentions = re.findall(mention_pattern, text)
                
                for mention in mentions:
                    # Try to resolve @mention to channel ID
                    try:
                        resolved_channel_id = youtube_service.get_channel_by_username(mention)
                        if resolved_channel_id and resolved_channel_id != channel_id:
                            collaboration_channels.append({
                                'channel_id': resolved_channel_id,
                                'title': f'@{mention}',
                                'service': 'youtube_mention',
                                'confidence': 0.5,
                                'discovery_method': 'youtube_collaborations',
                                'source_video': video.get('video_id', '')
                            })
                    except:
                        continue
            
            # Remove duplicates
            unique_channels = {}
            for channel in collaboration_channels:
                channel_key = channel['channel_id']
                if channel_key not in unique_channels:
                    unique_channels[channel_key] = channel
            
            result = list(unique_channels.values())[:10]  # Limit to 10
            logger.info(f"YouTube collaborations found {len(result)} channels for {channel_id}")
            return result
            
        except Exception as e:
            logger.error(f"YouTube collaborations discovery failed for {channel_id}: {str(e)}")
            return []
    
    def discover_via_smart_keyword_search(self, channel_id: str) -> List[Dict]:
        """Discover channels using intelligent keyword search based on channel content"""
        try:
            # First, get channel metadata to extract keywords
            session = self.get_db_session()
            from app.models import Channel
            
            channel = session.query(Channel).filter_by(channel_id=channel_id).first()
            if not channel:
                logger.warning(f"Channel {channel_id} not found in database")
                return []
            
            # Extract keywords from channel data
            keywords = []
            
            # Use existing keywords if available
            if channel.keywords:
                keywords.extend(channel.keywords[:3])
            
            # Extract from description
            if channel.description:
                content_keywords = self.extract_smart_keywords(channel.description)
                keywords.extend(content_keywords[:3])
            
            # Use topic categories
            if channel.topic_categories:
                # Convert topic URLs to searchable terms
                for topic in channel.topic_categories[:2]:
                    if '/m/' in topic:
                        # Extract readable topic name from Google's topic URLs
                        topic_name = topic.split('/')[-1].replace('_', ' ')
                        keywords.append(topic_name)
            
            # Fallback: use channel title words
            if not keywords and channel.title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', channel.title.lower())
                keywords.extend(title_words[:2])
            
            session.close()
            
            if not keywords:
                logger.warning(f"No keywords found for channel {channel_id}")
                return []
            
            # Search for channels using these keywords
            return self.discover_via_keyword_search(channel_id, keywords[:3])
            
        except Exception as e:
            logger.error(f"Smart keyword search failed for {channel_id}: {str(e)}")
            return []
    
    def extract_smart_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text using simple NLP"""
        if not text:
            return []
        
        # Clean and normalize text
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # Extended stop words
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
            'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our',
            'their', 'myself', 'yourself', 'himself', 'herself', 'ourselves',
            'themselves', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
            'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'now', 'here', 'there', 'then', 'once',
            'youtube', 'channel', 'video', 'subscribe', 'like', 'comment',
            'please', 'thanks', 'thank', 'welcome', 'new', 'latest', 'best'
        }
        
        # Filter meaningful words
        meaningful_words = []
        for word in words:
            if (len(word) > 3 and 
                word not in stop_words and 
                not word.isdigit() and 
                word.isalpha()):
                meaningful_words.append(word)
        
        # Count frequency and return most common
        from collections import Counter
        word_counts = Counter(meaningful_words)
        
        return [word for word, count in word_counts.most_common(8)]
    
    def get_db_session(self):
        """Get a new database session"""
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        return SessionLocal()
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