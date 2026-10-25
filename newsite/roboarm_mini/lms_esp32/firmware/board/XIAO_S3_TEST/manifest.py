# Same frozen app as the real board, plus simhub.py (the fake hub).
freeze("$(PORT_DIR)/modules")
freeze("$(BOARD_DIR)/../../../app", ("arm.py", "lump.py", "ble.py", "simhub.py"))
