import os
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import random
import time
from typing import List, Dict, Optional
from app.models import APIKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self):
        self.service = None
        self.current_api_key = None
        self.setup_database()
    
    def setup_database(self):
        """Setup database connection for API key management"""
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost/youtube_channels?schema=public')
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")
        logger.info(f"Connecting to database: {DATABASE_URL}")
        # Create engine and session
        self.engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db_session = SessionLocal()
    
    def get_available_api_key(self) -> Optional[APIKey]:
        """Get an available YouTube API key with quota remaining"""
        available_keys = self.db_session.query(APIKey).filter(
            APIKey.service == 'youtube',
            APIKey.is_active == True,
            APIKey.quota_used < APIKey.quota_limit
        ).order_by(APIKey.quota_used.asc()).all()
        
        if not available_keys:
            logger.error("No available YouTube API keys with quota remaining")
            return None
        
        # Return the key with lowest usage
        return available_keys[0]
    
    def get_youtube_service(self):
        """Get YouTube API service with automatic key rotation"""
        if not self.service or not self.current_api_key or not self.current_api_key.can_use():
            api_key = self.get_available_api_key()
            if not api_key:
                raise Exception("No available YouTube API keys")
            
            try:
                self.service = build('youtube', 'v3', developerKey=api_key.api_key)
                self.current_api_key = api_key
                logger.info(f"Using YouTube API key: {api_key.key_name}")
            except Exception as e:
                logger.error(f"Failed to initialize YouTube service with key {api_key.key_name}: {str(e)}")
                api_key.error_count += 1
                if api_key.error_count >= 5:
                    api_key.is_active = False
                self.db_session.commit()
                raise
        
        return self.service
    
    def handle_api_call(self, api_call_func, quota_cost=1):
        """Handle API call with error handling and quota management"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                service = self.get_youtube_service()
                result = api_call_func(service)
                
                # Update API key usage
                if self.current_api_key:
                    self.current_api_key.increment_usage(quota_cost)
                    self.db_session.commit()
                
                return result
                
            except HttpError as e:
                error_code = e.resp.status
                error_reason = e.error_details[0].get('reason', '') if e.error_details else ''
                
                logger.error(f"YouTube API error {error_code}: {error_reason}")
                
                if error_code == 403:
                    if 'quotaExceeded' in error_reason or 'dailyLimitExceeded' in error_reason:
                        # Mark current key as quota exceeded
                        if self.current_api_key:
                            self.current_api_key.quota_used = self.current_api_key.quota_limit
                            self.db_session.commit()
                        
                        # Try to get a new key
                        self.service = None
                        self.current_api_key = None
                        retry_count += 1
                        continue
                    else:
                        # Other 403 errors (e.g., API key invalid)
                        if self.current_api_key:
                            self.current_api_key.error_count += 1
                            if self.current_api_key.error_count >= 5:
                                self.current_api_key.is_active = False
                            self.db_session.commit()
                        raise
                
                elif error_code == 400:
                    # Bad request - don't retry
                    logger.error(f"Bad request: {str(e)}")
                    raise
                
                elif error_code >= 500:
                    # Server error - retry with backoff
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = (2 ** retry_count) + random.uniform(0, 1)
                        logger.info(f"Server error, retrying in {wait_time:.2f} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                
                else:
                    # Other errors
                    raise
                    
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = (2 ** retry_count) + random.uniform(0, 1)
                    logger.info(f"API call failed, retrying in {wait_time:.2f} seconds: {str(e)}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"API call failed after {max_retries} retries: {str(e)}")
                    raise
        
        raise Exception(f"API call failed after {max_retries} retries")
    
    def get_channel_metadata(self, channel_id: str) -> Optional[Dict]:
        """Get comprehensive channel metadata"""
        def api_call(service):
            request = service.channels().list(
                part='snippet,statistics,brandingSettings,status,topicDetails',
                id=channel_id
            )
            response = request.execute()
            return response
        
        try:
            response = self.handle_api_call(api_call, quota_cost=2)
            
            if not response.get('items'):
                logger.warning(f"No data found for channel ID: {channel_id}")
                return None
            
            channel_data = response['items'][0]
            snippet = channel_data.get('snippet', {})
            statistics = channel_data.get('statistics', {})
            branding = channel_data.get('brandingSettings', {}).get('channel', {})
            topics = channel_data.get('topicDetails', {})
            
            # Parse published date
            published_at = None
            if snippet.get('publishedAt'):
                try:
                    published_at = datetime.fromisoformat(
                        snippet['publishedAt'].replace('Z', '+00:00')
                    )
                except:
                    pass
            
            metadata = {
                'title': snippet.get('title'),
                'description': snippet.get('description'),
                'subscriber_count': int(statistics.get('subscriberCount', 0)),
                'video_count': int(statistics.get('videoCount', 0)),
                'view_count': int(statistics.get('viewCount', 0)),
                'country': snippet.get('country'),
                'custom_url': snippet.get('customUrl'),
                'published_at': published_at,
                'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                'banner_url': branding.get('bannerExternalUrl'),
                'keywords': branding.get('keywords', '').split(',') if branding.get('keywords') else [],
                'topic_categories': topics.get('topicCategories', [])
            }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get metadata for channel {channel_id}: {str(e)}")
            return None
    
    def get_channel_videos(self, channel_id: str, max_results: int = 50) -> List[Dict]:
        """Get recent videos for a channel"""
        videos = []
        
        # First get the channel's upload playlist ID
        def get_uploads_playlist(service):
            request = service.channels().list(
                part='contentDetails',
                id=channel_id
            )
            response = request.execute()
            return response
        
        try:
            response = self.handle_api_call(get_uploads_playlist, quota_cost=1)
            
            if not response.get('items'):
                logger.warning(f"No uploads playlist found for channel: {channel_id}")
                return []
            
            uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from uploads playlist
            next_page_token = None
            videos_fetched = 0
            
            while videos_fetched < max_results:
                def get_playlist_items(service):
                    request = service.playlistItems().list(
                        part='snippet',
                        playlistId=uploads_playlist_id,
                        maxResults=min(50, max_results - videos_fetched),
                        pageToken=next_page_token
                    )
                    response = request.execute()
                    return response
                
                response = self.handle_api_call(get_playlist_items, quota_cost=1)
                
                if not response.get('items'):
                    break
                
                # Extract video IDs for detailed info
                video_ids = [item['snippet']['resourceId']['videoId'] for item in response['items']]
                
                # Get detailed video information
                def get_video_details(service):
                    request = service.videos().list(
                        part='snippet,statistics,contentDetails,status',
                        id=','.join(video_ids)
                    )
                    response = request.execute()
                    return response
                
                video_details = self.handle_api_call(get_video_details, quota_cost=1)
                
                for video_data in video_details.get('items', []):
                    snippet = video_data.get('snippet', {})
                    statistics = video_data.get('statistics', {})
                    content_details = video_data.get('contentDetails', {})
                    
                    # Parse published date
                    published_at = None
                    if snippet.get('publishedAt'):
                        try:
                            published_at = datetime.fromisoformat(
                                snippet['publishedAt'].replace('Z', '+00:00')
                            )
                        except:
                            pass
                    
                    video_info = {
                        'video_id': video_data['id'],
                        'title': snippet.get('title'),
                        'description': snippet.get('description'),
                        'published_at': published_at,
                        'duration': content_details.get('duration'),
                        'view_count': int(statistics.get('viewCount', 0)),
                        'like_count': int(statistics.get('likeCount', 0)),
                        'comment_count': int(statistics.get('commentCount', 0)),
                        'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                        'tags': snippet.get('tags', []),
                        'category_id': int(snippet.get('categoryId', 0)) if snippet.get('categoryId') else None
                    }
                    
                    videos.append(video_info)
                    videos_fetched += 1
                    
                    if videos_fetched >= max_results:
                        break
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            
            logger.info(f"Retrieved {len(videos)} videos for channel {channel_id}")
            return videos
            
        except Exception as e:
            logger.error(f"Failed to get videos for channel {channel_id}: {str(e)}")
            return []
    
    def search_channels(self, query: str, max_results: int = 25) -> List[Dict]:
        """Search for channels by query"""
        def api_call(service):
            request = service.search().list(
                part='snippet',
                q=query,
                type='channel',
                maxResults=max_results,
                order='relevance'
            )
            response = request.execute()
            return response
        
        try:
            response = self.handle_api_call(api_call, quota_cost=100)
            
            channels = []
            for item in response.get('items', []):
                snippet = item.get('snippet', {})
                
                channel_info = {
                    'channel_id': item['id']['channelId'],
                    'title': snippet.get('title'),
                    'description': snippet.get('description'),
                    'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                    'published_at': snippet.get('publishedAt')
                }
                channels.append(channel_info)
            
            return channels
            
        except Exception as e:
            logger.error(f"Failed to search channels with query '{query}': {str(e)}")
            return []
    
    def get_channel_by_username(self, username: str) -> Optional[str]:
        """Get channel ID by username/handle"""
        def api_call(service):
            request = service.channels().list(
                part='id',
                forUsername=username
            )
            response = request.execute()
            return response
        
        try:
            response = self.handle_api_call(api_call, quota_cost=1)
            
            if response.get('items'):
                return response['items'][0]['id']
            return None
            
        except Exception as e:
            logger.error(f"Failed to get channel ID for username '{username}': {str(e)}")
            return None
    
    def get_related_channels(self, channel_id: str) -> List[str]:
        """Get related channels (via channel sections if available)"""
        def api_call(service):
            request = service.channelSections().list(
                part='snippet,contentDetails',
                channelId=channel_id
            )
            response = request.execute()
            return response
        
        try:
            response = self.handle_api_call(api_call, quota_cost=1)
            
            related_channels = []
            for section in response.get('items', []):
                content_details = section.get('contentDetails', {})
                channels = content_details.get('channels', [])
                related_channels.extend(channels)
            
            return list(set(related_channels))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Failed to get related channels for {channel_id}: {str(e)}")
            return []
    
    def validate_api_key(self, api_key: str) -> bool:
        """Validate if an API key is working"""
        try:
            service = build('youtube', 'v3', developerKey=api_key)
            request = service.channels().list(part='id', mine=True)
            request.execute()
            return True
        except:
            return False
    
    def close(self):
        """Close database session"""
        if hasattr(self, 'db_session'):
            self.db_session.close()