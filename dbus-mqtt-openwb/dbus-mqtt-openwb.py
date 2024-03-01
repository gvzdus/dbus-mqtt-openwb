#!/usr/bin/env python

from gi.repository import GLib  # pyright: ignore[reportMissingImports]
import platform
import logging
import sys
import os
from time import sleep, time
import paho.mqtt.client as mqtt
import configparser  # for config/ini file
import _thread

# import Victron Energy packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService

# get values from config.ini file
try:
    config_file = (os.path.dirname(os.path.realpath(__file__))) + "/config.ini"
    if os.path.exists(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)
        if config['MQTT']['broker_address'] == "IP_ADDR_OR_FQDN":
            print(
                "ERROR:The \"config.ini\" is using invalid default values like IP_ADDR_OR_FQDN. The driver restarts "
                "in 60 seconds.")
            sleep(60)
            sys.exit()
    else:
        print(
            "ERROR:The \"" + config_file + "\" is not found. Did you copy or rename the \"config.sample.ini\" to "
                                           "\"config.ini\"? The driver restarts in 60 seconds.")
        sleep(60)
        sys.exit()

except Exception:
    exception_type, exception_object, exception_traceback = sys.exc_info()
    file = exception_traceback.tb_frame.f_code.co_filename
    line = exception_traceback.tb_lineno
    print(f"Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
    print("ERROR:The driver restarts in 60 seconds.")
    sleep(60)
    sys.exit()

# Get logging level from config.ini
# ERROR = shows errors only
# WARNING = shows ERROR and warnings
# INFO = shows WARNING and running functions
# DEBUG = shows INFO and data/values
if 'DEFAULT' in config and 'logging' in config['DEFAULT']:
    if config['DEFAULT']['logging'] == 'DEBUG':
        logging.basicConfig(level=logging.DEBUG)
    elif config['DEFAULT']['logging'] == 'INFO':
        logging.basicConfig(level=logging.INFO)
    elif config['DEFAULT']['logging'] == 'ERROR':
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.WARNING)

# get timeout
if 'DEFAULT' in config and 'timeout' in config['DEFAULT']:
    timeout = int(config['DEFAULT']['timeout'])
else:
    timeout = 60

# set variables
connected = 0
last_changed = 0
last_updated = 0
topic_prefix = ''
vphase_packets = 0
dbus_service = None
client = None

wb_power = -1
wb_current = 0
wb_forward = 0
wb_plugstat = 0
wb_chargestatus = 0
# 0 = Sofort, 1 = MinPV, 2 = PV, 3 = Stop
wb_chargemode = 3
start_of_charge = -1

wb_voltages = [230, 230, 230]

wb_L1_power = None
wb_L1_current = None
wb_L2_power = None
wb_L2_current = None
wb_L3_power = None
wb_L3_current = None


# MQTT requests
def on_disconnect(lclient, userdata, rc):
    global connected
    logging.warning("MQTT client: Got disconnected")
    if rc != 0:
        logging.warning('MQTT client: Unexpected MQTT disconnection. Will auto-reconnect')
    else:
        logging.warning('MQTT client: rc value:' + str(rc))

    while connected == 0:
        try:
            logging.warning("MQTT client: Trying to reconnect")
            lclient.connect(config['MQTT']['broker_address'])
            connected = 1
        except Exception as err:
            logging.error(
                f"MQTT client: Error in retrying to connect with broker ({config['MQTT']['broker_address']}:{config['MQTT']['broker_port']}): {err}")
            logging.error("MQTT client: Retrying in 15 seconds")
            connected = 0
            sleep(15)


def on_connect(lclient, userdata, flags, rc):
    global connected, topic_prefix
    if rc == 0:
        logging.info("MQTT client: Connected to MQTT broker!")
        connected = 1
        topic_prefix = config['MQTT']['topic']
        lclient.subscribe([(topic_prefix, 0), ('openWB/global/ChargeMode', 0)])
        if topic_prefix.endswith('#'):
            topic_prefix = topic_prefix[:-1]

    else:
        logging.error("MQTT client: Failed to connect, return code %d\n", rc)


