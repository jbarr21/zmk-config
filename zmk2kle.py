#!/usr/bin/env python3
import argparse
import configparser
from dataclasses import dataclass
from logging import root
import os
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from sys import argv
from textwrap import dedent
from tree_sitter import Language, Parser
import urllib.parse

# KLE JSON for a 3x6+3
KLE_LAYOUT = dedent('''
    [{a:7,f:3},{y:0.3},"","",{y:-0.2},"",{y:-0.1},"",{y:0.1},"",{y:0.2},"",{x:3},"",{y:-0.1},"",{y:-0.1},"",{y:0.1},"",{y:0.2},"","",{y:-0.4}],
    [{y:0.3},"","",{y:-0.2},"",{y:-0.1},"",{y:0.1},"",{y:0.2},"",{x:3},"",{y:-0.1},"",{y:-0.1},"",{y:0.1},"",{y:0.2},"","",{y:-0.4}],
    [{y:0.3},"","",{y:-0.2},"",{y:-0.1},"",{y:0.1},"",{y:0.2},"",{x:3},"",{y:-0.1},"",{y:-0.1},"",{y:0.1},"",{y:0.2},"",""],
    [{x:4,y:0.5},"","",{h:1.5,y:-0.5},"",{x:1},{h:1.5},"",{y:0.5},"",""],
''')

MODS = ['LGUI', 'LSHFT', 'LALT', 'LCTRL', 'RGUI', 'RSHFT', 'RALT', 'RCTRL']
kle_chars_needing_escaping = ['/', ';', '@', '&', '_', '=']
zmk_to_name = { }

@dataclass
class KeyAction:
    type: str
    tap: str
    hold: str

@dataclass
class Key:
    cells: list[str]

    def label(self, encoded=False) -> str:
        action = self._action()
        label = action.tap
        if encoded:
            for ch in [c for c in kle_chars_needing_escaping if c in label]:
                label = label.replace(ch, '/' + ch)

        if action.hold is not None:
            label += f"\n\n\n\n{action.hold}"

        if not encoded:
            label = label.replace('\\', '\\\\').replace('\n', '\\n')
 
        return urllib.parse.quote(label).replace('/', '%2F') if encoded else label

    def _action(self) -> KeyAction:
        type = self.cells[0].text.decode()[1:]
        args = [self._legend(x.text.decode()) for x in self.cells[1:]]

        if type == 'kp':
            return KeyAction(type=type, tap=args[0], hold=None)
        elif type in ['mt', 'lt']:
            return KeyAction(type=type, tap=args[1], hold=args[0])
        elif type in ['sk', 'sl']:
            return KeyAction(type=type, tap=f"{args[0]}<br>{type.upper()}", hold=None)
        elif type == 'trans':
            return KeyAction(type=type, tap='___', hold=None) 
        elif type == 'none':
            return KeyAction(type=type, tap='', hold=None)
        else:
            tap = self._legend((type if len(args) == 0 else ' '.join(args)).upper())
            return KeyAction(type=type, tap=tap, hold=None)

    def _legend(self, code) -> str:
        code = zmk_to_name.get(code, code)
        if len(code) == 2 and code.startswith('N'):
            code = code[1:]
        elif code.startswith('C_'):
            code = code[2:]
        elif re.match(r'\w\w\(\w+\)', code):
            code = zmk_to_name.get(code[0:2]) + ' + ' +code[3:-1]
        
        if len(code) > 1:
            code = code.replace('_', ' ')
        return code

@dataclass
class Layer:
    name: str
    label: str
    keys: list[Key]

    def to_kle(self, encoded=False):
        layer_name = (self.label if self.label is not None else self.name.upper()).replace('_', '%20' if encoded else ' ')
        header = '''[{d:true,w:5,a:6,f:5}, %s],''' % (f"={layer_name}" if encoded else f"\"{layer_name}\"")
        data = f"{header}\n{KLE_LAYOUT.strip()}"
        if encoded:
            data = self._kle_encode(data)
        return self._add_keys(data, '""', [key.label(encoded=encoded) for key in self.keys], encoded)

    def to_kle_url(self):
        return self.to_kle(encoded=True).replace('\n', '')

    def _add_keys(self, text, target, replacements, encoded):
        item = 0
        index = text.find('""', 0)
        while index >= 0:
            try:
                if encoded:
                    text = text[:index] + '=' + replacements[item] + text[index+2:]
                else:
                    text = text[:index+1] + replacements[item] + text[index+1:]
            except Exception as ex:
                exit(str(ex) + f" index={index}, textLen={len(text)}, text={text}")
            index = text.find('""', index+1)
            item+=1
        return text

    def _kle_encode(self, text):
        semicolon = urllib.parse.quote(';')
        chars = {
            ',': '&',
            '[': '@',
            '{': '_',
            '}': semicolon,
            ']': semicolon,
            ' ':'',
        }
        for k, v in chars.items():
            text = text.replace(k, v)
        return text

