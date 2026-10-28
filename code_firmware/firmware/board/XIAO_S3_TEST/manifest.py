# Same frozen app as the real board, plus simhub.py (the fake hub).
# www_data.py is generated from app/www by tools/make_www.py.
freeze("$(PORT_DIR)/modules")
freeze("$(BOARD_DIR)/../../../app",
       ("arm.py", "lump.py", "web.py", "simhub.py", "www_data.py"))
