import json
import machine
import network
import onewire, ds18x20
from umqtt.simple import MQTTClient
import time
import utime
from ntptime import settime


class UUIDObject(object):
    def __init__(self):
        self.id = str(time.time())

    def from_json(self, json_dict):
        pass

    def to_json(self):
        pass


class WarmySetup(object):
    def __init__(self):
        self.daily_profiles_assignments = [None] * 7
        self.available_profiles = []
        self.base_temperature = 16.5
        self.last_edit_timestamp = time.time()

    def __get_profile_by_id(self, id):
        return [x for x in self.available_profiles if x['id'] == id][0]

    def get_required_temp(self, timestamp):
        timetuple = utime.localtime(timestamp)
        required_temp = self.base_temperature
        if self.daily_profiles_assignments[timetuple[6]] is not None:
            profile = self.__get_profile_by_id(self.daily_profiles_assignments[timetuple[6]])
            seconds_since_midnight = timetuple[3] * (60 * 60) + timetuple[4] * 60
            for interval in profile['temperatures']:
                if seconds_since_midnight >= interval['start'] and seconds_since_midnight <= interval['end']:
                    required_temp = interval.target_temperature

        return required_temp

    def from_json(self, json_dict):
        self.base_temperature = json_dict['base_temperature']
        self.daily_profiles_assignments = json_dict['daily_profiles_assignments']
        self.available_profiles = json_dict['daily_profiles']
        if 'last_edit_timestamp' in json_dict:
            self.last_edit_timestamp = json_dict['last_edit_timestamp']

    def to_json(self):
        return {
            'base_temperature': self.base_temperature,
            'daily_profiles': self.available_profiles,
            'daily_profiles_assignments': self.daily_profiles_assignments,
            'last_edit_timestamp': self.last_edit_timestamp
        }


class Warmy(UUIDObject):
    DISABLED_MODE = 'DISABLED'
    OVERRIDE_TEMPERATURE_MODE = 'OVERRIDE_TEMPERATURE'
    OVERRIDE_FIRE_MODE = 'OVERRIDE_FIRE'
    AUTO_MODE = 'AUTO'

    def __init__(self):
        self.internal_temperature = 0.0
        self.internal_temperature_last_update = None
        self.external_temperature = 0.0
        self.warming = False
        self.disabled = True
        self.desired_temperature = 0.0
        self.mode = Warmy.DISABLED_MODE
        self.hysteresis = 0.5
        self.setup = WarmySetup()
        self.id = 'warmy_1'

    def set_mode(self, new_mode_dict):
        if new_mode_dict['mode'] == Warmy.DISABLED_MODE:
            self.mode = Warmy.DISABLED_MODE

        if new_mode_dict['mode'] == Warmy.OVERRIDE_TEMPERATURE_MODE \
                and 'temperature' in new_mode_dict:
            self.mode = Warmy.OVERRIDE_TEMPERATURE_MODE
            self.desired_temperature = new_mode_dict['temperature']

        if new_mode_dict['mode'] == Warmy.AUTO_MODE:
            self.mode = Warmy.AUTO_MODE

    def set_temperature(self, temp):
        self.internal_temperature = temp
        self.internal_temperature_last_update = time.time()

    def is_warming_needed(self, desired_temp, measured_temp):
        if self.warming:
            return measured_temp < desired_temp + self.hysteresis
        else:
            return measured_temp < desired_temp - self.hysteresis

    def thermostat(self):

        if self.mode == Warmy.AUTO_MODE:
            self.disabled = False
            desired_temp = self.setup.get_required_temp(time.time())
            if self.is_warming_needed(desired_temp, self.internal_temperature):
                self.warming = True
            else:
                self.warming = False

        if self.mode == Warmy.OVERRIDE_TEMPERATURE_MODE:
            self.disabled = False
            if self.is_warming_needed(self.desired_temperature, self.internal_temperature):
                self.warming = True
            else:
                self.warming = False

        if self.mode == Warmy.DISABLED_MODE:
            self.disabled = True
            self.warming = False

    def to_json(self):
        now = time.time()

        return {
            'fired': self.warming,
            'mode': self.mode,
            'set_point': self.desired_temperature,
            'programmed_set_point': self.desired_temperature,
            'hysteresis': self.hysteresis,
            'timestamp': now,
            'external_temperature': self.external_temperature,
            'external_temperature_last_update': now,
            'internal_temperature': self.internal_temperature,
            'internal_temperature_last_update': self.internal_temperature_last_update,
            'override_end_timestamp': 999999
        }