@dataclass
class Keymap:
    layers: list[Layer]
    defines: dict[str, str]

    def to_kle(self):
        return '\n'.join([layer.to_kle() for layer in self.layers])

    def to_kle_url(self):
        layer_urls = ''.join([layer.to_kle_url() for layer in self.layers])
        return f"http://www.keyboard-layout-editor.com/##@{layer_urls}=undefined"

def save_image(url):
    download_dir = os.environ.get('GITHUB_WORKSPACE', os.environ.get('HOME')+'/Downloads')
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing_for_trusted_sources_enabled": False,
        "safebrowsing.enabled": False
    })
    driver = webdriver.Chrome(options=options)

    driver.get(url)
    driver.find_elements(by=By.CLASS_NAME, value='btn-success')[2].click()
    driver.find_elements(by=By.CLASS_NAME, value='dropdown-menu')[5].find_elements(by=By.TAG_NAME, value='a')[1].click()

    download_wait(download_dir, 30)

def download_wait(directory, timeout, nfiles=None):
    seconds = 0
    dl_wait = True
    while dl_wait and seconds < timeout:
        time.sleep(1)
        dl_wait = False
        files = os.listdir(directory)
        if nfiles and len(files) != nfiles:
            dl_wait = True

        for fname in files:
            if fname.endswith('.crdownload'):
                dl_wait = True

        seconds += 1
    return seconds

def parse_keymap(keymap_path):
    keymap_text = None
    with open(keymap_path, 'r') as f:
        keymap_text = f.read()

    so_path = 'devicetree.so' if not os.environ.get('GITHUB_WORKSPACE', None) else (os.environ.get('HOME')+'/.cache/tree-sitter/lib/devicetree.so')
    DTS_LANGUAGE = Language(so_path, 'devicetree')
    parser = Parser()
    parser.set_language(DTS_LANGUAGE)
    tree = parser.parse(bytes(keymap_text, 'utf8'))
    
    slash = [c for c in tree.root_node.children if c.type == 'node' and node_name(c) == '/'][0]
    keymap = [c for c in slash.children if c.type == 'node' and node_name(c) == 'keymap'][0]
    layers = [c for c in keymap.children if c.type == 'node']
    layers = [c for c in layers if len([p for p in c.children if node_name(p) == 'bindings']) > 0]
    keymap_layers = []

    for layer in layers:
        name = node_name(layer)
        bindings = [c for c in layer.children if node_name(c) == 'bindings'][0]
        label = [x.text.decode().replace('"', '') for x in flatten([c.children for c in layer.children if node_name(c) == 'label']) if x.type == 'string_literal']
        label = next(iter(label), None)
        layer_cells = [c for c in bindings.children if c.type == 'integer_cells'][0].children
        keys = []
        cells = []
        for i, cell in enumerate(layer_cells):
            if cell.type != 'comment' and node_name(cell) is not None and node_name(cell) != '<':
                cells += [cell]

            if (i == len(layer_cells) - 1 or layer_cells[i + 1].type == 'reference') and len(cells) > 0: 
                keys += [Key(cells)]
                cells = []

        keymap_layers += [Layer(name, label, keys)]
       
    return Keymap(keymap_layers, {})

def flatten(l):
    return [item for sublist in l for item in sublist]

def node_name(node):
    if node is None or not hasattr(node, 'type'):
        return None
    elif node.type == 'identifier':
        return node.text.decode()
    else:
        ids = [c for c in node.children if c.type == 'identifier']
        refs = [c for c in node.children if c.type == 'reference']
        props = [c for c in node.children if c.type == 'property']
        return node_name(next(iter(ids + refs + props), None))

def load_config():
    config = configparser.ConfigParser()
    config.optionxform = str
    with open('legends.properties', 'r') as f:
        config.read_file(f)
        if 'legends' in config._sections:
            zmk_to_name.update(config._sections.get("legends"))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert ZMK layout to KLE image')
    parser.add_argument('keymap', type=str, help='Path to keymap file')
    parser.add_argument('-i', '--save_image', help='Save the KLE image', action='store_true')
    parser.add_argument('-l', '--link_only', help='Show KLE link instead of KLE raw data', action='store_true')
    args = parser.parse_args()

    load_config()
    keymap = parse_keymap(args.keymap)
    print(keymap.to_kle_url() if args.link_only else keymap.to_kle())

    if args.save_image in argv:
        save_image(keymap.to_kle_url())