def on_message(lclient, userdata, msg):
    global dbus_service

    if not dbus_service:
        return

    try:
        global \
            last_changed, \
            wb_power, wb_current, wb_voltages, wb_forward, wb_plugstat, \
            wb_L1_power, wb_L1_current, \
            wb_L2_power, wb_L2_current, \
            wb_L3_power, wb_L3_current, \
            vphase_packets, wb_chargestatus, wb_chargemode, start_of_charge

        topic = msg.topic
        if topic.startswith(topic_prefix):
            topic = topic[len(topic_prefix):]
        if topic.startswith('VPhase'):
            vphase_packets += 1
            if topic == 'VPhase1':
                wb_voltages[0] = float(msg.payload)
            elif topic == 'VPhase2':
                wb_voltages[1] = float(msg.payload)
            elif topic == 'VPhase3':
                wb_voltages[2] = float(msg.payload)
                dbus_service['/Ac/Voltage'] = (wb_voltages[0] + wb_voltages[1] + wb_voltages[2]) / 3.0
                dbus_service['/ChargingTime'] = time()-start_of_charge if start_of_charge else None


        elif topic.startswith('APhase'):
            if topic == 'APhase1':
                wb_L1_current = float(msg.payload)
                dbus_service['/Ac/L1/Power'] = wb_L1_current * wb_voltages[0]
            elif topic == 'APhase2':
                wb_L2_current = float(msg.payload)
                dbus_service['/Ac/L2/Power'] = wb_L2_current * wb_voltages[1]
            elif topic == 'APhase3':
                wb_L3_current = float(msg.payload)
                dbus_service['/Ac/L3/Power'] = wb_L3_current * wb_voltages[2]

        elif topic == 'W':
            wb_power_new = int(msg.payload)
            if wb_power_new > 1000 and wb_power < 1000:
                start_of_charge = time()
            elif wb_power_new < 1000:
                start_of_charge = None
            dbus_service['/Ac/Power'] = wb_power_new
            wb_power = wb_power_new

        #        elif topic == 'kWhCounter':
        elif topic == 'kWhDailyCharged':
            wb_forward_new = float(msg.payload)
            if wb_forward_new != wb_forward:
                dbus_service['/Ac/Energy/Forward'] = wb_forward_new
            wb_forward = wb_forward_new

        elif topic == 'ChargeStatus' or topic == 'boolPlugStat':
            if topic == 'boolPlugStat':
                wb_plugstat = int(msg.payload)
            elif topic == 'ChargeStatus':
                wb_chargestatus = int(msg.payload)
            if wb_chargestatus == 1:
                dbus_service['/Status'] = 2
            else:
                dbus_service['/Status'] = wb_plugstat

        elif topic == 'AConfigured':
            dbus_service['/Current'] = int(msg.payload)

        elif topic == 'openWB/global/ChargeMode':
            wb_chargemode = int(msg.payload)
            dbus_service['/Mode'] = 1 if wb_chargemode == 2 else 0

        if msg.payload != '' and msg.payload != b'' and not topic.startswith('VPhase'):
            logging.debug("MQTT topic: " + topic + ", payload: " + str(msg.payload)[1:])

    except ValueError as e:
        logging.error("Received message is not a valid JSON. %s" % e)
        logging.debug("MQTT payload: " + str(msg.payload)[1:])

    except Exception:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        file = exception_traceback.tb_frame.f_code.co_filename
        line = exception_traceback.tb_lineno
        logging.error(f"Exception occurred: {repr(exception_object)} of type {exception_type} in {file} line #{line}")
        logging.debug("MQTT payload: " + str(msg.payload)[1:])


class DbusMqttWbService:
    def __init__(
            self,
            servicename,
            deviceinstance,
            paths,
            productname='MQTT OpenWB',
            connection='MQTT OpenWB service'
    ):

        global dbus_service

        self._dbusservice = VeDbusService(servicename)
        self._paths = paths

        logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

        paths_wo_unit = [
            '/Status',
            # value 'state' EVSE State - 1 Not Connected - 2 Connected - 3 Charging - 4 Error, 254 - sleep, 255 - disabled
            # old_goecharger 1: charging station ready, no vehicle 2: vehicle loads 3: Waiting for vehicle 4: Charge finished, vehicle still connected
        ]

        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion',
                                   'Unknown version, and running on Python ' + platform.python_version())
        self._dbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 0xFFFF)  #
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/CustomName', productname)
        self._dbusservice.add_path('/FirmwareVersion', '0.9')
        self._dbusservice.add_path('/HardwareVersion', 2)
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/UpdateIndex', 0)

        # add paths without units
        for path in paths_wo_unit:
            self._dbusservice.add_path(path, None)

        # add path values to dbus
        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['initial'], gettextcallback=settings['textformat'], writeable=True,
                onchangecallback=self._handlechangedvalue)

        dbus_service = self._dbusservice

    def _update(self):

        global \
            last_changed, last_updated

        now = int(time())

        if last_changed != last_updated:
            last_updated = last_changed

            # quit driver if timeout is exceeded
        if timeout != 0 and (now - last_changed) > timeout:
            logging.error(
                "Driver stopped. Timeout of %i seconds exceeded, since no new MQTT message was received in this time." % timeout)
            sys.exit()

            # increment UpdateIndex - to show that new data is available
        index = self._dbusservice['/UpdateIndex'] + 1  # increment index
        if index > 255:  # maximum value of the index
            index = 0  # overflow from 255 to 0
        self._dbusservice['/UpdateIndex'] = index
        return True

    def _handlechangedvalue(self, path, value):
        if path == '/StartStop' and client:
            if value == 0:
                client.publish("openWB/set/ChargeMode", payload=3, qos=0, retain=False)
            if value == 1:
                client.publish("openWB/set/ChargeMode", payload=0, qos=0, retain=False)

        if path == '/Mode' and client:
            if value == 0:
                client.publish("openWB/set/ChargeMode", payload=0, qos=0, retain=False)
            if value == 1 and wb_chargemode != 2:
                client.publish("openWB/set/ChargeMode", payload=2, qos=0, retain=False)
            if value == 1 and wb_chargemode != 0:
                client.publish("openWB/set/ChargeMode", payload=0, qos=0, retain=False)

        if path == '/SetCurrent' and client:
            client.publish("openWB/config/set/sofort/lp1/current", payload=value, qos=0, retain=False)

        logging.debug("someone else updated %s to %s" % (path, value))
        return True  # accept the change


