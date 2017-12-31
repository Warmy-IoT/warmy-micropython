import uuid

from datetime import datetime


class JSONSerializable(object):
    def from_json(self, json_dict):
        pass

    def to_json(self):
        pass


class UUIDObject(JSONSerializable):
    def __init__(self):
        self.id = uuid.uuid4()


class TempInterval(UUIDObject):
    def __init__(self):
        super(TempInterval, self).__init__()
        self.start = 0
        self.end = 0
        self.target_temperature = 0

    def from_json(self, json_dict):
        self.start = json_dict['start']
        self.end = json_dict['end']
        self.target_temperature = json_dict['target_temperature']

    def to_json(self):
        return {

            'start': self.start,
            'end': self.end,
            'target_temperature': self.target_temperature
        }


class TempProfile(UUIDObject):
    def __init__(self):
        super(TempProfile, self).__init__()
        self.name = ''
        self.temperatures = [
        ]

    def order_intervals(self):
        self.temperatures = sorted(self.temperatures, key=lambda x: x.start, reverse=False)

    def from_json(self, json_dict):
        self.id = json_dict['id']
        self.name = json_dict['name']
        self.temperatures = []
        for t in json_dict['temperatures']:
            ti = TempInterval()
            ti.from_json(t)
            self.temperatures.append(ti)

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'temperatures': [t.to_json() for t in self.temperatures]
        }


class WarmySetup(JSONSerializable):
    def __init__(self):
        self.daily_profiles_assignments = [None] * 7
        self.available_profiles = []
        self.base_temperature = 16.5

    def __get_profile_by_id(self, id):
        return [x for x in self.available_profiles if x.id == id][0]

    def get_required_temp(self, date_time):
        weekday = date_time.weekday()

        required_temp = self.base_temperature

        if self.daily_profiles_assignments[weekday] is not None:

            profile = self.__get_profile_by_id(self.daily_profiles_assignments[weekday])
            assert (isinstance(profile, TempProfile))
            seconds_since_midnight = (
                date_time -
                date_time.replace(hour=0,
                                  minute=0,
                                  second=0,
                                  microsecond=0)
            ).total_seconds()

            for interval in profile.temperatures:
                assert (isinstance(interval, TempInterval))
                if seconds_since_midnight >= interval.start and seconds_since_midnight <= interval.end:
                    required_temp = interval.target_temperature
        return required_temp

    def from_json(self, json_dict):
        self.base_temperature = json_dict['base_temperature']
        self.daily_profiles_assignments = json_dict['daily_profiles_assignments']
        for p in json_dict['daily_profiles']:
            pr = TempProfile()
            pr.from_json(p)
            self.available_profiles.append(pr)

    def to_json(self):
        return {
            'base_temperature': self.base_temperature,
            'daily_profiles': [x.to_json() for x in self.available_profiles],
            'daily_profiles_assignments': self.daily_profiles_assignments
        }


class Warmy(object):
    DISABLED_MODE = 'DISABLED'
    OVERRIDE_TEMPERATURE_MODE = 'OVERRIDE_TEMPERATURE'
    OVERRIDE_FIRE_MODE = 'OVERRIDE_FIRE'
    AUTO_MODE = 'AUTO'

    def __init__(self):
        self.internal_temperature = 0.0
        self.external_temperature = 0.0
        self.warming = False
        self.disabled = True
        self.desired_temperature = 0.0
        self.mode = Warmy.DISABLED_MODE
        self.hysteresis = 0.5
        self.setup = WarmySetup()

    def set_mode(self, new_mode_dict):
        if new_mode_dict['mode'] == Warmy.DISABLED_MODE:
            self.mode = Warmy.DISABLED_MODE

        if new_mode_dict['mode'] == Warmy.OVERRIDE_TEMPERATURE_MODE \
                and 'temperature' in new_mode_dict:
            self.mode = Warmy.OVERRIDE_TEMPERATURE_MODE
            self.desired_temperature = new_mode_dict['temperature']

        if new_mode_dict['mode'] == Warmy.AUTO_MODE:
            self.mode = Warmy.AUTO_MODE

    def is_warming_needed(self, desired_temp, measured_temp):
        if self.warming:
            return measured_temp < desired_temp + self.hysteresis
        else:
            return measured_temp < desired_temp - self.hysteresis

    def thermostat(self):

        if self.mode == Warmy.AUTO_MODE:
            self.disabled = False
            desired_temp = self.setup.get_required_temp(datetime.now())
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
