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

    def __init__(self):
        pass

    @contextmanager
    def _deviceContext(self):

        with usb1.USBContext() as ctx:
            _device = ctx.openByVendorIDAndProductID(
                self.VENDOR_ID,
                self.PRODUCT_ID,
                skip_on_error=True,
            )

            if _device is None:
                # Device not present, or user is not allowed to access device.
                raise Exception("No device with VID %s and PID %s found!" % (self.PRODUCT_ID, self.VENDOR_ID))

            if _device.kernelDriverActive(0):
                _device.detachKernelDriver(0)

            _device.setConfiguration(1)

            with _device.claimInterface(0):
                yield _device

    def resetDevice(self):
        with self._deviceContext() as device:
            device.resetDevice()

    def commandNameByIndex(self, name):
        if name not in self.CMD_MAP:
            raise Exception("Unknown command %s" % name)

        return self.CMD_MAP[name]


class NooliteTX(NooliteBase):
    VENDOR_ID = 5824
    PRODUCT_ID = 1503

    def __init__(self):
        super(NooliteBase, self).__init__()
        self._ctrl_mode = (2 << 3) + (4 << 5)

    def bind(self, channel):
        with self._deviceContext() as device:
            self.sendCommand(device, "bind", channel)

    def unbind(self, channel):
        with self._deviceContext() as device:
            self.sendCommand(device, "unbind", channel)

    def turn_on(self, channel):
        with self.deviceContext() as device:
            self.sendCommand(device, "turn_on", channel)

    def turn_off(self, channel):
        with self._deviceContext() as device:
            self.sendCommand(device, "turn_off", channel)

    def switch(self, channel):
        with self._deviceContext() as device:
            self.sendCommand(device, "switch", channel)

    def brightness(self, channel, brightness):
        with self._deviceContext() as device:
            self.sendCommand(device, "brightness", channel, brightness)

    def rgb(self, channel, r, g, b):
        with self._deviceContext() as device:
            self.sendCommand(device, "rgb", channel, r, g, b)

    def executeMany(self, commands):
        with self._deviceContext() as device:
            for command, channel, args in commands:
                self.sendCommand(device, command, channel, *args)
                # Device needs a pause between commands in order to transmit the actual radio sequense
                # Pause duration depends on device control mode (self._ctrl_mode), which has encoded bitrate and number of repetitions.
                # When the bitrate is 2000bps, length of radio sequence is approximately 40ms(preambule) + 40ms * number of repetitions
                # (2 << 3) + (4 << 5), Bitrate mode 2 with 4 data repetitions worked best, so 300ms delay should be more than enough.
                time.sleep(0.3)

    def sendCommand(self, device, command, channel, *args):

        cmd = [self._ctrl_mode, 0, 0, 0, int(channel), 0, 0, 0]
        if command == "turn_on":
            cmd[1] = 2
        elif command == "turn_off":
            cmd[1] = 0
        elif command == "switch":
            cmd[1] = 4
        elif command == "brightness":
            assert len(args) == 1, "brightness command requires 1 additional positional argument"
            cmd[1] = 6
            cmd[2] = 1
            cmd[5] = int(args[0])
        elif command == "rgb":
            assert len(args) == 3, "rgb command requires 3 additional positional arguments"
            cmd[1] = 6
            cmd[2] = 3
            cmd[5] = int(args[0])
            cmd[6] = int(args[1])
            cmd[7] = int(args[2])
        elif command == "bind":
            cmd[1] = 9
        elif command == "unbind":
            cmd[1] = 15

        device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes(cmd), 1000)


class NooliteRX(NooliteBase):

    VENDOR_ID = 5824
    PRODUCT_ID = 1500

    def __init__(self):
        super(NooliteBase, self).__init__()

        self._stopping = False
        self._callback = lambda c, a, f, d: print("channel:     %s\naction:      %s\nfmt:    %s\ndata:        %s" % (c, a, f, d))

    def _eventHandler(self, togl, input):
        channel = input[1]
        action = self.commandNameByIndex(input[2])
        fmt = input[3]
        data = list(input[4:])

        self._callback(channel, action, fmt, data)

    def setMessageCallback(self, callback):
        self._callback = callback

    def bindChannel(self, channel):
        with self._deviceContext() as device:
            self.sendCommand(device, "bind", channel)

    def unbindChannel(self, channel):
        with self._deviceContext() as device:
            self.sendCommand(device, "unbind", channel)

    def unbindAll(self):
        with self._deviceContext() as device:
            self.sendCommand(device, "unbind_all")

    def sendCommand(self, device, command, channel, *args):

        cmd = [0, int(channel), 0, 0, 0, 0, 0, 0]
        if command == "bind":
            cmd[0] = 1
        elif command == "unbind":
            cmd[0] = 3
        elif command == "unbind_all":
            cmd[0] = 4
            cmd[1] = 0

        device.controlWrite(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT, 0x9, 0x300, 0, bytes(cmd), 1000)

    def listen(self):
        self._stopping = False

        with self._deviceContext() as device:
            new_togl = 0;
            prev_togl = -1;

            while not self._stopping:
                ret = device.controlRead(usb1.REQUEST_TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_IN, 0x9, 0x300, 0, 8, 200)
                if len(ret) == 0:
                    continue

                new_togl = ret[0] & 63;

                if new_togl != prev_togl and prev_togl != -1:
                    self._eventHandler(new_togl, ret)

                time.sleep(0.3)
                prev_togl = new_togl

    def stopListening(self):
        self._stopping = True
