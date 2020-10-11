from quart import Quart, jsonify, render_template, request
from dataclasses import asdict

from youtube.analysis.graph import related_channels_graph
from youtube.analysis.channel import analyse_channel
from youtube.data import descriptor_to_channel_id

app = Quart(__name__)

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/extract_channel_id')
async def extract_channel_id():
    descriptor = request.args.get('descriptor')
    result = await descriptor_to_channel_id(descriptor) 

    return jsonify(result)

@app.route('/analyse_channel/<channel_id>')
async def channel_analysis_route(channel_id):
    result = await analyse_channel(channel_id)

    return jsonify(asdict(result))

@app.route('/channel_graph/<channel_id>')
async def channel_graph_route(channel_id):
    result = await related_channels_graph(channel_id)

    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)