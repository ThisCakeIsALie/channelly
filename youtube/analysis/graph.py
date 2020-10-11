import asyncio
from youtube.data import channel_data
from youtube.analysis.channel import related_channels
from cachetools import LRUCache, cached
from async_lru import alru_cache

def _deduplicate_channels_graph(graph):
    nodes = graph['nodes']
    edges = graph['edges']

    new_nodes = []
    new_edges = []
    
    seen_nodes = set()
    seen_edges = set()

    for node in nodes:
        if node['id'] in seen_nodes:
            continue

        new_nodes.append(node)
        seen_nodes.add(node['id'])

    for edge in edges:

        # We don't care about the direction for the time being
        edge_id = tuple(sorted([edge['source'], edge['target']]))

        if edge_id in seen_edges:
            continue

        new_edges.append(edge)
        seen_edges.add(edge_id)
            
    return { 'nodes': new_nodes, 'edges': new_edges }

# Add cache to prevent repeating work if a child was already visited
@alru_cache(maxsize=4096)
async def _raw_channels_graph(channel_id, depth, max_children):
    nodes = []
    edges = []

    data = await channel_data(channel_id)
    
    if data is None:
        return None
        
    snippet = data['snippet']

    node = {
        'id': channel_id,
        'data': {
            'label': snippet['title'],
            'image': snippet['thumbnails']['default']['url']
        }
    }

    nodes.append(node)

    if depth == 0:
        return { 'nodes': nodes, 'edges': edges }
    
    found_channels = await related_channels(channel_id)

        
    async def channel_task(other_channel_id):
        friend_graph = await _raw_channels_graph(other_channel_id, depth-1, max_children)
        
        if friend_graph is None:
            return

        edge = { 'source': channel_id, 'target': other_channel_id }
        
        nodes.extend(friend_graph['nodes'])
        edges.extend(friend_graph['edges'])
        edges.append(edge)

    await asyncio.gather(*[channel_task(channel_id) for channel_id in list(found_channels)[:max_children]])
        
    return { 'nodes': nodes, 'edges': edges }

async def related_channels_graph(channel_id, depth=2, max_children=5):
    raw_graph = await _raw_channels_graph(channel_id, depth, max_children)
    deduplicated_graph = _deduplicate_channels_graph(raw_graph)
    
    return deduplicated_graph

"""
TODO: Be more strict about channel_id format while scraping (no ... etc.)
"""
