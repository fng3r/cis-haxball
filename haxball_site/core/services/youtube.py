import logging
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional, Union

import isodate
from django.core.cache import cache
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from haxball_site import settings

logger = logging.getLogger('haxball_site')

def cache_with_timeout(timeout_seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args):
            cache_key = f"{func.__name__}__{'_'.join([str(arg) for arg in args[1:]])}"
            result = cache.get(cache_key)
            
            if result:
                logger.debug(f'Cache hit for key: {cache_key}')
            else:
                logger.debug(f'Cache miss for key: {cache_key}')
                result = func(*args)
                cache.set(cache_key, result, timeout_seconds)
            
            return result
        return wrapper
    return decorator


class YoutubeService:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=settings.YOUTUBE_API_KEY)

    @cache_with_timeout(180)
    def search_channel_livestreams(self, channel_id):
        # First get the uploads playlist ID for the channel
        channel_response = self.youtube.channels().list(
            part='contentDetails',
            id=channel_id
        ).execute()
        
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Get recent videos from uploads playlist
        playlist_response = self.youtube.playlistItems().list(
            part='snippet',
            playlistId=uploads_playlist_id,
            maxResults=10
        ).execute()
        
        video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response.get('items', [])]
        
        active_streams = []
        completed_streams = []
        
        video_response = self.youtube.videos().list(
            part='snippet,liveStreamingDetails,contentDetails,statistics',
            id=','.join(video_ids)
        ).execute()
        
        for video_data in video_response.get('items', []):
            # Check if it's a livestream
            if video_data.get('liveStreamingDetails'):
                live_details = video_data['liveStreamingDetails']
                start_time = live_details.get('actualStartTime')
                end_time = live_details.get('actualEndTime')
                thumbnails = video_data['snippet']['thumbnails']
                thumbnail = ''
                for quality in ['maxres', 'high', 'medium', 'default']:
                    if quality in thumbnails:
                        thumbnail = thumbnails[quality]['url']
                        break
                
                if start_time:
                    is_live = end_time is None
                    stream = {
                        'is_live': is_live,
                        'id': video_data['id'],
                        'title': video_data['snippet']['title'],
                        'thumbnail_url': thumbnail,
                        'channelTitle': video_data['snippet']['channelTitle'],
                        'url': f"https://www.youtube.com/watch?v={video_data['id']}",
                        'actual_start_time': datetime.fromisoformat(start_time.replace('Z', '+00:00')),
                    }
                    if is_live:
                        stream['concurrent_viewers'] = live_details.get('concurrentViewers')
                        active_streams.append(stream)
                    else:
                        stream['duration'] = self._parse_iso_duration(video_data['contentDetails'].get('duration'))
                        completed_streams.append(stream)
        
        completed_streams.sort(key=lambda x: x['actual_start_time'], reverse=True)
        completed_streams = completed_streams[:2]
        
        return {
            'active': active_streams,
            'completed': completed_streams
        }
    
    @cache_with_timeout(900)
    def get_videos_by_ids(self, video_ids: List[str]) -> List[Dict]:
        """
        Fetch videos by their IDs and return detailed information.
        
        Args:
            video_ids: List of YouTube video IDs
            
        Returns:
            List of dictionaries containing video details:
            - id: Video ID
            - title: Video title
            - thumbnail_url: URL to the highest quality thumbnail
            - channel_title: Name of the channel
            - url: Full YouTube URL
            - published_at: Publication datetime
            - duration: Duration object with hours, minutes, seconds and formatted string
        """
        if not video_ids:
            logger.warning("No video IDs provided to get_videos_by_ids")
            return []
            
        try:
            # Split into batches of 50 (YouTube API limit)
            results = []
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                
                video_response = self.youtube.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=','.join(batch)
                ).execute()
                
                for video_data in video_response.get('items', []):
                    try:
                        snippet = video_data['snippet']
                        content_details = video_data['contentDetails']
                        
                        thumbnails = snippet['thumbnails']
                        thumbnail_url = ''
                        for quality in ['maxres', 'high', 'medium', 'default']:
                            if quality in thumbnails:
                                thumbnail_url = thumbnails[quality]['url']
                                break
                        
                        published_at = datetime.fromisoformat(
                            snippet['publishedAt'].replace('Z', '+00:00')
                        )
                        
                        duration = self._parse_iso_duration(content_details.get('duration'))
                        
                        results.append({
                            'id': video_data['id'],
                            'title': snippet['title'],
                            'thumbnail_url': thumbnail_url,
                            'channel_title': snippet['channelTitle'],
                            'url': f"https://www.youtube.com/watch?v={video_data['id']}",
                            'published_at': published_at,
                            'duration': duration,
                            'view_count': video_data.get('statistics', {}).get('viewCount')
                        })
                    except Exception as e:
                        logger.error(f"Error processing video {video_data.get('id')}: {str(e)}")
                        continue
                        
            return results
            
        except HttpError as e:
            logger.error(f"YouTube API error in get_videos_by_ids: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in get_videos_by_ids: {str(e)}")
            return []
        
    def _parse_iso_duration(self, iso_duration):
        """Parse ISO 8601 duration format (e.g., PT1H24M35S)"""
        try:
            duration = isodate.parse_duration(iso_duration)
            seconds = duration.total_seconds()
        
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            return {
                'hours': int(hours),
                'minutes': int(minutes),
                'seconds': int(seconds),
                'formatted': (
                    f'{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}' if hours
                    else f'{int(minutes):02d}:{int(seconds):02d}'
                )
            }
        except Exception as e:
            logger.error(f"Error parsing duration {iso_duration}: {str(e)}")
            return {
                'hours': 0,
                'minutes': 0,
                'seconds': 0,
                'formatted': '00:00'
            }