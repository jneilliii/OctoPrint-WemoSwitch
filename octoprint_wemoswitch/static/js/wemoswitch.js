/*
 * View model for OctoPrint-WemoSwitch
 *
 * Author: jneilliii
 * License: AGPLv3
 */
$(function() {
    function wemoswitchViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];
		self.loginState = parameters[1];

		self.arrSmartplugs = ko.observableArray();
		self.isPrinting = ko.observable(false);
		self.selectedPlug = ko.observable();
		self.selected_discovered_device = ko.observable();
		self.processing = ko.observableArray([]);
		self.powerOffWhenIdle = ko.observable(false);
		self.show_sidebar = ko.pureComputed(function(){
		    var filtered = ko.utils.arrayFilter(self.settings.settings.plugins.wemoswitch.arrSmartplugs(), function(item) {
                return item["automaticShutdownEnabled"];
            });
			return filtered.length > 0;
		});

		self.toggleShutdownTitle = ko.pureComputed(function() {
			return self.settings.settings.plugins.wemoswitch.powerOffWhenIdle() ? 'Disable Automatic Power Off' : 'Enable Automatic Power Off';
		})

		// Hack to remove automatically added Cancel button
		// See https://github.com/sciactive/pnotify/issues/141
		PNotify.prototype.options.confirm.buttons = [];
		self.timeoutPopupText = gettext('Powering off in ');
		self.timeoutPopupOptions = {
			title: gettext('Automatic Power Off'),
			type: 'notice',
			icon: true,
			hide: false,
			confirm: {
				confirm: true,
				buttons: [{
					text: gettext('Cancel Power Off'),
					addClass: 'btn-block btn-danger',
					promptTrigger: true,
					click: function(notice, value){
						notice.remove();
						notice.get().trigger("pnotify.cancel", [notice, value]);
					}
				}]
			},
			buttons: {
				closer: false,
				sticker: false,
			},
			history: {
				history: false
			}
		};

		self.onToggleAutomaticShutdown = function(data) {
			if (self.settings.settings.plugins.wemoswitch.powerOffWhenIdle()) {
				$.ajax({
					url: API_BASEURL + "plugin/wemoswitch",
					type: "POST",
					dataType: "json",
					data: JSON.stringify({
						command: "disableAutomaticShutdown"
					}),
					contentType: "application/json; charset=UTF-8"
				}).done(function(data){
				    console.log(data);
				    self.settings.settings.plugins.wemoswitch.powerOffWhenIdle(data.powerOffWhenIdle);
				});
			} else {
				$.ajax({
					url: API_BASEURL + "plugin/wemoswitch",
					type: "POST",
					dataType: "json",
					data: JSON.stringify({
						command: "enableAutomaticShutdown"
					}),
					contentType: "application/json; charset=UTF-8"
				}).done(function(data){
				    console.log(data);
				    self.settings.settings.plugins.wemoswitch.powerOffWhenIdle(data.powerOffWhenIdle);
				});
			}
		}

		self.abortShutdown = function(abortShutdownValue) {
			self.timeoutPopup.remove();
			self.timeoutPopup = undefined;
			$.ajax({
				url: API_BASEURL + "plugin/wemoswitch",
				type: "POST",
				dataType: "json",
				data: JSON.stringify({
					command: "abortAutomaticShutdown"
				}),
				contentType: "application/json; charset=UTF-8"
			})
		}

		self.onBeforeBinding = function() {
			self.arrSmartplugs(self.settings.settings.plugins.wemoswitch.arrSmartplugs());
        }

		self.onAfterBinding = function() {
			self.checkStatuses();
		}

        self.onEventSettingsUpdated = function(payload) {
			self.arrSmartplugs(self.settings.settings.plugins.wemoswitch.arrSmartplugs());
		}

		self.onEventPrinterStateChanged = function(payload) {
			if (payload.state_id === "PRINTING" || payload.state_id === "PAUSED"){
				self.isPrinting(true);
			} else {
				self.isPrinting(false);
			}
		}

		self.cancelClick = function(data) {
			self.processing.remove(data.ip());
		}

		self.editPlug = function(data) {
			self.selectedPlug(data);
			$("#WemoSwitchEditor").modal("show");
		}

		self.use_discovered = function(data) {
		    if(self.selected_discovered_device()) {
                data.ip(self.selected_discovered_device().ip());
                data.label(self.selected_discovered_device().label());
            }
        }

		self.addPlug = function() {
			self.selectedPlug({'ip':ko.observable(''),
                                'label':ko.observable(''),
                                'icon':ko.observable('fas fa-bolt'),
                                'displayWarning':ko.observable(true),
                                'warnPrinting':ko.observable(false),
                                'thermal_runaway':ko.observable(false),
                                'gcodeEnabled':ko.observable(false),
                                'gcodeOnDelay':ko.observable(0),
                                'gcodeOffDelay':ko.observable(0),
                                'autoConnect':ko.observable(true),
                                'autoConnectDelay':ko.observable(10.0),
                                'autoDisconnect':ko.observable(true),
                                'autoDisconnectDelay':ko.observable(0),
                                'sysCmdOn':ko.observable(false),
                                'sysRunCmdOn':ko.observable(''),
                                'sysCmdOnDelay':ko.observable(0),
                                'sysCmdOff':ko.observable(false),
                                'sysRunCmdOff':ko.observable(''),
                                'sysCmdOffDelay':ko.observable(0),
                                'currentState':ko.observable('unknown'),
                                'btnColor':ko.observable('#808080'),
                                'automaticShutdownEnabled':ko.observable(false),
                                'event_on_startup':ko.observable(false),
                                'event_on_upload':ko.observable(false)});
			self.settings.settings.plugins.wemoswitch.arrSmartplugs.push(self.selectedPlug());
			$("#WemoSwitchEditor").modal("show");
		}

		self.removePlug = function(row) {
			self.settings.settings.plugins.wemoswitch.arrSmartplugs.remove(row);
		}

		self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin !== "wemoswitch") {
                return;
            }

			if(data.hasOwnProperty("powerOffWhenIdle")) {
			    if (data.type == "timeout") {
					if ((data.timeout_value != null) && (data.timeout_value > 0)) {
						self.timeoutPopupOptions.text = self.timeoutPopupText + data.timeout_value;
						if (typeof self.timeoutPopup != "undefined") {
							self.timeoutPopup.update(self.timeoutPopupOptions);
						} else {
							self.timeoutPopup = new PNotify(self.timeoutPopupOptions);
							self.timeoutPopup.get().on('pnotify.cancel', function() {self.abortShutdown(true);});
						}
					} else {
						if (typeof self.timeoutPopup != "undefined") {
							self.timeoutPopup.remove();
							self.timeoutPopup = undefined;
						}
					}
				}
				return;
			}

			plug = ko.utils.arrayFirst(self.settings.settings.plugins.wemoswitch.arrSmartplugs(),function(item){
				return item.ip() === data.ip;
				}) || {'ip':data.ip,'currentState':'unknown','btnColor':'#808080'};

			if (plug.currentState !== data.currentState) {
				plug.currentState(data.currentState)
				switch(data.currentState) {
					case "on":
						break;
					case "off":
						break;
					default:
						new PNotify({
							title: 'Wemo Switch Error',
							text: 'Status ' + plug.currentState() + ' for ' + plug.ip() + '. Double check Device Name in Wemo Switch Settings.',
							type: 'error',
							hide: true
							});
				self.settings.saveData();
				}
			}
			self.processing.remove(data.ip);
        };

		self.toggleRelay = function(data) {
			self.processing.push(data.ip());
			switch(data.currentState()){
				case "on":
					self.turnOff(data);
					break;
				case "off":
					self.turnOn(data);
					break;
				default:
					self.checkStatus(data.ip());
			}
		}

		self.turnOn = function(data) {
            $.ajax({
                url: API_BASEURL + "plugin/wemoswitch",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "turnOn",
					ip: data.ip()
                }),
                contentType: "application/json; charset=UTF-8"
            });
		}

    	self.turnOff = function(data) {
			if((data.displayWarning() || (self.isPrinting() && data.warnPrinting())) && !$("#WemoSwitchWarning").is(':visible')){
				self.selectedPlug(data);
				$("#WemoSwitchWarning").modal("show");
			} else {
				$("#WemoSwitchWarning").modal("hide");
                $.ajax({
                url: API_BASEURL + "plugin/wemoswitch",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "turnOff",
                    ip: data.ip()
                }),
                contentType: "application/json; charset=UTF-8"
                });
			}
        };

		self.checkStatus = function(plugIP) {
            $.ajax({
                url: API_BASEURL + "plugin/wemoswitch",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "checkStatus",
					ip: plugIP
                }),
                contentType: "application/json; charset=UTF-8"
            }).done(function(data){
                console.log(data);
				self.settings.saveData();
				});
        };

		self.checkStatuses = function() {
			ko.utils.arrayForEach(self.settings.settings.plugins.wemoswitch.arrSmartplugs(),function(item){
				if(item.ip() !== "") {
					console.log("checking " + item.ip())
					self.checkStatus(item.ip());
				}
			});
			if (self.settings.settings.plugins.wemoswitch.pollingEnabled()) {
				setTimeout(function() {self.checkStatuses();}, (parseInt(self.settings.settings.plugins.wemoswitch.pollingInterval(),10) * 60000));
			};
        };
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        wemoswitchViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        ["settingsViewModel","loginStateViewModel"],

        // "#navbar_plugin_wemoswitch","#settings_plugin_wemoswitch"
        ["#navbar_plugin_wemoswitch","#settings_plugin_wemoswitch","#sidebar_plugin_wemoswitch_wrapper"]
    ]);
});
