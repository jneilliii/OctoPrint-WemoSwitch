# Wemo Switch

This plugin allows for the control of Belkin Wemo devices via navbar buttons and gcode commands.

## Firmware Warning

Starting in May of 2020, Belkin started requiring users to create an account and login to the app (Android app version 1.25). In addition to the account, most of the app functionality now requires a connection to the cloud (internet access), even for simple actions such as toggling a switch. All of the commands that go through the cloud are encrypted and cannot be easily inspected. This raises the possibility that Belkin could, in the future, update Wemo device firmware and make breaking API changes that can not longer be deciphered. If this happens, pywemo (dependency of this plugin) may no longer function on that device rendering this plugin useless. It would be prudent to upgrade firmware cautiously and preferably only after confirming that breaking API changes have not been introduced.

## Screenshots

![on](screenshot_on.png)

![off](screenshot_off.png)

## Settings

![screenshot](settings.png)

Once installed go into settings and enter the name of your wemo device. Adjust additional settings as needed.

- **Enable startup event monitoring**: will power on enabled wemos when OctoPrint starts up after boot.
- **Enable upload event monitoring**: will power on enabled wemos when a file is uploaded with the start print on upload setting enabled (requires OctoPrint 1.4.1).
- **Enable thermal runaway monitoring**: will power off enabled wemos at set max temperatures.
- **Enable power off on idle**: will power off enabled wemos using following parameters.
  - Abort Power Off Timeout: a prompt will displayed in the UI to allow aborting idle power off for this period of time.
  - Idle Timeout: amount of time to wait before automatic power off of enabled wemos begins. Waits for timelapses to complete and for all temperatures to be below configured `Idle Target Temperature`.
  - Idle Target Temperature: temperature threshold to be below prior to starting idle timeout.
  - GCode Commands to Ignore for Idle: commands to be ignored for determining idle state.
- **Enable polling of status**: when enabled and while the UI is open the current state of all wemos will be checked at set interval.
- **Enable debug logging**: enables `plugin_wemoswitch_debug.log` file in OctoPrint's logging section for troubleshooting purposes.

![screenshot](settings_wemo_editor.png)

- **IP Address**: IP address of the wemo device.
- **Icon Class**: class name from [fontawesome](http://fontawesome.io/3.2.1/cheatsheet/) to use for icon on button.
- **Label**: label to use for title attribute on hover over button in navbar.
- **Off on Idle**: power off wemo on idle timeout. Requires `Enable power off on idle` setting to be enabled.
- **On on Startup**: power on with OctoPrint startup. Requires `Enable startup event monitoring` setting to be enabled.
- **On on Upload**: power on when file is uploaded and flagged to auto start printing. Requires `Enable upload event monitoring` setting to be enabled and OctoPrint 1.4.1.
- **Warning Prompt**: confirmation prompt will always display when powering off a wemo from the navbar.
- **Warn While Printing**: confirmation prompt will display while printing when powering off a wemo from the navbar. Enabling this will also prevent gcode processing from powering off the wemo while printing unless a sufficient `GCODE Off Delay` is entered.
- **Thermal Runaway**: when enabled will power off wemo when main temperature thresholds are exceeded.
- **Auto Connect**: power on wemo and then automatically connect to printer after configured delay in seconds.
- **Auto Disconnect**: automatically disconnect printer and then power off the wemo after configured delay in seconds.
- **GCODE Trigger**: enable the processing of `M80`, `M81`, `@WEMOON`, and `@WEMOOFF` GCODE commands using configured delays. Syntax for gcode command is `M80`/`M81`/`@WEMOON`/`@WEMOOFF` followed by the wemo's ip address.  For example if your wemo's IP address is `192.168.0.104` your gcode command might be **@WEMOOFF 192.168.0.104:49153**.
- **Run System Command After On**: power on wemo and run configured system command after configured delay in seconds.
- **Run System Command Before Off**: run configured system command and then power off the wemo after configured delay in seconds.

## Most recent changelog

### [0.1.10](https://github.com/jneilliii/OctoPrint-WemoSwitch/releases/tag/0.1.10) (01/11/2021)

**Fixed**
* python 2 bug introduced in last release

### [All releases](https://github.com/jneilliii/OctoPrint-WemoSwitch/releases)

## Get Help

If you experience issues with this plugin or need assistance please use the issue tracker by clicking issues above.

### Additional Plugins

Check out my other plugins [here](https://plugins.octoprint.org/by_author/#jneilliii)

### Sponsors
- Andreas Lindermayr
- [@Mearman](https://github.com/Mearman)
- [@TheTuxKeeper](https://github.com/thetuxkeeper)
- [@tideline3d](https://github.com/tideline3d/)
- [SimplyPrint](https://simplyprint.dk/)
- [Andrew Beeman](https://github.com/Kiendeleo)
- [Calanish](https://github.com/calanish)
- [Lachlan Bell](https://lachy.io/)
- [Johnny Bergdal](https://github.com/bergdahl)
- [Leigh Johnson](https://github.com/leigh-johnson)
- [Stephen Berry](https://github.com/berrystephenw)
- [Guyot François](https://github.com/iFrostizz)
- [Steve Dougherty](https://github.com/Thynix)
- [Flying Buffalo Aerial Photography](http://flyingbuffalo.info/)
## Support My Efforts
I, jneilliii, programmed this plugin for fun and do my best effort to support those that have issues with it, please return the favor and leave me a tip or become a Patron if you find this plugin helpful and want me to continue future development.

[![Patreon](patreon-with-text-new.png)](https://www.patreon.com/jneilliii) [![paypal](paypal-with-text.png)](https://paypal.me/jneilliii)

<small>No paypal.me? Send funds via PayPal to jneilliii&#64;gmail&#46;com</small>

