import asyncio
from itertools import islice
from googleapiclient.discovery import build
from youtube import extraction
from youtube.extraction import CandidateType
from cachetools import LRUCache, cached
from async_lru import alru_cache

_CHANNEL_PARTS = ['contentDetails', 'snippet',
    'brandingSettings', 'statistics']
_VIDEO_PARTS = ['snippet']

QUOTA_COUNTER = 0


# https://stackoverflow.com/questions/63732618/is-it-possible-to-detect-when-all-async-tasks-are-suspended
async def _wait_for_deadlock(empty_loop_threshold: int = 0):
    def check_for_deadlock():
        nonlocal empty_loop_count

        if loop._ready:
            empty_loop_count = 0
            loop.call_soon(check_for_deadlock)
        elif empty_loop_count < empty_loop_threshold:
            empty_loop_count += 1
            loop.call_soon(check_for_deadlock)
        else:
            future.set_result(None)

    empty_loop_count = 0
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    asyncio.get_running_loop().call_soon(check_for_deadlock)
    await future


class YoutubeResource:

    def __init__(self, api):
        self.api = api
        self.cache = LRUCache(maxsize=4096)
        self.requests = set()
        self.supply_event = None

    # Fetch data and notify all waiting parties
    def supply_requested(self):
        chosen_requests = list(islice(self.requests, 50))
        self.requests -= set(chosen_requests)

        resources = self.supply(chosen_requests)

        for request, resource in zip(chosen_requests, resources):
            self.cache[request] = resource

        if self.supply_event is not None:
            self.supply_event.set()
            #self.supply_event.clear()
            self.supply_event = None
            # TODO: Save corresponding loop for each request

    def supply(self, requests):
        pass

    async def request(self, data):
        if self.supply_event is None:
            self.supply_event = asyncio.Event()

        if data in self.cache:
            return self.cache[data]

        self.requests.add(data)

        while data not in self.cache:
            if data not in self.requests:
                self.requests.add(data)

            if self.supply_event is None:
                self.supply_event = asyncio.Event()

            await self.supply_event.wait()

        return self.cache[data]

    @property
    def current_request_count(self):
        return len(self.requests)


class ChannelDataResource(YoutubeResource):

    def supply(self, channel_ids):
        print(f'supplying {channel_ids}')
        response = self.api.channels().list(part=_CHANNEL_PARTS, id=channel_ids).execute()
        global QUOTA_COUNTER
        QUOTA_COUNTER += 1

        if 'items' not in response:
            print('No channel data fetched')
            return [None] * len(channel_ids)

        resources = []

        for channel_id in channel_ids:
            item = next(
                (it for it in response['items'] if it['id'] == channel_id), None)
            resources.append(item)

        return resources


class VideoDataResource(YoutubeResource):

    def supply(self, video_ids):
        print(f'supplying {video_ids}')
        response = self.api.videos().list(part=_VIDEO_PARTS, id=video_ids).execute()
        global QUOTA_COUNTER
        QUOTA_COUNTER += 1

        if 'items' not in response:
            print('No video data fetched')
            return [None] * len(video_ids)

        resources = []

        for video_id in video_ids:
            item = next(
                (it for it in response['items'] if it['id'] == video_id), None)
            resources.append(item)

        return resources


class Youtube:

    _REQUEST_TYPES = [
        'channel_data',
        'video_data',
        'channel_videos'
    ]

    def __init__(self, developerKey):
        self.api = build('youtube', 'v3', developerKey=developerKey)

        self.resources = {
            'channel_data': ChannelDataResource(self.api),
            'video_data': VideoDataResource(self.api)
        }

        self._initialized_event_loops = []

    async def channel_data(self, channel_id):
        return await self.resources['channel_data'].request(channel_id)

    async def video_data(self, video_id):
        return await self.resources['video_data'].request(video_id)

    @alru_cache(maxsize=4096)
    async def playlist_data(self, playlist_id):
        print('supplying playlist')
        response = self.api.playlistItems().list(playlistId=playlist_id,
                                         part='snippet', maxResults=50, pageToken=None).execute()
        global QUOTA_COUNTER
        QUOTA_COUNTER += 1

        if 'items' not in response:
            return None

        return response['items']

    async def recent_channel_videos(self, channel_id):
        channel_info = await self.channel_data(channel_id)

        if channel_info is None:
            return None

        upload_playlist_id = channel_info['contentDetails']['relatedPlaylists']['uploads']

        return await self.playlist_data(upload_playlist_id)

    @alru_cache(maxsize=4096)
    async def descriptor_to_channel_id(self, descriptor, allow_search=False):
        global QUOTA_COUNTER
        candidate, candidate_type = extraction.extract_candidate(descriptor)

        if candidate_type == CandidateType.CHANNEL_ID or candidate_type == CandidateType.UNKNOWN:
            data = await self.channel_data(candidate)

            if data is not None:
                return candidate

        if candidate_type == CandidateType.USERNAME or candidate_type == CandidateType.UNKNOWN:
            response = self.api.channels().list(part=_CHANNEL_PARTS, forUsername=candidate).execute()
            QUOTA_COUNTER += 1

            if 'items' in response and len(response['items']) > 0:
                return response['items'][0]['id']

        if candidate_type == CandidateType.VIDEO_ID or candidate_type == CandidateType.UNKNOWN:
            video_data = await self.video_data(candidate)

            if video_data is not None:
                return video_data['snippet']['channelId']

        if candidate_type == CandidateType.UNKNOWN:
            if allow_search:
                response = self.api.search().list(part='snippet', q=descriptor, type='channel', maxResults=1).execute()
                QUOTA_COUNTER += 100
        
                if 'items' not in response:
                    return None
                
                if len(response['items']) == 0:
                    return None
        
                return response['items'][0]['id']['channelId']

        return None

    async def _watch_resources(self):
        while True:
            await _wait_for_deadlock()

            busiest_resource = max(self.resources.values(), key=lambda res: res.current_request_count)

            if busiest_resource.current_request_count > 0:
                busiest_resource.supply_requested()

    @property
    def launched(self):
        return asyncio.get_running_loop() in self._initialized_event_loops

    def launch(self):
        self._initialized_event_loops.append(asyncio.get_running_loop())
        asyncio.create_task(self._watch_resources())

youtube = Youtube('your super secret youtube key...')

async def channel_data(channel_id):
    if not youtube.launched:
        youtube.launch()
    return await youtube.channel_data(channel_id)

async def video_data(video_id):
    if not youtube.launched:
        youtube.launch()
    return await youtube.video_data(video_id)

async def recent_channel_videos(channel_id):
    if not youtube.launched:
        youtube.launch()
    return await youtube.recent_channel_videos(channel_id)

async def descriptor_to_channel_id(descriptor):
    if not youtube.launched:
        youtube.launch()
    return await youtube.descriptor_to_channel_id(descriptor)

def used_quota():
    return QUOTA_COUNTER

def reset_quota():
    global QUOTA_COUNTER
    QUOTA_COUNTER = 0
