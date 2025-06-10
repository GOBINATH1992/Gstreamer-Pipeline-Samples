# GstPerf

A GStreamer element to measure framerate, CPU usage

## Build Instructions

On Debian-based systems:
```bash
./autogen.sh
./configure --prefix /usr/ --libdir /usr/lib/$(uname -m)-linux-gnu/
make
sudo make install
```

Configure options may vary according to your specific system.

## Usage

Just link in the `perf` element wherever you want to take the
measurements from. For example, record an MP4 file and print
framerate, bitrate and CPU usage measurements at the output of the
encoder:

```bash
gst-launch-1.0 -e videotestsrc ! x264enc ! perf ! qtmux  ! fakesink
```
### python usage
```bash
python3 fps_test.py
```


