import re
import asyncio
from youtube.data import recent_channel_videos, video_data, channel_data
from async_lru import alru_cache
from cachetools import LRUCache, cached
from dataclasses import dataclass
from typing import Optional, List
from wordcloud import WordCloud

@alru_cache(maxsize=4096)
async def related_topics(channel_id):
    videos = await recent_channel_videos(channel_id)
    
    video_ids = [video['snippet']['resourceId']['videoId'] for video in videos]
    
    tags = []

    async def topic_task(video_id):
        data = await video_data(video_id)
        
        if 'tags' in data['snippet']:
            tags.extend(data['snippet']['tags'])

    await asyncio.gather(*[topic_task(video_id) for video_id in video_ids])
    
    return tags


def _extract_channels(description):
    direct_channels = re.findall('youtube.com\/channel\/([^\s\/\&\?]+)', description)
    
    user_links = re.findall('youtube.com\/user\/([^\s\/\&\?]+)', description)

    # TODO: Readd those and also add youtu.be links
    """
    user_channels = []
    for user_name in user_links:
        channel_id = youtube.channels().list(part='snippet', forUsername=user_name).execute()['items'][0]['id']
        user_channels.append(channel_id)
    
    video_links = re.findall('youtube.com\/watch\?v=([^\s\/\&]+)', description)
    
    link_channels = []
    
    for video_id in video_links:
        channel_id = youtube.videos().list(part='snippet', id=video_id).execute()['items'][0]['snippet']['channelId']
        link_channels.append(channel_id)
    
    return direct_channels + user_channels + link_channels
    """
    
    return direct_channels

@alru_cache(maxsize=4096)
async def related_channels(channel_id):
    channel_info = await channel_data(channel_id)

    if channel_info is None:
        return set()

    branding = channel_info['brandingSettings']['channel']

    if 'featuredChannelsUrls' in branding:
        featured_channels = set(branding['featuredChannelsUrls'])
    else:
        featured_channels = set()

    videos = await recent_channel_videos(channel_id)

    if videos is not None:
        descriptions = [video['snippet']['description'] for video in videos if 'description' in video['snippet']]
        
        mentioned_channels = {channel for desc in descriptions for channel in _extract_channels(desc)}
    else:
        mentioned_channels = set()

    return (mentioned_channels | featured_channels) - {channel_id}

@dataclass
class ChannelStatistics:
    view_count: int
    subscriber_count: Optional[int]
    video_count: int

@alru_cache(maxsize=4096)
async def channel_statistics(channel_id):
    data = await channel_data(channel_id)
    
    if data is None:
        return None
    
    statistics = data['statistics']
    
    view_count = int(statistics['viewCount'])
    video_count = int(statistics['videoCount'])
    
    subscriber_count = None if statistics['hiddenSubscriberCount'] else int(statistics['subscriberCount'])
    
    return ChannelStatistics(view_count=view_count, video_count=video_count, subscriber_count=subscriber_count)

def channel_sentiment(channel_id):
    return 0

async def channel_name(channel_id):
    data = await channel_data(channel_id)
    
    if data is None:
        return None
        
    snippet = data['snippet']

    return snippet['title']

@dataclass
class ChannelAnalysis:
    name: str
    topics: List[str]
    sentiment: float
    statistics: ChannelStatistics

@alru_cache(maxsize=4096)
async def analyse_channel(channel_id):
    name = await channel_name(channel_id)
    topics = await related_topics(channel_id)
    sentiment = channel_sentiment(channel_id)
    statistics = await channel_statistics(channel_id)
    
    return ChannelAnalysis(name, topics, sentiment, statistics)