.PHONY: install run test tests

CONFIG_DIR ?= /config
OPTIONS_PATH ?= /data/options.json
PORT ?= 8099

run:
	HASS_CONFIG_DIR="$(CONFIG_DIR)" HASS_OPTIONS_PATH="$(OPTIONS_PATH)" \
		uv run --project . \
		python rootfs/app/main.py --port "$(PORT)"

install:
	uv sync --project . --extra dev

tests:
	uv run --project . --extra dev \
		pytest tests

test: tests
