import re
from enum import Enum, auto

class CandidateType(Enum):
    CHANNEL_ID = auto()
    USERNAME = auto()
    VIDEO_ID = auto()
    UNKNOWN = auto()

def extract_candidate(descriptor):
    channel_id_url_regex = r'youtube\.com\/channel\/([0-9A-Za-z_-]+)'
    channel_name_url_regex = r"youtube\.com\/user/([0-9A-Za-z_\.'-]+)"
    video_id_long_regex = r'youtube\.com\/watch\S+v=([0-9A-Za-z_-]+)'
    video_id_short_regex = r'youtu\.be\/([0-9A-Za-z_-]+)'
    
    if matches := re.findall(channel_id_url_regex, descriptor):
        return matches[0], CandidateType.CHANNEL_ID
    
    if matches := re.findall(channel_name_url_regex, descriptor):
        return matches[0], CandidateType.USERNAME
    
    if matches := re.findall(video_id_long_regex, descriptor):
        return matches[0], CandidateType.VIDEO_ID
    
    if matches := re.findall(video_id_short_regex, descriptor):
        return matches[0], CandidateType.VIDEO_ID
    
    return descriptor, CandidateType.UNKNOWN