with open('config.json', 'r') as config:
    config = json.loads(config.read())
    config["essid"]
WIFI_CONFIG = {
    "essid": config['essid'],
    "wifi_password": config['pwd'],
}


class WarmyThermostat(object):
    MAX_ERRORS_NUMBER = 60
    OFFSET = 1.4
    override_pin = machine.Pin(5, machine.Pin.OUT)
    override_pin.high()
    warming_pin = machine.Pin(4, machine.Pin.OUT)
    warming_pin.high()
    thermometer_pin = machine.Pin(2, machine.Pin.IN)
    thermometer = ds18x20.DS18X20(onewire.OneWire(thermometer_pin))
    client = None

    def __init__(self):
        self.errors_count = 0
        self.client = MQTTClient(config['client_id'], config['broker'], config['port'])
        self.client.set_callback(self.on_message_received)

        self.client.connect()
        self.client.subscribe('warmy2/{}/in/command/set-mode'.format(config['client_id']))
        self.client.subscribe('warmy2/{}/in/command/setup'.format(config['client_id']))
        self.warmy = Warmy()
        self.warmy.id = config['client_id']

    def store_settings(self):
        json_settings = self.warmy.setup.to_json()
        print("Settings encoded in json")
        with open('settings.json', 'w') as settings:
            print("File Opened")
            settings.write(json.dumps(json_settings))
            print("File Wrote")

    def load_settings(self):
        try:
            with open('settings.json', 'r') as settings:
                json_settings = json.loads(settings.read())
                setup = WarmySetup()
                setup.from_json(json_settings)
                self.warmy.setup = setup
        except:
            pass

    def on_message_received(self, topic, msg):
        payload_string = msg.decode("utf-8")

        if 'in/command/set-mode' in str(topic):
            self.set_mode(payload_string)

        if 'in/command/setup' in str(topic):
            self.set_config(payload_string)

        self.store_settings()

    def notify(self, topic, payload):
        self.client.publish(topic, payload)

    def notify_state(self):
        self.notify('warmy2/%s/state' % self.warmy.id, json.dumps(self.warmy.to_json()))

    def notify_config(self):
        self.notify('warmy2/%s/setup' % self.warmy.id, json.dumps(self.warmy.setup.to_json()))

    def set_mode(self, payload_string):
        self.warmy.set_mode(json.loads(payload_string))

    def set_config(self, payload_string):
        self.warmy.setup.from_json(json.loads(payload_string))

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

    def thermostat(self):
        self.client.check_msg()
        actual_temp = self.measure_temp()

        self.warmy.set_temperature(actual_temp)

        if self.warmy.disabled:
            self.override_pin.high()
            self.warming_pin.high()
        else:
            self.override_pin.low()
            if self.warmy.warming:
                self.warming_pin.high()
            else:
                self.warming_pin.low()

        print(
            """
Mode: %s
Override: %s
Warming: %s
Temp: %s
            """ % (
                self.warmy.mode,
                not self.warmy.disabled,
                self.warmy.warming,
                self.warmy.internal_temperature
            )
        )

        self.notify_state()
        self.notify_config()


def main():
    """
    :return:
    """
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(WIFI_CONFIG['essid'], WIFI_CONFIG['wifi_password'])
        wlan.config('mac')
        wlan.ifconfig()
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

        settime()
        thermostat = WarmyThermostat()
        # Load previous settings from file system
        thermostat.load_settings()
        while True:
            thermostat.thermostat()
    except Exception as e:
        print(e)
        machine.reset()



if __name__ == '__main__':
    main()
