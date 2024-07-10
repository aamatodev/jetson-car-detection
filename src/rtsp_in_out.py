#!/usr/bin/env python3

################################################################################
# SPDX-FileCopyrightText: Copyright (c) 2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
################################################################################

import sys
import pyds
import platform
import math
import time
from ctypes import *
import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer, GLib
import configparser
import argparse
from common.bus_call import bus_call
from common.is_aarch_64 import is_aarch64
from common.FPS import PERF_DATA

MAX_DISPLAY_LEN = 64
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_OUTPUT_WIDTH = 1920
MUXER_OUTPUT_HEIGHT = 1080
MUXER_BATCH_TIMEOUT_USEC = 4000000
TILED_OUTPUT_WIDTH = 1280
TILED_OUTPUT_HEIGHT = 720
GST_CAPS_FEATURES_NVMM = "memory:NVMM"
OSD_PROCESS_MODE = 0
OSD_DISPLAY_TEXT = 0
pgie_classes_str = ["Vehicle", "TwoWheeler", "Person", "RoadSign"]




def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    print("gstname=", gstname)
    if gstname.find("video") != -1:
        print("features=", features)
        if features.contains("memory:NVMM"):
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write(
                    "Failed to link decoder src pad to source bin ghost pad\n"
                )
        else:
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")


def decodebin_child_added(child_proxy, Object, name, user_data):
    print("Decodebin child added:", name, "\n")
    if name.find("decodebin") != -1:
        Object.connect("child-added", decodebin_child_added, user_data)


