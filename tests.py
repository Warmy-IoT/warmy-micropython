import json
from datetime import datetime

from jsondiff import diff

from warmy import WarmySetup, TempProfile, TempInterval


def test_profiles_creation():
    hour = 60 * 60

    p = WarmySetup()

    giorno_lavorativo = TempProfile()

    mattina = TempInterval()
    mattina.start = 8 * hour
    mattina.end = 12 * hour
    mattina.target_temperature = 18.0

    giorno_lavorativo.temperatures.append(mattina)

    pomeriggio = TempInterval()
    pomeriggio.start = 13 * hour
    pomeriggio.end = 16 * hour
    pomeriggio.target_temperature = 12.0

    giorno_lavorativo.temperatures.append(pomeriggio)

    sera = TempInterval()
    sera.start = 20 * hour
    sera.end = 23 * hour
    sera.target_temperature = 20.0

    giorno_lavorativo.temperatures.append(sera)

    giorno_feriale = TempProfile()

    feriale = TempInterval()
    feriale.start = 8 * hour
    feriale.end = 20 * hour
    feriale.target_temperature = 18.5

    giorno_feriale.temperatures.append(feriale)

    p.available_profiles.append(giorno_lavorativo)
    p.available_profiles.append(giorno_feriale)

    for i in range(0, 5):
        p.daily_profiles_assignments[i] = giorno_lavorativo.id

    for i in range(5, 7):
        p.daily_profiles_assignments[i] = giorno_feriale.id

    monday = datetime(2017, 12, 25, 12, 30)

    tuesday = datetime(2017, 12, 26, 20, 30)

    sunday = datetime(2017, 12, 24, 12, 00)

    pairs = [
        (p.get_required_temp(monday), "Monday at 12:30", 16.5),
        (p.get_required_temp(tuesday), "Tuesday at 20:30", 20.0),
        (p.get_required_temp(sunday), "Sunday at 12:00", 18.5)
    ]

    for t in pairs:
        assert (t[0] == t[2])
        print("%s on %s, expected %s" % t)


def test_setup_decode():
    json_setup = """
{"base_temperature":16.5,"daily_profiles":[{"id":"giorno_lavorativo","name":"Giorno Lavorativo","temperatures":[{"start":0,"end":3600,"target_temperature":19},{"start":27000,"end":32400,"target_temperature":21},{"start":64800,"end":86399,"target_temperature":19}]},{"id":"weekends","name":"Week end","temperatures":[{"start":64800,"end":86399,"target_temperature":19}]}],"daily_profiles_assignments":["weekends","giorno_lavorativo","giorno_lavorativo","giorno_lavorativo","giorno_lavorativo","giorno_lavorativo","weekends"]}
    """

    json_setup = """
{"base_temperature":16.5,"daily_profiles":[{"id":"giorno_lavorativo","name":"Giorno Lavorativo","temperatures":[{"start":0,"end":3600,"target_temperature":19},{"start":27000,"end":32400,"target_temperature":21},{"start":64800,"end":86399,"target_temperature":19}]},{"id":"weekends","name":"Week end","temperatures":[{"start":64800,"end":86399,"target_temperature":19}]}],"daily_profiles_assignments":["weekends","giorno_lavorativo","giorno_lavorativo","giorno_lavorativo","giorno_lavorativo","giorno_lavorativo","weekends"],"last_edit_timestamp":1508875332}
    """

    setup = WarmySetup()
    setup.from_json(json.loads(json_setup))

    assert (diff(setup.to_json(), json.loads(json_setup)) == {})

if __name__ == '__main__':
    test_profiles_creation()
    test_setup_decode()