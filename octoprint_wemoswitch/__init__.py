# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.access.permissions import Permissions, ADMIN_GROUP, USER_GROUP
from flask_babel import gettext
from octoprint.events import eventManager, Events
from octoprint.util import RepeatedTimer
import socket
import flask
import logging
import os
import re
import threading
import time
import pywemo

try:
	from octoprint.util import ResettableTimer
except ImportError:
	class ResettableTimer(threading.Thread):
		def __init__(self, interval, function, args=None, kwargs=None, on_reset=None, on_cancelled=None):
			threading.Thread.__init__(self)
			self._event = threading.Event()
			self._mutex = threading.Lock()
			self.is_reset = True

			if args is None:
				args = []
			if kwargs is None:
				kwargs = dict()

			self.interval = interval
			self.function = function
			self.args = args
			self.kwargs = kwargs
			self.on_cancelled = on_cancelled
			self.on_reset = on_reset

		def run(self):
			while self.is_reset:
				with self._mutex:
					self.is_reset = False
				self._event.wait(self.interval)

			if not self._event.isSet():
				self.function(*self.args, **self.kwargs)
			with self._mutex:
				self._event.set()

		def cancel(self):
			with self._mutex:
				self._event.set()

			if callable(self.on_cancelled):
				self.on_cancelled()

		def reset(self, interval=None):
			with self._mutex:
				if interval:
					self.interval = interval

				self.is_reset = True
				self._event.set()
				self._event.clear()

			if callable(self.on_reset):
				self.on_reset()