def create_source_bin(index, uri):
    print("Creating source bin")
    bin_name = "source-bin-%02d" % index
    print(bin_name)
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    uri_decode_bin.set_property("uri", uri)
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(
        Gst.GhostPad.new_no_target(
            "src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin


class DeepStreamApp:
    def __init__(self, args):
        self.args = args
        self.codec = args.codec
        self.bitrate = args.bitrate
        self.port = args.port
        self.gie = args.gie
        self.num_car = 0
        self.num_obj = 0

        self.perf_data = PERF_DATA(2)

    
    def tiler_src_pad_buffer_probe(self, pad, info, u_data):
        frame_number = 0
        num_rects = 0
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            print("Unable to get GstBuffer ")
            return

        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration:
                break

            frame_number = frame_meta.frame_num
            l_obj = frame_meta.obj_meta_list
            num_rects = frame_meta.num_obj_meta
            obj_counter = {
                PGIE_CLASS_ID_VEHICLE: 0,
                PGIE_CLASS_ID_PERSON: 0,
                PGIE_CLASS_ID_BICYCLE: 0,
                PGIE_CLASS_ID_ROADSIGN: 0,
            }
            while l_obj is not None:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration:
                    break
                obj_counter[obj_meta.class_id] += 1
                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break

            print(
                "Frame Number=", frame_number,
                "Number of Objects=", num_rects,
                "Vehicle_count=", obj_counter[PGIE_CLASS_ID_VEHICLE],
                "Person_count=", obj_counter[PGIE_CLASS_ID_PERSON]
            )

            self.num_obj = num_rects
            self.num_car = obj_counter[PGIE_CLASS_ID_VEHICLE]

            try:
                l_frame = l_frame.next
            except StopIteration:
                break

        return Gst.PadProbeReturn.OK

    def get_data(self):
        return self.num_obj, self.num_car

    def run(self, url):

        Gst.init(None)
        number_sources = 1
        print("Creating Pipeline \n ")
        pipeline = Gst.Pipeline()
        is_live = False

        if not pipeline:
            sys.stderr.write(" Unable to create Pipeline \n")
        print("Creating streamux \n ")

        streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
        if not streammux:
            sys.stderr.write(" Unable to create NvStreamMux \n")

        pipeline.add(streammux)

        print("Creating source_bin ", " \n ")
        uri_name = url
        if uri_name.find("rtsp://") == 0:
            is_live = True
        source_bin = create_source_bin(0, uri_name)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
            return -1
        pipeline.add(source_bin)
        padname = "sink_%u" % 0
        sinkpad = streammux.get_request_pad(padname)
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
            return -2
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
            return -3
        srcpad.link(sinkpad)

        print("Creating Pgie \n ")
        if self.gie == "nvinfer":
            pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
        else:
            pgie = Gst.ElementFactory.make("nvinferserver", "primary-inference")
        if not pgie:
            sys.stderr.write(" Unable to create pgie \n")
            return -4
        print("Creating tiler \n ")
        tiler = Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
        if not tiler:
            sys.stderr.write(" Unable to create tiler \n")
            return -5
        print("Creating nvvidconv \n ")
        nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
        if not nvvidconv:
            sys.stderr.write(" Unable to create nvvidconv \n")
            return -6
        print("Creating nvosd \n ")
        nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
        if not nvosd:
            sys.stderr.write(" Unable to create nvosd \n")
            return -7
        nvvidconv_postosd = Gst.ElementFactory.make(
            "nvvideoconvert", "convertor_postosd")
        if not nvvidconv_postosd:
            sys.stderr.write(" Unable to create nvvidconv_postosd \n")
            return -8

        caps = Gst.ElementFactory.make("capsfilter", "filter")
        caps.set_property(
            "caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420")
        )

        if self.codec == "H264":
            encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")
            print("Creating H264 Encoder")
        elif self.codec == "H265":
            encoder = Gst.ElementFactory.make("nvv4l2h265enc", "encoder")
            print("Creating H265 Encoder")
        if not encoder:
            sys.stderr.write(" Unable to create encoder")
            return -9
        encoder.set_property("bitrate", self.bitrate)
        if is_aarch64():
            encoder.set_property("preset-level", 1)
            encoder.set_property("insert-sps-pps", 1)

        if self.codec == "H264":
            rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
            print("Creating H264 rtppay")
        elif self.codec == "H265":
            rtppay = Gst.ElementFactory.make("rtph265pay", "rtppay")
            print("Creating H265 rtppay")
        if not rtppay:
            sys.stderr.write(" Unable to create rtppay")
            return -10

        sink = Gst.ElementFactory.make("udpsink", "udpsink")
        if not sink:
            sys.stderr.write(" Unable to create udpsink")
            return -11

        print("Playing file %s " % self.args.input)
        sink.set_property("host", self.args.host)
        sink.set_property("port", self.args.port)
        if is_live:
            print("At least one of the sources is live")
            streammux.set_property("live-source", 1)
        streammux.set_property("width", MUXER_OUTPUT_WIDTH)
        streammux.set_property("height", MUXER_OUTPUT_HEIGHT)
        streammux.set_property("batch-size", number_sources)
        streammux.set_property("batched-push-timeout", MUXER_BATCH_TIMEOUT_USEC)
        pgie.set_property("config-file-path", self.args.config_file)

        tiler_rows = int(math.sqrt(number_sources))
        tiler_columns = int(math.ceil((1.0 * number_sources) / tiler_rows))
        tiler.set_property("rows", tiler_rows)
        tiler.set_property("columns", tiler_columns)
        tiler.set_property("width", TILED_OUTPUT_WIDTH)
        tiler.set_property("height", TILED_OUTPUT_HEIGHT)
        sink.set_property("qos", 0)

        pipeline.add(pgie)
        pipeline.add(tiler)
        pipeline.add(nvvidconv)
        pipeline.add(nvosd)
        pipeline.add(nvvidconv_postosd)
        pipeline.add(caps)
        pipeline.add(encoder)
        pipeline.add(rtppay)
        pipeline.add(sink)

        streammux.link(pgie)
        pgie.link(nvvidconv)
        nvvidconv.link(tiler)
        tiler.link(nvosd)
        nvosd.link(nvvidconv_postosd)
        nvvidconv_postosd.link(caps)
        caps.link(encoder)
        encoder.link(rtppay)
        rtppay.link(sink)

        # create an event loop and feed gstreamer bus mesages to it
        loop = GLib.MainLoop()
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", bus_call, loop)

        pgie_src_pad = pgie.get_static_pad("src")
        if not pgie_src_pad:
            sys.stderr.write(" Unable to get src pad \n")
        else:
            pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, self.tiler_src_pad_buffer_probe, 0)
            # perf callback function to print fps every 5 sec
            # perf callback function to print fps every 5 sec
            GLib.timeout_add(5000, self.perf_data.perf_print_callback)

        # Start streaming
        rtsp_port_num = 8554

        server = GstRtspServer.RTSPServer.new()
        server.props.service = "%d" % rtsp_port_num
        server.attach(None)

        factory = GstRtspServer.RTSPMediaFactory.new()
        factory.set_launch(
            '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 " )'
            % (self.port, self.codec)
        )
        factory.set_shared(True)
        server.get_mount_points().add_factory("/ds-test", factory)

        print(
            "\n *** DeepStream: Launched RTSP Streaming at rtsp://localhost:%d/ds-test ***\n\n"
            % rtsp_port_num
        )

        # start play back and listen to events
        print("Starting pipeline \n")
        pipeline.set_state(Gst.State.PLAYING)
        try:
            loop.run()
        except BaseException:
            pass
        # cleanup
        pipeline.set_state(Gst.State.NULL)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="RTSP Output Example")
    parser.add_argument("-i", "--input", default="rtmp://10.100.4.210/live/livestream", help="List of input URI(s)")
    parser.add_argument("-c", "--codec", default="H264", help="RTSP Streaming Codec H264/H265",
                        choices=["H264", "H265"])
    parser.add_argument("-b", "--bitrate", default=4000000, help="Set the encoding bitrate", type=int)
    parser.add_argument("-p", "--port", default=5400, help="Port of the RTSP Video Stream", type=int)
    parser.add_argument("--gie", default="nvinfer", help="Inferencing Engine", choices=["nvinfer", "nvinferserver"])
    parser.add_argument("--config-file", default="dstest1_pgie_config.txt", help="Set the config file for nvinfer")
    parser.add_argument("--host", default="224.224.255.255", help="Multicast IPv4 Address", type=str)
    args = parser.parse_args()

    app = DeepStreamApp(args)
    app.run()
