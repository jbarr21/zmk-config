#!/usr/bin/env python3
import os
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from sys import argv
from textwrap import dedent
import argparse
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
zmk_to_name = {
  'SEMI': ';',
  'BSLH': '\\',
  'APOS': '\'',
  'COMMA': ',',
  'DOT': '.',
  'FSLH': '/',
  'SPACE': 'Space',
  'BSPC': '⌫',
  'RET': '⏎',
  'EXCL': '!',
  'AT': '@',
  'HASH': '#',
  'DLLR': '$',
  'PRCNT': '%',
  'CARET': '^',
  'AMPS': '&',
  'STAR': '*',
  'PLUS': '+',
  'UNDER': '_',
  'EQUAL': '=',
  'MINUS': '-',
  'GRAVE': '`',
  'PIPE': '|',
  'LT': '<',
  'LBKT': '[',
  'LBRC': '{',
  'LPAR': '(',
  'TILDE': '~',
  'QMARK': '?',
  'RPAR': ')',
  'RBRC': '}',
  'RBKT': ']',
  'GT': '>',
  'C_PREV': '|◀',
  'C_STOP': '■',
  'C_PP': '▶',
  'C_NEXT': '|▶',
  'LEFT': '←',
  'DOWN': '↓',
  'UP': '↑',
  'RIGHT': '→',
  'KP_DOT': '.',
  'LGUI': '⌘',
  'RGUI': '⌘',
  'LSHFT': '⇧',
  'RSHFT': '⇧',
  'LALT': '⌥',
  'RALT': '⌥',
  'LCTRL': '⎈',
  'RCTRL': '⎈',
  'LG': '⌘',
  'RG': '⌘',
  'LS': '⇧',
  'RS': '⇧',
  'LA': '⌥',
  'RA': '⌥',
  'LC': '⎈',
  'RC': '⎈',
}

class Key:
    def __init__(self, code, aliases):
        self.hold = None
        args = code.split(' ')
        action = args[0]

        if action == '&kp':
            self.tap = self.name(args[1])
        elif action == '&mt' or action == '&lt':
            self.hold = self.name(args[1])
            self.tap = self.name(args[2])
        elif action == '&sk' or action == '&sl':
            self.tap = self.name(args[1]) + '<br>' + action.replace('&', '').upper()
        elif action == '&none':
            self.tap = ''
        else:
            self.tap = self.name(code)

    def name(self, code):
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

    def label(self, encoded=False):
        label = self.tap
        if encoded:
            for ch in [c for c in kle_chars_needing_escaping if c in label]:
                label = label.replace(ch, '/' + ch)

        if self.hold is not None:
            label += f"\n\n\n\n{self.hold}"

        if not encoded:
            label = label.replace('\\', '\\\\').replace('\n', '\\n')
 
        return urllib.parse.quote(label).replace('/', '%2F') if encoded else label


class Layer:
    Key = re.compile(r'&\w+(?:.(?!(&|$)))*')
    
    def __init__(self, data, aliases):
        self.name = re.search(r'(?<=label = ")\w+(?=";)', data).group()
        self.keys = []
        for key in Layer.Key.finditer(data):
            self.keys += [Key(key.group().strip(), aliases)]

    def to_kle(self, encoded=False):
        header = '''[{d:true,w:5,a:6,f:5}, %s],''' % (f"={self.name}" if encoded else f"\"{self.name}\"")
        data = f"{header}\n{KLE_LAYOUT.strip()}"
        if encoded:
            data = self.kle_encode(data)
        return self.add_keys(data, '""', [key.label(encoded=encoded) for key in self.keys], encoded)

    def to_kle_url(self):
        return self.to_kle(encoded=True).replace('\n', '')

    def add_keys(self, text, target, replacements, encoded):
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

    def kle_encode(self, text):
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

class Layout:
    Layer = re.compile(r'(default_layer|layer_\w+) {.*?};', re.DOTALL | re.MULTILINE)

    def __init__(self, file):
        self.layers = []
        self.aliases = {}
        with open(file, 'r') as f:
            text = f.read()
            for layer in Layout.Layer.finditer(text):
                self.layers += [Layer(layer.group(), self.aliases)]
    
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert ZMK layout to KLE image')
    parser.add_argument('keymap', type=str, help='Path to keymap file')
    parser.add_argument('-i', '--save_image', help='Save the KLE image', action='store_true')
    parser.add_argument('-l', '--link_only', help='Show KLE link instead of KLE raw data', action='store_true')
    args = parser.parse_args()

    try:
        layout = Layout(args.keymap)
        if args.link_only:
            print(layout.to_kle_url())
        else:
            print(layout.to_kle())

        if args.save_image in argv:
            save_image(layout.to_kle_url())

    except Exception as ex:
        exit(str(ex))