class wemoswitchPlugin(octoprint.plugin.SettingsPlugin,
					   octoprint.plugin.AssetPlugin,
					   octoprint.plugin.TemplatePlugin,
					   octoprint.plugin.SimpleApiPlugin,
					   octoprint.plugin.StartupPlugin,
					   octoprint.plugin.EventHandlerPlugin):

	def __init__(self):
		self._logger = logging.getLogger("octoprint.plugins.wemoswitch")
		self._wemoswitch_logger = logging.getLogger("octoprint.plugins.wemoswitch.debug")
		self.discovered_devices = []
		self.abortTimeout = 0
		self._timeout_value = None
		self._abort_timer = None
		self._countdown_active = False
		self._waitForHeaters = False
		self._waitForTimelapse = False
		self._timelapse_active = False
		self._skipIdleTimer = False
		self.powerOffWhenIdle = False
		self._idleTimer = None
		self.idleTimeout = 30
		self.idleIgnoreCommands = 'M105'
		self._idleIgnoreCommandsArray = []
		self.idleTimeoutWaitTemp = 50

	##~~ StartupPlugin mixin

	def on_startup(self, host, port):
		# setup customized logger
		from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
		wemoswitch_logging_handler = CleaningTimedRotatingFileHandler(self._settings.get_plugin_logfile_path(postfix="debug"), when="D", backupCount=3)
		wemoswitch_logging_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
		wemoswitch_logging_handler.setLevel(logging.DEBUG)

		self._wemoswitch_logger.addHandler(wemoswitch_logging_handler)
		self._wemoswitch_logger.setLevel(
			logging.DEBUG if self._settings.get_boolean(["debug_logging"]) else logging.INFO)
		self._wemoswitch_logger.propagate = False

	def on_after_startup(self):
		self._logger.info("WemoSwitch loaded!")

		self.abortTimeout = self._settings.get_int(["abortTimeout"])
		self._wemoswitch_logger.debug("abortTimeout: %s" % self.abortTimeout)

		self.powerOffWhenIdle = self._settings.get_boolean(["powerOffWhenIdle"])
		self._wemoswitch_logger.debug("powerOffWhenIdle: %s" % self.powerOffWhenIdle)

		self.idleTimeout = self._settings.get_int(["idleTimeout"])
		self._wemoswitch_logger.debug("idleTimeout: %s" % self.idleTimeout)
		self.idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		self._idleIgnoreCommandsArray = self.idleIgnoreCommands.split(',')
		self._wemoswitch_logger.debug("idleIgnoreCommands: %s" % self.idleIgnoreCommands)
		self.idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])
		self._wemoswitch_logger.debug("idleTimeoutWaitTemp: %s" % self.idleTimeoutWaitTemp)
		if self._settings.get_boolean(["event_on_startup_monitoring"]):
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_startup"] is True:
					self.turn_on(plug["ip"])
		self._reset_idle_timer()

	##~~ SettingsPlugin mixin

	def get_discovered_device(self, index):
		tmp_ret = self.discovered_devices[index]
		return {"label": tmp_ret.name,
				"ip": "{}:{}".format(tmp_ret.host, tmp_ret.port),
				"sn": tmp_ret.serialnumber}

	def get_discovered_devices(self):
		self._wemoswitch_logger.debug("Discovering devices")
		self.discovered_devices = pywemo.discover_devices()
		tmp_ret = []
		for index in range(len(self.discovered_devices)):
			d = self.get_discovered_device(index)
			tmp_ret.append(d)
		return tmp_ret

	def get_settings_defaults(self):
		return dict(
			debug_logging=False,
			arrSmartplugs=[],
			pollingInterval=15,
			pollingEnabled=False,
			thermal_runaway_monitoring=False,
			thermal_runaway_max_bed=0,
			thermal_runaway_max_extruder=0,
			abortTimeout=30,
			powerOffWhenIdle=False,
			idleTimeout=30,
			idleIgnoreCommands='M105',
			idleTimeoutWaitTemp=50,
			event_on_upload_monitoring=False,
			event_on_startup_monitoring=False
		)

	def on_settings_save(self, data):
		old_debug_logging = self._settings.get_boolean(["debug_logging"])
		old_power_off_when_idle = self._settings.get_boolean(["powerOffWhenIdle"])

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		self.abortTimeout = self._settings.get_int(["abortTimeout"])
		self.powerOffWhenIdle = self._settings.get_boolean(["powerOffWhenIdle"])

		self.idleTimeout = self._settings.get_int(["idleTimeout"])
		self.idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		self._idleIgnoreCommandsArray = self.idleIgnoreCommands.split(',')
		self.idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])

		if self.powerOffWhenIdle != old_power_off_when_idle:
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

		if self.powerOffWhenIdle:
			self._wemoswitch_logger.debug("Settings saved, Automatic Power Off Enabled, starting idle timer...")
			self._reset_idle_timer()

		new_debug_logging = self._settings.get_boolean(["debug_logging"])
		if old_debug_logging != new_debug_logging:
			if new_debug_logging:
				self._wemoswitch_logger.setLevel(logging.DEBUG)
			else:
				self._wemoswitch_logger.setLevel(logging.INFO)

	def get_settings_version(self):
		return 3

	def on_settings_migrate(self, target, current=None):
		if current is None or current < 1:
			# Reset plug settings to defaults.
			self._logger.debug("Resetting arrSmartplugs for wemoswitch settings.")
			self._settings.set(['arrSmartplugs'], self.get_settings_defaults()["arrSmartplugs"])
		if current == 1:
			self._logger.debug("Adding new plug settings thermal_runaway, automaticShutdownEnabled, event_on_upload, event_on_startup.")
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["thermal_runaway"] = False
				plug["automaticShutdownEnabled"] = False
				plug["event_on_upload"] = False
				plug["event_on_startup"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)
		if current == 2:
			self._logger.debug("Adding new plug settings automaticShutdownEnabled, event_on_upload, event_on_startup.")
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["automaticShutdownEnabled"] = False
				plug["event_on_upload"] = False
				plug["event_on_startup"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/jquery-ui.min.js", "js/knockout-sortable.1.2.0.js", "js/fontawesome-iconpicker.js", "js/ko.iconpicker.js", "js/wemoswitch.js"],
			css=["css/font-awesome.min.css", "css/font-awesome-v4-shims.min.css", "css/fontawesome-iconpicker.css", "css/wemoswitch.css"]
		)

	##~~ TemplatePlugin mixin

	def get_template_configs(self):
		return [
			dict(type="navbar", custom_bindings=True),
			dict(type="settings", custom_bindings=True),
			dict(type="sidebar", icon="plug", custom_bindings=True, data_bind="visible: show_sidebar", template_header="wemoswitch_sidebar_header.jinja2")
		]

	##~~ SimpleApiPlugin mixin

	def turn_on(self, plugip):
		self._wemoswitch_logger.debug("Turning on %s." % plugip)
		plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
		self._wemoswitch_logger.debug(plug)
		chk = self.sendCommand("on", plugip)
		if chk == 0:
			self.check_status(plugip)
			if plug["autoConnect"]:
				t = threading.Timer(int(plug["autoConnectDelay"]), self._printer.connect)
				t.start()
			if plug["sysCmdOn"]:
				t = threading.Timer(int(plug["sysCmdOnDelay"]), os.system, args=[plug["sysRunCmdOn"]])
				t.start()
			self._reset_idle_timer()
			return "on"

	def turn_off(self, plugip):
		self._wemoswitch_logger.debug("Turning off %s." % plugip)
		plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
		self._wemoswitch_logger.debug(plug)
		if plug["sysCmdOff"]:
			t = threading.Timer(int(plug["sysCmdOffDelay"]), os.system, args=[plug["sysRunCmdOff"]])
			t.start()
		if plug["autoDisconnect"]:
			self._printer.disconnect()
			time.sleep(int(plug["autoDisconnectDelay"]))
		chk = self.sendCommand("off", plugip)
		if chk == 0:
			self.check_status(plugip)

	def check_status(self, plugip):
		self._wemoswitch_logger.debug("Checking status of %s." % plugip)
		if plugip != "":
			chk = self.sendCommand("info", plugip)
			if chk == 1:
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="on", ip=plugip))
			elif chk == 8:
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="on", ip=plugip))
			elif chk == 0:
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="off", ip=plugip))
			else:
				self._wemoswitch_logger.debug(chk)
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="unknown", ip=plugip))

	def get_api_commands(self):
		return dict(turnOn=["ip"],
					turnOff=["ip"],
					checkStatus=["ip"],
					enableAutomaticShutdown=[],
					disableAutomaticShutdown=[],
					abortAutomaticShutdown=[])

	def on_api_get(self, request):
		if not Permissions.PLUGIN_WEMOSWITCH_CONTROL.can():
			return flask.make_response("Insufficient rights", 403)

		if request.args.get("discover_devices"):
			return flask.jsonify({"discovered_devices": self.get_discovered_devices()})

	def on_api_command(self, command, data):
		if not Permissions.PLUGIN_WEMOSWITCH_CONTROL.can():
			return flask.make_response("Insufficient rights", 403)

		if command == 'turnOn':
			self.turn_on("{ip}".format(**data))
		elif command == 'turnOff':
			self.turn_off("{ip}".format(**data))
		elif command == 'checkStatus':
			self.check_status("{ip}".format(**data))
		elif command == 'enableAutomaticShutdown':
			self._wemoswitch_logger.debug("enabling automatic power off on idle")
			self.powerOffWhenIdle = True
			self._reset_idle_timer()
			self._settings.set_boolean(["powerOffWhenIdle"], True)
			self._settings.save(trigger_event=True)
			return flask.jsonify(dict(powerOffWhenIdle=self.powerOffWhenIdle))
		elif command == 'disableAutomaticShutdown':
			self._wemoswitch_logger.debug("disabling automatic power off on idle")
			self.powerOffWhenIdle = False
			self._stop_idle_timer()
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._timeout_value = None
			self._settings.set_boolean(["powerOffWhenIdle"], False)
			self._settings.save(trigger_event=True)
			return flask.jsonify(dict(powerOffWhenIdle=self.powerOffWhenIdle))
		elif command == 'abortAutomaticShutdown':
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._timeout_value = None
			self._wemoswitch_logger.debug("Power off aborted.")
			self._wemoswitch_logger.debug("Restarting idle timer.")
			self._reset_idle_timer()

	##~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		# Client Opened Event
		if event == Events.CLIENT_OPENED:
			if self._settings.get_boolean(["powerOffWhenIdle"]):
				self._reset_idle_timer()
			self._plugin_manager.send_plugin_message(self._identifier, dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout", timeout_value=self._timeout_value))
			return
		# Print Started Event
		if event == Events.PRINT_STARTED and self.powerOffWhenIdle is True:
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
				self._tplinksmartplug_logger.debug("Power off aborted because starting new print.")
			if self._idleTimer is not None:
				self._reset_idle_timer()
			self._timeout_value = None
			self._plugin_manager.send_plugin_message(self._identifier, dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout", timeout_value=self._timeout_value))
		# Cancelled Print Interpreted Event
		if event == Events.PRINT_FAILED and not self._printer.is_closed_or_error() and self.powerOffWhenIdle is True:
			self._reset_idle_timer()
		# Print Done Event
		if event == Events.PRINT_DONE and self.powerOffWhenIdle is True:
			self._reset_idle_timer()
		# Timelapse Events
		if self.powerOffWhenIdle is True and event == Events.MOVIE_RENDERING:
			self._wemoswitch_logger.debug("Timelapse generation started: %s" % payload.get("movie_basename", ""))
			self._timelapse_active = True

		if self._timelapse_active and event == Events.MOVIE_DONE or event == Events.MOVIE_FAILED:
			self._wemoswitch_logger.debug("Timelapse generation finished: %s. Return Code: %s" % (payload.get("movie_basename", ""), payload.get("returncode", "completed")))
			self._timelapse_active = False

		# File Uploaded Event
		if event == Events.UPLOAD and self._settings.getBoolean(["event_on_upload_monitoring"]):
			if payload.get("print", False): # implemented in OctoPrint version 1.4.1
				self._wemoswitch_logger.debug("File uploaded: %s. Turning enabled plugs on." % payload.get("name", ""))
				self._wemoswitch_logger.debug(payload)
				for plug in self._settings.get(['arrSmartplugs']):
					self._wemoswitch_logger.debug(plug)
					if plug["event_on_upload"] is True and not self._printer.is_ready():
						self._wemoswitch_logger.debug("powering on %s due to %s event." % (plug["ip"], event))
						response = self.turn_on(plug["ip"])
						if response == "on":
							self._wemoswitch_logger.debug("power on successful for %s attempting connection in %s seconds" % (plug["ip"], plug.get("autoConnectDelay", "0")))
							if payload.get("path", False) is not False and payload.get("target") == "local":
								time.sleep(int(plug.get("autoConnectDelay", "0"))+1)
								if self._printer.is_ready():
									self._wemoswitch_logger.debug("printer connected starting print of %s" % (payload.get("path", "")))
									self._printer.select_file(payload.get("path"), False, printAfterSelect=True)

	##~~ Idle Timeout

	def _start_idle_timer(self):
		self._stop_idle_timer()

		if self.powerOffWhenIdle:
			self._idleTimer = ResettableTimer(self.idleTimeout * 60, self._idle_poweroff)
			self._idleTimer.start()

	def _stop_idle_timer(self):
		if self._idleTimer:
			self._idleTimer.cancel()
			self._idleTimer = None

	def _reset_idle_timer(self):
		try:
			if self._idleTimer.is_alive():
				self._idleTimer.reset()
			else:
				raise Exception()
		except:
			self._start_idle_timer()

	def _idle_poweroff(self):
		if not self.powerOffWhenIdle:
			return

		if self._waitForHeaters:
			return

		if self._waitForTimelapse:
			return

		if self._printer.is_printing() or self._printer.is_paused():
			return

		self._wemoswitch_logger.debug("Idle timeout reached after %s minute(s). Waiting for hot end to cool prior to powering off plugs." % self.idleTimeout)
		if self._wait_for_heaters():
			self._wemoswitch_logger.debug("Heaters below temperature.")
			if self._wait_for_timelapse():
				self._timer_start()
		else:
			self._wemoswitch_logger.debug("Aborted power off due to activity.")

	##~~ Timelapse Monitoring

	def _wait_for_timelapse(self):
		self._waitForTimelapse = True
		self._wemoswitch_logger.debug("Checking timelapse status before shutting off power...")

		while True:
			if not self._waitForTimelapse:
				return False

			if not self._timelapse_active:
				self._waitForTimelapse = False
				return True

			self._wemoswitch_logger.debug("Waiting for timelapse before shutting off power...")
			time.sleep(5)

	##~~ Temperature Cooldown

	def _wait_for_heaters(self):
		self._waitForHeaters = True
		heaters = self._printer.get_current_temperatures()

		for heater, entry in heaters.items():
			target = entry.get("target")
			if target is None:
				# heater doesn't exist in fw
				continue

			try:
				temp = float(target)
			except ValueError:
				# not a float for some reason, skip it
				continue

			if temp != 0:
				self._wemoswitch_logger.debug("Turning off heater: %s" % heater)
				self._skipIdleTimer = True
				self._printer.set_temperature(heater, 0)
				self._skipIdleTimer = False
			else:
				self._wemoswitch_logger.debug("Heater %s already off." % heater)

		while True:
			if not self._waitForHeaters:
				return False

			heaters = self._printer.get_current_temperatures()

			highest_temp = 0
			heaters_above_waittemp = []
			for heater, entry in heaters.items():
				if not heater.startswith("tool"):
					continue

				actual = entry.get("actual")
				if actual is None:
					# heater doesn't exist in fw
					continue

				try:
					temp = float(actual)
				except ValueError:
					# not a float for some reason, skip it
					continue

				self._wemoswitch_logger.debug("Heater %s = %sC" % (heater, temp))
				if temp > self.idleTimeoutWaitTemp:
					heaters_above_waittemp.append(heater)

				if temp > highest_temp:
					highest_temp = temp

			if highest_temp <= self.idleTimeoutWaitTemp:
				self._waitForHeaters = False
				return True

			self._wemoswitch_logger.debug("Waiting for heaters(%s) before shutting power off..." % ', '.join(heaters_above_waittemp))
			time.sleep(5)

	##~~ Abort Power Off Timer

	def _timer_start(self):
		if self._abort_timer is not None:
			return

		self._wemoswitch_logger.debug("Starting abort power off timer.")

		self._timeout_value = self.abortTimeout
		self._abort_timer = RepeatedTimer(1, self._timer_task)
		self._abort_timer.start()

	def _timer_task(self):
		if self._timeout_value is None:
			return

		self._timeout_value -= 1
		self._plugin_manager.send_plugin_message(self._identifier, dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout", timeout_value=self._timeout_value))
		if self._timeout_value <= 0:
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._shutdown_system()

	def _shutdown_system(self):
		self._wemoswitch_logger.debug("Automatically powering off enabled plugs.")
		for plug in self._settings.get(['arrSmartplugs']):
			if plug.get("automaticShutdownEnabled", False):
				self.turn_off("{ip}".format(**plug))

	##~~ Utilities

	def plug_search(self, list, key, value):
		for item in list:
			if item[key] == value:
				return item

	def sendCommand(self, cmd, plugip):
		# try to connect via ip address
		port = None
		try:
			if ':' in plugip:
				plugip, port = plugip.split(':', 1)
				port = int(port)
			socket.inet_aton(plugip)
			self._wemoswitch_logger.debug("IP %s is valid." % plugip)
		except socket.error or ValueError:
			# try to convert hostname to ip
			self._wemoswitch_logger.debug("Invalid ip %s trying hostname." % plugip)
			try:
				plugip = socket.gethostbyname(plugip)
				self._wemoswitch_logger.debug("Hostname %s is valid." % plugip)
			except (socket.herror, socket.gaierror):
				self._wemoswitch_logger.debug("Invalid hostname %s." % plugip)
				return 3

		try:
			self._wemoswitch_logger.debug("Attempting to connect to %s" % plugip)
			if port is None:
				port = pywemo.ouimeaux_device.probe_wemo(plugip)
			url = 'http://%s:%s/setup.xml' % (plugip, port)
			url = url.replace(':None', '')
			self._wemoswitch_logger.debug("Getting device info from %s" % url)
			device = pywemo.discovery.device_from_description(url, None)

			self._wemoswitch_logger.debug("Found device %s" % device)
			self._wemoswitch_logger.debug("Sending command %s to %s" % (cmd, plugip))

			if cmd == "info":
				return device.get_state()
			elif cmd == "on":
				device.on()
				return 0
			elif cmd == "off":
				device.off()
				return 0

		except socket.error:
			self._wemoswitch_logger.debug("Could not connect to %s." % plugip)
			return 3

	##~~ Access Permissions Hook

	def get_additional_permissions(self, *args, **kwargs):
		return [
			dict(key="CONTROL",
				 name="Control Plugs",
				 description=gettext("Allows control of configured plugs."),
				 roles=["admin"],
				 dangerous=True,
				 default_groups=[ADMIN_GROUP])
		]

	##~~ Gcode processing hook

	def gcode_turn_off(self, plug):
		if plug["warnPrinting"] and self._printer.is_printing():
			self._logger.info("Not powering off %s because printer is printing." % plug["label"])
		else:
			self.turn_off(plug["ip"])

	def processAtCommand(self, comm_instance, phase, command, parameters, tags=None, *args, **kwargs):
		if command in ["WEMOON", "WEMOOFF"]:
			plugip = parameters.strip()
			self._wemoswitch_logger.debug("Received %s command, attempting power on of %s." % (command, plugip))
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._wemoswitch_logger.debug(plug)
		else:
			return None
		if command == "WEMOON":
			if plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOnDelay"]), self.turn_on, args=[plugip])
				t.start()
			return None
		if command == "WEMOOFF":
			if plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOffDelay"]), self.gcode_turn_off, args=[plug])
				t.start()
			return None

	def processGCODE(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if self.powerOffWhenIdle and not (gcode in self._idleIgnoreCommandsArray):
			self._waitForHeaters = False
			self._reset_idle_timer()
		if gcode:
			if cmd.startswith("M80"):
				plugip = re.sub(r'^M80\s?', '', cmd)
				self._wemoswitch_logger.debug("Received M80 command, attempting power on of %s." % plugip)
				plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
				self._wemoswitch_logger.debug(plug)
				if plug["gcodeEnabled"]:
					t = threading.Timer(int(plug["gcodeOnDelay"]), self.turn_on, args=[plugip])
					t.start()
				return
			elif cmd.startswith("M81"):
				plugip = re.sub(r'^M81\s?', '', cmd)
				self._wemoswitch_logger.debug("Received M81 command, attempting power off of %s." % plugip)
				plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
				self._wemoswitch_logger.debug(plug)
				if plug["gcodeEnabled"]:
					t = threading.Timer(int(plug["gcodeOffDelay"]), self.gcode_turn_off, [plug])
					t.start()
				return
			else:
				return

	def check_temps(self, parsed_temps):
		thermal_runaway_triggered = False
		for k, v in parsed_temps.items():
			if k == "B" and v[1] > 0 and v[0] > int(self._settings.get(["thermal_runaway_max_bed"])):
				self._wemoswitch_logger.debug("Max bed temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if k.startswith("T") and v[1] > 0 and v[0] > int(self._settings.get(["thermal_runaway_max_extruder"])):
				self._wemoswitch_logger.debug("Extruder max temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if thermal_runaway_triggered == True:
				for plug in self._settings.get(['arrSmartplugs']):
					if plug["thermal_runaway"] == True:
						response = self.turn_off(plug["ip"])
						if response["currentState"] == "off":
							self._plugin_manager.send_plugin_message(self._identifier, response)

	def monitor_temperatures(self, comm, parsed_temps):
		if self._settings.get(["thermal_runaway_monitoring"]):
			# Run inside it's own thread to prevent communication blocking
			t = threading.Timer(0, self.check_temps, [parsed_temps])
			t.start()
		return parsed_temps

	##~~ Softwareupdate hook

	def get_update_information(self):
		return dict(
			wemoswitch=dict(
				displayName="Wemo Switch",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="jneilliii",
				repo="OctoPrint-WemoSwitch",
				current=self._plugin_version,
                stable_branch=dict(
                    name="Stable", branch="master", comittish=["master"]
                ),
                prerelease_branches=[
                    dict(
                        name="Release Candidate",
                        branch="rc",
                        comittish=["rc", "master"],
                    )
                ],

				# update method: pip
				pip="https://github.com/jneilliii/OctoPrint-WemoSwitch/archive/{target_version}.zip"
			)
		)


__plugin_name__ = "Wemo Switch"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = wemoswitchPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.processGCODE,
		"octoprint.comm.protocol.atcommand.sending": __plugin_implementation__.processAtCommand,
		"octoprint.comm.protocol.temperatures.received": __plugin_implementation__.monitor_temperatures,
		"octoprint.access.permissions": __plugin_implementation__.get_additional_permissions,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
