import json
import machine
import network
import onewire,ds18x20
from umqtt.simple import MQTTClient
import uuid
import time
from datetime import datetime
class UUIDObject(object):
 def __init__(self):
  self.id=uuid.uuid4()
 def from_json(self,json_dict):
  pass
 def to_json(self):
  pass
class TempInterval(UUIDObject):
 def __init__(self):
  super(TempInterval,self).__init__()
  self.start=0
  self.end=0
  self.target_temperature=0
 def from_json(self,json_dict):
  self.start=json_dict['start']
  self.end=json_dict['end']
  self.target_temperature=json_dict['target_temperature']
 def to_json(self):
  return{'start':self.start,'end':self.end,'target_temperature':self.target_temperature}
class TempProfile(UUIDObject):
 def __init__(self):
  super(TempProfile,self).__init__()
  self.name=''
  self.temperatures=[]
 def order_intervals(self):
  self.temperatures=sorted(self.temperatures,key=lambda x:x.start,reverse=False)
 def from_json(self,json_dict):
  self.id=json_dict['id']
  self.name=json_dict['name']
  self.temperatures=[]
  for t in json_dict['temperatures']:
   ti=TempInterval()
   ti.from_json(t)
   self.temperatures.append(ti)
  self.order_intervals()
 def to_json(self):
  return{'id':self.id,'name':self.name,'temperatures':[t.to_json()for t in self.temperatures]}
class WarmySetup(object):
 def __init__(self):
  self.daily_profiles_assignments=[None]*7
  self.available_profiles=[]
  self.base_temperature=16.5
 def __get_profile_by_id(self,id):
  return[x for x in self.available_profiles if x.id==id][0]
 def get_required_temp(self,date_time):
  weekday=date_time.weekday()
  required_temp=self.base_temperature
  if self.daily_profiles_assignments[weekday]is not None:
   profile=self.__get_profile_by_id(self.daily_profiles_assignments[weekday])
   assert(isinstance(profile,TempProfile))
   seconds_since_midnight=(date_time-date_time.replace(hour=0,minute=0,second=0,microsecond=0)).total_seconds()
   for interval in profile.temperatures:
    assert(isinstance(interval,TempInterval))
    if seconds_since_midnight>=interval.start and seconds_since_midnight<=interval.end:
     required_temp=interval.target_temperature
  return required_temp
 def from_json(self,json_dict):
  self.base_temperature=json_dict['base_temperature']
  self.daily_profiles_assignments=json_dict['daily_profiles_assignments']
  for p in json_dict['daily_profiles']:
   pr=TempProfile()
   pr.from_json(p)
   self.available_profiles.append(pr)
 def to_json(self):
  return{'base_temperature':self.base_temperature,'daily_profiles':[x.to_json()for x in self.available_profiles],'daily_profiles_assignments':self.daily_profiles_assignments}
class Warmy(UUIDObject):
 DISABLED_MODE='DISABLED'
 OVERRIDE_TEMPERATURE_MODE='OVERRIDE_TEMPERATURE'
 OVERRIDE_FIRE_MODE='OVERRIDE_FIRE'
 AUTO_MODE='AUTO'
 def __init__(self):
  self.internal_temperature=0.0
  self.internal_temperature_last_update=None
  self.external_temperature=0.0
  self.warming=False
  self.disabled=True
  self.desired_temperature=0.0
  self.mode=Warmy.DISABLED_MODE
  self.hysteresis=0.5
  self.setup=WarmySetup()
  self.id='warmy_1'
 def set_mode(self,new_mode_dict):
  if new_mode_dict['mode']==Warmy.DISABLED_MODE:
   self.mode=Warmy.DISABLED_MODE
  if new_mode_dict['mode']==Warmy.OVERRIDE_TEMPERATURE_MODE and 'temperature' in new_mode_dict:
   self.mode=Warmy.OVERRIDE_TEMPERATURE_MODE
   self.desired_temperature=new_mode_dict['temperature']
  if new_mode_dict['mode']==Warmy.AUTO_MODE:
   self.mode=Warmy.AUTO_MODE
 def set_temperature(self,temp):
  self.internal_temperature=temp
  self.internal_temperature_last_update=time.time()
 def is_warming_needed(self,desired_temp,measured_temp):
  if self.warming:
   return measured_temp<desired_temp+self.hysteresis
  else:
   return measured_temp<desired_temp-self.hysteresis
 def thermostat(self):
  if self.mode==Warmy.AUTO_MODE:
   self.disabled=False
   desired_temp=self.setup.get_required_temp(datetime.now())
   if self.is_warming_needed(desired_temp,self.internal_temperature):
    self.warming=True
   else:
    self.warming=False
  if self.mode==Warmy.OVERRIDE_TEMPERATURE_MODE:
   self.disabled=False
   if self.is_warming_needed(self.desired_temperature,self.internal_temperature):
    self.warming=True
   else:
    self.warming=False
  if self.mode==Warmy.DISABLED_MODE:
   self.disabled=True
   self.warming=False
 def to_json(self):
  now=time.time()
  return{'fired':self.warming,'mode':self.mode,'set_point':self.desired_temperature,'hysteresis':self.hysteresis,'timestamp':now,'external_temperature':self.external_temperature,'external_temperature_last_update':now,'internal_temperature':self.internal_temperature,'internal_temperature_last_update':self.internal_temperature_last_update}
