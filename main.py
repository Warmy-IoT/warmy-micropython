import json

import machine
import time
import ubinascii
import network
import onewire, ds18x20
from umqtt.simple import MQTTClient

try:
    with open('config.json', 'r') as config:
        config = json.loads(config.read())
        config["essid"]
except:
    config = {
        'essid': '<your-ssid>',
        'pwd': '<your-password>',
        "broker": "platform.nextechs.it",
        "port": 7000,
        "sensor_pin": 0,
        "client_id": "warmy_1",
        "topic": "warmy",
        "name": "Warmy 1"
    }

WIFI_CONFIG = {
    "essid": config['essid'],
    "wifi_password": config['pwd'],
}

wlan = network.WLAN(network.STA_IF)
print("Starting Wifi")
wlan.active(True)
print("Wifi started")
print("Attempting to connect to {}".format(WIFI_CONFIG['essid']))
wlan.connect(WIFI_CONFIG['essid'], WIFI_CONFIG['wifi_password'])
wlan.config('mac')
wlan.ifconfig()

# These defaults are overwritten with the contents of /config.json by load_config()
CONFIG = {
    "broker": config["broker"],
    "port": config["port"],
    "sensor_pin": config["sensor_pin"],
    "client_id": config["client_id"],
    "topic": config["topic"],
    "name": config["name"]
}

MAP = [
    (16, 'D0'),
    (2, 'D4'),
    (13, 'D7'),
    (12, 'D6'),
    (14, 'D5'),
    (0, 'D3'),
    (4, 'D2'),
    (5, 'D1'),
]


