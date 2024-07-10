from flask import Flask, json, request, jsonify
import argparse
from rtsp_in_out import DeepStreamApp
from threading import Thread
from flask_cors import CORS

current_monitored_streams = []

api = Flask(__name__)

parser = argparse.ArgumentParser(description="RTSP Output Example")
parser.add_argument("-i", "--input", default=None, help="List of input URI(s)")
parser.add_argument("-c", "--codec", default="H264", help="RTSP Streaming Codec H264/H265",
                    choices=["H264", "H265"])
parser.add_argument("-b", "--bitrate", default=4000000, help="Set the encoding bitrate", type=int)
parser.add_argument("-p", "--port", default=5400, help="Port of the RTSP Video Stream", type=int)
parser.add_argument("--gie", default="nvinfer", help="Inferencing Engine", choices=["nvinfer", "nvinferserver"])
parser.add_argument("--config-file", default="dstest1_pgie_config.txt", help="Set the config file for nvinfer")
parser.add_argument("--host", default="224.224.255.255", help="Multicast IPv4 Address", type=str)
args = parser.parse_args()

CORS(api)
app = DeepStreamApp(args)

@api.route('/set-video-stream', methods=['POST'])
def set_video_stream():
    data = request.get_json(force=True)
    url = data["url"]

    if url not in current_monitored_streams:
        current_monitored_streams.append(url)
        thread = Thread(target=app.run, args=(str(url),))
        thread.start()

        return [{"result": f"starting object detection on {url}"}]

    else:
        return [{"result": f"already submitted a request for {url}"}]


@api.route('/get-current-car-counter', methods=['GET'])
def get_car_counter():
    objs, car = app.get_data()
    ret = {
        "car": car,
        "objs": objs
    }
    response = jsonify(ret)
    return response


if __name__ == '__main__':
    api.run(host='0.0.0.0')
