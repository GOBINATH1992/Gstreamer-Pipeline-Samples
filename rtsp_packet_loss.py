import sys
import traceback
import argparse

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GObject, Gst
from gi.repository import GLib, GstRtspServer
from gi.repository import Gst, GObject 


# Initializes Gstreamer, it's variables, paths
Gst.init(sys.argv)

DEFAULT_PIPELINE = "rtspsrc location=rtsp://some.server/url ! fakesink"

ap = argparse.ArgumentParser()
ap.add_argument("-p", "--pipeline", required=False,
                default=DEFAULT_PIPELINE, help="Gstreamer pipeline without gst-launch")

args = vars(ap.parse_args())


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


command = args["pipeline"]

# Gst.Pipeline https://lazka.github.io/pgi-docs/Gst-1.0/classes/Pipeline.html
# https://lazka.github.io/pgi-docs/Gst-1.0/functions.html#Gst.parse_launch
pipeline = Gst.parse_launch(command)

# https://lazka.github.io/pgi-docs/Gst-1.0/classes/Bus.html
bus = pipeline.get_bus()

# allow bus to emit messages to main thread
bus.add_signal_watch()

# timeout function to call at regular inerval
GLib.timeout_add_seconds(30, watchDog, pipeline)

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