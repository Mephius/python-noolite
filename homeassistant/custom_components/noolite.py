"""
Support for Noolite devices.

"""
import logging
import threading
import time
from queue import Queue

import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.entity import Entity

REQUIREMENTS = []

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'noolite'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
    }),
}, extra=vol.ALLOW_EXTRA)

NOOLITE_COMPONENTS = [
    'sensor', 'light', 'switch'
]

RX_CONTROLLER = None
TX_CONTROLLER = None


# pylint: disable=unused-argument, too-many-function-args
def setup(hass, base_config):

    global RX_CONTROLLER, TX_CONTROLLER

    config = base_config.get(DOMAIN)

    RX_CONTROLLER = NooliteRXController(hass)
    RX_CONTROLLER.start()

    TX_CONTROLLER = NooliteTXController()
    TX_CONTROLLER.start()

    def stop_subscription(event):
        """Shutdown NooliteRX subscriptions and subscription thread on exit."""
        _LOGGER.info("Shutting down RX/TX listeners...")
        RX_CONTROLLER.stop()
        TX_CONTROLLER.stop()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_subscription)
    hass.bus.listen("noolite.tx.send_command", TX_CONTROLLER.sendCommand)

    return True


class NooliteRXController(object):

    def __init__(self, hass):
        self._hass = hass
        self._poll_thread = None
        self._rx = None

    def start(self):
        """Start a thread to handle NooliteRX polling."""
        self._poll_thread = threading.Thread(target=self._run, name='NooliteRX Polling Thread')
        self._poll_thread.deamon = True
        self._poll_thread.start()

    def stop(self):
        """Tell the polling thread to terminate."""
        if self._rx is not None and self._poll_thread is not None:
            self._rx.stopListening()
            self._poll_thread.join()
            _LOGGER.info("NooliteRXController: Terminated polling thread")

    def on_rx_message(self, channel, action, fmt, data):
        _LOGGER.info("Received RX command: (channel: %s, action: %s, fmt: %s, data: %s" % (channel, action, fmt, data))
        self._hass.bus.async_fire("noolite.rx.message", {"channel": channel, "action": action, "fmt": fmt, "data": data})

    def _run(self):
        _LOGGER.info("Starting NooliteRX poller thread")
        from noolitetxrx import NooliteRX

        self._rx = NooliteRX()
        self._rx.setMessageCallback(self.on_rx_message)
        _LOGGER.info("Starting NooliteRX.listen()")
        self._rx.listen()

class NooliteTXController(object):

    def __init__(self):
        self._q = Queue()
        self._status = 0

    def start(self):
        """Start a thread to handle NooliteRX polling."""
        self._poll_thread = threading.Thread(target=self._run, name='NooliteTX Executor Thread')
        self._poll_thread.deamon = True
        self._poll_thread.start()

    def stop(self):
        """Tell the polling thread to terminate."""
        self._q.put(("quit", -1, ()))
        self._poll_thread.join()
        _LOGGER.info("NooliteTXController: Terminated executor thread")

    def sendCommand(self, event):
        _LOGGER.info("NooliteTXController: Queuing command %s on channel %s" % (event.data[0], event.data[1]))
        self._q.put(event.data)

    def _run(self):
        _LOGGER.info("Starting NooliteTX executor thread")
        from noolitetxrx import NooliteTX
        tx = NooliteTX()

        while True:
            command, channel, args = self._q.get(True)
            if command == "quit":
                _LOGGER.info("Terminating execution")
                self._q.task_done()
                return
            else:
                cmds = []
                cmds.append((command, channel, args))
                _LOGGER.info("Executing TX command %s on channel %s " % (command, channel))
                
                # if queue has tasks left, execute them in same context
                while self._q.qsize() > 0:
                    try:
                        command, channel, args = self._q.get_nowait()
                        cmds.append((command, channel, args))
                        _LOGGER.info("Executing TX command %s on channel %s " % (command, channel))
                        self._q.task_done()
                    except Exception as e:
                        _LOGGER.error(str(e))
                        pass

                tx.executeMany(cmds)


class NooliteDevice(Entity):

    def __init__(self, hass, object_id, name, tx_channel=None, rx_channels=()):
 
        self._hass = hass
        self.entity_id = "noolite.{}".format(object_id)
        self._name = name
        self._tx_channel = tx_channel
        self._rx_channels = rx_channels

        hass.bus.listen("noolite.rx.message", self.on_rx_event)

    def on_rx_event(self, event):
        if "channel" in event.data and event.data["channel"] in self._rx_channels:
            self.process_rx_command(event.data)

    def process_rx_command(self, event_data):
        pass

    @property
    def name(self):
        return self._name
