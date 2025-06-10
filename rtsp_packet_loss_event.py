import sys
import traceback
import argparse

import gi
from time import sleep
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GObject, Gst
from gi.repository import GLib, GstRtspServer
from gi.repository import Gst, GObject 

# Initializes Gstreamer, it's variables, paths
Gst.init(None)


def on_message(bus: Gst.Bus, message: Gst.Message, loop: GLib.MainLoop()):
    mtype = message.type
    """
        Gstreamer Message Types and how to parse
        https://lazka.github.io/pgi-docs/Gst-1.0/flags.html#Gst.MessageType
    """
    if mtype == Gst.MessageType.EOS:
        print("End of stream")
        loop.quit()

    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(err, debug)
        loop.quit()

    elif mtype == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print(err, debug)

    return True

def iterate_elements_recursively(element, level=0):
    indent = "  " * level
    ename = element.get_name()
    etype = element.get_factory().get_name() if element.get_factory() else 'no-factory'
    
    #print(f"{indent}Element: {ename} ({etype})")
    if etype == "rtpjitterbuffer":
        element.set_property("do-lost",True)
        stats = element.get_property("stats")
        st= stats.to_string()
        print(f"Element name : {ename}, Stats : {st}")
        
    
    if isinstance(element, Gst.Bin):
        it = element.iterate_elements()
        while True:
            try:
                ok, child = it.next()
                if not ok or child is None:
                    break
                iterate_elements_recursively(child, level + 1)
            except Exception:
                break 

def watchDog(pipeline: object):
    iterate_elements_recursively(pipeline)  # Iterate pipeline and print rtpjitterbuffer stats
    return True


def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    print("gstname=", gstname)
    if gstname.find("video") != -1:
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        print("features=", features)
        
        # Get the source bin ghost pad
        bin_ghost_pad = source_bin.get_static_pad("src")
        if not bin_ghost_pad.set_target(decoder_src_pad):
            sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
        

def new_jitterbuffer_callback (rtpbin, jitterbuffer, session, ssrc, udata):
    ename = jitterbuffer.get_name()
    print(f"Element : {ename} \n")
    jitterbuffer.set_property("do-lost", True) 
    
    

def manager_callback (rtspsrc, manager, user_data):
    ename = manager.get_name()
    print(f"Element : {ename} \n", )
    manager.set_property("do-lost", True) 
    
    manager.connect("new-jitterbuffer", new_jitterbuffer_callback, user_data)
    manager.connect("pad-added", new_rtpbin_pad, user_data)
    
    
def new_rtpbin_pad (rtpbin, pad, user_data):
    pad_name  = pad.get_name()

    if ("recv_rtp_src" in pad_name):
        #gst_pad_add_probe (pad, GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM, rtpjitter_monitor_probe_func, bin, NULL)
        pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, _on_rtpbin_downstream_event, 0)
        print(f"rtpbin pad : {pad_name} \n" )
       

def _on_rtpbin_downstream_event(pad, info,u_data):
    event = info.get_event()
    
    if event.type != Gst.EventType.CUSTOM_DOWNSTREAM:
        name =  Gst.EventType.get_name(event.type)
        print('Rtpbin downstream basic event: %s', name)
        return Gst.PadProbeReturn.OK
    
    name = event.get_structure().get_name()
    #print('Rtpbin downstream basic event: %s', name)
    if name == 'GstRTPPacketLost':
        print('Rtpbin downstream packet loss')
    else:
        print('Rtpbin downstream custom event: %s', name)
    return Gst.PadProbeReturn.OK  
    


    

def decodebin_child_added(child_proxy, Object, name, user_data):
    print("Decodebin child added:", name, "\n")
    if name.find("decodebin") != -1:
        Object.connect("child-added", decodebin_child_added, user_data)

    if name.find("source") != -1:
        Object.connect("new-manager", manager_callback, user_data)
        Object.set_property("drop-on-latency", True)
        Object.set_property("latency", 10)
        
    



def create_source_bin(index, uri):
    print("Creating source bin")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name = "source-bin-%02d" % index
    print(bin_name)
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri", uri)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    # We need to create a ghost pad for the source bin which will act as a proxy
    # for the video decoder src pad. The ghost pad will not have a target right
    # now. Once the decode bin creates the video decoder and generates the
    # cb_newpad callback, we will set the ghost pad target to the video decoder
    # src pad.
    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(
        Gst.GhostPad.new_no_target(
            "src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin


import random
def buffer_probe(pad, info, u_data):
    random_integer = random.randint(120, 180)
    sleep(random_integer)
    
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return
      
    return Gst.PadProbeReturn.OK
    

        

RTSP_URL = "rtsp://server/url"

print("Creating Pipeline \n ")
pipeline = Gst.Pipeline()
src = create_source_bin(0,RTSP_URL)
queue = Gst.ElementFactory.make("queue")
sink = Gst.ElementFactory.make("fakesink")

pipeline.add(src, queue, sink)
src.link(queue)
queue.link(sink)

# https://lazka.github.io/pgi-docs/Gst-1.0/classes/Bus.html
bus = pipeline.get_bus()

# allow bus to emit messages to main thread
bus.add_signal_watch()

# timeout function to call at regular inerval
GLib.timeout_add_seconds(30, watchDog, pipeline)


src_pad=queue.get_static_pad("src")
if not src_pad:
    sys.stderr.write(" Unable to get src pad \n")
else:
    pass
    #src_pad.add_probe(Gst.PadProbeType.BUFFER, buffer_probe, 0) # to simulate larency

# Start pipeline
pipeline.set_state(Gst.State.PLAYING)

# Init GObject loop to handle Gstreamer Bus Events
loop = GLib.MainLoop()

# Add handler to specific signal
# https://lazka.github.io/pgi-docs/GObject-2.0/classes/Object.html#GObject.Object.connect
bus.connect("message", on_message, loop)

try:
    loop.run()
except Exception:
    traceback.print_exc()
    loop.quit()

# Stop Pipeline
pipeline.set_state(Gst.State.NULL)