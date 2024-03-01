# dbus-mqtt-openwb - displays and controls an OpenWB 1.9 wallbox in Victron ESS

<small>GitHub repository: [gvz/dbus-mqtt-openwb](https://github.com/gvzdus/dbus-mqtt-openwb)</small>

### Disclaimer

I wrote this script for myself. I'm not responsible, if you damage something using my script.
It is derived from the work of mr-manuel: [/mr-manuel/venus-os_dbus-mqtt-pv](https://github.com/mr-manuel/venus-os_dbus-mqtt-pv)</small>


### Purpose

The script integrates the OpenWB Wallbox in Venus OS.
It connects to the MQTT broker on the OpenWB, subscribes to configured topics and publishes the information on the dbus as the service `com.victronenergy.evcharger` with the VRM instance `53`.


### Config

Copy or rename the `config.sample.ini` to `config.ini` in the `dbus-mqtt-openwb` folder and change it as you need it.
Minimum requirement should be to adapt the IP address


### Install

1. Login to your Venus OS device via SSH. See [Venus OS:Root Access](https://www.victronenergy.com/live/ccgx:root_access#root_access) for more details.

2. Execute this commands to download and extract the files:

    ```bash
    # change to temp folder
    cd /tmp

    # download driver
    wget -O /tmp/dbus-mqtt-openwb.zip https://github.com/gvzdus/dbus-mqtt-openwb/archive/refs/heads/master.zip

    # If updating: cleanup old folder
    rm -rf /tmp/dbus-mqtt-openwb-master

    # unzip folder
    unzip dbus-mqtt-openwb.zip

    # If updating: backup existing config file
    mv /data/etc/dbus-mqtt-openwb/config.ini /data/etc/dbus-mqtt-openwb_config.ini

    # If updating: cleanup existing driver
    rm -rf /data/etc/dbus-mqtt-openwb

    # copy files
    cp -R /tmp/dbus-mqtt-openwb-master/dbus-mqtt-openwb/ /data/etc/

    # If updating: restore existing config file
    mv /data/etc/dbus-mqtt-openwb_config.ini /data/etc/dbus-mqtt-openwb/config.ini
    ```

3. Copy the sample config file, if you are installing the driver for the first time and edit it to your needs.

    ```bash
    # copy default config file
    cp /data/etc/dbus-mqtt-openwb/config.sample.ini /data/etc/dbus-mqtt-openwb/config.ini

    # edit the config file with nano
    nano /data/etc/dbus-mqtt-openwb/config.ini
    ```

4. Run `bash /data/etc/dbus-mqtt-openwb/install.sh` to install the driver as service.

   The daemon-tools should start this service automatically within seconds.

### Uninstall

Run `/data/etc/dbus-mqtt-openwb/uninstall.sh`

### Restart

Run `/data/etc/dbus-mqtt-openwb/restart.sh`

### Debugging

The logs can be checked with `tail -n 100 -f /data/log/dbus-mqtt-openwb/current | tai64nlocal`

The service status can be checked with svstat `svstat /service/dbus-mqtt-openwb`

This will output somethink like `/service/dbus-mqtt-openwb: up (pid 5845) 185 seconds`

If the seconds are under 5 then the service crashes and gets restarted all the time. If you do not see anything in the logs you can increase the log level in `/data/etc/dbus-mqtt-openwb/dbus-mqtt-openwb.py` by changing `level=logging.WARNING` to `level=logging.INFO` or `level=logging.DEBUG`

If the script stops with the message `dbus.exceptions.NameExistsException: Bus name already exists: com.victronenergy.pvinverter.mqtt_pv"` it means that the service is still running or another service is using that bus name.

### Multiple instances

It's possible to have multiple instances, but it's not automated. Follow these steps to achieve this:

1. Save the new name to a variable `driverclone=dbus-mqtt-openwb-2`

2. Copy current folder `cp -r /data/etc/dbus-mqtt-openwb/ /data/etc/$driverclone/`

3. Rename the main script `mv /data/etc/$driverclone/dbus-mqtt-openwb.py /data/etc/$driverclone/$driverclone.py`

4. Fix the script references for service and log
    ```
    sed -i 's:dbus-mqtt-openwb:'$driverclone':g' /data/etc/$driverclone/service/run
    sed -i 's:dbus-mqtt-openwb:'$driverclone':g' /data/etc/$driverclone/service/log/run
    ```

5. Change the `device_name` and increase the `device_instance` in the `config.ini`

Now you can install and run the cloned driver. Should you need another instance just increase the number in step 1 and repeat all steps.

### Compatibility

It was tested on Venus OS `v3.22` on the following device:

* CerboGX