def main():
    global client
    _thread.daemon = True  # allow the program to quit

    from dbus.mainloop.glib import DBusGMainLoop  # pyright: ignore[reportMissingImports]
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    # formatting
    _kwh = lambda p, v: (str(round(v, 2)) + 'kWh')
    _a = lambda p, v: (str(round(v, 1)) + 'A')
    _w = lambda p, v: (str(round(v, 1)) + 'W')
    _v = lambda p, v: (str(round(v, 1)) + 'V')
    _degC = lambda p, v: (str(v) + '°C')
    _s = lambda p, v: (str(v) + 's')
    _t = lambda p, v: (str(v))

    paths_dbus = {
        '/Ac/Power': {'initial': 0, 'textformat': _w},
        '/Ac/L1/Power': {'initial': 0, 'textformat': _w},
        '/Ac/L2/Power': {'initial': 0, 'textformat': _w},
        '/Ac/L3/Power': {'initial': 0, 'textformat': _w},
        '/Ac/Energy/Forward': {'initial': 0, 'textformat': _kwh},
        '/ChargingTime': {'initial': 0, 'textformat': _s},

        '/Ac/Voltage': {'initial': 0, 'textformat': _v},
        '/Current': {'initial': 0, 'textformat': _a},
        '/SetCurrent': {'initial': 0, 'textformat': _a},
        '/MaxCurrent': {'initial': config['WALLBOX']['max'], 'textformat': _a},
        '/MCU/Temperature': {'initial': 0, 'textformat': _degC},
        '/Mode': {'initial': 0, 'textformat': _t},
        '/Position': {'initial': int(config['WALLBOX']['position']), 'textformat': _t},
        '/StartStop': {'initial': 0, 'textformat': _t}
    }

    DbusMqttWbService(
        servicename='com.victronenergy.evcharger.mqtt_wb_' + str(config['DEFAULT']['device_instance']),
        deviceinstance=int(config['DEFAULT']['device_instance']),
        productname=config['DEFAULT']['device_name'],
        paths=paths_dbus
    )
    logging.info('Connected to dbus and switching over to GLib.MainLoop() (= event based)')

    # MQTT setup
    client = mqtt.Client("MqttOpenWB_" + str(config['DEFAULT']['device_instance']))
    client.on_disconnect = on_disconnect
    client.on_connect = on_connect
    client.on_message = on_message

    # check tls and use settings, if provided
    if 'tls_enabled' in config['MQTT'] and config['MQTT']['tls_enabled'] == '1':
        logging.info("MQTT client: TLS is enabled")

        if 'tls_path_to_ca' in config['MQTT'] and config['MQTT']['tls_path_to_ca'] != '':
            logging.info("MQTT client: TLS: custom ca \"%s\" used" % config['MQTT']['tls_path_to_ca'])
            client.tls_set(config['MQTT']['tls_path_to_ca'], tls_version=2)
        else:
            client.tls_set(tls_version=2)

        if 'tls_insecure' in config['MQTT'] and config['MQTT']['tls_insecure'] != '':
            logging.info("MQTT client: TLS certificate server hostname verification disabled")
            client.tls_insecure_set(True)

    # check if username and password are set
    if 'username' in config['MQTT'] and 'password' in config['MQTT'] and config['MQTT']['username'] != '' and \
            config['MQTT']['password'] != '':
        logging.info("MQTT client: Using username \"%s\" and password to connect" % config['MQTT']['username'])
        client.username_pw_set(username=config['MQTT']['username'], password=config['MQTT']['password'])

    # connect to broker
    logging.info(
        f"MQTT client: Connecting to broker {config['MQTT']['broker_address']} on port {config['MQTT']['broker_port']}")
    client.connect(
        host=config['MQTT']['broker_address'],
        port=int(config['MQTT']['broker_port'])
    )
    client.loop_start()

    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()
