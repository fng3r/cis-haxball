from datetime import datetime
from functools import wraps

import isodate
from django.core.cache import cache
from googleapiclient.discovery import build

from haxball_site import settings


def cache_with_timeout(timeout_seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}"
            result = cache.get(cache_key)
            
            if result is None:
                result = func(*args, **kwargs)
                cache.set(cache_key, result, timeout_seconds)
            
            return result
        return wrapper
    return decorator

class YoutubeService:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=settings.YOUTUBE_API_KEY)

    @cache_with_timeout(180)  # Cache for 3 minutes
    def search_channel_livestreams(self):
        # First get the uploads playlist ID for the channel
        channel_response = self.youtube.channels().list(
            part='contentDetails',
            id=settings.YOUTUBE_CHANNEL_ID
        ).execute()
        
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Get recent videos from uploads playlist
        playlist_response = self.youtube.playlistItems().list(
            part='snippet',
            playlistId=uploads_playlist_id,
            maxResults=10
        ).execute()
        
        video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response.get('items', [])]
        
        live_streams = []
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
                thumbnail = video_data['snippet']['thumbnails']['maxres']['url']
                
                # Active livestream: has started but not ended
                if start_time and not end_time:
                    live_streams.append({
                        'is_live': True,
                        'id': video_data['id'],
                        'title': video_data['snippet']['title'],
                        'thumbnail_url': thumbnail,
                        'channelTitle': video_data['snippet']['channelTitle'],
                        'url': f"https://www.youtube.com/watch?v={video_data['id']}",
                        'actual_start_time': datetime.fromisoformat(start_time.replace('Z', '+00:00')),
                        'concurrent_viewers': live_details.get('concurrentViewers')
                    })
                # Completed livestream: has both start and end time
                elif start_time and end_time:
                    completed_streams.append({
                        'is_live': False,
                        'id': video_data['id'],
                        'title': video_data['snippet']['title'],
                        'thumbnail_url': thumbnail,
                        'channel_title': video_data['snippet']['channelTitle'],
                        'url': f"https://www.youtube.com/watch?v={video_data['id']}",
                        'total_views': video_data['statistics'].get('viewCount'),
                        'actual_start_time': datetime.fromisoformat(start_time.replace('Z', '+00:00')),
                        'duration': self._parse_iso_duration(video_data['contentDetails'].get('duration')),
                    })
        
        completed_streams.sort(key=lambda x: x['actual_start_time'], reverse=True)
        completed_streams = completed_streams[:2]
        
        return {
            'active': live_streams,
            'completed': completed_streams
        }
        
        
    def _parse_iso_duration(self, iso_duration):
        """Parse ISO 8601 duration format (e.g., PT1H24M35S)"""
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