with open('config.json','r')as config:
 config=json.loads(config.read())
 config["essid"]
WIFI_CONFIG={"essid":config['essid'],"wifi_password":config['pwd'],}
wlan=network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_CONFIG['essid'],WIFI_CONFIG['wifi_password'])
wlan.config('mac')
wlan.ifconfig()
class WarmyThermostat(object):
 MAX_ERRORS_NUMBER=60
 OFFSET=1.4
 override_pin=machine.Pin(5,machine.Pin.OUT)
 override_pin.high()
 warming_pin=machine.Pin(4,machine.Pin.OUT)
 warming_pin.high()
 thermometer_pin=machine.Pin(2,machine.Pin.IN)
 thermometer=ds18x20.DS18X20(onewire.OneWire(thermometer_pin))
 client=None
 def __init__(self):
  self.errors_count=0
  self.client=MQTTClient(config['client_id'],config['broker'],config['port'])
  self.client.set_callback(self.on_message_received)
  self.client.connect()
  self.client.subscribe('/{}/{}/mode/set'.format(config['topic'],config['client_id']))
  self.client.subscribe('/{}/{}/manual/desired_temperature/set'.format(config['topic'],config['client_id']))
  self.warmy=Warmy()
 def store_settings(self):
  json_settings=self.warmy.setup.to_json()
  with open('settings.json','w')as settings:
   settings.write(json.dumps(json_settings))
 def load_settings(self):
  try:
   with open('settings.json','r')as settings:
    json_settings=json.loads(settings.read())
    setup=WarmySetup()
    setup.from_json(json_settings)
    self.warmy.setup=setup
  except:
   pass
 def on_message_received(self,topic,msg):
  payload_string=msg.decode("utf-8")
  if 'desired_temperature/set' in str(topic):
   self.desired_temp=float(payload_string)
  if 'mode/set' in str(topic):
   self.mode=payload_string
  self.store_settings()
 def notify(self,topic,payload):
  try:
   self.client.publish(topic,payload)
   self.errors_count=0
  except:
   self.errors_count+=1
   if self.errors_count>WarmyThermostat.MAX_ERRORS_NUMBER:
    machine.reset()
 def notify_state(self):
  self.notify('warmy2/%s/state'%self.warmy.id,json.dumps(self.warmy.to_json()))
 def notify_config(self):
  self.notify('warmy2/%s/config'%self.warmy.id,json.dumps(self.warmy.setup.to_json()))
 def set_mode(self,payload_string):
  self.warmy.set_mode(json.loads(payload_string))
 def set_config(self,payload_string):
  setup=WarmySetup()
  setup.from_json(json.loads(payload_string))
  self.warmy.setup=setup
 def measure_temp(self):
  try:
   roms=self.thermometer.scan()
   self.thermometer.convert_temp()
   time.sleep_ms(500)
   for rom in roms:
    actual_temp=self.thermometer.read_temp(rom)-self.OFFSET
  except:
   time.sleep_ms(500)
   actual_temp=0
  return actual_temp
 def thermostat(self):
  self.client.check_msg()
  actual_temp=self.measure_temp()
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
  print( """
Mode: %sOverride: %sWarming:%sTemp: %s            """  % (
  self.warmy.mode,not self.warmy.disabled,self.warmy.warming,self.warmy.internal_temperature)
  )
  self.notify_state()self.notify_config()def main():MAX_CONNECTION_WAIT_PERIODS=120 CONNECTION_WAIT_PERIOD=1 connection_periods_spent=0 while not wlan.isconnected():print("Waiting for connection")time.sleep(CONNECTION_WAIT_PERIOD)connection_periods_spent+=1 if connection_periods_spent>MAX_CONNECTION_WAIT_PERIODS:machine.reset()thermostat=WarmyThermostat()thermostat.load_settings()while True:thermostat.thermostat()if __name__=='__main__':main()
# Created by pyminifier (https://github.com/liftoff/pyminifier)
