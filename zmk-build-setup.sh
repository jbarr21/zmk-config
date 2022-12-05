#!/bin/bash
git clone https://github.com/urob/zmk.git
cd zmk
west init -l app/
west update
west zephyr-export
pip3 install --user -r zephyr/scripts/requirements-base.txt

# west build -s app -b nice_nano_v2 -- -DZMK_CONFIG=/zmk-config/config -DSHIELD=ffkb