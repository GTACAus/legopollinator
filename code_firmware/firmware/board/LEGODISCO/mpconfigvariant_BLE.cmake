# The Bluetooth build (firmware/build.sh BLE -> legopollinator-ble.bin), for trying the Bluetooth
# remote: no hotspot; the iPad opens the remote from the website (newsite/roboarm_mini/remote) in
# Bluefy and connects to the board over Bluetooth (app/ble.py). Same hub program. Flash
# legopollinator.bin again to go back to the hotspot.
list(APPEND SDKCONFIG_DEFAULTS boards/sdkconfig.ble ${MICROPY_BOARD_DIR}/sdkconfig.ble)
list(APPEND MICROPY_DEF_BOARD
    MICROPY_HW_BOARD_NAME="LMS-ESP32 GTAC pollinator (Bluetooth)"
    MICROPY_PY_BLUETOOTH=1
)
