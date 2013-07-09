# -*- coding: utf-8 -*-

# Copyright (c) 2013 Johannes Baiter. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
spreads CLI code.
"""

from __future__ import division, unicode_literals

import argparse
import logging
import os
import sys
import time

import spreads.confit as confit
from clint.textui import puts, colored

import spreads.workflow as workflow
from spreads import config
from spreads.plugin import get_devices, get_pluginmanager
from spreads.util import DeviceException

# Kudos to http://stackoverflow.com/a/1394994/487903
try:
    from msvcrt import getch
except ImportError:
    def getch():
        """ Wait for keypress on stdin.

        :returns: unicode -- Value of character that was pressed

        """
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def configure(args=None):
    for orientation in ('left', 'right'):
        puts("Please connect and turn on the device labeled \'{0}\'"
             .format(orientation))
        puts(colored.blue("Press any key when ready."))
        _ = getch()
        devs = get_devices()
        if len(devs) > 1:
            raise DeviceException("Please ensure that only one device is"
                                  " turned on!")
        if not devs:
            raise DeviceException("No device found!")
        devs[0].set_orientation(orientation)
        puts(colored.green("Configured \'{0}\' device.".format(orientation)))
        puts("Please turn off the device.")
        puts(colored.blue("Press any key when ready."))
        _ = getch()


def capture(args=None, devices=[]):
    if not devices:
        puts("Starting capture workflow, please connect and turn on the"
             " devices.")
        puts(colored.blue("Press any key to continue."))
        getch()
        puts("Detecting devices.")
        devices = get_devices()
        if len(devices) != 2:
            raise DeviceException("Please connect and turn on two"
                                  " pre-configured devices! ({0} were"
                                  " found)".format(len(devices)))
        puts(colored.green("Found {0} devices!".format(len(devices))))
        if any(not x.orientation for x in devices):
            raise DeviceException("At least one of the devices has not been"
                                  " properly configured, please re-run the"
                                  " program with the \'configure\' option!")
    # Set up for capturing
    puts("Setting up devices for capturing.")
    workflow.prepare_capture(devices)
    # Start capture loop
    puts(colored.blue("Press 'b' to capture."))
    shot_count = 0
    start_time = time.time()
    pages_per_hour = 0
    capture_keys = config['capture']['capture_keys'].as_str_seq()
    while True:
        if not getch().lower() in capture_keys:
            break
        workflow.capture(devices)
        shot_count += len(devices)
        pages_per_hour = (3600/(time.time() - start_time))*shot_count
        status = ("\rShot {0} pages [{1:.0f}/h]"
                  .format(colored.green(unicode(shot_count)), pages_per_hour))
        sys.stdout.write(status)
        sys.stdout.flush()
    workflow.finish_capture(devices)
    sys.stdout.write("\rShot {0} pages in {1:.1f} minutes, average speed was"
                     " {2:.0f} pages per hour"
                     .format(colored.green(str(shot_count)),
                             (time.time() - start_time)/60, pages_per_hour))
    sys.stdout.flush()


def download(args=None, path=None):
    if args.path:
        path = args.path
    devices = get_devices()
    status_str = "Downloading {0} images from devices"
    if config['download']['keep'].get(bool):
        status_str = status_str.format("and deleting ")
    else:
        status_str = status_str.format("")
    puts(colored.green(status_str))
    workflow.download(devices, path)


def postprocess(args=None, path=None):
    if args.path:
        path = args.path
    workflow.process(path)


def wizard(args):
    # TODO: Think about how we can make this more dynamic, i.e. get list of
    #       options for plugin with a description for each entry
    path = args.path
    puts("Please connect and turn on the devices.")
    puts(colored.blue("Press any key to continue."))
    getch()
    puts(colored.green("Detecting devices."))
    devices = get_devices()
    if any(not x.orientation for x in devices):
        puts(colored.yellow("Devices not yet configured!"))
        puts(colored.blue("Please turn both devices off."
                          " Press any key when ready."))
        while True:
            try:
                configure()
                break
            except DeviceException as e:
                print e

    puts(colored.green("=========================="))
    puts(colored.green("Starting capturing process"))
    puts(colored.green("=========================="))
    capture(devices=devices)

    puts(colored.green("========================="))
    puts(colored.green("Starting download process"))
    puts(colored.green("========================="))
    download(path=path)

    puts(colored.green("======================="))
    puts(colored.green("Starting postprocessing"))
    puts(colored.green("======================="))
    postprocess(path=path)

def setup_parser():
    pluginmanager = get_pluginmanager()
    parser = argparse.ArgumentParser(
        description="Scanning Tool for  DIY Book Scanner")
    subparsers = parser.add_subparsers()

    parser.add_argument(
        '--verbose', '-v', dest="verbose", action="store_true")

    config_parser = subparsers.add_parser(
        'configure', help="Perform initial configuration of the devices.")
    config_parser.set_defaults(func=configure)

    capture_parser = subparsers.add_parser(
        'capture', help="Start the capturing workflow")
    capture_parser.set_defaults(func=capture)
    # Add arguments from plugins
    pluginmanager.map(lambda x, y, z: x.plugin.add_arguments(y, z),
                      'capture', capture_parser)

    download_parser = subparsers.add_parser(
        'download', help="Download scanned images.")
    download_parser.add_argument(
        "path", help="Path where scanned images are to be stored")
    download_parser.add_argument(
        "--keep", "-k", dest="keep", action="store_true",
        help="Keep files on devices after download")
    download_parser.set_defaults(func=download)
    # Add arguments from plugins
    pluginmanager.map(lambda x, y, z: x.plugin.add_arguments(y, z),
                      'download', download_parser)

    postprocess_parser = subparsers.add_parser(
        'postprocess',
        help="Postprocess scanned images.")
    postprocess_parser.add_argument(
        "path", help="Path where scanned images are stored")
    postprocess_parser.add_argument(
        "--jobs", "-j", dest="jobs", type=int, default=None,
        metavar="<int>", help="Number of concurrent processes")
    postprocess_parser.set_defaults(func=postprocess)
    # Add arguments from plugins
    pluginmanager.map(lambda x, y, z: x.plugin.add_arguments(y, z),
                      'postprocess', postprocess_parser)

    wizard_parser = subparsers.add_parser(
        'wizard', help="Interactive mode")
    wizard_parser.add_argument(
        "path", help="Path where scanned images are to be stored")
    wizard_parser.set_defaults(func=wizard)

    pluginmanager.map(lambda x, y: x.plugin.add_command_parser(y),
                      subparsers)
    return parser


def main():
    parser = setup_parser()
    args = parser.parse_args()
    cfg_path = os.path.join(config.config_dir(), confit.CONFIG_FILENAME)
    if not os.path.exists(cfg_path):
        logging.info("Dumping default configuration to {0}".format(cfg_path))
        config.dump(filename=cfg_path)
    config.set_args(args)
    loglevel = config['loglevel'].as_choice({
        'none':     logging.NOTSET,
        'info':     logging.INFO,
        'debug':    logging.DEBUG,
        'warning':  logging.WARNING,
        'error':    logging.ERROR,
        'critical': logging.CRITICAL,
    })
    if args.verbose:
        loglevel = logging.DEBUG
    logging.basicConfig(level=loglevel)
    args.func(args)