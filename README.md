# zmk-config

This is a [ZMK](https://zmk.dev) config repo for my wireless mechanical keyboards.

Also see my [QMK userspace](https://github.com/jbarr21/qmk_userspace/) for equivalent keymap definitions for QMK.

Build with Docker:
```sh
docker run -it --rm -v $(realpath .):/zmk-config -w="/" zmkfirmware/zmk-dev-arm:3.0-branch /bin/bash
cd zmk
west build -s app -b nice_nano_v2 -- -DZMK_CONFIG=/zmk-config/config -DSHIELD=ffkb
```

![ZMK Layout](keyboard-layout.png)
