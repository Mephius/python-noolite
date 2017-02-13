import signal
import time

import usb1

from contextlib import contextmanager

class NooliteBase(object):

    VENDOR_ID = 5824
    PRODUCT_ID = 0

    CMD_MAP = {
        0: 'turn_off',
        1: 'darken',
        2: 'turn_on',
        3: 'lighten',
        4: 'toggle',
        5: 'change_dim_direction',
        6: 'set_brightness',
        7: 'run_scene',
        8: 'record_scene',
        9: 'unbind',
        10: 'stop_dim',
        15: 'bind',
        16: 'rgb_slow_change',
        17: 'rgb_switch_color',
        18: 'rgb_switch_mode',
        19: 'rgb_switch_speed',
        20: 'battery_low',
        21: 'temperature'
    }

    @contextmanager
    def _deviceContext(self):

        with usb1.USBContext() as ctx:
            device = ctx.openByVendorIDAndProductID(
                self.VENDOR_ID,
                self.PRODUCT_ID,
                skip_on_error=True,
            )

            if device is None:
                # Device not present, or user is not allowed to access device.
                raise Exception("No device with VID %s and PID %s found!" % (self.PRODUCT_ID, self.VENDOR_ID))

            if device.kernelDriverActive(0):
                device.detachKernelDriver(0)

            device.setConfiguration(1)

            with device.claimInterface(0):
                yield device

    def resetDevice(self):
        with self._deviceContext() as device:
            device.resetDevice()


class NooliteTX(NooliteBase):
    VENDOR_ID = 5824
    PRODUCT_ID = 1503

    def __init__(self):
        self._ctrl_mode = (2 << 3) + (3 << 5)

    def bind(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 9, 0, 0, int(channel), 0, 0, 0]), 300)

    def unbind(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 15, 0, 0, int(channel), 0, 0, 0]), 300)

    def turn_on(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 2, 0, 0, int(channel), 0, 0, 0]), 300)

    def turn_off(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 0, 0, 0, int(channel), 0, 0, 0]), 300)

    def switch(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 4, 0, 0, int(channel), 0, 0, 0]), 300)

    def brightness(self, channel, brightness):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 6, 1, 0, int(channel), int(brightness), 0, 0]), 300)

    def rgb(self, channel, r, g, b):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([self._ctrl_mode, 6, 3, 0, int(channel), int(r), int(g), int(b)]), 300)


class NooliteRX(NooliteBase):

    VENDOR_ID = 5824
    PRODUCT_ID = 1500

    def __init__(self):
        self._status = 0
        self._callback = lambda c, a, l, d: print("channel:     %s\naction:      %s\ndata_len:    %s\ndata:        %s" % (c, a, l, d))

    def _signalHandler(self, signal, frame):
         self._status = 1

    def _eventHandler(self, togl, input):
        # print("Input: %s" % input)
        channel = input[1]
        action = input[2]
        data_len = input[3]
        data = input[4:]

        self._callback(channel, action, data_len, data)

    def bindChannel(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([1, int(channel), 0, 0, 0, 0, 0, 0]), 1000)

    def unbindChannel(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([3, int(channel), 0, 0, 0, 0, 0, 0]), 1000)

    def unbindAll(self, channel):
        with self._deviceContext() as device:
            device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes([4, int(channel), 0, 0, 0, 0, 0, 0]), 1000)

    def setMessageCallback(self, callback):
        self._callback = callback

    def listen(self):
        signal.signal(signal.SIGINT, self._signalHandler)
        signal.signal(signal.SIGTERM, self._signalHandler)

        with self._deviceContext() as device:
            new_togl = 0;
            prev_togl = -1;

            while self._status == 0:
                ret = device.controlRead(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_IN, 0x9, 0x300, 0, 8, 200)
                if len(ret) == 0:
                    continue

                new_togl = ret[0] & 63;

                if new_togl != prev_togl and prev_togl != -1:
                    self._eventHandler(new_togl, ret)

                time.sleep(0.2)
                prev_togl = new_togl

        self._status = 0
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