class Thermostat(object):
    OFF_MODE = 'OFF'
    MANUAL_MODE = 'MANUAL'
    PROGRAM_MODE = 'PROGRAM'

    MAX_ERRORS_NUMBER = 60

    TOLERANCE = 0.5

    OFFSET = 1.4

    """
    The desired temp in celsius
    """
    desired_temp = 18

    """
    Override variable, if true the old thermostat has to be overridden
    """
    mode = OFF_MODE

    """
    """
    warming = False

    """
    The actual measured temperature
    """
    actual_temp = 20

    """
    The output of this pin overrides the old thermostat
    """
    override_pin = machine.Pin(5, machine.Pin.OUT)

    override_pin.high()
    """
    The output of this pin starts warming
    """
    warming_pin = machine.Pin(4, machine.Pin.OUT)
    warming_pin.high()

    """
    The input pin that reads from DS18B20 thermometer
    """

    thermometer_pin = machine.Pin(2, machine.Pin.IN)

    """
    The thermometer object
    """
    thermometer = ds18x20.DS18X20(onewire.OneWire(thermometer_pin))

    client = None

    def __init__(self):
        self.errors_count = 0
        print("Attempting to connect to broker {}".format(CONFIG['broker']))

        self.client = MQTTClient(CONFIG['client_id'], CONFIG['broker'], CONFIG['port'])
        self.client.set_callback(self.on_message_received)

        self.client.connect()
        self.client.subscribe('/{}/{}/mode/set'.format(CONFIG['topic'],
                                                       CONFIG['client_id']))
        self.client.subscribe('/{}/{}/manual/desired_temperature/set'.format(CONFIG['topic'],
                                                                             CONFIG['client_id']))
        print("Connected to {}".format(CONFIG['broker']))

    def store_settings(self):
        json_settings = {
            'mode': self.mode,
            'desired_temp': self.desired_temp
        }

        with open('settings.json', 'w') as settings:
            settings.write(json.dumps(json_settings))

    def load_settings(self):
        try:
            with open('settings.json', 'r') as settings:
                json_settings = json.loads(settings.read())
                self.mode = json_settings['mode']
                self.desired_temp = json_settings['desired_temp']
        except:
            pass

    def on_message_received(self, topic, msg):
        payload_string = msg.decode("utf-8")

        if 'desired_temperature/set' in str(topic):
            self.desired_temp = float(payload_string)

        if 'mode/set' in str(topic):
            self.mode = payload_string

        self.store_settings()

    def notify(self, topic, payload):
        try:
            self.client.publish(topic, payload)
            self.errors_count = 0
        except:
            print("Error Publishing data")
            self.errors_count += 1
            if self.errors_count > Thermostat.MAX_ERRORS_NUMBER:
                machine.reset()

    def notify_name(self):
        message = 'Actual temperature is {}'.format(self.actual_temp)

        self.notify('/{}/{}/name'.format(CONFIG['topic'],
                                         CONFIG['client_id']),
                    bytes(CONFIG['name'], 'utf-8'))
        print(message)

    def notify_actual_temp(self):
        message = 'Actual temperature is {}'.format(self.actual_temp)

        self.notify('/{}/{}/actual_temperature'.format(CONFIG['topic'],
                                                       CONFIG['client_id']),
                    bytes(str(self.actual_temp), 'utf-8'))
        print(message)

    def notify_desired_temp(self):
        message = 'Desired temperature is {}'.format(self.desired_temp)

        self.notify('/{}/{}/desired_temperature'.format(CONFIG['topic'],
                                                        CONFIG['client_id']),
                    bytes(str(self.desired_temp), 'utf-8'))
        print(message)

    def notify_actual_mode(self):
        message = 'Actual Mode is {}'.format(self.mode)

        self.notify('/{}/{}/mode'.format(CONFIG['topic'],
                                         CONFIG['client_id']),
                    bytes(self.mode, 'utf-8'))
        print(message)

    def notify_is_warming(self):
        message = 'Warming is {}'.format(self.warming)
        payload = '0'
        if self.warming:
            payload = '1'

        self.notify('/{}/{}/warming'.format(CONFIG['topic'],
                                            CONFIG['client_id']),
                    bytes(payload, 'utf-8'))
        print(message)

    def print_pin_status(self, pin_name, status):
        print("Pin {} is {}".format(pin_name, status))

    def measure_temp(self):
        try:
            roms = self.thermometer.scan()
            self.thermometer.convert_temp()
            time.sleep_ms(500)
            for rom in roms:
                actual_temp = self.thermometer.read_temp(rom) - self.OFFSET
        except:
            time.sleep_ms(500)
            actual_temp = 0

        return actual_temp

    def is_warming_needed(self):
        if self.warming:
            return self.actual_temp < self.desired_temp + self.TOLERANCE
        else:
            return self.actual_temp < self.desired_temp - self.TOLERANCE

    def thermostat(self):
        self.client.check_msg()
        self.actual_temp = self.measure_temp()

        if self.mode == self.MANUAL_MODE:
            self.override_pin.low()
            if self.is_warming_needed():
                self.warming_pin.low()
                self.warming = True
            else:
                self.warming_pin.high()
                self.warming = False
        else:
            self.override_pin.high()
            self.warming_pin.high()
            self.warming = False

        self.notify_actual_mode()
        self.notify_actual_temp()
        self.notify_desired_temp()
        self.notify_is_warming()
        self.notify_name()


class Main(object):
    thermostat = None


def main():
    """
    :return:
    """

    # Wait MAX_CONNECTION_WAIT_PERIODS, if is not connected restart
    MAX_CONNECTION_WAIT_PERIODS = 120
    # Wait period length in seconds
    CONNECTION_WAIT_PERIOD = 1
    # Number of periods spent waiting
    connection_periods_spent = 0

    while not wlan.isconnected():
        print("Waiting for connection")
        time.sleep(CONNECTION_WAIT_PERIOD)
        connection_periods_spent += 1
        if connection_periods_spent > MAX_CONNECTION_WAIT_PERIODS:
            machine.reset()

    Main.thermostat = Thermostat()

    # Load previous settings from file system
    Main.thermostat.load_settings()

    while True:
        Main.thermostat.thermostat()


if __name__ == '__main__':
    main()
