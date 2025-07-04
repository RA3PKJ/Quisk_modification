# -*- coding: utf-8 -*- #added by RA3PKJ - строчка добавилась после того, как начал писать комментарии на русском языке ----------------------------------

#!/usr/bin/env python3

# All QUISK software is Copyright (C) 2006-2025 by James C. Ahlstrom.
# This free software is licensed for use under the GNU General Public
# License (GPL), see http://www.opensource.org.
# Note that there is NO WARRANTY AT ALL.  USE AT YOUR OWN RISK!!

"""The main program for Quisk, a software defined radio.

Usage:  python quisk.py [-c | --config config_file_path]
This can also be installed as a package and run as quisk.main().
"""

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

# ----------------------------------------------------- добавлено ----------------------- заголовок окна -------- 3 RA3PKJ
global version_quisk
version_quisk = 'QUISK 4.2.42.24 by N7DDC, RA3PKJ'

# Change to the directory of quisk.py.  This is necessary to import Quisk packages,
# to load other extension modules that link against _quisk.so, to find shared libraries *.dll and *.so,
# and to find ./__init__.py and ./help.html.
import sys, os

# ----------------------------------------------------- добавлено -------------------- автоматика водопада ------ 24 RA3PKJ
import numpy as np
import array

import serial # --------------------------------------- добавлено ------------------- COM-порты для Odyssey ----- 63 RA3PKJ

#print ('getcwd', os.getcwd())
#print ('__file__', __file__)
os.chdir(os.path.normpath(os.path.dirname(__file__)))	# change directory to the location of this script
if sys.path[0] != '':		# Make sure the current working directory is on path
  sys.path.insert(0, '')
#print ('getcwd', os.getcwd())

import wx, wx.html, wx.lib.stattext, wx.lib.colourdb, wx.grid
import math, cmath, time, traceback, string, select, subprocess
import threading, pickle, webbrowser, json
try:
  from xmlrpc.client import ServerProxy
except ImportError:
  from xmlrpclib import ServerProxy
import _quisk as QS
from quisk_widgets import *
from filters import Filters
import dxcluster
import configure
import quisk_conf_defaults as conf
import quisk_wdsp

for name in configure.name2format:      # Add defaults. These may be overwritten by a user config file.
  setattr(conf, name, configure.name2format[name][1])

DEBUGSHELL = False
if DEBUGSHELL:
  from wx.py.crust import CrustFrame
  from wx.py.shell import ShellFrame

# Fldigi XML-RPC control opens a local socket.  If socket.setdefaulttimeout() is not
# called, the timeout on Linux is zero (1 msec) and on Windows is 2 seconds.  So we
# call it to insure consistent behavior.
import socket
socket.setdefaulttimeout(0.005)

HAMLIB_DEBUG = 0

application = None

if sys.version_info.major > 2:
  Q3StringTypes = str
else:
  Q3StringTypes = (str, unicode)

class StdOutput(wx.Frame):
  def __init__(self, app):
    self.app = app
    self.ctrl = None
    self.old_stdout = sys.stdout
    self.old_stderr = sys.stderr
    self.old_excepthook = sys.excepthook
    self.path = os.path.join(app.QuiskFilesDir, "quisk_logfile.txt")
    try:
      size = os.path.getsize(self.path)
    except:
      size = 0
    if size > 10000:
      try:
        fp = open(self.path, 'r')
        lines = fp.readlines()
        fp.close()
        fp = open(self.path, 'w')
        for i in range(len(lines) // 2, len(lines)):
          fp.write(lines[i])
        fp.close()
      except:
        pass
    try:
      self.fp = open(self.path, "a", buffering=1, encoding='utf-8', errors='replace', newline=None)
    except:
      self.fp = None
    sys.stdout = self
    sys.stderr = self
    sys.excepthook = self.ExceptHook
    if self.fp:
      self.fp.write("\n\n*** Quisk started on %s at %s\n" % (sys.platform, time.asctime()))
  def Create(self, parent):
    w = self.app.screen_width * 4 // 10
    h = self.app.screen_height * 4 // 10
    title = "Quisk Log File %s" % self.path
    wx.Frame.__init__(self, parent, -1, title, size = (w, h), style=wx.DEFAULT_FRAME_STYLE)
    self.ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL)
    self.Bind(wx.EVT_SIZE, self.OnSize)
    self.Bind(wx.EVT_CLOSE, self.OnBtnClose)
    self.ctrl.write("*** Quisk started on %s at %s\n" % (sys.platform, time.asctime()))
  def OnSize(self, event):
    event.Skip()
    w, h = self.GetClientSize()
    self.ctrl.SetSize(w, h)
  def OnBtnClose(self, event):
    self.Show(False)
  def Logfile(self, text):
    if self.fp:
      self.fp.write(text)
      self.fp.write("\n")
  def write(self, text):
    if self.fp:
      self.fp.write(text)
    if self.old_stdout:
      self.old_stdout.write(text)
    if self.ctrl:
      self.ctrl.write(text)
  def flush(self):
    pass
  def ExceptHook(self, typ, value, traceb):
    self.Show(True)
    self.Raise()
    self.old_excepthook(typ, value, traceb)

# Command line parsing: be able to specify the config file.
from optparse import OptionParser
parser = OptionParser()
parser.add_option('-c', '--config', dest='config_file_path',
		help='Specify the configuration file path')
parser.add_option('', '--config2', dest='config_file_path2', default='',
		help='Specify a second configuration file to read after the first')
parser.add_option('-r', '--radio', dest="radio", default='',
		help='Specify the radio to use when starting')
parser.add_option('-a', '--ask', action="store_true", dest='AskMe', default=False,
		help='Ask which radio to use when starting')
parser.add_option('', '--local', dest='local_option', default='',
		help='Specify a custom option that you have programmed yourself')
argv_options = parser.parse_args()[0]
ConfigPath = argv_options.config_file_path	# Get config file path
ConfigPath2 = argv_options.config_file_path2
LocalOption = argv_options.local_option
if sys.platform == 'win32':
  path = os.getenv('HOMEDRIVE', '') + os.getenv('HOMEPATH', '')
  for thedir in ("Documents", "My Documents", "Eigene Dateien", "Documenti", "Mine Dokumenter"):
    config_dir = os.path.join(path, thedir)
    if os.path.isdir(config_dir):
      break
  else:
    config_dir = os.path.join(path, "My Documents")
  try:
    try:
      import winreg as Qwinreg
    except ImportError:
      import _winreg as Qwinreg
    key = Qwinreg.OpenKey(Qwinreg.HKEY_CURRENT_USER,
       r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
    val = Qwinreg.QueryValueEx(key, "Personal")
    val = Qwinreg.ExpandEnvironmentStrings(val[0])
    Qwinreg.CloseKey(key)
    if os.path.isdir(val):
      DefaultConfigDir = val
    else:
      DefaultConfigDir = config_dir
  except:
    traceback.print_exc()
    DefaultConfigDir = config_dir
  if not ConfigPath:
    ConfigPath = os.path.join(DefaultConfigDir, "quisk_conf.py")
    if not os.path.isfile(ConfigPath):
      path = os.path.join(config_dir, "quisk_conf.py")
      if os.path.isfile(path):
        ConfigPath = path
  del config_dir
else:
  DefaultConfigDir = os.path.expanduser('~')
  if not ConfigPath:
    ConfigPath = os.path.join(DefaultConfigDir, ".quisk_conf.py")

# These FFT sizes have multiple small factors, and are preferred for efficiency.  FFT size must be an even number.
fftPreferedSizes = []
for f2 in range(1, 13):
  for y in (1, 3, 5, 7, 9, 11, 13, 15):
    for z in (1, 3, 5, 7, 9, 11, 13, 15):
      x = 2**f2 * y * z
      if 300 <= x <= 5000 and x not in fftPreferedSizes:
        fftPreferedSizes.append(x)
fftPreferedSizes.sort()

def round(x):	# round float to nearest integer
  if x >= 0:
    return int(x + 0.5)
  else:
    return - int(-x + 0.5)

def str2freq (freq):
  if '.' in freq:
    freq = int(float(freq) * 1E6 + 0.1)
  else:
    freq = int(freq)
  return freq

def get_filter_tx(mode):	# Return the bandwidth, center of the Tx filters
  if mode in ('LSB', 'USB'):
    # -------------------------------------------------------- удалено----------------- Кнопка SSBtx Low ------- 45 RA3PKJ
    # bw = 2700
    # center = 1650
    # --------------------------------------------------------- взамен ---------------- Кнопка SSBtx Low ------- 45 RA3PKJ
    offset = application.offset_tx
    bw = 3000 - offset
    center = bw//2 + offset

  elif mode in ('CWL', 'CWU'):
    bw = 10
    center = 0
  elif mode in ('AM', 'DGT-IQ'):
    bw = 6000
    center = 0
  elif mode in ('FM', 'DGT-FM'):
    bw = 10000
    center = 0
  elif mode in ('FDV-L', 'FDV-U'):
    bw = 2700
    center = 1500
  else:
    bw = 2700
    center = 1650
  if mode in ('CWL', 'LSB', 'DGT-L', 'FDV-L'):
    center = - center
  return bw, center

Mode2Index = {'CWL':0, 'CWU':1, 'LSB':2, 'USB':3, 'AM':4, 'FM':5, 'EXT':6, 'DGT-U':7, 'DGT-L':8, 'DGT-IQ':9,
      'IMD':10, 'FDV-U':11, 'FDV-L':12, 'DGT-FM':13}

class Timer:
  """Debug: measure and print times every ptime seconds.

  Call with msg == '' to start timer, then with a msg to record the time.
  """
  def __init__(self, ptime = 1.0):
    self.ptime = ptime		# frequency to print in seconds
    self.time0 = 0			# time zero; measure from this time
    self.time_print = 0		# last time data was printed
    self.timers = {}		# one timer for each msg
    self.names = []			# ordered list of msg
    self.heading = 1		# print heading on first use
  def __call__(self, msg):
    tm = time.time()
    if msg:
      if not self.time0:		# Not recording data
        return
      if msg in self.timers:
        count, average, highest = self.timers[msg]
      else:
        self.names.append(msg)
        count = 0
        average = highest = 0.0
      count += 1
      delta = tm - self.time0
      average += delta
      if highest < delta:
        highest = delta
      self.timers[msg] = (count, average, highest)
      if tm - self.time_print > self.ptime:	# time to print results
        self.time0 = 0		# end data recording, wait for reset
        self.time_print = tm
        if self.heading:
          self.heading = 0
          print ("count, msg, avg, max (msec)")
        print("%4d" % count, end=' ')
        for msg in self.names:		# keep names in order
          count, average, highest = self.timers[msg]
          if not count:
            continue
          average /= count
          print("  %s  %7.3f  %7.3f" % (msg, average * 1e3, highest * 1e3), end=' ')
          self.timers[msg] = (0, 0.0, 0.0)
        print()
    else:	# reset the time to zero
      self.time0 = tm		# Start timer
      if not self.time_print:
        self.time_print = tm

## T = Timer()		# Make a timer instance

class HamlibHandlerSerial:
  "Create a serial port for Hamlib control that emulates the FlexRadio PowerSDR 2.x command set."
  # This implements some Kenwood TS-2000 commands, but it is far from complete.
  # See http://k5fr.com/binary/CatCommandReferenceGuide.pdf
  # Test on linux by setting the Quisk serial port to /tmp/QuiskTTY0 and using putty with font Ubuntu Mono.
  # Commands are "ZZAR;"  and  "ZZAR+030;"   -   no newline.

  # Additional logic contributed by Dr. Karsten Schmidt

  Mo2CoKen = {'CWL':7, 'CWU':3, 'LSB':1, 'USB':2, 'AM':5, 'FM':4, 'DGT-U':9, 'DGT-L':6, 'DGT-FM':4, 'DGT-IQ':9}
  Co2MoKen = {1:'LSB', 2:'USB', 3:'CWU', 4:'FM', 5:'AM', 6:'DGT-L', 7:'CWL', 9:'DGT-U'}
  Mo2CoFlex = {'CWL':3, 'CWU':4, 'LSB':0, 'USB':1, 'AM':6, 'FM':5, 'DGT-U':7, 'DGT-L':9, 'DGT-FM':5, 'DGT-IQ':7}
  Co2MoFlex = {0:'LSB', 1:'USB', 3:'CWL', 4:'CWU', 5:'FM', 6:'AM', 7:'DGT-U', 9:'DGT-L'}
  ConvertZZAC_P1_2_Step = { 0:     1,
                          1:    10,
                          2:    50,
                          3:   100,
                          4:   250,
                          5:    500,
                          6:   1000,
                          7:   5000,
                          8:   9000,
                          9:   10000,
                         10:   100000,
                         11:   250000,
                         12:   500000,
                         13:  1000000,
                         14: 10000000}
  ConvertZZAC_Step_2_P1 = {         1:  0,
                                 10:  1,
                                 50:  2,
                                100:  3,
                                250:  4,
                                500:  5,
                              1000:  6,
                              5000:  7,
                              9000:  8,
                             10000:  9,
                            100000: 10,
                            250000: 11,
                            500000: 12,
                          1000000: 13,
                         10000000: 14}
  def __init__(self, app, public_name):
    self.app = app
    self.port = None
    self.received = ''
    self.radio_id = '019'
    self.public_name = public_name	# the public name for the serial port
    self.tune_step = 1000
    if sys.platform == 'win32' or public_name.startswith("/dev/"):
      self.port_is_mod_serial = True	# self.port is from the serial module
      try:
        import serial
      except:
        print ("Please install the pyserial module.")
      else:
        try:
          self.port = serial.Serial(public_name, timeout=0, write_timeout=0)
          if HAMLIB_DEBUG: print ("Open CAT serial port", public_name)
        except:
          print ("The serial port %s could not be opened." % public_name)
    else:
      import tty
      self.port_is_mod_serial = False	# self.port is a file descriptor
      if os.path.lexists(public_name):
        try:
          os.remove(public_name)
        except:
          print ("Can not remove the file", public_name)
      try:
        self.port, slave = os.openpty()	# we are the master device fd, slave is a pseudo tty
        tty.setraw(self.port)
        tty.setraw(slave)
      except:
        print ("Can not create the serial port")
        self.port = None
      else:
        try:
          os.symlink(os.ttyname(slave), public_name)	# create a link from the specified name to the slave device
        except:
          print ("Can not create a link named", public_name)
          self.port = None
        else:
          if HAMLIB_DEBUG: print ("Create", public_name, "from", os.ttyname(slave))
  def open(self):
    return
  def close(self):
    if self.port_is_mod_serial:
      if self.port:
        self.port.close()
      self.port = None
    else:
      if self.public_name:
        try:
          os.remove(self.public_name)
        except:
          pass
  def Read(self):
    if self.port is None:
      return
    if self.port_is_mod_serial:
      text = self.port.read(99)
      if not isinstance(text, Q3StringTypes):
        text = text.decode('utf-8')
      self.received += text
    else:
      while True:
        r, w, x = select.select((self.port,), (), (), 0)
        if not r:
          break
        text = os.read(self.port, 1)
        if not isinstance(text, Q3StringTypes):
          text = text.decode('utf-8')
        self.received += text
  def Process(self):
    """This is the main processing loop, and is called frequently.  It reads and satisfies requests."""
    self.Read()
    if ';' in self.received:	# A complete command ending with semicolon is available
      cmd, self.received = self.received.split(';', 1)	# Split off the command, save any further characters
    else:
      return
    cmd = cmd.strip()		# Here is our command and data
    if cmd[0:2] in ('ZZ', 'zz', 'Zz', 'zZ'):
      data = cmd[4:]
      cmd = cmd[0:4].upper()
      func = cmd
    else:
      data = cmd[2:]
      cmd = cmd[0:2].upper()
      #if cmd in ('FA', 'FB', 'IF', 'PS'): # Use the ZZxx command method # ---- удалено ---- устранение ошибок из-за несоответствия CAT-протоколов TS-590S и Flex ---- 54 RA3PKJ
      if cmd in ('FA', 'FB', 'PS'):        # Use the ZZxx command method # ----- взамен ---- устранение ошибок из-за несоответствия CAT-протоколов TS-590S и Flex ---- 54 RA3PKJ
        func = 'ZZ' + cmd
      else:			# Use the two-letter method
        func = cmd
    if data:
      if HAMLIB_DEBUG: print ("Process command  :", cmd, data)
    try:
      func = getattr(self, func)
    except:
      print ("Unimplemented serial port function", func, 'cmd', cmd, 'data', data)
      self.Write('?;')
      return
    func(cmd, data, len(data))
  def Error(self, cmd, data):
    self.Write('?;')
    print ("*** Error for cmd %s data %s" % (cmd, data))
  def Write(self, data):
    if HAMLIB_DEBUG: print ("Serial port write:", data)
    if self.port is None:
      return
    if isinstance(data, Q3StringTypes):
      data = data.encode('utf-8', errors='ignore')
    if self.port_is_mod_serial:
      self.port.write(data)
    else:
      r, w, x = select.select((), (self.port,), (), 0)
      if w:
        os.write(self.port, data)
  def set_frequency(self, freq):	# This changes the Rx frequency
    self.app.ChangeRxTxFrequency(freq, None)
    if HAMLIB_DEBUG: print("New Freq rx,tx", self.app.txFreq + self.app.VFO, self.app.rxFreq + self.app.VFO)
  def ZZAC(self, cmd, data, length):  # Set or read tune steps
    if length == 0:
      xxx = self.ConvertZZAC_Step_2_P1.get(self.tune_step)
      self.Write("%s%02d;" % (cmd, xxx))
    elif length == 2:
      p1 = int(data, base=10)
      try:
        self.tune_step = self.ConvertZZAC_P1_2_Step.get(p1)
      except:
        self.Error(cmd, data)
    else:
      self.Error(cmd, data)
  def ZZAD(self, cmd, data, length):  # VFO A down by a selected step
    if length == 0:
      oldfreq = self.app.rxFreq + self.app.VFO
      self.tune_step = application.freq_step # ------------------------------ добавлено ----------------------------------- шаг перестройки ------- 30 RA3PKJ
      freq = oldfreq - self.tune_step
      self.set_frequency(freq)
    else:
      self.Error(cmd, data)
  def AG(self, cmd, data, length):	# audio gain
    if length == 1:
      self.Write("%s%s120;" % (cmd, data[0]))
  def ZZAG(self, cmd, data, length):	# audio gain
    if length == 0:
      n = (self.app.volumeAudio + 5) / 10
      self.Write("%s%03d;" % (cmd, n))
    elif length == 3:
      vol = int(data, base=10) * 10
      self.app.sliderVol.SetValue(vol)
      self.app.ChangeVolume()
    else:
      self.Error(cmd, data)
  def ZZAR(self, cmd, data, length):	# AGC level
    if length == 0:
      n = self.app.levelAGC * 140 // 1000 - 20	# Convert AGC 0 to 1000 -> -20 to 120
      if n < 0:
        self.Write("%s-%03d;" % (cmd, - n))
      else:
        self.Write("%s+%03d;" % (cmd, n))
    elif length == 4:
      val = int(data, base=10)
      val = (val + 20) * 1000 // 140	# Convert AGC -20 to 120 -> 0 to 1000
      self.app.SliderAGC.SetSlider(value_on=val)
      self.app.BtnAGC.SetValue(True, True)
    else:
      self.Error(cmd, data)
  def ZZAU(self, cmd, data, length):  # VFO A up by a selected step
    if length == 0:
      oldfreq = self.app.rxFreq + self.app.VFO
      self.tune_step = application.freq_step # ------------------------------ добавлено ----------------------------------- шаг перестройки ------- 30 RA3PKJ
      freq = oldfreq + self.tune_step
      self.set_frequency(freq)
    else:
      self.Error(cmd, data)
  def ZZBD(self, cmd, data, length): # диапазон вниз ------------------------ добавлено ---- встраивание своих CAT-команд для аппаратной панели --- 53 RA3PKJ
    band = self.app.lastBand
    if band == '40' or band == '60':
      band = '80'
      index_band = conf.bandLabels.index(band)
    else:
      index_band = conf.bandLabels.index(band)
      index_band -= 1
    length = len(conf.bandLabels)
    if index_band < 0:
      index_band = length -1
    band = conf.bandLabels[index_band]
    self.app.bandBtnGroup.SetLabel(band, do_cmd=True, direction=0)
  def ZZBU(self, cmd, data, length): # диапазон вверх ----------------------- добавлено ---- встраивание своих CAT-команд для аппаратной панели --- 53 RA3PKJ
    band = self.app.lastBand
    if band == '80' or band == '60':
      band = '40'
      index_band = conf.bandLabels.index(band)
    else:
      index_band = conf.bandLabels.index(band)
      index_band += 1
    length = len(conf.bandLabels)
    if index_band >= length:
      index_band = 0
    band = conf.bandLabels[index_band]
    self.app.bandBtnGroup.SetLabel(band, do_cmd=True, direction=0)
  def ZZBS(self, cmd, data, length):	# band switch
    if length == 0:
      band = self.app.lastBand
      try:
        band = int(band, base=10)
        self.Write("%s%03d;" % (cmd, band))
      except:
        self.Write("%s888;" % cmd)
    elif length == 3:
      band = data
      if band[0] == '0':
        band = band[1:]
      if band[0] == '0':
        band = band[1:]
      try:
        self.app.bandBtnGroup.SetLabel(band, do_cmd=True, direction=0)
      except:
        self.Error(cmd, data)
    else:
      self.Error(cmd, data)
  def ZZAI(self, cmd, data, length):	# broadcast changes
    if length == 0:
      self.Write("%s0;" % cmd)
    elif length == 1 and data[0] == '0':
      pass
    else:
      self.Error(cmd, data)
  def ZZFA(self, cmd, data, length):	# frequency of VFO A, the receive frequency
    if length == 0:
      self.Write("%s%011d;" % (cmd, self.app.rxFreq + self.app.VFO))
    elif length == 11:
      freq = int(data, base=10)
      self.set_frequency(freq)
    else:
      self.Error(cmd, data)
  def ZZFB(self, cmd, data, length):	# frequency of VFO B
    if length == 0:
      self.Write("%s%011d;" % (cmd, self.app.txFreq + self.app.VFO))
    elif length == 11:
      freq = int(data, base=10)
      tune = freq - self.app.VFO
      d = self.app.sample_rate * 45 // 100
      if -d <= tune <= d:	# Frequency is on-screen
        vfo = self.app.VFO
      else:					# Change the VFO
        vfo = (freq // 5000) * 5000 - 5000
        tune = freq - vfo
      self.app.BandFromFreq(freq)
      self.app.ChangeHwFrequency(tune, vfo, 'FreqEntry')
    else:
      self.Error(cmd, data)
  def FR(self, cmd, data, length):	# receive VFO is always VFO A
    if length == 0:
      self.Write("%s0;" % cmd)
    elif length == 1 and data[0] == '0':
      pass
    else:
      self.Error(cmd, data)
  def FT(self, cmd, data, length):	# transmit VFO
    if self.app.split_rxtx:
      vfo = '1'
    else:
      vfo = '0'
    if length == 0:
      self.Write("%s%s;" % (cmd, vfo))
    elif length == 1 and data[0] == vfo:
      pass
    else:
      self.Error(cmd, data)
  def ID(self, cmd, data, length):	# return radio ID
    if length == 0:
      self.Write('%s%s;' % (cmd, self.radio_id))
    else:
      self.Error(cmd, data)
  def ZZID(self, cmd, data, length):	# set radio id to Flex
    if length == 0:
      self.radio_id = '900'
    else:
      self.Error(cmd, data)
  def IF(self, cmd, data, length):# -------------- добавлено ------- устранение ошибок из-за несоответствия CAT-протоколов TS-590S и Flex -------- 54 RA3PKJ
    ritFreq = self.app.ritScale.GetValue()
    if self.app.ritButton.GetValue():
      rit = 1
    else:
      rit = 0
    mode = self.app.mode
    info = cmd
    info += "%011d" % (self.app.rxFreq + self.app.VFO)    # frequency, ZZFA
    info += '00000'
    if ritFreq < 0:    # RIT freq
      info += "-%04d" % -ritFreq
    else:
      info += "+%04d" % ritFreq
    info += "%d" % rit    # RIT status
    info += '0000'
    if QS.is_key_down():    # MOX, key down
      info += '1'
    else:
      info += '0'
    if len(cmd) == 4:    # Flex ZZIF
      code = self.Mo2CoFlex.get(mode, 1)
      info += "%02d" % code    # operating mode
    else:        # Kenwood IF
      code = self.Mo2CoKen.get(mode, 1)
      info += "%d" % code    # operating mode
    info += '00'
    if self.app.split_rxtx:
      info += '1'
    else:
      info += '0'
    info += '0000'
    info += ';'
    self.Write(info)
  def ZZIF(self, cmd, data, length):	# return information for ZZIF and IF
    ritFreq = self.app.ritScale.GetValue()
    if self.app.ritButton.GetValue():
      rit = 1
    else:
      rit = 0
    mode = self.app.mode
    info = cmd
    info += "%011d" % (self.app.rxFreq + self.app.VFO)	# frequency, ZZFA
    if len(cmd) == 4:	# Flex ZZIF
      info += '0000'
      if ritFreq < 0:	# RIT freq
        info += "-%05d" % -ritFreq
      else:
        info += "+%05d" % ritFreq
    else:		# Kenwood IF
      info += '00000'
      if ritFreq < 0:	# RIT freq
        info += "-%04d" % -ritFreq
      else:
        info += "+%04d" % ritFreq
    info += "%d" % rit	# RIT status
    info += '0000'
    if QS.is_key_down():	# MOX, key down
      info += '1'
    else:
      info += '0'
    if len(cmd) == 4:	# Flex ZZIF
      code = self.Mo2CoFlex.get(mode, 1)
      info += "%02d" % code	# operating mode
    else:		# Kenwood IF
      code = self.Mo2CoKen.get(mode, 1)
      info += "%d" % code	# operating mode
    info += '00'
    if self.app.split_rxtx:
      info += '1'
    else:
      info += '0'
    info += '0000'
    info += ';'
    self.Write(info)
  def IG(self, cmd, data, length): # ------------------------ добавлено -------------- встраивание своих CAT-команд для аппаратной панели -------- 53 RA3PKJ
    ritFreq = self.app.ritScale.GetValue()
    if self.app.ritButton.GetValue():
      rit = 1
    else:
      rit = 0
    mode = self.app.mode
    info = cmd
    info += "%011d" % (self.app.rxFreq + self.app.VFO)    # frequency, ZZFA
    info += "%05d" % application.freq_step # --------------------------------- добавлен шаг перестойки
    if ritFreq < 0:    # RIT freq
      info += "-%04d" % -ritFreq
    else:
      info += "+%04d" % ritFreq
    info += "%d" % rit    # RIT status
    info += '0000'
    if QS.is_key_down():    # MOX, key down
      info += '1'
    else:
      info += '0'
    if len(cmd) == 4:    # Flex ZZIF
      code = self.Mo2CoFlex.get(mode, 1)
      info += "%02d" % code    # operating mode
    else:        # Kenwood IF
      code = self.Mo2CoKen.get(mode, 1)
      info += "%d" % code    # operating mode
    info += '00'
    if self.app.split_rxtx:
      info += '1'
    else:
      info += '0'
    info += '0000'
    info += ';'
    self.Write(info)
  def IJ(self, cmd, data, length): # переключение шага ---- добавлено ---- встраивание своих CAT-команд для аппаратной панели -------- 53 RA3PKJ
    step_label = application.step_btn.GetLabel()
    if step_label == 'Step 1':
      application.freq_step = 10
      application.step_btn.SetLabel("Step 10", do_cmd=False)
    elif step_label == 'Step 10':
      application.freq_step = 25
      application.step_btn.SetLabel("Step 25", do_cmd=False)
    elif step_label == 'Step 25':
      application.freq_step = 50
      application.step_btn.SetLabel("Step 50", do_cmd=False)
    elif step_label == 'Step 50':
      application.freq_step = 100
      application.step_btn.SetLabel("Step 100", do_cmd=False)
    elif step_label == 'Step 100':
      application.freq_step = 250
      application.step_btn.SetLabel("Step 250", do_cmd=False)
    elif step_label == 'Step 250':
      application.freq_step = 500
      application.step_btn.SetLabel("Step 500", do_cmd=False)
    elif step_label == 'Step 500':
      application.freq_step = 1000
      application.step_btn.SetLabel("Step 1kHz", do_cmd=False)
    elif step_label == 'Step 1kHz':
      application.freq_step = 1
      application.step_btn.SetLabel("Step 1", do_cmd=False)
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    configure.Settings[4]["FrequencyStep"] = application.freq_step
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False
  def MD(self, cmd, data, length):	# the mode; USB, CW, etc.
    if length == 0:
      mode = self.app.mode
      code = self.Mo2CoKen.get(mode, 2)
      self.Write("%s%d;" % (cmd, code))
    elif length == 1:
      code = int(data, base=10)
      mode = self.Co2MoKen.get(code, 'USB')
      self.app.modeButns.SetLabel(mode, True)		# Set mode
    else:
      self.Error(cmd, data)
  def ZZMD(self, cmd, data, length):	# the mode; USB, CW, etc.
    if length == 0:
      mode = self.app.mode
      code = self.Mo2CoFlex.get(mode, 1)
      self.Write("%s%02d;" % (cmd, code))
    elif length == 2:
      code = int(data, base=10)
      mode = self.Co2MoFlex.get(code, 'USB')
      self.app.modeButns.SetLabel(mode, True)		# Set mode
    else:
      self.Error(cmd, data)
  def ZZMU(self, cmd, data, length):	# MultiRx on/off
    if length == 0:
      self.Write("%s0;" % cmd)
  def OI(self, cmd, data, length):      # return information
    self.ZZIF(cmd, data, length)
  def ZZPA(self, cmd, data, length): # переключените аттенюатора HiQSDDR --- добавлено --- встраивание своих CAT-команд для аппаратной панели --- 53 RA3PKJ
    try:
      if Hardware.hard_radio == "hiqsdr":
        att_label = application.BtnRfGain.GetLabel()
        if att_label == 'ATT 0db':
          Hardware.HiQSDR_Attenuator = 0x08
          Hardware.rf_gain = -10
          application.BtnRfGain.SetLabel("ATT -10db", do_cmd=False)
        elif att_label == 'ATT -10db':
          Hardware.HiQSDR_Attenuator = 0x10
          Hardware.rf_gain = -20
          application.BtnRfGain.SetLabel("ATT -20db", do_cmd=False)
        elif att_label == 'ATT -20db':
          Hardware.HiQSDR_Attenuator = 0x18
          Hardware.rf_gain = -30
          application.BtnRfGain.SetLabel("ATT -30db", do_cmd=False)
        elif att_label == 'ATT -30db':
          Hardware.HiQSDR_Attenuator = 0
          Hardware.rf_gain = 0
          application.BtnRfGain.SetLabel("ATT 0db", do_cmd=False)
        Hardware.NewUdpStatus()
    except:
      pass
  def ZZPS(self, cmd, data, length):	# power status
    if length == 0:
      self.Write("%s1;" % cmd)
  def ZZRC(self, cmd, data, length): # обнуление RIT --------------------- добавлено ---- встраивание своих CAT-команд для аппаратной панели ---- 53 RA3PKJ
    application.ritScale.SetValue(0)
    application.OnRitScale()
  def ZZRD(self, cmd, data, length): # RIT на один шаг меньше ------------ добавлено ---- встраивание своих CAT-команд для аппаратной панели ---- 53 RA3PKJ
    ritFreq = application.ritScale.GetValue()
    ritFreq -= application.freq_step
    if ritFreq < -2000:
      ritFreq = -2000
    application.ritScale.SetValue(ritFreq)
    application.ritButton.SetLabel("RIT %d" % ritFreq)
    application.ritButton.Refresh()
    application.OnRitScale()
  def ZZRS(self, cmd, data, length):	# the RX2 status
    if length == 0:
      self.Write("%s0;" % cmd)
    elif length == 1 and data[0] == '0':
      pass
    else:
      self.Error(cmd, data)
  def ZZRT(self, cmd, data, length): # вкл/выкл RIT ---------------------- добавлено ---- встраивание своих CAT-команд для аппаратной панели ---- 53 RA3PKJ
    if not application.ritButton.GetValue(): # ------------ если RIT не нажата, то нажать
      application.ritButton.SetValue("RIT") # ------- происходит физическое нажатие кнопки в окне Quisk
      application.OnBtnRit() # --------------------- происходит реальное применение расстройки, которая накручена слайдером RIT
    else:
      application.ritButton.SetValue("") # ---------- происходит физическое отжатие кнопки в окне Quisk
      application.ritFreq = 0 # -------------------- подготовка для возврата приёмника на исходную частоту
      application.OnBtnRit() # --------------------- происходит реальное отключение расстройки
  def ZZRU(self, cmd, data, length): # RIT на один шаг больше ------------ добавлено ---- встраивание своих CAT-команд для аппаратной панели ---- 53 RA3PKJ
    ritFreq = application.ritScale.GetValue()
    ritFreq += application.freq_step
    if ritFreq > 2000:
      ritFreq = 2000
    application.ritScale.SetValue(ritFreq)
    application.ritButton.SetLabel("RIT %d" % ritFreq)
    application.ritButton.Refresh()
    application.OnRitScale()
  def RX(self, cmd, data, length):	# turn off MOX
    if length == 0:
      self.app.pttButton.SetValue(0, True)
    else:
      self.Error(cmd, data)
  def ZZSM(self, cmd, data, length):	# return the S-meter value in dB * 2; 0 to 260
    if length == 0:			# 0 to 260 is -140 to -10 dB; S9 == -73 dB == 134; dB = ZZSM / 2 - 140
      i = round((self.app.hamlib_strength + 67) * 2)
      if i < 0:
        i = 0
      elif i > 260:
        i = 260
      self.Write('%s%03d;' % (cmd, i))
    else:
      self.Error(cmd, data)
  def ZZSP(self, cmd, data, length):	# the split status
    if length == 0:
      if self.app.split_rxtx:
        self.Write("%s1;" % cmd)
      else:
        self.Write("%s0;" % cmd)
    else:
      self.Error(cmd, data)
  def ZZSW(self, cmd, data, length):	# transmit VFO is A or B
    if length == 0:
      if self.app.split_rxtx:
        self.Write("%s1;" % cmd)
      else:
        self.Write("%s0;" % cmd)
  def TX(self, cmd, data, length):	# turn on MOX
    if length == 0:
      self.app.pttButton.SetValue(1, True)
    else:
      self.Error(cmd, data)
  def ZZTX(self, cmd, data, length):	# the MOX status
    if length == 0:
      if QS.is_key_down():
        self.Write("%s1;" % cmd)
      else:
        self.Write("%s0;" % cmd)
    elif length == 1:
      if data[0] == '0':
        self.app.pttButton.SetValue(0, True)
      else:
        self.app.pttButton.SetValue(1, True)
    else:
      self.Error(cmd, data)
  def ZZVE(self, cmd, data, length):	# is VOX enabled
    if length == 0:
      if self.app.useVOX:
        self.Write("%s1;" % cmd)
      else:
        self.Write("%s0;" % cmd)
    else:
      self.Error(cmd, data)
  def XT(self, cmd, data, length):	# the XIT
    if length == 0:
      self.Write("%s0;" % cmd)
    elif length == 1 and data[0] == '0':
      pass
    else:
      self.Error(cmd, data)

class HamlibHandlerRig2:	# Test with telnet localhost 4532
  """This class is created for each connection to the server.  It services requests from each client."""
  SingleLetters = {		# convert single-letter commands to long commands
    '_':'info',
    'f':'freq',
    'i':'split_freq',
    'l':'level',
    'm':'mode',
    'p':'parm',
    's':'split_vfo',
    't':'ptt',
    'u':'func',
    'v':'vfo',
    }
  def __init__(self, app, sock, address):
    self.app = app		# Reference back to the "hardware"
    self.sock = sock
    sock.settimeout(0.0)
    self.address = address
    self.params = ''	# params is the string following the command
    self.received = ''
    self.input = ''
    self.vfo = "Main"
    self.split_mode = 0
    self.split_vfo = 'VFO'
    h = self.Handlers = {}
    h[''] = self.ErrProtocol
    h['dump_state']	= self.DumpState
    h['chk_vfo']	= self.ChkVfo	# Thanks to Franco Spinelli, IW2DHW
    h['get_freq']	= self.GetFreq
    h['set_freq']	= self.SetFreq
    h['get_info']	= self.GetInfo
    h['get_mode']	= self.GetMode
    h['set_mode']	= self.SetMode
    h['get_vfo']	= self.GetVfo
    h['set_vfo']	= self.SetVfo
    h['get_func']	= self.GetFunc
    h['set_func']	= self.SetFunc
    h['get_level']	= self.GetLevel
    h['set_level']	= self.SetLevel
    h['get_parm']	= self.GetParm
    h['set_parm']	= self.SetParm
    h['get_ptt']	= self.GetPtt
    h['set_ptt']	= self.SetPtt
    h['get_split_freq']	= self.GetSplitFreq
    h['set_split_freq']	= self.SetSplitFreq
    h['get_split_vfo']	= self.GetSplitVfo
    h['set_split_vfo']	= self.SetSplitVfo
    self.MakeDumpState()
  def MakeDumpState(self):
    dump_state = []
    # rigctld protocol version
    dump_state.append( b"0" )
    # rig model
    dump_state.append( b"2" )
    # ITU region
    dump_state.append( b"1" ) # Europe, Africa and Northern Asia
    #dump_state.append( b"2" ) # North America, South America and Greenland
    #dump_state.append( b"3" ) # South Pacific and Southern Asia
    # RX frequency ranges
    # start, end, modes, low_power, high_power, vfo, ant
    #dump_state.append( b"150000.000000 1500000000.000000 0x1ff -1 -1 0x10000003 0x3" )
    # AM | CW | USB | LSB | NFM | WFM | DSB
    dump_state.append( b"100000.000000 6000000000.000000 0x8006f -1 -1 0x4000000 0x3" ) # HackRF (100kHz - 6GHz), VFO:Main
    # End of RX frequency ranges
    dump_state.append( b"0 0 0 0 0 0 0" )
    # TX frequency ranges
    # start, end, modes, low_power, high_power, vfo, ant
    dump_state.append( b"100000.000000 6000000000.000000 0x8006f -1 -1 0x4000000 0x3" ) # HackRF (100kHz - 6GHz), VFO:Main
    # End of TX frequency ranges
    dump_state.append( b"0 0 0 0 0 0 0" )
    # Tuning steps
    # mode, tuning_step
    dump_state.append( b"0x1ff 1" )
    dump_state.append( b"0x1ff 0" )
    # End of tuning steps
    dump_state.append( b"0 0" )
    # Filter sizes
    # mode, width
    dump_state.append( b"0x1e 2400" )
    dump_state.append( b"0x2 500" )
    dump_state.append( b"0x1 8000" )
    dump_state.append( b"0x1 2400" )
    dump_state.append( b"0x20 15000" )
    dump_state.append( b"0x20 8000" )
    dump_state.append( b"0x40 230000" )
    # End of filter sizes
    dump_state.append( b"0 0" )
    # ------ ??? ------
    # max_rit
    dump_state.append( b"9990" )
    # max_xit
    dump_state.append( b"9990" )
    # max_ifshift
    dump_state.append( b"10000" )
    # announces
    dump_state.append( b"0" )
    # MAXDBLSTSIZ preamp
    dump_state.append( b"10" )
    # MAXDBLSTSIZ attenuator
    dump_state.append( b"10 20 30" )
    # has_get_func
    dump_state.append( b"0x3effffff" )
    # has_set_func
    dump_state.append( b"0x3effffff" )
    # has_get_level
    dump_state.append( b"0xfffffffff7ffffff" )
    # has_set_level
    dump_state.append( b"0xffffffff83ffffff" )
    # has_get_parm
    dump_state.append( b"0xffffffffffffffff" )
    # has_set_parm
    dump_state.append( b"0xffffffffffffffbf" )
    # END
    self.dump_state = b'\n'.join(dump_state)
    self.dump_state += b'\n'
  def Send(self, text):
    """Send text back to the client."""
    if isinstance(text, Q3StringTypes):
      text = text.encode('utf-8', errors='ignore')
    if HAMLIB_DEBUG:
      print ("Rig2 send", text)
    try:
      self.sock.sendall(text)
    except socket.error:
      self.sock.close()
      self.sock = None
  def Reply(self, *args):	# args is name, value, name, value, ..., int
    """Create a string reply of name, value pairs, and an ending integer code."""
    if self.extended:	# Use extended format; echo the command and parameters.
      t = "%s:" % self.command
      if self.params:
        t += " %s" % self.params
      t += self.extended
      for i in range(0, len(args) - 1, 2):
        t = "%s%s: %s%c" % (t, args[i], args[i+1], self.extended)
      t += "RPRT %d\n" % args[-1]
    elif len(args) > 1:		# Use simple format
      t = ''
      for i in range(1, len(args) - 1, 2):
        t = "%s%s\n" % (t, args[i])
    else:		# No names; just the required integer code
      t = "RPRT %d\n" % args[0]
    self.Send(t)
  def Reply2(self, text, code):
    """Create a reply string in a different format."""
    if self.extended:			# Use extended format
      t = "%s: %s%s%s\nRPRT %d\n" % (self.command, self.params, self.extended, text, code)
      self.Send(t)
    else:
      if self.command[0:4] == "set_":
        self.Send("%s\nRPRT %d\n" % (text, code))
      else:
        self.Send("%s\n" % text)
  def ErrParam(self):		# Invalid parameter
    self.input = ''
    self.Reply(-1)
  def UnImplemented(self):	# Command not implemented
    self.input = ''
    self.Reply(-4)
  def ErrProtocol(self):	# Protocol error
    self.input = ''
    self.Reply(-8)
  def GetParamNumber(self):
    if not self.input:
      return None
    number = ''
    for i in range(len(self.input)):
      ch = self.input[i]
      if ch in "+-.0123456789":
        number = number + ch
      else:
        self.input = self.input[i:].strip()
        break
    else:
      self.input = ''
    if self.params:
      self.params = self.params + ' ' + number
    else:
      self.params = number
    try:
      if '.' in number:
        return float(number)
      else:
        return int(number)
    except:
      return None
  def GetParamName(self):
    if not self.input:
      return ''
    if self.input[0] == '?':
      self.params = '?'
      self.input = self.input[1:].strip()
      return '?'
    name = ''
    for i in range(len(self.input)):
      ch = self.input[i]
      if ch in string.ascii_letters or ch in "_-":
        name = name + ch
      else:
        self.input = self.input[i:].strip()
        break
    else:
      self.input = ''
    if self.params:
      self.params = self.params + ' ' + name
    else:
      self.params = name
    return name
  def Process(self):
    """This is the main processing loop, and is called frequently.  It reads and satisfies requests."""
    if not self.sock:
      return 0
    try:	# Read any data from the socket
      text = self.sock.recv(1024)
    except socket.timeout:	# This does not work
      pass
    except socket.error:	# Nothing to read
      pass
    else:					# We got some characters
      if not isinstance(text, Q3StringTypes):
        text = text.decode('utf-8')
      self.received += text
      if HAMLIB_DEBUG and text:
        print ("Raw rig2 received:", text)
    if '\n' in self.received:	# A complete command ending with newline is available
      self.input, self.received = self.received.split('\n', 1)	# Split off the command, save any further characters
    else:
      return 1
    self.input = self.input.strip()		# Here is our command line
    if HAMLIB_DEBUG:
      print ("Rig2 received", self.input)
    while self.input:
      # Parse the commands and call the appropriate handlers
      self.params = ''
      if self.input[0] == '+':			# rigctld Extended Response Protocol
        self.extended = '\n'
        self.input = self.input[1:].strip()
      elif self.input[0] in ';|,':		# rigctld Extended Response Protocol
        self.extended = self.input[0]
        self.input = self.input[1:].strip()
      else:
        self.extended = None
      letter = self.input[0:1]
      if letter == '\\':		# long form command starting with backslash
        args = self.input[1:].split(None, 1)
        self.command = args[0]
        if len(args) == 1:
          self.input = ''
        else:
          self.input = args[1].strip()
      else:		# single-letter commands
        self.input = self.input[1:].strip()
        if letter in 'Qq':	# Quit command
          self.sock.close()
          self.input = ''
          return 0
        try:
          command = self.SingleLetters[letter.lower()]
        except KeyError:
          self.UnImplemented()
          return 1
        else:
          if letter in string.ascii_uppercase:
            self.command = 'set_' + command
          else:
            self.command = 'get_' + command
      self.Handlers.get(self.command, self.UnImplemented)()
    return 1
  # These are the handlers for each request
  def DumpState(self):
    self.Send(self.dump_state)
  def ChkVfo(self):
    if self.extended:
      self.Send('ChkVFO: 0\n')
    else:
      self.Send('0\n')
  def GetFreq(self):	# The Rx frequency
    rx = self.app.multi_rx_screen.receiver_list
    if rx:
      rx = rx[0]
      self.Reply('Frequency', rx.txFreq + rx.VFO, 0)
      if HAMLIB_DEBUG:
        print ("GetFreq rx", rx.txFreq, rx.VFO)
    else:
      self.Reply('Frequency', self.app.rxFreq + self.app.VFO, 0)
      if HAMLIB_DEBUG:
        print ("GetFreq app", self.app.rxFreq, self.app.txFreq, self.app.VFO)
  def SetFreq(self):	# The Rx frequency
    freq = self.GetParamNumber()
    try:
      freq = float(freq)
      self.Reply(0)
    except:
      self.ErrParam()
    else:
      freq = int(freq + 0.5)
      # For multiple receivers this controls the first added receiver frequency; else it controls split Rx/Tx frequency.
      rx = self.app.multi_rx_screen.receiver_list
      if rx:
        rx[0].ChangeRxTxFrequency(freq)
      else:
        self.app.ChangeRxTxFrequency(freq, None)
  def GetSplitFreq(self):	# The Tx Frequency
    self.Reply('TX Frequency', self.app.txFreq + self.app.VFO, 0)
  def SetSplitFreq(self):	# The Tx Frequency
    freq = self.GetParamNumber()
    try:
      freq = float(freq)
      self.Reply(0)
    except:
      self.ErrParam()
    else:
      freq = int(freq + 0.5)
      # This always controls the Tx frequency
      self.app.ChangeRxTxFrequency(None, freq)
  def GetSplitVfo(self):
    self.Reply('Split', self.split_mode, 'TX VFO', self.split_vfo, 0)
  def SetSplitVfo(self):
    split = self.GetParamNumber()
    vfo = self.GetParamName()
    try:
      split = int(split)
      self.Reply(0)
    except:
      # traceback.print_exc()
      self.ErrParam()
    else:
      self.split_mode = split
      if split:
        self.split_vfo = vfo
      else:
        self.split_vfo = 'VFO'
      # If there are no multi receivers, this sets split Rx/Tx mode.
      if not self.app.multi_rx_screen.receiver_list:
        self.app.splitButton.SetValue(split, True)
  def GetInfo(self):
    self.Reply("Info", self.app.main_frame.title, 0)
  def GetMode(self):
    mode = self.app.mode
    if mode == 'CWU':
      mode = 'CW'
    elif mode == 'CWL':		# Is this what CWR means?
      mode = 'CWR'
    elif mode == 'DGT-U':
      mode = 'PKTUSB'
    elif mode == 'DGT-L':
      mode = 'PKTLSB'
    elif mode == 'DGT-FM':
      mode = 'PKTFM'
    elif mode[0:4] == 'DGT-IQ':
      mode = 'PKTUSB'
    self.Reply('Mode', mode, 'Passband', self.app.filter_bandwidth, 0)
  def SetMode(self):
    mode = self.GetParamName()
    bw = self.GetParamNumber()
    if mode == '?':	# send back supported parameters
      self.Reply2('USB LSB AM FM CW CWR PKTUSB PKTLSB PKTFM', 0)
      return
    try:
      bw = int(bw)
    except:
      self.ErrParam()
      return
    if mode in ('USB', 'LSB', 'AM', 'FM'):
      self.Reply(0)
    elif mode[0:4] == 'DGT-':
      self.Reply(0)
    elif mode == 'PKTUSB':
      mode = 'DGT-U'
      self.Reply(0)
    elif mode == 'PKTLSB':
      mode = 'DGT-L'
      self.Reply(0)
    elif mode == 'PKTFM':
      mode = 'DGT-FM'
      self.Reply(0)
    elif mode == 'CW':
      mode = 'CWU'
      self.Reply(0)
    elif mode == 'CWR':
      mode = 'CWL'
      self.Reply(0)
    else:
      self.ErrParam()
      return
    self.app.modeButns.SetLabel(mode, True)		# Set mode
    if bw <= 0:		# use default bandwidth
      return
    # Choose button closest to requested bandwidth
    buttons = self.app.filterButns.GetButtons()
    Lab = buttons[0].GetLabel()
    diff = abs(int(Lab) - bw)
    for i in range(1, len(buttons) - 1):
      label = buttons[i].GetLabel()
      df = abs(int(label) - bw)
      if df < diff:
        Lab = label
        diff = df
    self.app.filterButns.SetLabel(Lab, True)
  def GetVfo(self):
    self.Reply('VFO', self.vfo, 0)
  def SetVfo(self):
    name = self.GetParamName()
    if name == '?':	# send back supported parameters
      self.Reply2('Main', 0)
    else:
      self.vfo = name
      self.Reply(0)
  def GetPtt(self):
    if QS.is_key_down():
      self.Reply('PTT', 1, 0)
    else:
      self.Reply('PTT', 0, 0)
  def SetPtt(self):
    ptt = self.GetParamNumber()
    try:
      ptt = int(ptt)
      self.Reply(0)
    except:
      self.ErrParam()
    else:
      self.app.pttButton.SetValue(ptt, True)
  def GetFunc(self):
    name = self.GetParamName()
    if name == '?':	# send back supported functions
      self.Reply2('TUNER', 0)
    elif name == 'TUNER':
      if self.app.spotButton.GetValue():
        self.Reply2(1, 0)
      else:
        self.Reply2(0, 0)
    else:
      self.ErrParam()
  def SetFunc(self):
    name = self.GetParamName()
    value = self.GetParamNumber()
    if name == '?':	# send back supported functions
      self.Reply2('TUNER', 0)
    elif name == 'TUNER':
      try:
        value = int(value)
      except:
        self.ErrParam()
      else:
        self.Reply(0)
        if value:
          self.app.spotButton.SetValue(1, True)
        else:
          self.app.spotButton.SetValue(0, True)
    else:
      self.ErrParam()
  def GetLevel(self):
    name = self.GetParamName()
    if name == '?':	# send back supported parameters
      self.Reply2('AGC AF STRENGTH', 0)
    elif name == 'AGC':
      if self.app.BtnAGC.GetValue():
        self.Reply2(4, 0)
      else:
        self.Reply2(0, 0)
    elif name == 'AF':
      x = self.app.audio_volume	# audio_volume is 0 to 1.000
      self.Reply2("%.5f" % x, 0)
    elif name == 'STRENGTH':
      i = round(self.app.hamlib_strength)
      self.Reply2(i, 0)
    else:
      self.ErrParam()
  def SetLevel(self):
    name = self.GetParamName()
    value = self.GetParamNumber()
    if name == '?':	# send back supported parameters
      self.Reply2('AGC AF', 0)
    elif name == 'AGC':
      try:
        value = int(value)
      except:
        self.ErrParam()
      else:
        self.Reply(0)
        if value:
          self.app.BtnAGC.SetValue(1, True)
        else:
          self.app.BtnAGC.SetValue(0, True)
    elif name == 'AF':
      try:
        value = float(value)
      except:
        self.ErrParam()
      else:
        self.Reply(0)
        v = 1000.0 * math.log10(49.0 * value + 1) / math.log10(50)
        self.app.sliderVol.SetValue(int(v + 0.5))
        self.app.ChangeVolume()
    else:
      self.ErrParam()
  def GetParm(self):
    name = self.GetParamName()
    if name == '?':	# send back supported parameters
      self.Reply2('', 0)
    else:
      self.ErrParam()
  def SetParm(self):
    name = self.GetParamName()
    if name == '?':	# send back supported parameters
      self.Reply2('', 0)
    else:
      self.ErrParam()

class CatControl:
  def GetFreqVfo(self, vfoB=False):
    if vfoB:	# The Tx Frequency
      return self.app.txFreq + self.app.VFO
    else:	# The Rx Frequency
      rx = self.app.multi_rx_screen.receiver_list
      if rx:
        rx = rx[0]
        return rx.txFreq + rx.VFO
      else:
        return self.app.rxFreq + self.app.VFO
  def SetFreqVfo(self, freq, vfoB=False):
    if vfoB:	# The Tx Frequency
      self.app.ChangeRxTxFrequency(None, freq)
    else:	# The Rx Frequency
      # For multiple receivers this controls the first added receiver frequency; else it controls split Rx/Tx frequency.
      rx = self.app.multi_rx_screen.receiver_list
      if rx:
        rx[0].ChangeRxTxFrequency(freq)
      else:
        self.app.ChangeRxTxFrequency(freq, None)
  def GetFilterBW(self):
    return self.app.filter_bandwidth
  def SetFilterBW(self, bw):
    # Choose button closest to requested bandwidth
    buttons = self.app.filterButns.GetButtons()
    Lab = buttons[0].GetLabel()
    diff = abs(int(Lab) - bw)
    for i in range(1, len(buttons) - 1):
      label = buttons[i].GetLabel()
      df = abs(int(label) - bw)
      if df < diff:
        Lab = label
        diff = df
    self.app.filterButns.SetLabel(Lab, True)

class ElecraftK4Handler(CatControl):	# Test with telnet localhost 9200
  Mo2CoElecraft = {'LSB':1, 'USB':2, 'CWU':3, 'FM':4, 'AM':5, 'DGT-U':6, 'CWL':7, 'DGT-L':9, 'DGT-FM':4, 'DGT-IQ':6}
  Co2MoElecraft = {1:'LSB', 2:'USB', 3:'CWU', 4:'FM', 5:'AM', 6:'DGT-U', 7:'CWL', 9:'DGT-L'}
  def __init__(self, app, conf, sock, address):
    self.app = app
    self.conf = conf
    self.sock = sock
    sock.settimeout(0.0)
    self.address = address
    self.params = ''	# params is the string following the command
    self.received = ''
    self.cmds = []
    self.K31Elecraft = False	# K31 mode
    h = self.Handlers = {}	# Branch on the first two letters of the command
    h['AI']	= self.AiAutoInfo
    h['CW']	= self.CwCWPitch
    h['DT']	= self.DtDataMode
    h['FA']	= self.FaFbVfoFreq
    h['FB']	= self.FaFbVfoFreq
    h['FT']	= self.FtTxVfo
    h['FW']	= self.FwFilterBW
    h['ID']	= self.IdIdent
    h['IF']	= self.IfInfo
    h['IS']	= self.IsCenterPitch
    h['KS']	= self.KsKeyerSpeed
    h['K3']	= self.K3Elecraft
    h['LN']	= self.LnLinkVfo
    h['MD']	= self.MdMode
    h['OM']	= self.OmOptionModules
    h['RV']	= self.RvFirmware
    h['RX']	= self.RxReceive
    h['SB']	= self.SbSubReceiver
    h['SM']	= self.SmSmeter
    h['TX']	= self.TxTransmit
  def Send(self, text):
    """Send text back to the client."""
    if HAMLIB_DEBUG:
      for cmd in self.cmds[0:-1]:
        print ("CatTcp received: %-10s" % cmd)
      print ("CatTcp received: %-10s ; sent %s" % (self.cmds[-1], text))
      del self.cmds[:]
    text = text.encode('utf-8', errors='ignore')
    try:
      self.sock.sendall(text)
    except socket.error:
      self.sock.close()
      self.sock = None
  def Process(self):
    """This is the main processing loop, and is called frequently.  It reads and satisfies requests."""
    if not self.sock:
      return 0
    try:	# Read any data from the socket
      text = self.sock.recv(1024)
    except socket.timeout:	# This does not work
      pass
    except socket.error:	# Nothing to read
      pass
    else:					# We got some characters
      text = text.decode('utf-8', errors='ignore')
      self.received += text
      if HAMLIB_DEBUG and text:
        pass #print ("Raw CatTcp received:", text)
    if ';' in self.received:	# A complete command ending with semicolon is available
      cmd, self.received = self.received.split(';', 1)	# Split off the command, save any further characters
    else:
      return 1
    cmd = cmd.strip()		# Here is our command line
    if len(cmd) < 2:
      return 1
    if HAMLIB_DEBUG:
      self.cmds.append(cmd)
    base = cmd[0:2].upper()
    try:
      handler = self.Handlers[base]
    except KeyError:
      self.Send(cmd[0:2] + "?;")
      #print ("Unknown command", cmd)
      return 1
    if len(cmd) == 2:
      args = ''
    elif cmd[2] == '$': # base is the first two letters upper case and any following "$"
      base += '$'
      args = cmd[3:]
    else:
      args = cmd[2:]
    handler(base, args) # args is the remainder
    return 1
  def AiAutoInfo(self, base, args):
    if not args:
      self.Send("AI0;")
    elif args != '0':
      self.Send("AI0;")
  def CwCWPitch(self, base, args):
    pitch = self.conf.cwTone
    pitch = (pitch + 5) // 10
    if pitch < 25:
      pitch = 25
    elif pitch > 95:
      pitch = 95
    self.Send("CW%d;" % pitch)
  def DtDataMode(self, base, args):
    self.Send("%s0;" % base)
  def IdIdent(self, base, args):
    if args:
      self.Send("ID?;")
    else:
      self.Send("ID017;")
      #self.Send("IDQuisk;")
  def IfInfo(self, base, args):
    rxfreq = self.GetFreqVfo()
    info = "%011d     " % rxfreq	# Rx frequency, five blanks
    ritFreq = self.app.ritScale.GetValue()
    if ritFreq < 0:	# +/- RIT freq
      info += "-%04d" % -ritFreq
    else:
      info += "+%04d" % ritFreq
    if self.app.ritButton.GetValue():	# RIT status, XIT status, blank "00"
      info += "10 00"
    else:
      info += "00 00"
    if QS.is_key_down():	# MOX, key down
      info += '1'
    else:
      info += '0'
    mode = self.Mo2CoElecraft.get(self.app.mode, 2)
    info += "%d" % mode		# Mode 1-9
    info += '00'		# Rx on VFOA, no scan
    if self.app.split_rxtx:	# VFO split status
      info += '1'
    else:
      info += '0'
    info += '001 ;'
    self.Send(info)
  def FaFbVfoFreq(self, base, args):
    if base[1] in ('B', 'b'):
      vfoB = True
    else:
      vfoB = False
    if not args:	# Get command
      freq = "%06d" % self.GetFreqVfo(vfoB)
      self.Send(base + freq + ';')
    else:		# Put command
      try:
        freq = int(args)
      except:
        self.Send(base + "?;")
      else:
        l = len(args)
        if l <= 2:
          freq *= 1000000
        elif l <= 5:
          freq *= 1000
        self.SetFreqVfo(freq, vfoB)
  def FtTxVfo(self, base, args):
    if not args:
      if self.app.split_rxtx:
        self.Send("FT1;")
      else:
        self.Send("FT0;")
    else:
      # Set split Rx/Tx mode.
      is_split = self.app.splitButton.GetValue()
      split = int(args)
      if split and not is_split:
        self.app.splitButton.SetValue(split, True)
      elif is_split and not split:
        self.app.splitButton.SetValue(split, True)
  def FwFilterBW(self, base, args):
    if not args:
      code = self.GetFilterBW()
      self.Send("%s%04d;" % (base, (code + 5) // 10))
    else:
      self.SetFilterBW(int(args) * 10)
  def IsCenterPitch(self, base, args):
    if not args:
      code = self.GetFilterBW() // 2
      if self.K31Elecraft:
        self.Send("%s %04d;" % (base, code))
      else:
        code = (code + 5) // 10
        self.Send("%s%04d;" % (base, code))
    else:
      if self.K31Elecraft:
        self.SetFilterBW(int(args) * 2)
      else:
        self.SetFilterBW(int(args) * 2 * 10)
  def K3Elecraft(self, base, args):
    if args == '1':
      self.K31Elecraft = True
    else:
      self.K31Elecraft = False
  def KsKeyerSpeed(self, base, args):
    if len(base) == 2:
      self.Send("KS013;")
  def LnLinkVfo(self, base, args):
    if args != '0':
      self.Send("LN0;")
  def MdMode(self, base, args):
    if args:		# set the mode
      code = int(args)
      mode = self.Co2MoElecraft[code]
      self.app.modeButns.SetLabel(mode, True)
    else:		# return the mode
      code = self.Mo2CoElecraft.get(self.app.mode, 2)
      self.Send("%s%d;" % (base, code))
  def OmOptionModules(self, base, args):
    self.Send("OM ------------;")
  def RvFirmware(self, base, args):
    self.Send("%s99.99;" % base)
  def RxReceive(self, base, args):
    self.app.pttButton.SetValue(0, True)
  def SbSubReceiver(self, base, args):
    self.Send("SB0;")
  def SmSmeter(self, base, args):
    if base[0:3].upper() == "SMH":
      self.Send(base + "?;")
    elif args:
      self.Send(base + "?;")
    elif self.K31Elecraft:
      self.Send("SM0000;")
    else:
      self.Send("SM00;")
  def TxTransmit(self, base, args):
    self.app.pttButton.SetValue(1, True)

# ------------------------------------------- добавлено ------------------- COM-порты для Odyssey ----- 63 RA3PKJ
# программная CW манипуляция двухвёсельным ключом через программу-посредника
class OdysseyCWThread1(threading.Thread):
  def __init__(self, cw_com_method):
    self.do_init = 1
    threading.Thread.__init__(self)
    self.port = ''
    self.ser = None
    self.cw_com_method = cw_com_method
    if conf.odyssey_cw_port1:
      self.port = conf.odyssey_cw_port1
    else:
      self.port = None
  def run(self):
    if self.do_init:
      self.do_init = 0
      if self.port:
        try:
          if self.cw_com_method == 1:
            self.ser = serial.Serial(port=self.port, timeout=0.01, rtscts=1, dsrdtr=1)
        except:
          self.ser = None
    while self.ser:
      try:
        Hardware.odyssey_cw_tx = self.ser.cts
        Hardware.NewUdpStatus()
      except: break
      time.sleep(0.01)
  def stop(self):
    if self.ser:
      self.ser.close()
      self.ser = None

# ------------------------------------------- добавлено ------------------- COM-порты для Odyssey ----- 63 RA3PKJ
# программная CW манипуляция двухвёсельным ключом без программ-посредников
class OdysseyCWThread2(threading.Thread):
  def __init__(self,  cw_com_method):
    self.do_init = 1
    threading.Thread.__init__(self)
    self.port = ''
    self.ser = None
    self.cw_com_method = cw_com_method
    if conf.odyssey_cw_port2:
      self.port = conf.odyssey_cw_port2
    else:
      self.port = None
  def run(self):
    if self.do_init:
      self.do_init = 0
      if self.port:
        try:
          if self.cw_com_method == 2:
            self.ser = serial.Serial(port=self.port, timeout=0.01, rtscts=1, dsrdtr=1)
            self.ser.dtr = 1
        except:
          self.ser = None
    while self.ser:
      try:
        if self.ser.cts:
          if conf.options_cw == 0:
            Hardware.odyssey_cw_tx = 2 # dash
          elif conf.options_cw == 2 or conf.options_cw == 3:
            Hardware.odyssey_cw_tx = 4 # dot
        elif self.ser.dsr:
          if conf.options_cw == 0:
            Hardware.odyssey_cw_tx = 4 # dot
          elif conf.options_cw == 2 or conf.options_cw == 3:
            Hardware.odyssey_cw_tx = 2 # dash
        else:
          Hardware.odyssey_cw_tx = 0
        Hardware.NewUdpStatus()
      except: break
      time.sleep(0.005)
  def stop(self):
    if self.ser:
      self.ser.close()
      self.ser = None

class SoundThread(threading.Thread):
  """Create a second (non-GUI) thread to read, process and play sound."""
  def __init__(self, samples_from_python):
    self.samples_from_python = samples_from_python
    self.do_init = 1
    threading.Thread.__init__(self, name="QuiskSound")
    self.doQuit = threading.Event()
    self.doQuit.clear()
    #self.time0 = time.time()
    if hasattr(Hardware, "PollCwKey"):
      self.poll_cw = True
    else:
      self.poll_cw = False
  def run(self):
    """Read, process, play sound; then notify the GUI thread to check for FFT data."""
    if self.do_init:	# Open sound using this thread
      self.do_init = 0
      QS.start_sound()
      wx.CallAfter(application.PostStartup)
    while not self.doQuit.is_set():
      #tm = time.time()
      #print ("Quisk thread %12.3f" % ((tm - self.time0) * 1E3))
      #self.time0 = tm
      if self.samples_from_python:
        samples = Hardware.GetRxSamples()
        if samples:
          QS.set_params(rx_samples=samples)
      if self.poll_cw:
        Hardware.PollCwKey()
      if conf.midi_cwkey_device:
        byts = QS.control_midi(get_event=1)
        if byts:
          wx.CallAfter(application.OnReadMIDI, byts)
      application.wdsp.control()
      QS.read_sound()
      wx.CallAfter(application.OnReadSound)
      #if sys.platform == 'win32':
      #  time.sleep(0.000)
    QS.control_midi(close_port=1)
    QS.close_sound()
  def stop(self):
    """Set a flag to indicate that the sound thread should end."""
    self.doQuit.set()

# ------------------------------ добавлен новый класс для нового окна выбора радио (и их настроек) --------- кнопка Hardware ------- 15 RA3PKJ
class RadiosScreen(wx.Panel):
  """Display a notebook with radios data"""
  def __init__(self, parent, width):
    self.y_scale = 0
    self.y_zero = 0
    self.finish_pages = True
    self.width = width
    wx.Panel.__init__(self, parent)
    self.notebook_2 = notebook_2 = wx.Notebook(self)
    va = notebook_2.GetClassDefaultAttributes()
    notebook_2.tfg_color = va.colFg	# use for text foreground
    notebook_2.bg_color = va.colBg
    font = wx.Font(conf.config_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    notebook_2.SetFont(font)
    sizer = wx.BoxSizer()
    sizer.Add(notebook_2, 1, wx.EXPAND)
    self.SetSizer(sizer)
    self.radios = configure.Radios(notebook_2)
    self.SetBackgroundColour(self.radios.bg_color)
    self.SetForegroundColour(self.radios.tfg_color)
    notebook_2.bg_color = self.radios.bg_color
    notebook_2.tfg_color = self.radios.tfg_color
    notebook_2.AddPage(self.radios, "Radios")
  def FinishPages(self):
    if self.finish_pages:
      self.finish_pages = False
      application.local_conf.AddPagesRadios(self.notebook_2, self.width) # --- в окно добавить меню выбора радио и настроек радио
  def OnIdle(self, event):
    pass
  def SetTxFreq(self, tx_freq, rx_freq):
    pass
  def ChangeYscale(self, y_scale):
    pass
  def ChangeYzero(self, y_zero):
    pass

class ConfigScreen(wx.Panel):
  """Display a notebook with status and configuration data"""
  def __init__(self, parent, width, fft_size):
    self.y_scale = 0
    self.y_zero = 0
    self.zoom_control = 0
    self.finish_pages = True
    self.width = width
    wx.Panel.__init__(self, parent)
    self.notebook = notebook = wx.Notebook(self)
    font = wx.Font(conf.config_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    notebook.SetFont(font)
    sizer = wx.BoxSizer()
    sizer.Add(notebook, 1, wx.EXPAND)
    self.SetSizer(sizer)
    # create the page windows
    self.status = ConfigStatus(notebook, width, fft_size)
    self.SetBackgroundColour(self.status.bg_color)
    self.SetForegroundColour(self.status.tfg_color)
    notebook.bg_color = self.status.bg_color
    notebook.tfg_color = self.status.tfg_color
    notebook.AddPage(self.status, "Status")
    self.config = configure.ConfigConfig(notebook, width)
    notebook.AddPage(self.config, "Config")
    self.favorites = ConfigFavorites(notebook, width)
    notebook.AddPage(self.favorites, "Favorites")
    tx_audio = configure.ConfigTxAudio(notebook)
    notebook.AddPage(tx_audio, "Tx Audio")
    tx_audio.status = self.status
  def FinishPages(self): # --- добавить пункты меню на кнопке Config
    if self.finish_pages:
      self.finish_pages = False
      #application.local_conf.AddPages(self.notebook, self.width) # --------- удалено------------- кнопка Hardware ------ 15 RA3PKJ
      application.local_conf.AddPagesConfig(self.notebook, self.width) # ----- взамен------------- кнопка Hardware ------ 15 RA3PKJ
  def ChangeYscale(self, y_scale):
    pass
  def ChangeYzero(self, y_zero):
    pass
  def OnIdle(self, event):
    pass
  def SetTxFreq(self, tx_freq, rx_freq):
    pass
  def OnGraphData(self, data=None):
    self.status.OnGraphData(data)
  def InitBitmap(self):		# Initial construction of bitmap
    self.status.InitBitmap()

class ConfigStatus(wx.ScrolledCanvas):
  """Display the status screen."""
  def __init__(self, parent, width, fft_size):
    wx.ScrolledCanvas.__init__(self, parent)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.bg_color = self.GetBackgroundColour()
    try:
      va = wx.StaticText.GetClassDefaultAttributes()
      self.tfg_color = wx.Colour(va.colFg)	# use for text foreground
    except:
      self.tfg_color = self.GetForegroundColour()
    self.width = width
    self.fft_size = fft_size
    self.scroll_height = None
    self.interrupts = 0
    self.read_error = -1
    self.write_error = -1
    self.underrun_error = -1
    self.hl2_txbuf_errors = 0
    self.fft_error = -1
    self.latencyCapt = -1
    self.latencyPlay = -1
    self.y_scale = 0
    self.y_zero = 0
    self.zoom_control = 0
    self.rate_min = -1
    self.rate_max = -1
    self.chan_min = -1
    self.chan_max = -1
    self.mic_max_display = -90.0
    self.err_msg = "No response"
    self.msg1 = ""
    self.font = wx.Font(conf.status_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    if wxVersion in ('2', '3'):
      self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
    else:
      self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
    self.SetFont(self.font)
    charx = self.charx = self.GetCharWidth()
    chary = self.chary = self.GetCharHeight()
    self.dy = chary		# line spacing
    self.rjustify1 = (0, 1, 0)
    self.tabstops1 = [0] * 3
    self.tabstops1[0] = x = charx
    self.tabstops1[1] = x = x + self.GetTextExtent("FFT number of errors 1234567890")[0]
    self.tabstops1[2] = x = x + self.GetTextExtent("XXXX")[0]
    self.rjustify2 = (0, 0, 1, 1, 1, 1)
    self.tabstops2 = []
  def MakeTabstops(self):
    luse = lname = 0
    for use, name, rate, latency, errors, level, dev_errmsg in QS.sound_errors():
      name = self.TrimName(name)
      w, h = self.GetTextExtent(use)
      luse = max(luse, w)
      w, h = self.GetTextExtent(name)
      lname = max(lname, w)
    if luse == 0:
      return
    charx = self.charx
    self.tabstops2 = [0] * 6
    self.tabstops2[0] = x = charx
    self.tabstops2[1] = x = x + luse + charx * 6
    self.tabstops2[2] = x = x + lname + self.GetTextExtent("Sample rateXXXXXX")[0]
    self.tabstops2[3] = x = x + charx * 12
    self.tabstops2[4] = x = x + charx * 12
    self.tabstops2[5] = x = x + charx * 12
  def TrimName(self, name):
    if len(name) > 50:
      name = name[0:30] + '|||' + name[-17:]
    return name
  def OnPaint(self, event):
    # Make and blit variable data
    self.MakeBitmap()
    dc = wx.AutoBufferedPaintDC(self)
    x, y = self.GetViewStart()
    dc.Blit(0, 0, self.mem_width, self.mem_height, self.mem_dc, x, y)
  def MakeRow2(self, *args):
    for col in range(len(args)):
      t = args[col]
      if t is None:
        continue
      if not isinstance(t, Q3StringTypes):
        t = str(t)
      x = self.tabstops[col]
      if self.rjustify[col]:
        w, h = self.mem_dc.GetTextExtent(t)
        x -= w
      if ("Error" in t or "Stream error" in t) and t != "Errors":
        self.mem_dc.SetTextForeground('Red')
        self.mem_dc.DrawText(t, x, self.mem_y)
        self.mem_dc.SetTextForeground(self.tfg_color)
      else:
        self.mem_dc.DrawText(t, x, self.mem_y)
    self.mem_y += self.dy
  def InitBitmap(self):		# Initial construction of bitmap
    self.mem_height = application.screen_height
    self.mem_width = application.screen_width
    self.bitmap = EmptyBitmap(self.mem_width, self.mem_height)
    self.mem_dc = wx.MemoryDC()
    self.mem_rect = wx.Rect(0, 0, self.mem_width, self.mem_height)
    self.mem_dc.SelectObject(self.bitmap)
    br = wx.Brush(self.bg_color)
    self.mem_dc.SetBackground(br)
    self.mem_dc.SetFont(self.font)
    self.mem_dc.SetTextForeground(self.tfg_color)
    self.mem_dc.Clear()
  def MakeBitmap(self):
    self.mem_dc.Clear()
    self.mem_y = self.charx
    self.tabstops = self.tabstops1
    self.rjustify = self.rjustify1
    if conf.config_file_exists:
      cfile = "Configuration file:  %s" % conf.config_file_path
    else:
      cfile = "Configuration file:  None"
    qfile = "Quisk user files are in %s" % application.QuiskFilesDir
    level = "%3.0f" % self.mic_max_display
    if self.err_msg:
      err_msg = self.err_msg
    else:
      err_msg = None
    self.MakeRow2("Sample interrupts", self.interrupts, cfile)
    self.MakeRow2("Microphone or DGT level dB", level, qfile)
    self.MakeRow2("FFT number of points", self.fft_size, err_msg)
    if application.dxCluster:
      msg = application.dxCluster.dxStatus()
      self.MakeRow2("FFT number of errors", self.fft_error, msg)
    else:
      self.MakeRow2("FFT number of errors", self.fft_error)
    if conf.use_rx_udp == 10:		# Hermes UDP protocol
      self.MakeRow2("Hermes-Lite2 Tx buffer errors", self.hl2_txbuf_errors)
    self.mem_y += self.dy
    if not self.tabstops2:
      return
    self.tabstops = self.tabstops2
    self.rjustify = self.rjustify2
    self.font.SetUnderlined(True)
    self.mem_dc.SetFont(self.font)
    self.MakeRow2("Device", "Name", "Sample rate", "Latency", "Errors", "Level dB")
    self.font.SetUnderlined(False)
    self.mem_dc.SetFont(self.font)
    self.mem_y += self.dy * 3 // 10
    if conf.use_sdriq:
      self.MakeRow2("Capture radio samples", "SDR-IQ", application.sample_rate, self.latencyCapt, self.read_error)
    elif conf.use_rx_udp:
      self.MakeRow2("Capture radio samples", "UDP", application.sample_rate, self.latencyCapt, self.read_error)
    elif conf.use_soapy:
      self.MakeRow2("Capture radio samples", "SoapySDR", application.sample_rate, self.latencyCapt, self.read_error)
    for use, name, rate, latency, errors, level, dev_errmsg in QS.sound_errors():
      level = math.sqrt(level) / 2**31
      if level < 1.1E-5:
        level = "  -  "
      else:
        level = 20 * math.log10(level)
        level = "%.2f" % level
      self.MakeRow2(use, self.TrimName(name), rate, latency, errors, level)
      if dev_errmsg:
        x = self.tabstops[0] + self.charx * 4
        self.mem_dc.SetTextForeground('Red')
        self.mem_dc.DrawText(dev_errmsg, x, self.mem_y)
        self.mem_dc.SetTextForeground(self.tfg_color)
        self.mem_y += self.dy
    if self.scroll_height is None:
      self.scroll_height = self.mem_y + self.dy
      self.SetScrollbars(1, 1, 100, self.scroll_height)
  def OnGraphData(self, data=None):
    if not self.tabstops2:      # Must wait for sound to start
      self.MakeTabstops()
    (self.rate_min, self.rate_max, sample_rate, self.chan_min, self.chan_max,
         self.msg1, self.unused, self.err_msg,
         self.read_error, self.write_error, self.underrun_error,
         self.latencyCapt, self.latencyPlay, self.interrupts, self.fft_error, self.mic_max_display,
         self.data_poll_usec
     ) = QS.get_state()
    self.mic_max_display = 20.0 * math.log10((self.mic_max_display + 1) / 32767.0)
    if conf.use_rx_udp == 10:		# Hermes UDP protocol
      self.hl2_txbuf_errors = QS.get_params("hl2_txbuf_errors")
    self.RefreshRect(self.mem_rect)

class ConfigFavorites(wx.grid.Grid):
  def __init__(self, parent, width):
    wx.grid.Grid.__init__(self, parent)
    self.changed = False
    self.RepeaterDict = {}
    font = wx.Font(conf.favorites_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_BOLD, False, conf.quisk_typeface)
    self.SetFont(font)
    self.SetBackgroundColour(parent.bg_color)
    self.SetLabelFont(font)
    font = wx.Font(conf.favorites_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    self.SetDefaultCellFont(font)
    self.SetDefaultRowSize(self.GetCharHeight()+3)
    self.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK, self.OnRightClickLabel)
    self.Bind(wx.grid.EVT_GRID_LABEL_LEFT_CLICK, self.OnLeftClickLabel)
    if wxVersion in ('2', '3'):
      self.Bind(wx.grid.EVT_GRID_CELL_CHANGE, self.OnChange)    # wxPython 3
    else:
      self.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.OnChange)   # wxPython 4
    self.Bind(wx.grid.EVT_GRID_LABEL_LEFT_DCLICK, self.OnLeftDClick)
    self.CreateGrid(0, 6)
    self.EnableDragRowSize(False)
    w = self.GetTextExtent(' 999 ')[0]
    self.SetRowLabelSize(w)
    self.SetColLabelValue(0,  'Name')
    self.SetColLabelValue(1,  'Freq MHz')
    self.SetColLabelValue(2,  'Mode')	# This column has a choice editor
    self.SetColLabelValue(3,  'Description')
    self.SetColLabelValue(4,  'Offset kHz')
    self.SetColLabelValue(5,  'Tone Hz')
    w = self.GetTextExtent("xFrequencyx")[0]
    self.SetColSize(0, w * 3 // 2)
    self.SetColSize(1, w)
    self.SetColSize(4, w)
    self.SetColSize(5, w)
    self.SetColSize(2, w)
    ww = width - w * 7 - self.GetRowLabelSize() - 20
    if ww < w:
      ww = w
    self.SetColSize(3, ww)
    if conf.favorites_file_path:
      self.init_path = conf.favorites_file_path
    else:
      self.init_path = os.path.join(os.path.dirname(ConfigPath), 'quisk_favorites.txt')
    conf.favorites_file_in_use = self.init_path
    self.ReadIn()
    if self.GetNumberRows() < 1:
      self.AppendRows()
    # Make a popup menu
    self.popupmenu = wx.Menu()
    item = self.popupmenu.Append(-1, 'Tune to')
    self.Bind(wx.EVT_MENU, self.OnPopupTuneto, item)
    self.popupmenu.AppendSeparator()
    item = self.popupmenu.Append(-1, 'Append')
    self.Bind(wx.EVT_MENU, self.OnPopupAppend, item)
    item = self.popupmenu.Append(-1, 'Insert')
    self.Bind(wx.EVT_MENU, self.OnPopupInsert, item)
    item = self.popupmenu.Append(-1, 'Delete')
    self.Bind(wx.EVT_MENU, self.OnPopupDelete, item)
    self.popupmenu.AppendSeparator()
    item = self.popupmenu.Append(-1, 'Move Up')
    self.Bind(wx.EVT_MENU, self.OnPopupMoveUp, item)
    item = self.popupmenu.Append(-1, 'Move Down')
    self.Bind(wx.EVT_MENU, self.OnPopupMoveDown, item)
    # Make a timer
    self.timer = wx.Timer(self)
    self.Bind(wx.EVT_TIMER, self.OnTimer)
  def SetModeEditor(self, mode_names):
    self.mode_names = mode_names
    for row in range(self.GetNumberRows()):
      self.SetCellEditor(row, 2, wx.grid.GridCellChoiceEditor(mode_names, True))
  def FormatFloat(self, freq):
    freq = "%.6f" % freq
    for i in range(3):
      if freq[-1] == '0':
        freq = freq[:-1]
      else:
        break
    return freq
  def ReadIn(self):
    try:
      fp = open(self.init_path, 'r')
      lines = fp.readlines()
      fp.close()
    except:
      lines = ("my net|7210000|LSB|My net 2030 UTC every Thursday",
               "10m FM 1|29.620|FM|Fm local 10 meter repeater")
    for row in range(len(lines)):
      self.AppendRows()
      fields = lines[row].split('|')
      for col in range(len(fields)):
        if col == 1:    # Correct old entries made in Hertz
          freq = fields[1]
          try:
            freq = float(freq)
          except:
            pass
          else:
            if freq > 30000.0:    # Must be in Hertz
              freq *= 1E-6
              fields[1] = self.FormatFloat(freq)
        if col <= 5:
          self.SetCellValue(row, col, fields[col].strip())
    self.MakeRepeaterDict()
  def WriteOut(self):
    ncols = self.GetNumberCols()
    if ncols != 6:
      print ("Bad logic in favorites WriteOut()")
      return
    self.changed = False
    try:
      fp = open(self.init_path, 'w')
    except:
      return
    for row in range(self.GetNumberRows()):
      out = []
      for col in range(0, ncols):
        cell = self.GetCellValue(row, col)
        cell = cell.replace('|', ';')
        out.append(cell)
      t = "%20s | %10s | %10s | %30s | %10s | %10s\n" % tuple(out)
      fp.write(t)
    fp.close()
  def AddNewFavorite(self):
    self.InsertRows(0)
    self.SetCellValue(0, 0, 'New station');
    freq = (application.rxFreq + application.VFO) * 1E-6    # convert to megahertz
    freq = self.FormatFloat(freq)
    self.SetCellValue(0, 1, freq)
    self.SetCellValue(0, 2, application.mode);
    self.SetCellEditor(0, 2, wx.grid.GridCellChoiceEditor(self.mode_names, True))
    self.OnChange()
  def OnRightClickLabel(self, event):
    event.Skip()
    self.menurow = event.GetRow()
    if self.menurow >= 0:
      pos = event.GetPosition()
      self.PopupMenu(self.popupmenu, pos)
  def OnLeftClickLabel(self, event):
    self.OnRightClickLabel(event)
  def OnLeftDClick(self, event):		# Thanks to Christof, DJ4CM
    self.menurow = event.GetRow()
    if self.menurow >= 0:
      self.OnPopupTuneto(event)
  def OnPopupAppend(self, event):
    self.InsertRows(self.menurow + 1)
    self.SetCellEditor(self.menurow + 1, 2, wx.grid.GridCellChoiceEditor(self.mode_names, True))
    self.OnChange()
  def OnPopupInsert(self, event):
    self.InsertRows(self.menurow)
    self.SetCellEditor(self.menurow, 2, wx.grid.GridCellChoiceEditor(self.mode_names, True))
    self.OnChange()
  def OnPopupDelete(self, event):
    self.DeleteRows(self.menurow)
    if self.GetNumberRows() < 1:
      self.AppendRows()
      self.SetCellEditor(0, 2, wx.grid.GridCellChoiceEditor(self.mode_names, True))
    self.OnChange()
  def OnPopupMoveUp(self, event):
    row = self.menurow
    if row < 1:
      return
    for i in range(self.GetNumberCols()):
      c = self.GetCellValue(row - 1, i)
      self.SetCellValue(row - 1, i, self.GetCellValue(row, i))
      self.SetCellValue(row, i, c)
  def OnPopupMoveDown(self, event):
    row = self.menurow
    if row == self.GetNumberRows() - 1:
      return
    for i in range(self.GetNumberCols()):
      c = self.GetCellValue(row + 1, i)
      self.SetCellValue(row + 1, i, self.GetCellValue(row, i))
      self.SetCellValue(row, i, c)
  def OnPopupTuneto(self, event):
    freq = self.GetCellValue(self.menurow, 1)
    if not freq:
      return
    try:
      freq = str2freq (freq)
    except ValueError:
      print('Bad frequency')
      return
    if self.changed:
      if self.timer.IsRunning():
        self.timer.Stop()
      self.WriteOut()
    application.ChangeRxTxFrequency(None, freq)
    mode = self.GetCellValue(self.menurow, 2)
    mode = mode.upper()
    application.modeButns.SetLabel(mode, True)
    application.screenBtnGroup.SetLabel(conf.default_screen, do_cmd=True)
  def MakeRepeaterDict(self):
    self.RepeaterDict = {}
    for row in range(self.GetNumberRows()):
      offset = self.GetCellValue(row, 4)
      offset = offset.strip()
      if not offset:
        continue
      freq = self.GetCellValue(row, 1)
      tone = self.GetCellValue(row, 5)
      tone = tone.strip()
      if not tone:
        tone = '0'
      try:
        offset = float(offset)
        freq = float(freq)
        tone = float(tone)
      except:
        traceback.print_exc()
      else:
        freq = int(freq * 1E6 + 0.5)	# frequency in Hertz
        freq = (freq + 500) // 1000		# frequency in units of 1 kHz
        self.RepeaterDict[freq * 1000] = (offset, tone)
  def OnChange(self, event=None):
    self.MakeRepeaterDict()
    self.changed = True
    if self.timer.IsRunning():
      self.timer.Stop()
    self.timer.Start(5000, oneShot=True)
  def OnTimer(self, event):
    if self.changed:
      self.WriteOut()

# ------------------------------------------------------ добавлено ------------------------------- создание строки состояния ----------- 28 RA3PKJ
class TopScreen(wx.Window):
  def __init__(self, parent, width, height):
    wx.Window.__init__(self, parent,
       pos = (0, 0),
       size = (width, height),
       style = wx.NO_BORDER)
    self.width = width
    self.SetBackgroundColour('#103640') # --- цвет фона
    self.Bind(wx.EVT_PAINT, self.OnPaint)
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    Xpos = 0 # X-position
    Ypos = 2  # Y-position
    # ------------------------------------------------------------------------------------------------------------- версия
    dc.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface))
    dc.SetTextForeground('white')
    Xpos = Xpos + 5
    dc.DrawText(version_quisk, Xpos, Ypos - 1)
    # --------------------------------------------------------------------------------------------------------- Fast sound
    dc.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface))
    Xpos = Xpos + 250
    if conf.use_fast_sound:
      dc.SetTextForeground('#00FF00')
      dc.DrawText('Fast sound ON', Xpos, Ypos)
    else:
      dc.SetTextForeground('#777777')
      dc.DrawText('Fast sound OFF', Xpos, Ypos)
    # ----------------------------------------------------------------------------------------------- разделительная линия
    dc.SetPen(wx.Pen('#888888', 1))
    dc.DrawLine(0, Ypos + 17, self.width, Ypos + 17)

class GraphDisplay(wx.Window):
  """Display the FFT graph within the graph screen."""
  def __init__(self, parent, x, y, graph_width, height, chary):
    wx.Window.__init__(self, parent,
       pos = (x, y),
       size = (graph_width, height),
       style = wx.NO_BORDER)
    self.parent = parent
    self.chary = chary
    self.graph_width = graph_width
    self.display_text = ""
    self.line = [(0, 0), (1,1)]		# initial fake graph data
    #self.SetBackgroundColour(conf.color_graph)
    self.SetBackgroundColour('#06354F') # -------------- взамен ------------ цвет фона на панораме ------------ оформление панорамы ------- 4 RA3PKJ
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_LEFT_DOWN, parent.OnLeftDown)
    self.Bind(wx.EVT_RIGHT_DOWN, parent.OnRightDown)
    self.Bind(wx.EVT_RIGHT_UP, parent.OnRightUp) # ---- добавлено --------------------------------------- Перестройка типа PowerSDR ------ 47 RA3PKJ
    self.Bind(wx.EVT_LEFT_UP, parent.OnLeftUp)
    self.Bind(wx.EVT_MOTION, parent.OnMotion)
    self.Bind(wx.EVT_MOUSEWHEEL, parent.OnWheel)
    self.tune_tx = graph_width // 2	# Current X position of the Tx tuning line
    self.tune_rx = 0				# Current X position of Rx tuning line or zero
    self.scale = 20				# pixels per 10 dB
    self.peak_hold = 9999		# time constant for holding peak value
    self.height = 10
    self.y_min = 1000
    self.y_max = 0
    self.max_height = application.screen_height
    self.backgroundPen = wx.Pen(self.GetBackgroundColour(), 1)
    self.tuningPenTx = wx.Pen(conf.color_txline, 1)
    self.tuningPenRx = wx.Pen(conf.color_rxline, 1)
    self.backgroundBrush = wx.Brush(self.GetBackgroundColour())
    #self.filterBrush = wx.Brush(conf.color_bandwidth, wx.SOLID)
    self.filterBrush = wx.Brush('#009999', wx.SOLID) # ---------- взамен ---------- цвет шторки ----------- оформление панорамы ----------- 4 RA3PKJ
    #self.horizPen = wx.Pen(conf.color_gl, 1, wx.SOLID)
    self.horizPen = wx.Pen('#003C50', 1, wx.SOLID) # ------ взамен ----- цвет горизонтальных линий на панораме ---- оформление панорамы --- 4 RA3PKJ
    self.font = wx.Font(conf.graph_msg_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    self.SetFont(self.font)
    if wxVersion in ('2', '3'):
      self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
    else:
      self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

    #----------------------------------------------------------- добавлено ----------------------- колесо мыши ---------------------------- 1 RA3PKJ
    #if sys.platform == 'win32':
    if sys.platform.lower().startswith('win'):
      self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
  def OnEnter(self, event):
    if not application.w_phase:
      self.SetFocus()    # Set focus so we get mouse wheel events

  def OnPaint(self, event):
    #print ('GraphDisplay', self.GetUpdateRegion().GetBox())
    dc = wx.AutoBufferedPaintDC(self)
    dc.Clear()
    # Draw the tuning line and filter display to the screen.
    # If self.tune_rx is zero, draw the Rx filter at the Tx tuning line. There is no separate Rx display.
    # Otherwise draw both an Rx and Tx tuning display.

# --------------------------------------------------------------------------- добавлено --------- картинка на панораме --------------------- 5 RA3PKJ
    picture_bmp = application.picture_bmp
    # ------------- коррекция длины картинки -------------------------------- добавлено --------- на всю длину монитора ------------------- 33 RA3PKJ
    global MyDisplayWidth
    if conf.window_width > 0:
      if conf.window_width > MyDisplayWidth:
        aa = (conf.window_width * 1000) // MyDisplayWidth
        MyDisplayWidth = (MyDisplayWidth * aa) // 1000
      else:
        aa = (MyDisplayWidth * 1000) // conf.window_width
        MyDisplayWidth = (MyDisplayWidth * 1000) // aa
    bmp = wx.Image(picture_bmp, wx.BITMAP_TYPE_JPEG).Scale(MyDisplayWidth, (MyDisplayHeight//100) * 42)

    bmp_ = wx.Bitmap(bmp)
    dc.DrawBitmap(bmp_, 0, 0)
# -------------------------------------------------------------------------------------------------------------------------------------------------------

    self.DrawFilter(dc)
    dc.SetPen(self.horizPen)
    for y in self.parent.y_ticks:
      dc.DrawLine(0, y, self.graph_width, y)	# y line
    dc.SetPen(wx.Pen('white', 1)) # ---- перенесено и изменено ------------------------------ цвет шумовой дорожки ----- оформление панорамы ----- 4 RA3PKJ
    dc.DrawLines(self.line)

    # ------------------------------------------------------------------------- добавлено ------------------ надписи RX,TX,Lock на шторках ------- 55 RA3PKJ
    # СПРАВКА
    # x - координата левого края шторки относительно нулевой частоты (подавленной несущей в SSB)
    # w - ширина шторки
    # rit - смещение шторки при расстройке
    dc.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface))
    if application.new_split == True or application.split_rxtx == True: # если включен Split или RX2
      application.lockVFOButton_RX.Enable(True)
      application.lockVFOButton_TX.SetLabel('LockTX') # переименовать после перехода в режим Split (также RX2)
      application.lockVFOButton_TX.Refresh() # перерисовать кнопку
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=True) # получение параметров шторки и смещения шторки приёмника
      dc.SetTextForeground('white')
      if self.tune_rx == 0: # при совмещении двух шторок в Split(RX2) пропадает self.tune_rx
        dc.DrawText('RX', self.tune_tx + x + rit, 60)
      else:
        dc.DrawText('RX', self.tune_rx + x + rit, 60)
      if application.lockVFOButton_RX.GetValue(): # если включен LockRX
        dc.SetTextForeground('yellow')
        if self.tune_rx == 0: # при совмещении двух шторок в Split(RX2) пропадает self.tune_rx
          dc.DrawText('Lock', self.tune_tx + x + rit, 70)
        else:
          dc.DrawText('Lock', self.tune_rx + x + rit, 70)
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=False) # получение параметров шторки и смещения шторки передатчика
      dc.SetTextForeground('white')
      dc.DrawText('TX', self.tune_tx + x, 80) # у передатчика нет RIT
      if application.lockVFOButton_TX.GetValue(): # если включен LockTX
        dc.SetTextForeground('yellow')
        dc.DrawText('Lock', self.tune_tx + x, 90)
    else: # режим одной шторки
      application.lockVFOButton_RX.Enable(False) # отключить кнопку LockRX
      application.lockVFOButton_TX.SetLabel('LockF') # переименовать после перехода в режим одной шторки
      application.lockVFOButton_TX.Refresh()           # перерисовать кнопку
      if application.lockVFOButton_TX.GetValue(): # если включен LockF
        x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=True) # получение параметров шторки и смещения шторки приёмника (он же передатчик)
        dc.SetTextForeground('yellow')
        dc.DrawText('Lock', self.tune_tx + x + rit, 90)

    if self.display_text: # установки для текста на панораме
      dc.SetFont(self.font)
      dc.SetTextBackground(conf.color_graph_msg_bg)
      dc.SetTextForeground(conf.color_graph_msg_fg)
      dc.SetBackgroundMode(wx.SOLID)
      dc.DrawText(self.display_text, 0, 0)

    # --------------------- добавлено ------------------------------------------------------------------------ S-метр на панораме --------------- 7 RA3PKJ
    if self.display_text == "":
    # красный указатель S-метра на панораме
      SmtrX = 30 # X-position (изначальная позиция S-метра по оси Х)
      smeter_int = round(SmtrX - 15 + (application.smeter_sunits + 127) * 2.5) #вычислить новое положение бегунка S-метра по оси Х
      dc.SetPen(wx.Pen('red', 2)) #цвет бегунка S-метра
      dc.DrawLine(smeter_int, 38, smeter_int, 48) #отрисовка нового положения бегунка S-метра (указаны координаты начала и конца вертикальной чёрточки бегунка)
    # оцифровка S-метра на панораме, и другое
      dc.SetPen(wx.Pen('white', 1))
      dc.DrawLine(SmtrX, 30, SmtrX, 35)
      dc.DrawLine(SmtrX + 15, 30, SmtrX + 15, 35)
      dc.DrawLine(SmtrX + 30, 30, SmtrX + 30, 35)
      dc.DrawLine(SmtrX + 45, 30, SmtrX + 45, 35)
      dc.DrawLine(SmtrX + 60, 30, SmtrX + 60, 35)
      dc.DrawLine(SmtrX + 75, 30, SmtrX + 75, 35)
      dc.DrawLine(SmtrX + 90, 30, SmtrX + 90, 35)
      dc.DrawLine(SmtrX + 105, 30, SmtrX + 105, 35)
      dc.DrawLine(SmtrX + 120, 30, SmtrX + 120, 35)
      dc.DrawLine(SmtrX + 145, 30, SmtrX + 145, 35)
      dc.DrawLine(SmtrX + 170, 30, SmtrX + 170, 35)
      dc.DrawLine(SmtrX + 195, 30, SmtrX + 195, 35)
      dc.DrawLine(SmtrX + 220, 30, SmtrX + 220, 35)
      dc.DrawLine(SmtrX + 245, 30, SmtrX + 245, 35)
      dc.DrawLine(SmtrX + 270, 30, SmtrX + 270, 35)
      dc.SetTextForeground('green')
      dc.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface))
      dc.DrawText('1', SmtrX - 5, 10)
      dc.DrawText('2', SmtrX + 10, 10)
      dc.DrawText('3', SmtrX + 25, 10)
      dc.DrawText('4', SmtrX + 40, 10)
      dc.DrawText('5', SmtrX + 55, 10)
      dc.DrawText('6', SmtrX + 70, 10)
      dc.DrawText('7', SmtrX + 85, 10)
      dc.DrawText('8', SmtrX + 100, 10)
      dc.DrawText('9', SmtrX + 115, 10)
      dc.DrawText('+10', SmtrX + 128, 10)
      dc.DrawText('+20', SmtrX + 153, 10)
      dc.DrawText('+30', SmtrX + 178, 10)
      dc.DrawText('+40', SmtrX + 203, 10)
      dc.DrawText('+50', SmtrX + 228, 10)
      dc.DrawText('+60', SmtrX + 253, 10)

      # ---------------------------------------------------------------------- добавлено ------------------------- вынос из малого окошка ------- 8 RA3PKJ
      dc.SetTextForeground('yellow')
      dc.DrawText(("%7.2f dBm" % application.smeter_db), SmtrX+320, 10) #показать строку децибеллов
      if application.bandscope_flag:
        d = QS.get_hermes_adc()	# ---------- ADC level from bandscope, 0.0 to 1.0
        if d < 1E-10:
          d = 1E-10
        dc.DrawText("ADC %.0f%% %.0fdB" % (d * 100.0, 20 * math.log10(d)),  SmtrX+450, 10)
      elif application.freedv_flag:
        pass
      else:
        dc.DrawText(application.measure_audio_str + ' uV', SmtrX+450, 10) #показать строку напряжения аудио

    if application.tx_inhibit:
      dc.SetFont(self.font)
      dc.SetTextBackground(conf.color_graph_msg_bg)
      dc.SetTextForeground("red")
      dc.SetBackgroundMode(wx.SOLID)
      #dc.DrawText(" *** Tx Inhibit ***", 0, self.chary * 15 // 10) # --------- удалено -------- коррекция положения надписи "Tx Inhibit" ------- 38 RA3PKJ
      dc.DrawText(" *** Tx Inhibit ***", 0, self.chary * 4) # ----------------- взамен ---- self.chary * 4 - опустить надпись на четыре высоты шрифта

  def DrawFilter(self, dc):
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.SetLogicalFunction(wx.COPY)
    scale = 1.0 / self.parent.zoom / self.parent.sample_rate * self.graph_width
    dc.SetBrush(self.filterBrush)
    if self.tune_rx: # если включен Split и RX2
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=False)
      dc.DrawRectangle(self.tune_tx + x, 0, w, self.height)
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=True)
      dc.DrawRectangle(self.tune_rx + rit + x, 0, w, self.height)
      dc.SetPen(self.tuningPenRx)
      dc.DrawLine(self.tune_rx, 0, self.tune_rx, self.height)
    else: # режим одной шторки
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=True)
      dc.DrawRectangle(self.tune_tx + rit + x, 0, w, self.height)
    dc.SetPen(self.tuningPenTx)
    dc.DrawLine(self.tune_tx, 0, self.tune_tx, self.height)
    return rit
  def SetHeight(self, height):
    self.height = height
    self.SetSize((self.graph_width, height))
  def OnGraphData(self, data):
    x = 0
    for y in data:	# y is in dB, -200 to 0
      y = self.zeroDB - int(y * self.scale / 10.0 + 0.5)
      try:
        y0 = self.line[x][1]
      except IndexError:
        self.line.append([x, y])
      else:
        if y > y0:
          y = min(y, y0 + self.peak_hold)
        self.line[x] = [x, y]
      x = x + 1
    self.Refresh()
  def SetTuningLine(self, tune_tx, tune_rx):
    dc = wx.ClientDC(self)
    rit = self.parent.GetFilterDisplayRit()
    # Erase the old display
    dc.SetPen(self.backgroundPen)
    if self.tune_rx:
      dc.DrawLine(self.tune_rx, 0, self.tune_rx, self.height)
    dc.DrawLine(self.tune_tx, 0, self.tune_tx, self.height)
    # Draw a new display
    if self.tune_rx:
      dc.SetPen(self.tuningPenRx)
      dc.DrawLine(tune_rx, 0, tune_rx, self.height)
    dc.SetPen(self.tuningPenTx)
    dc.DrawLine(tune_tx, 0, tune_tx, self.height)
    self.tune_tx = tune_tx
    self.tune_rx = tune_rx

class GraphScreen(wx.Window):
  """Display the graph screen X and Y axis, and create a graph display."""
  def __init__(self, parent, data_width, graph_width, in_splitter=0):
    wx.Window.__init__(self, parent, pos = (0, 0))
    self.in_splitter = in_splitter	# Are we in the top of a splitter window?
    # self.split_unavailable = False # -------------------------- удалено ------------------------ реформа мышиного управления шторками -------- 13 RA3PKJ
    if in_splitter:
      self.y_scale = conf.waterfall_graph_y_scale
      self.y_zero = conf.waterfall_graph_y_zero
    else:
      self.y_scale = conf.graph_y_scale
      self.y_zero = conf.graph_y_zero
    self.zoom_control = 0
    self.y_ticks = []
    self.VFO = 0
    self.filter_mode = 'AM'
    self.filter_bandwidth = 0 # ширина шторки, например 2800
    self.filter_center = 0    # середина шторки (отрицательная, если нижняя боковая, и наоборот), например -1400
    self.ritFreq = 0				# receive incremental tuning frequency offset
    self.mouse_x = 0
    #self.WheelMod = conf.mouse_wheelmod # ------------------- удалено ------------------------------------ шаг перестройки -------------------- 30 RA3PKJ
    self.txFreq = 0
    self.sample_rate = application.sample_rate
    self.zoom = 1.0
    self.zoom_deltaf = 0
    self.data_width = data_width
    self.graph_width = graph_width
    self.doResize = False
    #self.pen_tick = wx.Pen(conf.color_graphticks, 1)
    self.pen_tick = wx.Pen('#646464', 1) # ----------------- взамен ---- цвет рисок вокруг панорамы ------- оформление панорамы ----------------- 4 RA3PKJ
    self.pen_center = wx.Pen(conf.color_graphticks, 3)
    self.font = wx.Font(conf.graph_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    self.SetFont(self.font)
    w = self.GetCharWidth() * 14 // 10
    h = self.GetCharHeight()
    self.charx = w
    self.chary = h
    self.tick = max(2, h * 3 // 10)
    self.originX = w * 5
    self.offsetY = h + self.tick
    self.width = self.originX + self.graph_width + self.tick + self.charx * 2
    self.height = application.screen_height * 3 // 10
    self.x0 = self.originX + self.graph_width // 2		# center of graph
    self.tuningX = self.x0
    self.originY = 10
    self.zeroDB = 10	# y location of zero dB; may be above the top of the graph
    self.scale = 10
    self.mouse_is_rx = False
    self.priznak_filter = 0 # 0-исходное, 1-перемещение мышью шторки RX в Split(RX2), 2-перемещение мышью шторки TX в Split(RX2) - добавлено - перемещение шторок мышью - 56 RA3PKJ

    # -------------------------------------------------------- добавлено ------------------------------------- кнопки f_Before и f_After --------- 51 RA3PKJ
    self.before_after_start = 0 # флаг старта программы
    self.f_before_1_buf = 0 # промежуточная переменная
    self.f_before_2_buf = 0 # промежуточная переменная
    self.motion_count = 0 # счётчик входов в функцию OnMotion
    self.SetSize((self.width, self.height))
    self.SetSizeHints(self.width, 1, self.width)
    self.SetBackgroundColour(conf.color_graph)
    #self.backgroundBrush = wx.Brush(conf.color_graph)
    self.backgroundBrush = wx.Brush('#000B10') # -------------- взамен ------- цвет вокруг панорамы ------------ оформление панорамы ------------ 4 RA3PKJ
    self.Bind(wx.EVT_SIZE, self.OnSize)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
    self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
    self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
    self.Bind(wx.EVT_MOTION, self.OnMotion)
    self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
    # handle bandplan info
# ------------------------------------------------------------ удалено ------------------------------------------ удаление Бенд Плана ---------- 61 RA3PKJ
##    self.bandplanWindow = wx.PopupWindow (parent)
##    self.bandplanInfo = wx.TextCtrl(self.bandplanWindow, style=wx.TE_READONLY)
##    self.bandplanInfo.SetFont(wx.Font(conf.status_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
##        wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface))
##    self.bandplanWindow.Hide();
    self.MakeDisplay()
  def MakeDisplay(self):
    self.display = GraphDisplay(self, self.originX, 0, self.graph_width, 5, self.chary)
    self.display.zeroDB = self.zeroDB
  def SetDisplayMsg(self, text=''):
    self.display.display_text = text
    self.display.Refresh()
  def ScrollMsg(self, chars):	# Add characters to a scrolling message
    self.display.display_text = self.display.display_text + chars
    self.display.display_text = self.display.display_text[-50:]
    self.display.Refresh()
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    dc.SetBackground(self.backgroundBrush)
    dc.Clear()
    dc.SetFont(self.font)
    #dc.SetTextForeground(conf.color_graphlabels)
    dc.SetTextForeground('yellow') # ------------------------ взамен -------- цвет оцифровки вокруг панорамы --------- оформление панорамы ----------- 4 RA3PKJ
    if self.in_splitter:
      self.MakeYTicks(dc)
    else:
      self.MakeYTicks(dc)
      self.MakeXTicks(dc)
  def OnIdle(self, event):
    if self.doResize:
      self.ResizeGraph()
  def OnSize(self, event):
    self.doResize = True
    event.Skip()
  def ResizeGraph(self):
    """Change the height of the graph.

    Changing the width interactively is not allowed because the FFT size is fixed.
    Call after changing the zero or scale to recalculate the X and Y axis marks.
    """
    w, h = self.GetClientSize()
    if self.in_splitter:	# Splitter window has no X axis scale
      self.height = h
      self.originY = h
    else:
      self.height = h - self.chary		# Leave space for X scale
      self.originY = self.height - self.offsetY
    if self.originY < 0:
      self.originY = 0
    self.MakeYScale()
    self.display.SetHeight(self.originY)
    self.display.scale = self.scale
    self.doResize = False
    self.Refresh()
  def ChangeYscale(self, y_scale):
    self.y_scale = y_scale
    self.doResize = True
  def ChangeYzero(self, y_zero):
    self.y_zero = y_zero
    self.doResize = True
  def ChangeZoom(self, zoom, deltaf, zoom_control):
    self.zoom = zoom
    self.zoom_deltaf = deltaf
    self.zoom_control = zoom_control
    self.doResize = True
  def MakeYScale(self):
    chary = self.chary
    #scale = (self.originY - chary)  * 10 // (self.y_scale + 20)	# Number of pixels per 10 dB # -- удалено -- ползунк Ys прямой --- 23 RA3PKJ
    scale = 33 + ((self.originY - chary) * (self.y_scale - 70) // 1300) # ---------------------------- взамен -- ползунк Ys прямой --- 23 RA3PKJ
    scale = max(1, scale)
    q = (self.originY - chary ) // scale // 2
    zeroDB = chary + q * scale - self.y_zero * scale // 10
    if zeroDB > chary:
      zeroDB = chary
    self.scale = scale
    self.zeroDB = zeroDB
    self.display.zeroDB = self.zeroDB
    QS.record_graph(self.originX, self.zeroDB, self.scale)
  def MakeYTicks(self, dc):
    chary = self.chary
    x1 = self.originX - self.tick * 3	# left of tick mark
    x2 = self.originX - 1		# x location of y axis
    x3 = self.originX + self.graph_width	# end of graph data
    dc.SetPen(self.pen_tick)
    dc.DrawLine(x2, 0, x2, self.originY + 1)	# y axis
    y = self.zeroDB
    del self.y_ticks[:]
    y_old = y
    for i in range(0, -99999, -10):
      if y >= chary // 2:
        dc.SetPen(self.pen_tick)
        dc.DrawLine(x1, y, x2, y)	# y tick
        self.y_ticks.append(y)
        t = repr(i)
        w, h = dc.GetTextExtent(t)
        # draw text on Y axis
        if y - y_old > h:
          if y + h // 2 <= self.originY:
            dc.DrawText(repr(i), x1 - w, y - h // 2)
          elif h < self.scale:
            dc.DrawText(repr(i), x1 - w, self.originY - h)
          y_old = y
      y = y + self.scale
      if y >= self.originY - 3:
        break
  def MakeXTicks(self, dc):
    sample_rate = int(self.sample_rate * self.zoom)
    VFO = self.VFO + self.zoom_deltaf
    originY = self.originY
    x3 = self.originX + self.graph_width	# end of fft data
    charx , z = dc.GetTextExtent('-30000XX')
    tick0 = self.tick
    tick1 = tick0 * 2
    tick2 = tick0 * 3
    # Draw the X axis
    dc.SetPen(self.pen_tick)
    dc.DrawLine(self.originX, originY, x3, originY)
    # Draw the band plan colors below the X axis
    x = self.originX
    f = float(x - self.x0) * sample_rate / self.data_width
    c = None
    y = originY + 1
    for freq, color in application.BandPlan:
      freq -= VFO
      if f < freq:
        xend = int(self.x0 + float(freq) * self.data_width / sample_rate + 0.5)
        if c is not None:
          dc.SetPen(wx.TRANSPARENT_PEN)
          dc.SetBrush(wx.Brush(c))
          dc.DrawRectangle(x, y, min(x3, xend) - x, tick0)  # x axis
        if xend >= x3:
          break
        x = xend
        f = freq
      c = color
    # check the width of the frequency label versus frequency span
    df = charx * sample_rate // self.data_width
    if VFO >= 10E9:     # Leave room for big labels
      df *= 1.33
    elif VFO >= 1E9:
      df *= 1.17
    # tfreq: tick frequency for labels in Hertz
    # stick: small tick in Hertz
    # mtick: medium tick
    # ltick: large tick
    s2 = 1000
    tfreq = None
    while tfreq is None:
      if df < s2:
        tfreq = s2
        stick = s2 // 10
        mtick = s2 // 2
        ltick = tfreq
      elif df < s2 * 2:
        tfreq = s2 * 2
        stick = s2 // 10
        mtick = s2 // 2
        ltick = s2
      elif df < s2 * 5:
        tfreq = s2 * 5
        stick = s2 // 2
        mtick = s2
        ltick = tfreq
      s2 *= 10
    # Draw the X axis ticks and frequency in kHz
    dc.SetPen(self.pen_tick)
    freq1 = VFO - sample_rate // 2
    freq1 = (freq1 // stick) * stick
    freq2 = freq1 + sample_rate + stick + 1
    y_end = 0
    for f in range (freq1, freq2, stick):
      x = self.x0 + int(float(f - VFO) / sample_rate * self.data_width)
      if self.originX <= x <= x3:
        if f % ltick == 0:		# large tick
          dc.DrawLine(x, originY, x, originY + tick2)
        elif f % mtick == 0:	# medium tick
          dc.DrawLine(x, originY, x, originY + tick1)
        else:					# small tick
          dc.DrawLine(x, originY, x, originY + tick0)
        if f % tfreq == 0:		# place frequency label
          t = str(f//1000)
          w, h = dc.GetTextExtent(t)
          dc.DrawText(t, x - w // 2, originY + tick2)
          y_end = originY + tick2 + h
    if y_end:		# mark the center of the display
      dc.SetPen(self.pen_center)
      dc.DrawLine(self.x0, y_end, self.x0, application.screen_height)
  def OnGraphData(self, data):
    i1 = (self.data_width - self.graph_width) // 2
    i2 = i1 + self.graph_width
    self.raw_graph_data = data[i1:i2]
    self.display.OnGraphData(data[i1:i2])
  def SetVFO(self, vfo):
    self.VFO = vfo
    self.doResize = True
  def SetTxFreq(self, tx_freq, rx_freq):
    sample_rate = int(self.sample_rate * self.zoom)
    self.txFreq = tx_freq
    tx_x = self.x0 + int(float(tx_freq - self.zoom_deltaf) / sample_rate * self.data_width)
    self.tuningX = tx_x
    rx_x = self.x0 + int(float(rx_freq - self.zoom_deltaf) / sample_rate * self.data_width)
    if abs(tx_x - rx_x) < 2:		# Do not display Rx line for small frequency offset
      self.display.SetTuningLine(tx_x - self.originX, 0)
    else:
      self.display.SetTuningLine(tx_x - self.originX, rx_x - self.originX)
  def GetFilterDisplayXWR(self, rx_filters):
    mode = self.filter_mode
    rit = self.ritFreq
    if rx_filters:	# return Rx filter
      bandwidth = self.filter_bandwidth
      center = self.filter_center
    else:	# return Tx filter
      bandwidth, center = get_filter_tx(mode)
    x = center - bandwidth // 2
    scale = 1.0 / self.zoom / self.sample_rate * self.data_width
    x = int(x * scale + 0.5)
    bandwidth = int(bandwidth * scale + 0.5)
    if bandwidth < 2:
      bandwidth = 1
    rit = int(rit * scale + 0.5)
    return x, bandwidth, rit		# Starting x, bandwidth and RIT frequency
  def GetFilterDisplayRit(self):
    rit = self.ritFreq
    scale = 1.0 / self.zoom / self.sample_rate * self.data_width
    rit = int(rit * scale + 0.5)
    return rit
  def GetMousePosition(self, event):
    """For mouse clicks in our display, translate to our screen coordinates."""
    mouse_x, mouse_y = event.GetPosition()
    win = event.GetEventObject()
    if win and win is not self:
      x, y = win.GetPosition().Get()
      mouse_x += x
      mouse_y += y
    return mouse_x, mouse_y
  def FreqRound(self, tune, vfo):
    if conf.freq_spacing and not conf.freq_round_ssb:
      freq = tune + vfo
      n = int(freq) - conf.freq_base
      if n >= 0:
        n = (n + conf.freq_spacing // 2) // conf.freq_spacing
      else:
        n = - ( - n + conf.freq_spacing // 2) // conf.freq_spacing
      freq = conf.freq_base + n * conf.freq_spacing
      return freq - vfo
    else:
      return tune

  def OnRightDown(self, event): # правая клавиша мыши вниз
    # ---------------------------------------------------- взамен ---------------------------- реформа мышиного управления шторками ----------- 13 RA3PKJ
    if application.split_rxtx == False and application.new_split == False and application.split_locktx: # если залочен передатчик (он же приёмник) в режиме одной шторки
      self.mouse_is_rx = False
      return

    # ---------------------------------------------------- добавлено --------------------------------------- кнопки f_Before и f_After ------- 51 RA3PKJ
    if self.before_after_start == 0: # первичная загрузка значений при старте программы
      application.f_before_1 = self.txFreq
      application.f_before_2 = self.VFO
      self.before_after_start = 1
# -------------------------------------------------------- удалено ------ отключён прыжок панорамы -------- Перестройка типа PowerSDR -------- 47 RA3PKJ
##    sample_rate = int(self.sample_rate * self.zoom)
##    VFO = self.VFO + self.zoom_deltaf
##    mouse_x, mouse_y = self.GetMousePosition(event)
##    freq = float(mouse_x - self.x0) * sample_rate / self.data_width
##    freq = int(freq)
##    if VFO > 0:
##      vfo = VFO + freq - self.zoom_deltaf
##      if sample_rate > 40000:
##        vfo = (vfo + 5000) // 10000 * 10000	# round to even number
##      elif sample_rate > 5000:
##        vfo = (vfo + 500) // 1000 * 1000
##      else:
##        vfo = (vfo + 50) // 100 * 100
##      tune = freq + VFO - vfo
##      tune = self.FreqRound(tune, vfo)
##      self.ChangeHwFrequency(tune, vfo, 'MouseBtn3', event=event)
    # ----------------------------------------------------- взамен ----------------------------------------  Перестройка типа PowerSDR ------- 47 RA3PKJ
    mouse_x, mouse_y = self.GetMousePosition(event)
    self.mouse_x = mouse_x
    self.motion_count = 0 # привести счётчик входов в функцию OnMotion в исходное положение

  # ------------------------------------------------------ добавлено ----------- добавлена функция --------- Перестройка типа PowerSDR ------- 47 RA3PKJ
  def OnRightUp(self, event): # правая клавиша мыши вверх
    # ----------------------------------------------------------------------------- добавлено ------------ реформа мышиного управления шторками --- 13 RA3PKJ
    if application.split_rxtx == False and application.new_split == False and application.split_locktx: # если залочен передатчик (он же приёмник) в режиме одной шторки
      self.mouse_is_rx = False
      return

    if self.motion_count < 2: # если не было перемещение панорамы в перестройке типа PowerSDR или было случайное перемещение на 1 шаг, то:
      # -------------------------------------------------- добавлено --------------------------------------- кнопки f_Before и f_After ------- 51 RA3PKJ
      self.f_before_1_buf = self.txFreq
      self.f_before_2_buf = self.VFO

      # выполнить прыжок панорамы
      sample_rate = int(self.sample_rate * self.zoom)
      VFO = self.VFO + self.zoom_deltaf
      mouse_x, mouse_y = self.GetMousePosition(event)
      freq = float(mouse_x - self.x0) * sample_rate / self.data_width
      freq = int(freq)
      if VFO > 0:
        vfo = VFO + freq - self.zoom_deltaf
        if sample_rate > 40000:
          vfo = (vfo + 5000) // 10000 * 10000    # round to even number
        elif sample_rate > 5000:
          vfo = (vfo + 500) // 1000 * 1000
        else:
          vfo = (vfo + 50) // 100 * 100
        tune = freq + VFO - vfo
        tune = self.FreqRound(tune, vfo)
        self.ChangeHwFrequency(tune, vfo, 'MouseBtn3', event=event)
    # -------------------------------------------------- добавлено -------------------------------------- кнопки f_Before и f_After --------- 51 RA3PKJ
        application.f_after_1 = tune
        application.f_after_2 = vfo
        freq_jump = abs((application.f_after_2 - application.f_after_1) - (self.f_before_2_buf - self.f_before_1_buf)) # определить, насколько далеко произошёл прыжок или перемещение частоты мышью
        if freq_jump > 5000: # если было изменение частоты более 5кГц, то:
          application.f_before_1 = self.f_before_1_buf
          application.f_before_2 = self.f_before_2_buf
    else: # если было перемещение панорамы в перестройке типа PowerSDR, то:
      application.f_after_1 = self.txFreq
      application.f_after_2 = self.VFO
      if self.motion_count > 40: # если было перемещение на заметную дистанцию, то:
        application.f_before_1 = self.f_before_1_buf
        application.f_before_2 = self.f_before_2_buf
    application.beforeButton.Enable(1)
    application.afterButton.Enable(0)
    self.motion_count = 0 # привести счётчик входов в функцию OnMotion в исходное положение

  def OnLeftDown(self, event): # левая клавиша мыши вниз
    # СПРАВКА
    # self.VFO - абсолютная частота посередине панорамы в Герцах
    # self.filter_center - середина шторки приёмника в однополосных модах (отрицательная - если нижняя боковая, и наоборот), например -1400 при полосе 2800
    # self.sample_rate - величина постоянная, например 192000
    # sample_rate - уменьшается ниже 192000, если делать ZOOM панорамы
    # self.filter_bandwidth - ширина шторки приёмника, например 2800
    # self.data_width - постоянная величина ширины панорамы в единицах разрешения экрана, прописанного в Quisk (Window width pixels
    # self.originX - предельная слева частота на панораме
    # self.display.tune_rx - частота приёмника по нулевым биениям в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.display.tune_tx - частота передатчика по нулевым биениям в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # x - позиция мыши в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.zoom - коэффициент зуммирования, пример использования: sample_rate = int(self.sample_rate * self.zoom)
    # self.originX - левый край, не зависит от ZOOM, но не равен нулю

    # ------------------------------------------------------------------------------------------- реформа мышиного управления шторками ----------- 13 RA3PKJ
    if application.split_rxtx == False and application.new_split == False and application.split_locktx: # если залочен передатчик (он же приёмник) в режиме одной шторки
      self.mouse_is_rx = False # т.е. оставить режим одной шторки перед выходом из функции
      return # выход из функции
    if application.split_locktx == True and application.split_lockrx == True: # если всё залочено
      return # выход из функции

    # ----------------------------------------------------- добавлено ------------------------------------- кнопки f_Before и f_After ------------ 51 RA3PKJ
    if self.before_after_start == 0: # первичная загрузка значений при старте программы
      application.f_before_1 = self.txFreq
      application.f_before_2 = self.VFO
      self.before_after_start = 1
    else:
      self.f_before_1_buf = self.txFreq
      self.f_before_2_buf = self.VFO

    # получить позицию "x" мыши в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    sample_rate = int(self.sample_rate * self.zoom)
    mouse_x, mouse_y = self.GetMousePosition(event)
    if mouse_x <= self.originX:		# click left of Y axis
      return
    if mouse_x >= self.originX + self.graph_width:	# click past FFT data
      return
    # ------------------------------------------------------ удалено ------------------------------- реформа мышиного управления шторками ------- 13 RA3PKJ
    #shift = wx.GetKeyState(wx.WXK_SHIFT) # проверить клавишу Shift
    #if shift:
      #mouse_x -= self.filter_center * self.data_width / sample_rate
    self.mouse_x = mouse_x
    x = mouse_x - self.originX

    # координаты шторок
    x_rx, w_rx, rit_rx = self.display.parent.GetFilterDisplayXWR(rx_filters=True) # параметры шторки приёмника в Split (RX2) или основной шторки в режиме одной шторки, параметры зависят от ZOOM
    x_tx, w_tx, rit_tx = self.display.parent.GetFilterDisplayXWR(rx_filters=False) # параметры шторки передатчика в Split (RX2),  параметры зависят от ZOOM
    # СПРАВКА
    # x_rx, x_tx - координата левого края шторки относительно нулевой частоты (подавленной несущей в SSB), отрицательная при нижней боковой и положительная при верхней боковой
    # w_rx, w_tx - абсолютная ширина шторки
    # rit_tx, rit_rx - смещение шторки при расстройке, но rit_tx похоже не существует, так как это тоже самое, что rit_rx

    if mouse_y < self.originY: # click above X axis - если клик на панораме (включая водопад), то получить частоту, которая соответствует клику мыши
      # -------------------------------------------------------------- добавлено ------------------ реформа мышиного управления шторками ---------- 13 RA3PKJ
      # для трансверторов большие прыжки
      if conf.freq_spacing:
        freq = float(mouse_x - self.x0) * sample_rate / self.data_width + self.zoom_deltaf
        freq = int(freq)
        if not self.mouse_is_rx:
          freq = self.FreqRound(freq, self.VFO)
      # прыжки в CW
      elif application.mode in ('CWU', 'CWL'):	# Move to a nearby peak
        freq = float(mouse_x - self.x0) * sample_rate / self.data_width + self.zoom_deltaf
        freq = int(freq)
        CW_width = self.data_width * application.filter_bandwidth // sample_rate // 2	# width tolerance
        CW_mouse = mouse_x - self.originX
        CW_max = -9999	# look for a peak significantly greater than the average
        CW_avg = 0.0
        CW_x1 = CW_mouse - CW_width
        CW_x2 = CW_mouse + CW_width
        try:
          for x in range(CW_x1, CW_x2):
            y = self.raw_graph_data[x]
            CW_avg += y
            if y > CW_max:
              CW_max = y
              CW_x = x
          CW_avg /= (CW_x2 - CW_x1)
          yp = self.raw_graph_data[CW_x + 1]
          ym = self.raw_graph_data[CW_x - 1]
          CW_correct = 0.5 * (ym - yp) / (ym - 2 * CW_max + yp)
        except:	# missing or short raw_graph_data, zero CW_width
          pass
        else:
          if CW_max - CW_avg > 5 and CW_max > yp and CW_max > ym:
            CW_x += CW_correct
            freq = float(CW_x + self.originX - self.x0) * sample_rate / self.data_width + self.zoom_deltaf
            freq = int(freq)

      # -------------------------------------------------------------- добавлено ------------------ реформа мышиного управления шторками ------ 13 RA3PKJ
      # прыжки шторок с совмещением курсора с центром шторок (self.filter_center существует только в однополосных модах, но в других видах и так всё прыгает по центру шторок)
      #else:
      # -------------------------------------------------------------- добавлено ------------------ реформа мышиного управления шторками ------ 13 RA3PKJ
      # найти к какому краю шторок ближе всего клик мыши
      if self.display.tune_rx: # если Split или RX2
        rx_down = abs(x - (self.display.tune_rx + x_rx + rit_rx))
        rx_up = abs(x - (self.display.tune_rx + x_rx + w_rx + rit_rx))
        tx_down = abs(x - (self.display.tune_tx + x_tx))
        tx_up = abs(x - (self.display.tune_tx + x_tx + w_tx))
      else: # одна шторка
        tx_down = abs(x - (self.display.tune_tx + x_rx))
        tx_up = abs(x - (self.display.tune_tx + x_rx + w_rx))
      if self.display.tune_rx and application.split_lockrx: # если Split или RX2, залочен приёмник
        slovar = {'tx_down':tx_down, 'tx_up':tx_up}
      elif self.display.tune_rx and application.split_locktx: # если Split или RX2, залочен передатчик
        slovar = {'rx_down':rx_down, 'rx_up':rx_up}
      elif self.display.tune_rx: # если Split или RX2, ничего не залочено
        slovar = {'rx_down':rx_down, 'rx_up':rx_up, 'tx_down':tx_down, 'tx_up':tx_up}
      else: # если одна шторка
        slovar = {'tx_down':tx_down, 'tx_up':tx_up}
      min_key = min(slovar, key=slovar.get) # получить шторку, до которой минимальное расстояние от клика
      # создать прыжок
      if min_key in ('tx_down', 'tx_up'): # если клик близко к передатчику
        if not self.filter_center == 0 and not application.mode in ('CWL','CWU'): # однополосные моды, но не телеграф
          if self.display.tune_rx: # если Split или RX2
            mouse_x -= x_tx + w_tx//2 # сымитировать смещение курсора мыши для ориентирования прыжков шторки по центру шторки в однополосных модах
          else:
            mouse_x -= self.filter_center * self.data_width / sample_rate # сымитировать смещение в режиме одной шторки
        freq = float(mouse_x - self.x0) * sample_rate / self.data_width + self.zoom_deltaf
        freq = int(freq)
        rnd = conf.freq_round_ssb # если установлен параметр "Frequency round for SSB" (прыжки частоты округляются до целого, например 1кГц)
        if rnd:
          freq = (freq + rnd // 2) // rnd * rnd
        self.priznak_filter = 2
        self.ChangeHwFrequency(freq, self.VFO, 'MouseBtn1', event=event) # прыжок передатчика
        # ------------------------------------------------------------ добавлено -------------------------- кнопки f_Before и f_After --------- 51 RA3PKJ
        application.f_after_1 = freq
        application.f_after_2 = self.VFO
      elif min_key in ('rx_down', 'rx_up'): # если клик близко к приёмнику
        if not self.filter_center == 0 and not application.mode in ('CWL','CWU'): # однополосные моды, но не телеграф
          mouse_x -= self.filter_center * self.data_width / sample_rate # сымитировать смещение курсора мыши для ориентирования прыжков шторки по центру шторки в однополосных модах
        freq = float(mouse_x - self.x0) * sample_rate / self.data_width + self.zoom_deltaf
        freq = int(freq)
        rnd = conf.freq_round_ssb # если установлен параметр "Frequency round for SSB" (прыжки частоты округляются до целого, например 1кГц)
        if rnd:
          freq = (freq + rnd // 2) // rnd * rnd
        self.priznak_filter = 1
        self.ChangeHwFrequency(self.txFreq, self.VFO, 'MouseBtn1', event=event, rx_freq=freq) # прыжок приёмника
        # ------------------------------------------------------------ добавлено -------------------------- кнопки f_Before и f_After --------- 51 RA3PKJ
        application.f_after_1 = self.txFreq
        application.f_after_2 = self.VFO

    if not self.HasCapture():
      self.CaptureMouse()

  def OnLeftUp(self, event): # левая клавиша мыши вверх
    self.mouse_is_rx = False # привести в исходное
    if self.HasCapture():
      self.ReleaseMouse()
      freq = self.FreqRound(self.txFreq, self.VFO)
      if freq != self.txFreq:
        self.ChangeHwFrequency(freq, self.VFO, 'MouseMotion', event=event)
    # ------------------------------------------------------------- добавлено --------------------------------- кнопки f_Before и f_After --------- 51 RA3PKJ
    if application.f_after_1 == None:
      application.f_after_1 = 0
    freq_jump = abs((self.VFO - application.f_after_1) - (self.VFO - self.f_before_1_buf)) # определить, насколько далеко произошёл прыжок или перемещение частоты мышью
    if freq_jump > 5000: # если было изменение частоты более 5кГц, то:
      application.f_before_1 = self.f_before_1_buf
      application.f_before_2 = self.f_before_2_buf
    application.beforeButton.Enable(1)
    application.afterButton.Enable(0)
    self.motion_count = 0 # привести счётчик входов в функцию OnMotion в исходное положение

  def OnMotion(self, event): # движение мыши по столу
    # СПРАВКА
    # self.VFO - абсолютная частота посередине панорамы в Герцах
    # self.filter_center - середина шторки приёмника в однополосных модах (отрицательная - если нижняя боковая, и наоборот), например -1400 при полосе 2800
    # self.sample_rate - величина постоянная, например 192000
    # sample_rate - уменьшается ниже 192000, если делать ZOOM панорамы
    # self.filter_bandwidth - ширина шторки приёмника, например 2800
    # self.data_width - постоянная величина ширины панорамы в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.originX - предельная слева частота на панораме
    # self.display.tune_rx - частота приёмника по нулевым биениям в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.display.tune_tx - частота передатчика по нулевым биениям в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # x - позиция мыши в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.zoom - коэффициент зуммирования, пример использования: sample_rate = int(self.sample_rate * self.zoom)
    # self.originX - левый край, не зависит от ZOOM, но не равен нулю

    sample_rate = int(self.sample_rate * self.zoom)

    # ----------------------------------------------------------------------------- добавлено ------------ реформа мышиного управления шторками --- 13 RA3PKJ
    if application.split_rxtx == False and application.new_split == False and application.split_locktx: # если залочен передатчик (он же приёмник) в режиме одной шторкиа
      self.mouse_is_rx = False
      return

    # ----------------------------------------------------------------------------- добавлено ----------------- кнопки f_Before и f_After --------- 51 RA3PKJ
    if self.motion_count == 0: # если первый вход в эту функцию, то:
      self.f_before_1_buf = self.txFreq
      self.f_before_2_buf = self.VFO
    self.motion_count += 1 # количество входов в эту функцию

    # Настройка как в PowerSDR (Mouse motion changes the VFO frequency)
    # ----------------------------------------------------------------------------- добавлено ----------------- Перестройка типа PowerSDR --------- 47 RA3PKJ
    if event.Dragging() and event.RightIsDown():
      pass
      mouse_x, mouse_y = self.GetMousePosition(event)
      x = (mouse_x - self.mouse_x)    # Thanks to VK6JBL
      self.mouse_x = mouse_x
      freq = float(x) * sample_rate / self.data_width
      freq = int(freq)
      self.ChangeHwFrequency(self.txFreq, self.VFO - freq, 'MouseMotion', event=event)
      return

    # Настройка как обычно в Quisk (Mouse motion changes the tuning frequency)
    if event.Dragging() and event.LeftIsDown():
      # Frequency changes more rapidly for higher mouse Y position
      # speed = max(10, self.originY - mouse_y) / float(self.originY + 1) # ------- удалено ----------- скорость шторки относительно курсора ------ 48 RA3PKJ
      mouse_x, mouse_y = self.GetMousePosition(event)   # получить координаты мыши
      x = (mouse_x - self.mouse_x)                      # получить смещение между новыми и старыми координатами мыши
      self.mouse_x = mouse_x                            # сохранить новые координаты мыши
      #freq = speed * x * sample_rate / self.data_width # ------------------------- удалено ----------- скорость шторки относительно курсора ------ 48 RA3PKJ
      freq = x * sample_rate / self.data_width          # пересчитать смещение в частоту --- взамен --- скорость шторки относительно курсора ------ 48 RA3PKJ
      freq = int(freq)                                  # отбросить дробную часть частотного смещения
      self.freq = freq # ---------------------------------------------------------- добавлено ----------------- кнопки f_Before и f_After --------- 51 RA3PKJ

# --------------------------------------------------------------------------------- добавлено ----------------- перемещение шторок мышью ---------- 56 RA3PKJ
      # СПРАВКА self.priznak_filter запоминает шторку, которую перемещает мышь без отрыва, т.е за один приём. 0-исходное, 1-перемещение мышью шторки RX в Split(RX2), 2-перемещение мышью шторки TX в Split(RX2)
      if application.split_rxtx == True or application.new_split == True:     # режим Split или RX2   # Mouse motion changes the receive frequency
        if application.split_lockrx and application.split_locktx:
          return
        if application.split_lockrx:
          self.priznak_filter = 2
        elif application.split_locktx:
          self.priznak_filter = 1

        if self.priznak_filter == 1:
          freq2 = application.rxFreq + freq                # новая частота приёмника с учётом частотного смещения
          self.ChangeHwFrequency(self.txFreq, self.VFO, 'MouseMotion', event=event, rx_freq=freq2)
          self.priznak_filter = 1
        elif self.priznak_filter == 2:
          self.ChangeHwFrequency(self.txFreq + freq, self.VFO, 'MouseMotion', event=event)
          self.priznak_filter = 2
        # ------------------------------------------------------------------------- добавлено ----------------- кнопки f_Before и f_After --------- 51 RA3PKJ
        application.f_after_1 = self.txFreq
        application.f_after_2 = self.VFO
      else:     # режим одной шторки  # Mouse motion changes the transmit frequency
        if application.split_locktx:
          return
        self.ChangeHwFrequency(self.txFreq + freq, self.VFO, 'MouseMotion', event=event)
        # ------------------------------------------------------------------------- добавлено ----------------- кнопки f_Before и f_After --------- 51 RA3PKJ
        application.f_after_1 = self.txFreq + freq
        application.f_after_2 = self.VFO
# ------------------------------------------------------------------------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------- удалено ------------------------ удаление Бенд Плана ---------- 61 RA3PKJ
##    else: # Bandplan mode message
##      mouse_x, mouse_y = self.GetMousePosition(event)
##      if not self.in_splitter and self.originY <= mouse_y <= self.originY + self.tick and (
##            self.originX <= mouse_x <= self.originX + self.graph_width):
##        dc = wx.ClientDC(self)    # Read the pixel at the mouse position
##        pixel = dc.GetPixel(mouse_x, mouse_y)
##        pixel = "#%02X%02X%02X" % (pixel[0], pixel[1], pixel[2])
##        txt = application.BandPlanC2T.get(pixel, '')
##        if pixel == "#000000":
##          pass
##        elif txt:
##          self.bandplanInfo.Clear()
##          self.bandplanInfo.write(txt)
##          width, height = self.bandplanInfo.GetTextExtent(txt)
##          width += self.bandplanInfo.GetCharWidth() * 2
##          height += self.bandplanInfo.GetCharHeight() // 2
##          self.bandplanInfo.SetSize(wx.Size(width, height))
##          self.bandplanWindow.SetClientSize((width, height))
##          rect = self.GetScreenRect()
##          if mouse_x > self.originX + self.graph_width * 3 // 4:
##            self.bandplanWindow.Move(mouse_x + rect.GetX() - width, mouse_y + rect.GetY() - height * 12 // 10)
##          else:
##            self.bandplanWindow.Move(mouse_x + rect.GetX(), mouse_y + rect.GetY() - height * 12 // 10)
##          if not self.bandplanWindow.IsShown():
##            self.bandplanWindow.Show()
##        else:
##          if self.bandplanWindow.IsShown():
##            self.bandplanWindow.Hide()
##      elif self.bandplanWindow.IsShown():
##        self.bandplanWindow.Hide()

  def OnWheel(self, event): # колесо мыши
    # СПРАВКА
    # self.VFO - абсолютная частота посередине панорамы в Герцах
    # self.filter_center - середина шторки приёмника в однополосных модах (отрицательная - если нижняя боковая, и наоборот), например -1400 при полосе 2800
    # self.sample_rate - величина постоянная, например 192000
    # sample_rate - уменьшается ниже 192000, если делать ZOOM панорамы
    # self.filter_bandwidth - ширина шторки приёмника, например 2800
    # self.data_width - постоянная величина ширины панорамы в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.originX - предельная слева частота на панораме
    # self.display.tune_rx - частота приёмника по нулевым биениям в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.display.tune_tx - частота передатчика по нулевым биениям в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # x - позиция мыши в единицах разрешения экрана, прописанного в Quisk (Window width pixels)
    # self.zoom - коэффициент зуммирования, пример использования: sample_rate = int(self.sample_rate * self.zoom)
    # self.originX - левый край, не зависит от ZOOM, но не равен нулю

    # -------------------------------------------------- добавлено -------------------------------- реформа мышиного управления шторками ------ 13 RA3PKJ
    if application.split_rxtx == False and application.new_split == False and application.split_locktx: # если залочен передатчик (он же приёмник) в режиме одной шторки
      self.mouse_is_rx = False # в исходное положение, чтобы не возникало артефактов в других режимах
      return # ничего не делать и молча выскочить

    # -------------------------------------------------- добавлено ------------------------------------- кнопки f_Before и f_After ------------ 51 RA3PKJ
    if self.before_after_start == 0: # первичная загрузка значений при старте программы
      application.f_before_1 = self.txFreq
      application.f_before_2 = self.VFO
      self.before_after_start = 1

    if conf.freq_spacing:
      wm = conf.freq_spacing
    else:
      #wm = self.WheelMod # ----------------------------------------------------------------- удалено -------------- шаг перестройки ----------- 30 RA3PKJ
      wm = application.freq_step # ----------------------------------------------------------- взамен -------------- шаг перестройки ----------- 30 RA3PKJ
    mouse_x, mouse_y = self.GetMousePosition(event)
    x = mouse_x - self.originX
    # --------------------------------------------------------------------------------------- удалено --- реформа мышиного управления шторками - 13 RA3PKJ
    #if self.split_unavailable:
      #self.mouse_is_rx = False

    # ----------------------------------------------------------------------------------- добавлено --- реформа мышиного управления шторками --- 13 RA3PKJ
    if self.display.tune_rx and abs(x - self.display.tune_tx) > abs(x - self.display.tune_rx): #если колесо мыши далеко от передатчика, то...
      self.mouse_is_rx = True # сдвинуть приёмник
    else:
      self.mouse_is_rx = False # сдвинуть передатчик

    # залочка шторок
    if application.split_lockrx and application.split_locktx:
      return
    if application.split_lockrx:
      self.mouse_is_rx = False
    if application.split_locktx:
      self.mouse_is_rx = True

    # двигать приёмник
    if self.mouse_is_rx:
      freq = application.rxFreq + self.VFO + wm * event.GetWheelRotation() // event.GetWheelDelta()
      if conf.freq_spacing:
        freq = self.FreqRound(freq, 0)
      elif freq >= 0:
        freq = freq // wm * wm
      else:		# freq can be negative when the VFO is zero
        freq = - (- freq // wm * wm)
      tune = freq - self.VFO
      self.ChangeHwFrequency(self.txFreq, self.VFO, 'MouseWheel', event=event, rx_freq=tune)
      # ----------------------------------------------------------------------------------- добавлено -------- кнопки f_Before и f_After --------- 51 RA3PKJ
      application.f_after_1 = self.txFreq
      application.f_after_2 = self.VFO
    # двигать передатчик
    else:
      freq = self.txFreq + self.VFO + wm * event.GetWheelRotation() // event.GetWheelDelta()
      if conf.freq_spacing:
        freq = self.FreqRound(freq, 0)
      elif freq >= 0:
        freq = freq // wm * wm
      else:		# freq can be negative when the VFO is zero
        freq = - (- freq // wm * wm)
      tune = freq - self.VFO
      self.ChangeHwFrequency(tune, self.VFO, 'MouseWheel', event=event)
      # ----------------------------------------------------------------------------------- добавлено -------- кнопки f_Before и f_After --------- 51 RA3PKJ
      application.f_after_1 = tune
      application.f_after_2 = self.VFO
    application.beforeButton.Enable(1)
    application.afterButton.Enable(0)

    self.mouse_is_rx = False # привести в исходное

  def ChangeHwFrequency(self, tune, vfo, source='', band='', event=None, rx_freq=None):
    application.ChangeHwFrequency(tune, vfo, source, band, event, rx_freq)
  def PeakHold(self, name):
    if name in ('GraphP1', 'WFallP1'):
      self.display.peak_hold = int(self.display.scale * conf.graph_peak_hold_1)
    elif name in ('GraphP2', 'WFallP2'):
      self.display.peak_hold = int(self.display.scale * conf.graph_peak_hold_2)
    else:
      self.display.peak_hold = 9999
    if self.display.peak_hold < 1:
      self.display.peak_hold = 1

class StationScreen(wx.Window):		# This code was contributed by Christof, DJ4CM.  Many Thanks!! Edited May 2022.
  """Create a window below the graph X axis to display interesting frequencies."""
  def __init__(self, parent, width, lines):
    self.lineMargin = 2
    self.lines = lines
    self.mouse_x = 0
    self.stationList = []
    graph = self.graph = application.graph
    height = lines * (graph.GetCharHeight() + self.lineMargin)	# The height may be zero
    wx.Window.__init__(self, parent, size=(graph.width, height), style = wx.NO_BORDER)
    self.font = wx.Font(conf.graph_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    self.SetFont(self.font)
    self.SetBackgroundColour(conf.color_graph)
    self.width = application.screen_width
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    if lines:
      self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
      self.Bind(wx.EVT_MOTION, self.OnMotion)
      self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeaveWindow)
      # handle station info
      self.stationWindow = wx.PopupWindow (parent)
      self.stationInfo = wx.TextCtrl(self.stationWindow, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.TE_NO_VSCROLL)
      self.stationInfo.SetFont(wx.Font(conf.status_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface))
      self.stationWindow.Hide();
      self.firstStationInRange = None
      self.lastStationX = 0
      self.nrStationInRange = 0
      self.tunedStation = 0
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    if not self.lines:
      return
    dc.SetFont(self.font)
    graph = self.graph
    dc.SetTextForeground(conf.color_graphlabels)
    dc.SetPen(graph.pen_tick)
    originX = graph.originX
    originY = graph.originY
    endX = originX + graph.graph_width    # end of fft data
    sample_rate = int(graph.sample_rate * graph.zoom)
    VFO = graph.VFO + graph.zoom_deltaf
    hl = self.GetCharHeight()
    y = 0
    for i in range (self.lines):
      dc.DrawLine(originX, y, endX, y)
      y += hl + self.lineMargin
    # create a sorted list of favorites in the frequency range
    freq1 = VFO - sample_rate // 2
    freq2 = VFO + sample_rate // 2
    self.stationList = []
    fav = application.config_screen.favorites
    for row in range (fav.GetNumberRows()):
      fav_f = fav.GetCellValue(row, 1)
      if fav_f:
        try:
          fav_f = str2freq(fav_f)
          if freq1 < fav_f < freq2:
            self.stationList.append((fav_f, conf.Xsym_stat_fav, fav.GetCellValue(row, 0),
                fav.GetCellValue(row, 2), fav.GetCellValue(row, 3)))
        except ValueError:
          pass
    # add memory stations
    for mem_f, mem_band, mem_vfo, mem_txfreq, mem_mode in application.memoryState:
      if freq1 < mem_f < freq2:
        self.stationList.append((mem_f, conf.Xsym_stat_mem, '', mem_mode, ''))
    #add dx spots
    if application.dxCluster:
      for entry in application.dxCluster.dxSpots:
        if freq1 < entry.getFreq() < freq2:
          for i in range (0, entry.getLen()):
            descr = entry.getSpotter(i) + '\t' + entry.getTime(i) + '\t' + entry.getLocation(i) + '\n' + entry.getComment(i)
            if i < entry.getLen()-1:
              descr += '\n'
          self.stationList.append((entry.freq, conf.Xsym_stat_dx, entry.dx, '', descr))
    # draw stations on graph
    self.stationList.sort()
    lastX = []
    line = 0
    for i in range (0, self.lines):
      lastX.append(graph.width)
    for statFreq, symbol, statName, statMode, statDscr in reversed (self.stationList):
      ws = dc.GetTextExtent(symbol)[0]
      statX = graph.x0 + int(float(statFreq - VFO) / sample_rate * graph.data_width)
      w, h = dc.GetTextExtent(statName)
      # shorten name until it fits into remaining space
      maxLen = 25
      tName = statName
      while (w > lastX[line] - statX - ws - 4) and maxLen > 0:
        maxLen -= 1
        tName = statName[:maxLen] + '..'
        w, h = dc.GetTextExtent(tName)
      dc.DrawLine(statX, line * (hl+self.lineMargin), statX, line * (hl+self.lineMargin) + 4)
      dc.DrawText(symbol + ' ' + tName, statX - ws//2, line * (hl+self.lineMargin) + self.lineMargin//2+1)
      lastX[line] = statX
      line = (line+1)%self.lines
  def OnLeftDown(self, event):
    if self.firstStationInRange != None:
      # tune to station
      if self.tunedStation >= self.nrStationInRange:
        self.tunedStation = 0
      freq, symbol, name, mode, dscr = self.stationList[self.firstStationInRange+self.tunedStation]
      self.tunedStation += 1
      if mode != '': # information about mode available
        mode = mode.upper()
        application.modeButns.SetLabel(mode, True)
      application.ChangeRxTxFrequency(None, freq)
  def OnMotion(self, event):
    mouse_x, mouse_y = event.GetPosition()
    x = (mouse_x - self.mouse_x)
    application.isTuning = False
    # show detailed station info
    if abs(self.lastStationX - mouse_x) > 30:
      self.firstStationInRange = None
    found = False
    graph = self.graph
    sample_rate = int(graph.sample_rate * graph.zoom)
    VFO = graph.VFO + graph.zoom_deltaf
    if abs(x) > 5: # ignore small mouse moves
      for index in range (0, len(self.stationList)):
        statFreq, symbol, statName, statMode, statDscr = self.stationList[index]
        statX = graph.x0 + int(float(statFreq - VFO) / sample_rate * graph.data_width)
        if abs(mouse_x-statX) < 10:
          self.lastStationX = mouse_x
          if found == False:
            self.firstStationInRange = index
            self.firstStationX = statX
            self.nrStationInRange = 0
            self.stationInfo.Clear()
            found = True
          self.nrStationInRange += 1
          t = " %s  %s" % (symbol, statName)
          width, height = self.stationInfo.GetTextExtent(t)
          txt = t
          t = " %s Hz   %s" % (FreqFormatter(statFreq), statMode)
          w, h = self.stationInfo.GetTextExtent(t)
          width = max(width, w)
          height += h
          txt += '\n'
          txt += t
          if len(statDscr) > 0:
            t = " %s" % statDscr
            w, h = self.stationInfo.GetTextExtent(t)
            width = max(width, w)
            height += h
            txt += '\n'
            txt += t
          self.stationInfo.write(txt)
          width += self.stationInfo.GetCharWidth() * 3
          height += self.stationInfo.GetCharHeight() // 2
          self.stationInfo.SetSize(wx.Size(width, height))
          self.stationWindow.SetClientSize((width, height))
          self.mouse_x = mouse_x
    if self.firstStationInRange != None:
      w, h = self.stationInfo.GetSize()
      # convert coordinates to screen
      rect = self.GetScreenRect()
      self.stationWindow.Move(self.firstStationX, rect.GetY() - h)
      if not self.stationWindow.IsShown():
        self.stationWindow.Show()
    else:
      self.stationWindow.Hide()
  def OnLeaveWindow(self, event):
    self.stationWindow.Hide()


class WaterfallDisplay(wx.Window):
  """Create a waterfall display within the waterfall screen."""
  def __init__(self, parent, x, y, graph_width, height, margin):
    wx.Window.__init__(self, parent,
       pos = (x, y),
       size = (graph_width, height),
       style = wx.NO_BORDER)
    self.parent = parent
    self.graph_width = graph_width
    self.margin = margin
    self.height = 10
    self.zoom = 1.0
    self.zoom_deltaf = 0
    self.rf_gain = 0 # Keep waterfall colors constant for variable RF gain ----------- бесполезная переменная

    # ------------------------------------------------------------------------------------------- добавлено ------ автоматика водопада ------ 24 RA3PKJ
    self.bright_const = -110.0	# уровень нормальной шумовой дорожки
    self.bright = 0
    self.contrast = 0
    # ------------------------------------------------------------------------------------------- добавлено --------- выбор водопада -------- 25 RA3PKJ
    self.current_pal = ''

    self.sample_rate = application.sample_rate
    self.SetBackgroundColour('Black')
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_LEFT_DOWN, parent.OnLeftDown)
    self.Bind(wx.EVT_RIGHT_DOWN, parent.OnRightDown)
    self.Bind(wx.EVT_LEFT_UP, parent.OnLeftUp)
    self.Bind(wx.EVT_MOTION, parent.OnMotion)
    self.Bind(wx.EVT_MOUSEWHEEL, parent.OnWheel)
    self.tune_tx = graph_width // 2	# Current X position of the Tx tuning line
    self.tune_rx = 0				# Current X position of Rx tuning line or zero
    self.marginPen = wx.Pen(conf.color_graph, 1)
    #self.tuningPen = wx.Pen('White', 3)
    self.tuningPen = wx.Pen('#82B3C8', 1) # цвет и ширина вертикальной линии на водопаде ---------------------------- взамен -- оформление панорамы -- 4 RA3PKJ
    #self.tuningPenTx = wx.Pen(conf.color_txline, 3)
    self.tuningPenTx = wx.Pen(conf.color_txline, 2) # цвет и ширина вертикального тонкого огрызка на водопаде (TX) -- взамен -- оформление панорамы -- 4 RA3PKJ
    #self.tuningPenRx = wx.Pen(conf.color_rxline, 3)
    self.tuningPenRx = wx.Pen(conf.color_rxline, 2) # цвет и ширина вертикального тонкого огрызка на водопаде (RX) -- взамен -- оформление панорамы -- 4 RA3PKJ
    #self.filterBrush = wx.Brush(conf.color_bandwidth, wx.SOLID)
    self.filterBrush = wx.Brush('#009999', wx.SOLID) # цвет шторки -------------------------------------------------- взамен -- оформление панорамы -- 4 RA3PKJ
    # Size of top faster scroll region is (top_key + 2) * (top_key - 1) // 2
    self.top_key = 8
    self.top_size = (self.top_key + 2) * (self.top_key - 1) // 2

    # ------------------------------------------------------------------------------------------- добавлено --------- выбор водопада -------- 25 RA3PKJ
    self.settings_changed = False
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    self.MakePalette(conf.waterfall_palette)
    self.current_pal = conf.waterfall_palette

    # --------------------------------------------------------------------------------------------- удалено --------- выбор водопада -------- 25 RA3PKJ
    # Make the palette
    #if conf.waterfall_palette == 'B':
      #pal2 = conf.waterfallPaletteB
    #elif conf.waterfall_palette == 'C':
      #pal2 = conf.waterfallPaletteC
    #else:
      #pal2 = conf.waterfallPalette
    #red = bytearray(256)
    #green = bytearray(256)
    #blue = bytearray(256)
    #n = 0
    #for i in range(256):
      #if i > pal2[n+1][0]:
         #n = n + 1
      #red[i]   = (i - pal2[n][0]) * (pal2[n+1][1] - pal2[n][1]) // (pal2[n+1][0] - pal2[n][0]) + pal2[n][1]
      #green[i] = (i - pal2[n][0]) * (pal2[n+1][2] - pal2[n][2]) // (pal2[n+1][0] - pal2[n][0]) + pal2[n][2]
      #blue[i]  = (i - pal2[n][0]) * (pal2[n+1][3] - pal2[n][3]) // (pal2[n+1][0] - pal2[n][0]) + pal2[n][3]
    #self.rgb_data = QS.watfall_RgbData(red, green, blue, self.graph_width, application.screen_height)
    #self.pixels = bytearray(self.graph_width * application.screen_height * 3)

  # ------------------------------------------------------------------------------- добавлена функция взамен --------- выбор водопада -------- 25 RA3PKJ
  def MakePalette(self, pal_type):
    if pal_type == 'B':
      pal2 = conf.waterfallPaletteB
      self.bright = 83
      self.contrast = 80
    elif pal_type == 'C':
      pal2 = conf.waterfallPaletteC
      self.bright = 93
      self.contrast = 95
    else:
      pal2 = conf.waterfallPalette
      self.bright = 78
      self.contrast = 65
    red = bytearray(256)
    green = bytearray(256)
    blue = bytearray(256)
    n = 0
    for i in range(256):
      if i > pal2[n+1][0]:
         n = n + 1
      red[i]   = (i - pal2[n][0]) * (pal2[n+1][1] - pal2[n][1]) // (pal2[n+1][0] - pal2[n][0]) + pal2[n][1]
      green[i] = (i - pal2[n][0]) * (pal2[n+1][2] - pal2[n][2]) // (pal2[n+1][0] - pal2[n][0]) + pal2[n][2]
      blue[i]  = (i - pal2[n][0]) * (pal2[n+1][3] - pal2[n][3]) // (pal2[n+1][0] - pal2[n][0]) + pal2[n][3]
    self.rgb_data = QS.watfall_RgbData(red, green, blue, self.graph_width, application.screen_height)
    self.pixels = bytearray(self.graph_width * application.screen_height * 3)

  # ----------------------------------------------------------------------------- добавлено -------------------------------- выбор водопада -------- 25 RA3PKJ
  def ChangePalette(self):
    if self.current_pal == 'A': self.current_pal  = 'B'
    elif self.current_pal == 'B': self.current_pal  = 'C'
    else: self.current_pal = 'A'

    index = configure.Settings[2].index(configure.Settings[1]) # -------- найти индекс текущего радио в списке радио
    configure.Settings[3][index]["waterfall_palette"] = self.current_pal
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False
    self.MakePalette(self.current_pal)

  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    dc.SetTextForeground(conf.color_graphlabels)
    dc.SetBackground(wx.Brush('Black'))
    rit = self.DrawFilter(dc)
    dc.SetLogicalFunction(wx.COPY)
    sample_rate = int(self.sample_rate * self.zoom)
    x_origin = int(float(self.VFO) / sample_rate * self.data_width + 0.5)
    width = self.graph_width
    height = self.height - self.margin
    if height <= 0:
      height = 1
    QS.watfall_GetPixels(self.rgb_data, self.pixels, x_origin, width, height)
    if wxVersion in ('2', '3'):
      bmap = wx.BitmapFromBuffer(width, height, self.pixels)
    else:
      bmap = wx.Bitmap.FromBuffer(width, height, self.pixels)
    dc.DrawBitmap(bmap, 0, self.margin)
    dc.SetPen(self.tuningPen)
    dc.SetLogicalFunction(wx.XOR)
    dc.DrawLine(self.tune_tx, self.margin, self.tune_tx, self.height)
    if self.tune_rx:
      dc.DrawLine(self.tune_rx, self.margin, self.tune_rx, self.height)
  def SetHeight(self, height):
    self.height = height
    self.SetSize((self.graph_width, height))
  def DrawFilter(self, dc):
    # Erase area at the top of the waterfall
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.SetLogicalFunction(wx.COPY)
    dc.SetBrush(self.parent.backgroundBrush)
    dc.DrawRectangle(0, 0, self.graph_width, self.margin)
    # Draw the filter and top tuning lines
    scale = 1.0 / self.zoom / self.sample_rate * self.data_width
    dc.SetBrush(self.filterBrush)
    if self.tune_rx:
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=False)
      dc.DrawRectangle(self.tune_tx + x, 0, w, self.margin)
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=True)
      dc.DrawRectangle(self.tune_rx + rit + x, 0, w, self.margin)
      dc.SetPen(self.tuningPenRx)
      dc.DrawLine(self.tune_rx, 0, self.tune_rx, self.margin)
    else:
      x, w, rit = self.parent.GetFilterDisplayXWR(rx_filters=True)
      dc.DrawRectangle(self.tune_tx + rit + x, 0, w, self.margin)
    dc.SetPen(self.tuningPenTx)
    dc.DrawLine(self.tune_tx, 0, self.tune_tx, self.margin)
    return rit

# ----------------------------------------------------------------------------------------------- удалено ------ автоматика водопада ------- 24 RA3PKJ
  #def OnGraphData(self, data, y_zero, y_scale):
# y_scale and y_zero range from zero to 160.
# y_zero controls the center position of the colors. Set to a bit over the noise level.
# y_scale controls how much the colors change when the sample deviates from y_zero.
    #gain = self.rf_gain
    #sample_rate = int(self.sample_rate * self.zoom)
    #x_origin = int(float(self.VFO) / sample_rate * self.data_width + 0.5)
    #QS.watfall_OnGraphData(self.rgb_data, data, y_zero, y_scale, gain, x_origin)
    #self.Refresh(False)

# ------------------------------------------------------------------------------------------------- взамен ------ автоматика водопада ------- 24 RA3PKJ
  def OnGraphData(self, data, y_zero, y_scale):
# y_scale and y_zero range from zero to 160.
# y_zero controls the center position of the colors. Set to a bit over the noise level.
# y_scale controls how much the colors change when the sample deviates from y_zero.
    gain = self.rf_gain
    sample_rate = int(self.sample_rate * self.zoom)
    x_origin = int(float(self.VFO) / sample_rate * self.data_width + 0.5)

    # отрезать крайние провалы, чтобы при нахождении персентайла не возникала ошибка, когда шторка стоит на провале и далее следует зуммирование
    l_s = len(data) // 10              # отрезка левого провала
    l_f = len(data) - len(data) // 10  # отрезка правого провала
    mn = data[l_s:l_f]
    percent_min  = np.percentile(mn,4) # находим максимальное значение из минимальных значений при 4-х процентной выборке из массива входных данных

    data_m = array.array('f', []) # будем заполнять массив из массива data путём сдвига уровней с целью привязки к константе self.bright_const
    if percent_min > self.bright_const:
      rf_corr = percent_min - self.bright_const # вычислить необходимый сдвиг
      for x in data:
        x = x - rf_corr
        data_m.append (x)
    elif percent_min < self.bright_const:
      rf_corr = self.bright_const - percent_min # вычислить необходимый сдвиг
      for x in data:
        x = x + rf_corr
        data_m.append (x)
    else:
      data_m = data

    QS.watfall_OnGraphData(self.rgb_data, data_m, self.bright, self.contrast, gain, x_origin)
    self.Refresh(False)

  def SetTuningLine(self, tune_tx, tune_rx):
    dc = wx.ClientDC(self)
    rit = self.DrawFilter(dc)
    dc.SetPen(self.tuningPen)
    dc.SetLogicalFunction(wx.XOR)
    dc.DrawLine(self.tune_tx, self.margin, self.tune_tx, self.height)
    if self.tune_rx:
      dc.DrawLine(self.tune_rx, self.margin, self.tune_rx, self.height)
      dc.DrawLine(tune_rx, self.margin, tune_rx, self.height)
    dc.DrawLine(tune_tx, self.margin, tune_tx, self.height)
    self.tune_tx = tune_tx
    self.tune_rx = tune_rx
  def ChangeZoom(self, zoom, deltaf, zoom_control):
    self.zoom = zoom
    self.zoom_deltaf = deltaf
    self.zoom_control = zoom_control

class WaterfallScreen(wx.SplitterWindow):
  """Create a splitter window with a graph screen and a waterfall screen"""
  def __init__(self, frame, width, data_width, graph_width):
    self.y_scale = conf.waterfall_y_scale
    self.y_zero = conf.waterfall_y_zero
    self.zoom_control = 0
    wx.SplitterWindow.__init__(self, frame)
    self.SetSizeHints(width, -1, width)
    self.SetSashGravity(0.50)
    self.SetMinimumPaneSize(1)
    self.SetSize((width, conf.waterfall_graph_size + 100))	# be able to set sash size
    self.pane1 = GraphScreen(self, data_width, graph_width, 1)
    self.pane2 = WaterfallPane(self, data_width, graph_width)
    self.SplitHorizontally(self.pane1, self.pane2, conf.waterfall_graph_size)
  def SetDisplayMsg(self, text=''):
    self.pane1.SetDisplayMsg(text)
  def ScrollMsg(self, char):	# Add a character to a scrolling message
    self.pane1.ScrollMsg(char)
  def OnIdle(self, event):
    self.pane1.OnIdle(event)
    self.pane2.OnIdle(event)
  def SetTxFreq(self, tx_freq, rx_freq):
    self.pane1.SetTxFreq(tx_freq, rx_freq)
    self.pane2.SetTxFreq(tx_freq, rx_freq)
  def SetVFO(self, vfo):
    self.pane1.SetVFO(vfo)
    self.pane2.SetVFO(vfo)

  def ChangeYscale(self, y_scale):		# Test if the shift key is down
    # --------------------------------------------------------------------------- удалено ------------ перевод слайдеров на график --------------- 26 RA3PKJ
    #if wx.GetKeyState(wx.WXK_SHIFT):	# Set graph screen
      #self.pane1.ChangeYscale(y_scale)
    #else:			# Set waterfall screen
      #self.y_scale = y_scale
      #self.pane2.ChangeYscale(y_scale)
    # --------------------------------------------------------------------------- взамен -------------- перевод слайдеров на график -------------- 26 RA3PKJ
    self.y_scale = y_scale # способствует запоминанию положения слайдера
    self.pane1.ChangeYscale(y_scale)
  def ChangeYzero(self, y_zero):		# Test if the shift key is down
    # --------------------------------------------------------------------------- удалено ------------- перевод слайдеров на график -------------- 26 RA3PKJ
    #if wx.GetKeyState(wx.WXK_SHIFT):	# Set graph screen
      #self.pane1.ChangeYzero(y_zero)
    #else:			# Set waterfall screen
      #self.y_zero = y_zero
      #self.pane2.ChangeYzero(y_zero)
    # --------------------------------------------------------------------------- взамен -------------- перевод слайдеров на график -------------- 26 RA3PKJ
    self.y_zero = y_zero # способствует запоминанию положения слайдера
    self.pane1.ChangeYzero(y_zero)

  def SetPane1(self, ysz):
    y_scale, y_zero = ysz
    self.pane1.ChangeYscale(y_scale)
    self.pane1.ChangeYzero(y_zero)
  def SetPane2(self, ysz):
    y_scale, y_zero = ysz
    self.y_scale = y_scale
    self.pane2.ChangeYscale(y_scale)
    self.y_zero = y_zero
    self.pane2.ChangeYzero(y_zero)
  def OnGraphData(self, data):
    self.pane1.OnGraphData(data)
    self.pane2.OnGraphData(data)
  def ChangeRfGain(self, gain):		# Set the correction for RF gain
    self.pane2.display.rf_gain = gain
  def ChangeZoom(self, zoom, deltaf, zoom_control):
    self.zoom_control = zoom_control
    self.pane1.ChangeZoom(zoom, deltaf, zoom_control)
    self.pane2.ChangeZoom(zoom, deltaf, zoom_control)
    self.pane2.display.ChangeZoom(zoom, deltaf, zoom_control)
  def PeakHold(self, name):
    self.pane1.PeakHold(name)
  # --------------------------------------------------------------------------- добавлено --------------------- выбор водопада -------------------- 25 RA3PKJ
  def ChangePalette(self):
    self.pane2.ChangePalette()

class WaterfallPane(GraphScreen):
  """Create a waterfall screen with an X axis and a waterfall display."""
  def __init__(self, frame, data_width, graph_width):
    GraphScreen.__init__(self, frame, data_width, graph_width)
    self.y_scale = conf.waterfall_y_scale
    self.y_zero = conf.waterfall_y_zero
    self.zoom_control = 0
    self.oldVFO = self.VFO
    self.filter_mode = 'AM'
    self.filter_bandwidth = 0
    self.filter_center = 0
    self.ritFreq = 0				# receive incremental tuning frequency offset
  def MakeDisplay(self):
    self.display = WaterfallDisplay(self, self.originX, 0, self.graph_width, 5, self.chary)
    self.display.VFO = self.VFO
    self.display.data_width = self.data_width
  def SetVFO(self, vfo):
    GraphScreen.SetVFO(self, vfo)
    self.display.VFO = vfo
    if self.oldVFO != vfo:
      self.oldVFO = vfo
      self.Refresh()
  def MakeYTicks(self, dc):
    pass
  def ChangeYscale(self, y_scale):
    self.y_scale = y_scale
  def ChangeYzero(self, y_zero):
    self.y_zero = y_zero
  def OnGraphData(self, data):
    i1 = (self.data_width - self.graph_width) // 2
    i2 = i1 + self.graph_width
    self.raw_graph_data = data[i1:i2]
    self.display.OnGraphData(data[i1:i2], self.y_zero, self.y_scale)
  # ------------------------------------------------------------- добавлено ------------------------------ выбор водопада ---------------------- 25 RA3PKJ
  def ChangePalette(self):
    self.display.ChangePalette()

class MultiRxGraph(GraphScreen):
  # The screen showing each added receiver
  the_modes = ('CWL', 'CWU', 'LSB', 'USB', 'AM', 'FM', 'DGT-U', 'DGT-L', 'DGT-FM', 'DGT-IQ')
  def __init__(self, parent, data_width, graph_width, index):
    multi_rx = application.multi_rx_screen
    width = multi_rx.rx_data_width
    GraphScreen.__init__(self, parent, width, width)
    self.graph_display = self.display
    self.waterfall_display = WaterfallDisplay(self, self.originX, 0, self.graph_width, 5, self.chary)
    self.waterfall_display.Hide()
    self.waterfall_display.VFO = self.VFO
    self.waterfall_display.data_width = self.data_width
    self.waterfall_y_scale = conf.waterfall_y_scale
    self.waterfall_y_zero = conf.waterfall_y_zero
    # self.split_unavailable = True # -------------------------- удалено ----------------------- реформа мышиного управления шторками ---------- 13 RA3PKJ
    width = self.originX + self.graph_width
    self.tabX = width + (multi_rx.graph.width - width - multi_rx.rx_btn_width) // 2
    self.popupX = self.tabX - multi_rx.rx_btn_width * 2
    self.multirx_index = index
    self.is_playing = False
    self.mode_index = 0
    self.band = '40'
    # Create controls
    posY = 0
    half_width = multi_rx.rx_btn_width // 2
    half_size = half_width, multi_rx.rx_btn_height
    self.rx_btn = QuiskPushbutton(self, self.OnPopButton, "Rx %d .." % (index + 1))
    self.rx_btn.SetSize(half_size)
    self.rx_btn.SetPosition((self.tabX, posY))
    self.play_btn = QuiskCheckbutton(self, self.OnPlayButton, "Play")
    self.play_btn.SetSize(half_size)
    self.play_btn.SetPosition((self.tabX + half_width, posY))
    posY += multi_rx.rx_btn_height
    btn1 = QuiskPushbutton(self, self.OnBtnDownBand, conf.Xbtn_text_range_dn, use_right=True)
    btn2 = QuiskPushbutton(self, self.OnBtnUpBand, conf.Xbtn_text_range_up, use_right=True)
    btn1.SetSize(half_size)
    btn2.SetSize(half_size)
    btn1.SetPosition((self.tabX, posY))
    btn2.SetPosition((self.tabX + half_width, posY))
    posY += multi_rx.rx_btn_height
    self.sliderYs = SliderBoxV(self, 'Ys', self.y_scale, 160, self.OnChangeYscale, True)
    self.sliderYz = SliderBoxV(self, 'Yz', self.y_zero, 160, self.OnChangeYzero, True)
    x = self.tabX + (half_width * 2 - self.sliderYs.width - self.sliderYz.width) // 2
    self.sliderYs.SetDimension(x, posY, self.sliderYs.width, 100)
    x += self.sliderYs.width
    self.sliderYz.SetDimension(x, posY, self.sliderYz.width, 100)
    # Create menu
    self.multi_rx_menu = wx.Menu()
    item = self.multi_rx_menu.Append(-1, 'Show graph')
    self.Bind(wx.EVT_MENU, self.OnShowGraph, item)
    item = self.multi_rx_menu.Append(-1, 'Show waterfall')
    self.Bind(wx.EVT_MENU, self.OnShowWaterfall, item)
    self.multi_rx_menu.AppendSeparator()
    menu = wx.Menu()
    self.multi_rx_menu.AppendSubMenu(menu, "Band")
    for band in conf.bandLabels:
      if not isinstance(band, Q3StringTypes):
        band = band[0]
        if band == 'Time':
          continue
      item = menu.Append(-1, band)
      self.Bind(wx.EVT_MENU, self.OnChangeBand, item)
    self.mode_menu = wx.Menu()
    self.multi_rx_menu.AppendSubMenu(self.mode_menu, "Mode")
    for mode in self.the_modes:
      item = self.mode_menu.AppendRadioItem(-1, mode)
      self.Bind(wx.EVT_MENU, self.OnChangeMode, item)
    self.filter_menu = wx.Menu()
    self.multi_rx_menu.AppendSubMenu(self.filter_menu, "Filter")
    for i in range(6):
      item = self.filter_menu.AppendRadioItem(-1, '0')
      self.Bind(wx.EVT_MENU, self.OnChangeFilter, item)
    self.multi_rx_menu.AppendSeparator()
    item = self.multi_rx_menu.Append(-1, 'Delete receiver')
    self.Bind(wx.EVT_MENU, self.OnDeleteReceiver, item)
    self.ChangeBand(application.lastBand)
    if multi_rx.rx_zero == multi_rx.waterfall:
      self.OnShowWaterfall()
  def ResizeGraph(self):
    GraphScreen.ResizeGraph(self)
    w, h = self.GetClientSize()
    x, y = self.sliderYs.GetPosition()
    height = max(h - y, self.sliderYs.text_height * 2)
    self.sliderYs.SetDimension(x, y, self.sliderYs.width, height)
    x, y = self.sliderYz.GetPosition()
    self.sliderYz.SetDimension(x, y, self.sliderYz.width, height)
  def MakeYTicks(self, dc):
    if self.display == self.graph_display:
      GraphScreen.MakeYTicks(self, dc)
  def OnPopButton(self, event):
    pos = (self.popupX, 10)
    self.PopupMenu(self.multi_rx_menu, pos)
  def OnDeleteReceiver(self, event):
    if self.is_playing:
      QS.set_multirx_play_channel(-1)
    application.multi_rx_screen.DeleteReceiver(self)
  def OnShowGraph(self, event):
    self.waterfall_display.Hide()
    self.display = self.graph_display
    self.SetTxFreq(self.txFreq, self.txFreq)
    self.sliderYs.SetValue(self.y_scale)
    self.sliderYz.SetValue(self.y_zero)
    self.display.Show()
    self.doResize = True
  def OnShowWaterfall(self, event=None):
    self.graph_display.Hide()
    self.display = self.waterfall_display
    self.SetTxFreq(self.txFreq, self.txFreq)
    self.sliderYs.SetValue(self.waterfall_y_scale)
    self.sliderYz.SetValue(self.waterfall_y_zero)
    self.display.Show()
    self.doResize = True
  def OnGraphData(self, data):
    self.raw_graph_data = data
    if self.display == self.graph_display:
      self.display.OnGraphData(data)
    else:
      self.display.OnGraphData(data, self.waterfall_y_zero, self.waterfall_y_scale)
  def OnPlayButton(self, event):
    application.multi_rx_screen.StopPlaying(self)
    self.is_playing = event.GetEventObject().GetValue()
    if self.is_playing:
      QS.set_filters(self.filter_I, self.filter_Q, self.filter_bandwidth, 0, 1)
      QS.set_multirx_play_channel(self.multirx_index)
    else:
      QS.set_multirx_play_channel(-1)
  def SetVFO(self, vfo):
    GraphScreen.SetVFO(self, vfo)
    self.waterfall_display.VFO = self.VFO
    self.waterfall_display.Refresh()
  def OnChangeBand(self, event):
    idd = event.GetId()
    band = event.GetEventObject().GetLabel(idd)
    self.ChangeBand(band)
  def OnChangeMode(self, event=None):
    if event is None:
      try:
        idx = self.the_modes.index(self.mode)
      except ValueError:
        self.mode = 'USB'
        idx = self.the_modes.index(self.mode)
      self.mode_menu.FindItemByPosition(idx).Check(True)
    else:
      idd = event.GetId()
      self.mode = event.GetEventObject().GetLabel(idd)
    bws = application.Mode2Filters(self.mode)
    self.mode_index = Mode2Index.get(self.mode, 3)
    QS.set_multirx_mode(self.multirx_index, self.mode_index)
    for i in range(6):
      item = self.filter_menu.FindItemByPosition(i)
      item.SetItemLabel(str(bws[i]))
      if i == 2:
        item.Check(True)
    self.filter_bandwidth = bws[2]
    self.OnChangeFilter()
  def OnChangeFilter(self, event=None):
    if event is not None:
      idd = event.GetId()
      self.filter_bandwidth = int(event.GetEventObject().GetLabel(idd))
    center = application.GetFilterCenter(self.mode, self.filter_bandwidth)
    frate = QS.get_filter_rate(Mode2Index.get(self.mode, 3), self.filter_bandwidth)
    self.filter_I, self.filter_Q = application.MakeFilterCoef(frate, None, self.filter_bandwidth, center)
    if self.is_playing:
      QS.set_filters(self.filter_I, self.filter_Q, self.filter_bandwidth, 0, 1)	# filter for receiver that is playing sound
    if self.multirx_index == 0:
      QS.set_filters(self.filter_I, self.filter_Q, self.filter_bandwidth, 0, 2)	# filter for digital mode output to sound device
    self.filter_mode = self.mode
    self.filter_center = center
  def ChangeBand(self, band):
    self.band = band
    try:
      vfo, tune, self.mode = application.bandState[band]
      #print (vfo, tune, self.mode)
    except:
      try:
        f1, f2 = conf.BandEdge[band]
      except KeyError:
        f1, f2 = 10000000, 12000000
      vfo = (f1 + f2) // 2
      vfo = vfo // 10000
      vfo *= 10000
      if vfo < 9000000:
        self.mode = 'LSB'
      else:
        self.mode = 'USB'
      tune = 0
    self.OnChangeMode()
    self.ChangeHwFrequency(tune, vfo, 'ChangeBand')
    if hasattr(application.Hardware, "ChangeBandFilters"):
      application.Hardware.ChangeBandFilters()
  def OnBtnDownBand(self, event):
    self.OnBtnUpBand(event, True)
  def OnBtnUpBand(self, event, is_band_down=False):
    sample_rate = application.sample_rate
    btn = event.GetEventObject()
    oldvfo = self.VFO
    if btn.direction > 0:		# left button was used, move a bit
      d = int(sample_rate // 9)
    else:						# right button was used, move to edge
      d = int(sample_rate * 45 // 100)
    if is_band_down:
      d = -d
    vfo = self.VFO + d
    if sample_rate > 40000:
      vfo = (vfo + 5000) // 10000 * 10000	# round to even number
      delta = 10000
    elif sample_rate > 5000:
      vfo = (vfo + 500) // 1000 * 1000
      delta = 1000
    else:
      vfo = (vfo + 50) // 100 * 100
      delta = 100
    if oldvfo == vfo:
      if is_band_down:
        d = -delta
      else:
        d = delta
    else:
      d = vfo - oldvfo
    self.ChangeHwFrequency(self.txFreq - d, self.VFO + d, 'BandUpDown', event=event)
  def OnChangeYscale(self, event):
    y_scale = self.sliderYs.GetValue()
    if self.display == self.graph_display:
      self.ChangeYscale(y_scale)
    else:
      self.waterfall_y_scale = y_scale
  def OnChangeYzero(self, event):
    y_zero = self.sliderYz.GetValue()
    if self.display == self.graph_display:
      self.ChangeYzero(y_zero)
    else:
      self.waterfall_y_zero = y_zero
  def ChangeHwFrequency(self, tune, vfo, source='', band='', event=None, rx_freq=None):
    #print ("Quisk", self.multirx_index, self.VFO, vfo, self.band)
    self.SetTxFreq(tune, tune)
    if self.VFO != vfo:
      self.SetVFO(vfo)
      Hardware.MultiRxFrequency(self.multirx_index, vfo, self.band)
    QS.set_multirx_freq(self.multirx_index, tune)
  def ChangeRxTxFrequency(self, freq):
    tune = freq - self.VFO
    d = self.sample_rate * 45 // 100
    if -d <= tune <= d:	# Frequency is on-screen
      vfo = self.VFO
    else:					# Change the VFO
      vfo = (freq // 5000) * 5000 - 5000
      tune = freq - vfo
    self.ChangeHwFrequency(tune, vfo, 'FreqEntry')

class MultiReceiverScreen(wx.SplitterWindow):
  # The top level screen showing a graph, waterfall and any additional receivers.
  # The first receiver is zero; additional receivers are in self.receiver_list[]
  def __init__(self, frame, data_width, graph_width):
    application.multi_rx_screen = self		# prevent phase error
    self.data_width = data_width
    self.graph_width = graph_width
    wx.SplitterWindow.__init__(self, frame)
    self.SetSashGravity(0.50)
    self.receiver_list = []
    self.graph = GraphScreen(self, data_width, graph_width)
    self.width = self.graph.width
    self.waterfall = WaterfallScreen(self, self.width, data_width, graph_width)
    self.rx_zero = self.graph
    self.Initialize(self.rx_zero)
    self.waterfall.Hide()
    self.SetSizeHints(self.width, -1, self.width)
    # Calculate control width
    rx_btn = QuiskPushbutton(self, None, "Rx 8....", style=wx.BU_EXACTFIT)
    self.rx_btn_width, self.rx_btn_height = rx_btn.GetSize().Get()
    self.rx_btn_width *= 2
    rx_btn.Destroy()
    del rx_btn
    self.SetMinimumPaneSize(self.rx_btn_height)
    self.rx_btn_border = 5
    width = data_width - self.rx_btn_width - self.rx_btn_border * 2
    self.rx_data_width = fftPreferedSizes[0]
    for x in fftPreferedSizes:
      if x >= width:
        break
      else:
        self.rx_data_width = x
  def __getattr__(self, name):
    return getattr(self.rx_zero, name)
  def ChangeRxZero(self, show_graph):
    if self.IsSplit():
      old = self.GetWindow2()
    else:
      old = self.GetWindow1()
    if show_graph:
      new = self.graph
    else:
      new = self.waterfall
    if old != new:
      self.ReplaceWindow(old, new)
      new.Show()
      old.Hide()
      self.rx_zero = new
  def StopPlaying(self, excpt):		# change to not playing on all panes except excpt
    for pane in self.receiver_list:
      if pane != excpt:
        pane.play_btn.SetValue(False)
        pane.is_playing = False
  def OnAddReceiver(self, event):
    index = len(self.receiver_list)
    if index >= 7:
      return
    if index == 0:
      pane2 = self.rx_zero
      splitter = pane2.GetParent()
      pane1 = MultiRxGraph(self, self.data_width, self.graph_width, index)
      self.receiver_list.append(pane1)
      splitter.SplitHorizontally(pane1, self.rx_zero)
    else:
      pane2 = self.receiver_list[-1]
      parent = pane2.GetParent()
      splitter = wx.SplitterWindow(parent)
      splitter.SetSizeHints(self.width, -1, self.width)
      splitter.SetMinimumPaneSize(self.rx_btn_height)
      splitter.SetSashGravity(0.50)
      pane1 = MultiRxGraph(splitter, self.data_width, self.graph_width, index)
      self.receiver_list.append(pane1)
      pane2.Reparent(splitter)
      parent.ReplaceWindow(pane2, splitter)
      splitter.SplitHorizontally(pane1, pane2)
    self.SizeEqually()
    index += 1		# len(self.receiver_list)
    Hardware.MultiRxCount(index)
    pane1.ChangeBand(application.lastBand)
  def DeleteReceiver(self, pane):
    Hardware.MultiRxCount(len(self.receiver_list) - 1)
    if len(self.receiver_list) == 1:
      self.Unsplit(pane)
      self.receiver_list.remove(pane)
      del pane
    elif pane in self.receiver_list[-2:]:
      self.receiver_list.remove(pane)
      splitter2 = pane.GetParent()
      splitter1 = splitter2.GetParent()
      del pane
      pane = self.receiver_list[-1]
      pane.Reparent(splitter1)
      splitter1.ReplaceWindow(splitter2, pane)
      splitter2.Destroy()
    else:
      self.receiver_list.remove(pane)
      splitter2 = pane.GetParent()
      splitter1 = splitter2.GetParent()
      splitter3 = splitter2.GetWindow1()
      del pane
      splitter3.Reparent(splitter1)
      splitter1.ReplaceWindow(splitter2, splitter3)
      splitter2.Destroy()
    index = 0
    for pane in self.receiver_list:
      pane.multirx_index = index
      pane.rx_btn.SetLabel("Rx %d" % (index + 1))
      QS.set_multirx_mode(index, pane.mode_index)
      QS.set_multirx_freq(index, pane.txFreq)
      index += 1
    if hasattr(application.Hardware, "ChangeBandFilters"):
      application.Hardware.ChangeBandFilters()
  def SizeEqually(self):
    w, h = self.GetClientSize()
    num = len(self.receiver_list)
    self.SetSashPosition(h * num // (num + 1))
    for rx in self.receiver_list[:-1]:
      splitter = rx.GetParent()
      w, h = splitter.GetClientSize()
      num -= 1
      splitter.SetSashPosition(h * num // (num + 1))
  def OnIdle(self, event):
    self.rx_zero.OnIdle(event)
    for pane in self.receiver_list:
      pane.OnIdle(event)
  def OnGraphData(self, data, index=None):
    if index is None:		# data is for the principal receiver
      self.waterfall.OnGraphData(data)	# Save data for switch to waterfall
      if self.rx_zero == self.graph:
        self.graph.OnGraphData(data)
    elif index < len(self.receiver_list):
      self.receiver_list[index].OnGraphData(data)
  def ChangeSampleRate(self, rate):
    self.graph.sample_rate = rate
    self.waterfall.pane1.sample_rate = rate
    self.waterfall.pane2.sample_rate = rate
    self.waterfall.pane2.display.sample_rate = rate
    for pane in self.receiver_list:
      pane.sample_rate = rate
      tune = pane.txFreq
      vfo = pane.VFO
      pane.txFreq = pane.VFO = -1		# demand change
      pane.ChangeHwFrequency(tune, vfo, 'NewDecim')

class ScopeScreen(wx.Window):
  """Create an oscilloscope screen (mostly used for debug)."""
  def __init__(self, parent, width, data_width, graph_width):
    wx.Window.__init__(self, parent, pos = (0, 0),
       size=(width, -1), style = wx.NO_BORDER)
    self.SetBackgroundColour(conf.color_graph)
    self.font = wx.Font(conf.config_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    self.SetFont(self.font)
    self.Bind(wx.EVT_SIZE, self.OnSize)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.horizPen = wx.Pen(conf.color_gl, 1, wx.SOLID)
    self.y_scale = conf.scope_y_scale
    self.y_zero = conf.scope_y_zero
    self.zoom_control = 0
    self.yscale = 1
    self.running = 1
    self.doResize = False
    self.width = width
    self.height = 100
    self.originY = self.height // 2
    self.data_width = data_width
    self.graph_width = graph_width
    w = self.charx = self.GetCharWidth()
    h = self.chary = self.GetCharHeight()
    tick = max(2, h * 3 // 10)
    self.originX = w * 3
    self.width = self.originX + self.graph_width + tick + self.charx * 2
    self.line = [(0,0), (1,1)]	# initial fake graph data
    self.fpout = None #open("jim96.txt", "w")
  def OnIdle(self, event):
    if self.doResize:
      self.ResizeGraph()
  def OnSize(self, event):
    self.doResize = True
    event.Skip()
  def ResizeGraph(self, event=None):
    # Change the height of the graph.  Changing the width interactively is not allowed.
    w, h = self.GetClientSize()
    self.height = h
    self.originY = h // 2
    self.doResize = False
    self.Refresh()
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    dc.SetFont(self.font)
    dc.SetTextForeground(conf.color_graphlabels)
    self.MakeYTicks(dc)
    self.MakeXTicks(dc)
    self.MakeText(dc)
    dc.SetPen(wx.Pen(conf.color_graphline, 1))
    dc.DrawLines(self.line)
  def MakeYTicks(self, dc):
    chary = self.chary
    originX = self.originX
    x3 = self.x3 = originX + self.graph_width	# end of graph data
    dc.SetPen(wx.Pen(conf.color_graphticks,1))
    dc.DrawLine(originX, 0, originX, self.originY * 3)	# y axis
    # Find the size of the Y scale markings
    themax = 2.5e9 * 10.0 ** - ((160 - self.y_scale) / 50.0)	# value at top of screen
    themax = int(themax)
    l = []
    for j in (5, 6, 7, 8):
      for i in (1, 2, 5):
        l.append(i * 10 ** j)
    for yvalue in l:
      n = themax // yvalue + 1			# Number of lines
      ypixels = self.height // n
      if n < 20:
        break
    dc.SetPen(self.horizPen)
    for i in range(1, 1000):
      y = self.originY - ypixels * i
      if y < chary:
        break
      # Above axis
      dc.DrawLine(originX, y, x3, y)	# y line
      # Below axis
      y = self.originY + ypixels * i
      dc.DrawLine(originX, y, x3, y)	# y line
    self.yscale = float(ypixels) / yvalue
    self.yvalue = yvalue
  def MakeXTicks(self, dc):
    originY = self.originY
    x3 = self.x3
    # Draw the X axis
    dc.SetPen(wx.Pen(conf.color_graphticks,1))
    dc.DrawLine(self.originX, originY, x3, originY)
    # Find the size of the X scale markings in microseconds
    for i in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000):
      xscale = i			# X scale in microseconds
      if application.sample_rate * xscale * 0.000001 > self.width // 30:
        break
    # Draw the X lines
    dc.SetPen(self.horizPen)
    for i in range(1, 999):
      x = int(self.originX + application.sample_rate * xscale * 0.000001 * i + 0.5)
      if x > x3:
        break
      dc.DrawLine(x, 0, x, self.height)	# x line
    self.xscale = xscale
  def MakeText(self, dc):
    if self.running:
      t = "   RUN"
    else:
      t = "   STOP"
    if self.xscale >= 1000:
      t = "%s    X: %d millisec/div" % (t, self.xscale // 1000)
    else:
      t = "%s    X: %d microsec/div" % (t, self.xscale)
    t = "%s   Y: %.0E/div" % (t, self.yvalue)
    dc.DrawText(t, self.originX, self.height - self.chary)
  def OnGraphData(self, data):
    if not self.running:
      if self.fpout:
        for cpx in data:
          re = int(cpx.real)
          im = int(cpx.imag)
          ab = int(abs(cpx))
          ph = math.atan2(im, re) * 360. / (2.0 * math.pi)
          self.fpout.write("%12d %12d %12d %12.1d\n" % (re, im, ab, ph))
      return		# Preserve data on screen
    line = []
    x = self.originX
    ymax = self.height
    for cpx in data:	# cpx is complex raw samples +/- 0 to 2**31-1
      y = cpx.real
      #y = abs(cpx)
      y = self.originY - int(y * self.yscale + 0.5)
      if y > ymax:
        y = ymax
      elif y < 0:
        y = 0
      line.append((x, y))
      x = x + 1
    self.line = line
    self.Refresh()
  def ChangeYscale(self, y_scale):
    self.y_scale = y_scale
    self.doResize = True
  def ChangeYzero(self, y_zero):
    self.y_zero = y_zero
  def SetTxFreq(self, tx_freq, rx_freq):
    pass

class BandscopeScreen(WaterfallScreen):
  def __init__(self, frame, width, data_width, graph_width, clock):
    self.zoom = 1.0
    self.zoom_deltaf = 0
    self.zoom_control = 0
    WaterfallScreen.__init__(self, frame, width, data_width, graph_width)
    self.sample_rate = self.pane1.sample_rate = self.pane2.sample_rate = int(clock) // 2
    self.VFO = clock // 4
    self.SetVFO(self.VFO)
  def SetTxFreq(self, tx_freq, rx_freq):
    freq = tx_freq + application.VFO - self.VFO
    WaterfallScreen.SetTxFreq(self, freq, freq)
  def SetFrequency(self, freq):		# freq is 7000000, not the offset from VFO
    freq = freq - self.VFO
    WaterfallScreen.SetTxFreq(self, freq, freq)
  def ChangeZoom(self, zoom_control):	# zoom_control is the slider value 0 to 1000
    self.zoom_control = zoom_control
    if zoom_control < 50:
      zoom = 1.0
      zoom_deltaf = 0
    else:
      zoom = 1.0 - zoom_control / 1000.0 * 0.95
      freq = application.rxFreq + application.VFO
      srate = int(self.sample_rate * zoom)		# reduced (zoomed) sample rate
      if freq - srate // 2 < 0:
        zoom_deltaf = srate // 2 - self.VFO
      elif freq + srate // 2 > self.sample_rate:
        zoom_deltaf = self.VFO - srate // 2
      else:
        zoom_deltaf = freq - self.VFO
    self.zoom = zoom
    self.zoom_deltaf = zoom_deltaf
    self.pane1.ChangeZoom(zoom, zoom_deltaf, zoom_control)
    self.pane2.ChangeZoom(zoom, zoom_deltaf, zoom_control)
    self.pane2.display.ChangeZoom(zoom, zoom_deltaf, zoom_control)

class FilterScreen(GraphScreen):
  """Create a graph of the receive filter response."""
  def __init__(self, parent, data_width, graph_width):
    GraphScreen.__init__(self, parent, data_width, graph_width)
    self.y_scale = conf.filter_y_scale
    self.y_zero = conf.filter_y_zero
    self.zoom_control = 0
    self.VFO = 0
    self.txFreq = 0
    self.data = []
    self.sample_rate = QS.get_filter_rate(-1, -1)
  def NewFilter(self):
    self.sample_rate = QS.get_filter_rate(-1, -1)
    self.data = QS.get_filter()
    mx = -1000
    for x in self.data:
      if mx < x:
        mx = x
    mx -= 3.0
    f1 = None
    for i in range(len(self.data)):
      x = self.data[i]
      if x > mx:
        if f1 is None:
          f1 = i
        f2 = i
    bw3 = float(f2 - f1) / len(self.data) * self.sample_rate
    mx -= 3.0
    f1 = None
    for i in range(len(self.data)):
      x = self.data[i]
      if x > mx:
        if f1 is None:
          f1 = i
        f2 = i
    bw6 = float(f2 - f1) / len(self.data) * self.sample_rate
    self.display.display_text = "Filter 3 dB bandwidth %.0f, 6 dB %.0f" % (bw3, bw6)
    #self.data = QS.get_tx_filter()
    self.doResize = True
  def OnGraphData(self, data):
    GraphScreen.OnGraphData(self, self.data)
  def ChangeHwFrequency(self, tune, vfo, source='', band='', event=None, rx_freq=None):
    GraphScreen.SetTxFreq(self, tune, tune)
    application.freqDisplay.Display(tune)
  def SetTxFreq(self, tx_freq, rx_freq):
    pass

class AudioFFTScreen(GraphScreen):
  """Create an FFT graph of the transmit audio."""
  def __init__(self, parent, data_width, graph_width, sample_rate):
    GraphScreen.__init__(self, parent, data_width, graph_width)
    self.y_scale = conf.filter_y_scale
    self.y_zero = conf.filter_y_zero
    self.zoom_control = 0
    self.VFO = 0
    self.txFreq = 0
    self.sample_rate = sample_rate
  def OnGraphData(self, data):
    GraphScreen.OnGraphData(self, data)
  def ChangeHwFrequency(self, tune, vfo, source='', band='', event=None, rx_freq=None):
    GraphScreen.SetTxFreq(self, tune, tune)
    application.freqDisplay.Display(tune)
  def SetTxFreq(self, tx_freq, rx_freq):
    pass

# --------------------------------------------------- удалено ----------------------------------- кнопка Hardware ---------- 15 RA3PKJ
##class HelpScreen(wx.html.HtmlWindow):
##  """Create the screen for the Help button."""
##  def __init__(self, parent, width, height):
##    wx.html.HtmlWindow.__init__(self, parent, -1, size=(width, height))
##    self.y_scale = 0
##    self.y_zero = 0
##    self.zoom_control = 0
##    if "gtk2" in wx.PlatformInfo:
##      self.SetStandardFonts()
##    self.SetFonts("", "", [10, 12, 14, 16, 18, 20, 22])
##    # read in text from file help.html in the directory of this module
##    self.LoadFile('help.html')
##  def OnGraphData(self, data):
##    pass
##  def ChangeYscale(self, y_scale):
##    pass
##  def ChangeYzero(self, y_zero):
##    pass
##  def OnIdle(self, event):
##    pass
##  def SetTxFreq(self, tx_freq, rx_freq):
##    pass
##  def OnLinkClicked(self, link):
##    webbrowser.open(link.GetHref(), new=2)

class QMainFrame(wx.Frame):
  """Create the main top-level window."""
  def __init__(self, width, height):
    # ----------------------------------------------------------- удалено ----------------- заголовок окна ------------------ 3 RA3PKJ
    #fp = open('__init__.py')		# Read in the title
    #self.title = fp.readline().strip()[1:]
    #fp.close()
    self.title = '!!!' # ------------------------------------------ взамен ------------------ заголовок окна ------------------ 3 RA3PKJ

    x = conf.window_posX
    y = conf.window_posY
    wx.Frame.__init__(self, None, -1, self.title, (x, y),
        (width, height), wx.DEFAULT_FRAME_STYLE, 'MainFrame')
    self.SetBackgroundColour(conf.color_bg)
    self.SetForegroundColour(conf.color_bg_txt)
    self.Bind(wx.EVT_CLOSE, self.OnBtnClose)
    if DEBUGSHELL:
      #debugshell = CrustFrame()
      debugshell = ShellFrame(parent=self)
      debugshell.Show()
      debugshell.shell.write("hw=quisk.application.Hardware")

  def OnBtnClose(self, event):
    application.OnBtnClose(event)
    self.Destroy()
  def SetConfigText(self, text):
    if len(text) > 100:
      text = text[0:80] + '|||' + text[-17:]
    self.SetTitle("N2ADR %s%s   %s" % (application.local_conf.RadioName, self.title, text)) # ------------- изменено ------------ заголовок окна ------ 3 RA3PKJ

class Spacer(wx.Window):
  """Create a bar between the graph screen and the controls"""
  def __init__(self, parent):
    wx.Window.__init__(self, parent, pos = (0, 0),
       size=(-1, 6), style = wx.NO_BORDER)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    r, g, b = parent.GetBackgroundColour().Get(False)
    dark = (r * 7 // 10, g * 7 // 10, b * 7 // 10)
    light = (r + (255 - r) * 5 // 10, g + (255 - g) * 5 // 10, b + (255 - b) * 5 // 10)
    self.dark_pen = wx.Pen(dark, 1, wx.SOLID)
    self.light_pen = wx.Pen(light, 1, wx.SOLID)
    self.width = application.screen_width
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    w = self.width
    dc.SetPen(self.dark_pen)
    dc.DrawLine(0, 0, w, 0)
    dc.DrawLine(0, 1, w, 1)
    dc.DrawLine(0, 2, w, 2)
    dc.SetPen(self.light_pen)
    dc.DrawLine(0, 3, w, 3)
    dc.DrawLine(0, 4, w, 4)
    dc.DrawLine(0, 5, w, 5)

class App(wx.App):
  """Class representing the application."""
  StateNames = [		# Names of state attributes to save and restore
  'bandState', 'bandAmplPhase', 'lastBand', 'VFO', 'txFreq', 'mode',
  'vardecim_set', 'filterAdjBw1', 'levelAGC', 'levelOffAGC', 'volumeAudio', 'levelSpot',
  'levelSquelch', 'levelSquelchSSB', 'levelVOX', 'timeVOX', 'sidetone_volume',
  'txAudioClipUsb', 'txAudioClipAm','txAudioClipFm', 'txAudioClipFdv',
  'txAudioPreemphUsb', 'txAudioPreemphAm', 'txAudioPreemphFm', 'txAudioPreemphFdv',
  'wfallScaleZ', 'wfallGrScaleZ', 'graphScaleZ', 'split_rxtx_play', 'modeFilter',
  'file_name_rec_audio', 'file_name_rec_samples', 'file_name_rec_mic', 'file_name_rec_tmp',
  'file_name_play_audio', 'file_name_play_samples', 'file_name_play_cq', 'freedv_mode',
  'file_play_source', 'hermes_LNA_dB']
  def __init__(self):
    global application
    QS.AppStatus(1)
    application = self
    self.bottom_widgets = None
    self.dxCluster = None
    self.main_frame = None
    self.quisk_height = None # ------------------- добавлено -------- запоминание высоты окна при выходе -------- 34 RA3PKJ
    # -------------------------------------------- добавлено ------------ запоминание позиции окна -------------- 35 RA3PKJ
    self.quisk_posX = None # позиция X окна
    self.quisk_posY = None # позиция Y окна

    # -------------------------------------------- добавлено -------------- COM-порты для Odyssey --------------- 63 RA3PKJ
    self.cw_com_method = 0
    self.ody_cw_thread1 = None
    self.ody_cw_thread2 = None

    self.remote_control_head = False
    self.remote_control_slave = False
    self.keys_down = []
    wx.App.__init__(self)
  def QuiskText(self, *args, **kw):			# Make our text control available to widget files
    return QuiskText(*args, **kw)
  def QuiskText1(self, *args, **kw):			# Make our text control available to widget files
    return QuiskText1(*args, **kw)
  def QuiskPushbutton(self, *args, **kw):	# Make our buttons available to widget files
    return QuiskPushbutton(*args, **kw)
  def  QuiskRepeatbutton(self, *args, **kw):
    return QuiskRepeatbutton(*args, **kw)
  def QuiskCheckbutton(self, *args, **kw):
    return QuiskCheckbutton(*args, **kw)
  def QuiskCycleCheckbutton(self, *args, **kw):
    return QuiskCycleCheckbutton(*args, **kw)
  def RadioButtonGroup(self, *args, **kw):
    return RadioButtonGroup(*args, **kw)
  def SliderBoxHH(self, *args, **kw):
    return SliderBoxHH(*args, **kw)
  def FilterEvent(self, event):
    try:	# I am not sure if older wxPython can do this
      typ = event.GetEventType()
      if typ == wx.EVT_KEY_DOWN.typeId:
        key = event.GetKeyCode()		# This is always upper case for letters
        if key not in self.keys_down:
          self.keys_down.append(key)
          #print (self.keys_down)
      elif typ == wx.EVT_KEY_UP.typeId:
        key = event.GetKeyCode()
        self.keys_down.remove(key)
        #print (self.keys_down)
    except:
      self.keys_down = []
    return -1
  def QuiskGetKeyState(self, key):	# Replace normal wx.GetKeyState() because it only works with Shift, Control, Alt
    if 97 <= key <= 122:	# key is an integer; convert to upper case
      key -= 32
    return key in self.keys_down
  def OnInit(self):
    """Perform most initialization of the app here (called by wxPython on startup)."""

    # ---------- получить разрешение дисплея ("system dpi aware") --------- добавлено ------- картинка на панораме --------------- 5 RA3PKJ
    global MyDisplayWidth
    global MyDisplayHeight
    (MyDisplayWidth, MyDisplayHeight) = wx.GetDisplaySize()

    wx.lib.colourdb.updateColourDB()	# Add additional color names
    import quisk_widgets		# quisk_widgets needs the application object
    quisk_widgets.application = self
    del quisk_widgets
    global conf		# conf is the module for all configuration data
    setattr(conf, 'config_file_path', ConfigPath)
    setattr(conf, 'DefaultConfigDir', DefaultConfigDir)
    if os.path.isfile(ConfigPath):	# See if the user has a config file
      setattr(conf, 'config_file_exists', True)
      d = {}
      d.update(conf.__dict__)		# make items from conf available
      exec(compile(open(ConfigPath).read(), ConfigPath, 'exec'), d)		# execute the user's config file
      if os.path.isfile(ConfigPath2):	# See if the user has a second config file
        exec(compile(open(ConfigPath2).read(), ConfigPath2, 'exec'), d)	# execute the user's second config file
      for k in d:		# add user's config items to conf
        v = d[k]
        if k[0] != '_':				# omit items starting with '_'
          setattr(conf, k, v)
    else:
      setattr(conf, 'config_file_exists', False)
    self.QuiskFilesDir = os.path.dirname(conf.settings_file_path)	# directory for Quisk files
    if not os.path.isdir(self.QuiskFilesDir):
      self.QuiskFilesDir = DefaultConfigDir
    self.std_out_err = StdOutput(self)
    self.std_out_err.Logfile("WxPython " + wx.version())
    QS.set_params(quisk_is_vna=0)	# We are not the VNA program
    # Read in configuration from the selected radio
    self.BandPlan = []
    if self.main_frame:
      self.local_conf = configure.Configuration(self, 'Same')
    else:
      self.local_conf = configure.Configuration(self, argv_options.AskMe, argv_options.radio)
    self.local_conf.UpdateConf()

    # Choose whether to use Unicode or text symbols
    for k in ('sym_stat_mem', 'sym_stat_fav', 'sym_stat_dx',
        'btn_text_range_dn', 'btn_text_range_up', 'btn_text_play', 'btn_text_rec', 'btn_text_file_rec',
		'btn_text_file_play', 'btn_text_fav_add',
        'btn_text_fav_recall', 'btn_text_mem_add', 'btn_text_mem_next', 'btn_text_mem_del'):

      # ------------------------------------------------- изменено -------------------------- надписи на кнопках ----------- 20 RA3PKJ
      #if conf.use_unicode_symbols:
      setattr(conf, 'X' + k, getattr(conf, 'U' + k))
      #else:
        #setattr(conf, 'X' + k, getattr(conf, 'T' + k))

    MakeWidgetGlobals()
    if conf.invertSpectrum:
      QS.invert_spectrum(1)
    if conf.use_sdriq:
      sample_rate = int(66666667.0 / conf.sdriq_decimation + 0.5)
    if conf.use_sdriq or conf.use_rx_udp:
      name_of_sound_capt = ''
      name_of_mic_play = ''
    self.wfallScaleZ = {}		# scale and zero for the waterfall pane2
    self.wfallGrScaleZ = {}		# scale and zero for the waterfall graph pane1
    self.graphScaleZ = {}		# scale and zero for the graph
    self.bandState = {}			# for key band, the current (self.VFO, self.txFreq, self.mode)
    self.bandState.update(conf.bandState)
    self.memoryState = []		# a list of (freq, band, self.VFO, self.txFreq, self.mode)
    self.bandAmplPhase = {}
    self.samples_from_python = False
    self.NewIdList = []                 # Hack: list of Ids in use for accelerator table
    self.midi_message = []
    self.idName2Button = {}
    self.midi_handler = None
    self.tx_inhibit = 0
    self.old_tx_inhibit = 0
    if conf.use_rx_udp == 10:		# Hermes UDP protocol
      self.bandscope_clock = conf.rx_udp_clock
    else:
      self.bandscope_clock = 0
    self.modeFilter = {			# the filter button index in use for each mode
      'CW'  : 3,
      'SSB' : 3,
      'AM'  : 3,
      'FM'  : 3,
      'DGT' : 1,
      'FDV' : 2,
      'IMD' : 3,
      conf.add_extern_demod : 3,
      }
    # if sys.platform == 'win32' and (conf.hamlib_com1_name or conf.hamlib_com2_name):# ----------------------------------- удалено --------------- CAT ----------- 49 RA3PKJ
    if sys.platform == 'win32' and (conf.hamlib_com1_name or conf.hamlib_com2_name or conf.hamlib_com3_name):# ------------- взамен --------------- CAT ----------- 49 RA3PKJ
      try:      # make sure the pyserial module exists
        import serial
      except:
        dlg = wx.MessageDialog(None, "The Python pyserial module is required but not installed. Do you want me to install it?",
          "Install Python pyserial", style = wx.YES|wx.NO)
        if dlg.ShowModal() == wx.ID_YES:
          subprocess.call([sys.executable, "-m", "pip", "install", "pyserial"])
          try:
            import serial
          except:
            dlg = wx.MessageDialog(None, "Installation of Python pyserial failed. Please install it by hand.",
               "Installation failed", style=wx.OK)
            dlg.ShowModal()
    # Open hardware file
    global Hardware
    if self.local_conf.GetHardware():
      pass
    else:
      if hasattr(conf, "Hardware"):	# Hardware defined in config file
        self.Hardware = conf.Hardware(self, conf)
        hname =  ConfigPath
      else:
        self.Hardware = conf.quisk_hardware.Hardware(self, conf)
        hname =  conf.quisk_hardware.__file__
      if hname[-3:] == 'pyc':
        hname = hname[0:-1]
      setattr(conf, 'hardware_file_name',  hname)
      if conf.quisk_widgets:
        hname =  conf.quisk_widgets.__file__
        if hname[-3:] == 'pyc':
          hname = hname[0:-1]
        setattr(conf, 'widgets_file_name',  hname)
      else:
        setattr(conf, 'widgets_file_name',  '')
    Hardware = self.Hardware
    self.use_fast_heart_beat = hasattr(Hardware, "FastHeartBeat")
    self.poll_gui_control = hasattr(Hardware, "PollGuiControl")
    # Initialization - may be over-written by persistent state
    self.local_conf.Initialize()
    self.clip_time0 = 0		# timer to display a CLIP message on ADC overflow
    self.smeter_db_count = 0	# average the S-meter
    self.smeter_db_sum = 0
    self.smeter_db = 0
    self.smeter_avg_seconds = 1.0	# seconds for S-meter average
    self.smeter_sunits = -87.0

    #self.smeter_usage = "smeter" # ----------------------------------------- удалено ---------- вынос из малого окошка ------- 8 RA3PKJ
    self.measure_audio_str = '' # --- значение напряжения аудио ------------ добавлено --------- вынос из малого окошка ------- 8 RA3PKJ

    self.hamlib_strength = 0.0;
    self.timer = time.time()		# A seconds clock
    self.heart_time0 = self.timer	# timer to call HeartBeat at intervals
    self.save_time0 = self.timer
    self.smeter_db_time0 = self.timer
    self.smeter_sunits_time0 = self.timer
    self.slowheart_time0 = self.timer
    self.multi_rx_index = 0
    self.multi_rx_timer = self.timer
    self.band_up_down = 0			# Are band Up/Down buttons in use?
    self.lastBand = 'Audio'
    self.filterAdjBw1 = 1000
    self.levelAGC = 500				# AGC level ON control, 0 to 1000
    self.levelOffAGC = 100			# AGC level OFF control, 0 to 1000
    self.levelSquelch = 500			# FM squelch level, 0 to 1000
    self.levelSquelchSSB = 200			# SSB squelch level, 0 to 1000
    self.levelVOX = -20				# audio level that triggers VOX
    self.timeVOX = 500				# hang time for VOX
    self.useVOX = False				# Is the VOX button down?
    self.txAudioClipUsb = 5			# Tx audio clip level in dB
    self.txAudioClipAm = 0
    self.txAudioClipFm = 0
    self.txAudioClipFdv = 0
    self.txAudioPreemphUsb = 70		# Tx audio preemphasis 0 to 100
    self.txAudioPreemphAm = 0
    self.txAudioPreemphFm = 0
    self.txAudioPreemphFdv = 0
    self.levelSpot = 500			# Spot level control, 0 to 1000
    self.TxLevel = 100 # ----------------------------------- добавлено ------------------- Вынос слайдера TxLevel в главное окно ------ 41 RA3PKJ
    self.DigiTxLev = 100 # --------------------------------- добавлено -------------- Вынос слайдера Digital TxLevel в главное окно --- 62 RA3PKJ
    # --------------------------------------------------------------------------------------------------------------------------------- 51 RA3PKJ
    self.f_before_1 = None # первый аргумент (частота "До") функции ChangeHwFrequency
    self.f_before_2 = None # второй аргумент (частота "До") функции ChangeHwFrequency
    self.f_after_1 = None  # первый аргумент (частота "После") функции ChangeHwFrequency
    self.f_after_2 = None  # второй аргумент (частота "После") функции ChangeHwFrequency

    self.speed_cw = 0 # ------------------------------------ добавлено -------------------------- CW paddle --------------------------- 60 RA3PKJ

    self.volumeAudio = 300			# audio volume
    self.VFO = 0					# frequency of the VFO
    self.ritFreq = 0				# receive incremental tuning frequency offset
    self.txFreq = 0				# Transmit frequency as +/- sample_rate/2
    self.rxFreq = 0				# Receive  frequency as +/- sample_rate/2
    self.tx_level = 100				# initially 100%; Caution: there is also a conf.tx_level dictionary
    self.digital_tx_level = conf.digital_tx_level
    self.fft_size = 1
    self.accel_list = []
    self.old_RxTx = 0
    self.wsjtx_process = [None] * 10	# Maximum of 10 receivers
    self.config_midi_window = None
    self.hot_key_ptt_is_down = False
    self.hot_key_ptt_was_down = False
    self.hot_key_ptt_pressed = False
    self.hot_key_ptt_active = False
    self.serial_ptt_active = False
    self.vox_ptt_active = False
    self.freedv_mode = 'Mode 700D'		# restore FreeDV mode setting
    self.freedv_menu = None
    self.hermes_LNA_dB = 20
    self.offset = 200 # цифра условная, т.к.берётся из quisk_settings.json --------------------------- добавлено ----- SSB RX Offset ---- 29 RA3PKJ
    self.offset_tx = 200 # цифра условная, т.к.берётся из quisk_settings.json ------------------------ добавлено --- Кнопка SSBtx Low --- 45 RA3PKJ
    self.freq_step = 50 # --- цифра условная, т.к.берётся из файла ----------------------------------- добавлено ---- шаг перестройки --- 30 RA3PKJ
    self.close = False #--------------------------------------------------- добавлено --- выключение режима TX при закрытии программы --- 46 RA3PKJ

    # --------------------------------------------------------------------- добавлено -------------- CW Training ------------------------ 52 RA3PKJ
    self.cts_old = None
    self.dsr_old = None

    # --- для слайдеров---------------------------------------------------- добавлено ------------ реформа кнопок ----------------------- 12 RA3PKJ
    self.y_scale = 0
    self.y_zoom = 0
    self.zoom_control = 0

    # --------------------------------------------------------------------- добавлено ---------- картинка на панораме -------------------- 5 RA3PKJ
    self.picture_bmp = "Pano_1.jpg"
    self.picture_list = [] # --- список картинок в папке
    self.picture_len = 0   # --- длина списка картинок
    self.picture_index = 0 # --- индекс в списке картинок

    # --------------------------------------------------------------------- добавлено -------- реформа обоих окошек частоты -------------- 9 RA3PKJ
    self.snr = 0.0
    self.freedv_flag = False # --- флаг моды freedv
    self.bandscope_flag = False

    if hasattr(Hardware, "OnChangeRxTx"):
      self.want_RxTx = True
    else:
      self.want_RxTx = False
    if conf.do_repeater_offset and hasattr(Hardware, "RepeaterOffset"):
      QS.tx_hold_state(1)
    # Quisk control by Hamlib through a serial port
    if conf.hamlib_com1_name:
      self.hamlib_com1_handler = HamlibHandlerSerial(self, conf.hamlib_com1_name)
    else:
      self.hamlib_com1_handler = None
    if conf.hamlib_com2_name:
      self.hamlib_com2_handler = HamlibHandlerSerial(self, conf.hamlib_com2_name)
    else:
      self.hamlib_com2_handler = None

    # --------------------------------------------------------------------- добавлено -------------------- CAT --------------------------- 49 RA3PKJ
    if conf.hamlib_com3_name:
      self.hamlib_com3_handler = HamlibHandlerSerial(self, conf.hamlib_com3_name)
    else:
      self.hamlib_com3_handler = None

    # Quisk control by Hamlib through rig 2
    self.hamlib_clients = []	# list of TCP connections to handle
    if conf.hamlib_port:
      try:
        self.hamlib_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.hamlib_socket.bind((conf.hamlib_ip, conf.hamlib_port))
        self.hamlib_socket.settimeout(0.0)
        self.hamlib_socket.listen(5)	# listen for TCP connections from multiple clients
      except:
        self.hamlib_socket = None
        # traceback.print_exc()
    else:
      self.hamlib_socket = None
    # Quisk control by K4 commands through a TCP port
    self.k4_tcp_clients = []	# list of TCP connections to handle
    if conf.k4_tcp_port:
      try:
        self.k4_tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.k4_tcp_socket.bind((conf.k4_tcp_ip, conf.k4_tcp_port))
        self.k4_tcp_socket.settimeout(0.0)
        self.k4_tcp_socket.listen(5)	# listen for TCP connections from multiple clients
      except:
        self.k4_tcp_socket = None
        # traceback.print_exc()
    else:
      self.k4_tcp_socket = None
    # Quisk control by fldigi
    self.fldigi_new_freq = None
    self.fldigi_freq = None
    if conf.digital_xmlrpc_url:
      self.fldigi_server = ServerProxy(conf.digital_xmlrpc_url)
    else:
      self.fldigi_server = None
    self.fldigi_rxtx = 'rx'
    self.fldigi_timer = 0

    # последнее значение частоты приёмника ---------------------- добавлено ----------------------- реформа кнопок ------------------------ 12 RA3PKJ
	# ----------------------------------------------------------- добавлено ------------ чистка кнопки Split и замена её на RX2 ----------- 10 RA3PKJ
    self.oldRxFreq = 0

    self.screen = None
    # Display the audio FFT instead of the RX filter or bandscope when self.rate_audio_fft > 0.
    # The sample rate is self.rate_audio_fft. Add an instance of quisk_calc_audio_graph() to C code to provide data.
    self.rate_audio_fft = 0
    self.audio_fft_screen = None
    self.audio_volume = 0.0		# Set output volume, 0.0 to 1.0
    self.sidetone_volume = 0	# sidetone control value 0 to 1000
    self.sidetone_0to1 = 0		# log taper sidetone volume 0.0 to 1.0
    self.sound_thread = None
    self.mode = conf.default_mode
    self.color_list = None
    self.color_index = 0
    self.vardecim_set = 48000
    self.w_phase = None
    self.zoom = 1.0
    self.filter_bandwidth = 1000    # filter bandwidth
    self.zoom_deltaf = 0
    self.zooming = False
    self.split_rxtx = False		# Are we in split Rx/Tx mode?

    self.new_split = False  # ------------------------------------------- добавлено ---------------------------------------- реформа кнопок ---------- 12 RA3PKJ

    self.split_locktx = False   # Flag Tx frequency is fixed
    self.split_lockrx = False   # Flag Rx frequency is fixed
    self.split_rxtx_play = 2    # Play 1=both, high on Right; 2=both, high on Left; 3=only Rx; 4=only Tx
    #self.split_offset = 0	# current frequency difference when using Split # ---- удалено -------- чистка кнопки Split и перевод её на RX2 ---------- 10 RA3PKJ
    self.savedState = {}
    self.tx_indicator = False
    self.tmp_playing = False
    self.file_play_state = 0	# 0 == not playing a file, 1 == playing a file, 2 == waiting for the repeat time
    self.file_play_repeat = 0	# Repeat time in seconds, or zero for no repeat
    self.file_play_timer = 0
    self.file_play_source = 0	# 10 == play audio file, 11 == play I/Q sample file, 12 == play CQ message
    self.file_name_rec_audio = ''
    self.file_name_rec_samples = ''
    self.file_name_rec_mic = ''
    self.file_name_rec_tmp = ''
    self.file_name_play_audio = ''
    self.file_name_play_samples = ''
    self.file_name_play_cq = ''
    self.midiControls = {}		# Control object and associated function for Midi control name
    # get the screen size - thanks to Lucian Langa
    x, y, self.screen_width, self.screen_height = wx.Display().GetGeometry()	# Using display index 0
    self.Bind(wx.EVT_IDLE, self.OnIdle)
    self.Bind(wx.EVT_QUERY_END_SESSION, self.OnEndSession)

# ===========================================================================================================================================================================
# ======================================================= Загрузка текущих настроек из файла quisk_init.json ================================================================
# ===========================================================================================================================================================================
    # Restore persistent program state
    state = None
    path = os.path.join(self.QuiskFilesDir, 'quisk_init.json')
    if os.path.isfile(path):
      try:
        fp = open(path, "r")
        state = json.load(fp) # ------------------------- загрузка текущих настроек
        fp.close()
      except:
        traceback.print_exc()
    else:	# Load from obsolete location
      path = os.path.join(os.path.dirname(ConfigPath), '.quisk_init.pkl')
      if os.path.isfile(path):
        try:
          fp = open(path, "rb")		# Pickle requires a bytes object
          state = pickle.load(fp)
          fp.close()
        except:
          pass #traceback.print_exc()
    if state: # -----------------------------------------применение текущих настроек
      try:
        for k in state:
          v = state[k]
          if k in self.StateNames:
            self.savedState[k] = v
            attr = getattr(self, k)
            if isinstance(attr, dict):
              attr.update(v)
            else:
              setattr(self, k, v)
      except:
        pass #traceback.print_exc()
# ===========================================================================================================================================================================
# ===========================================================================================================================================================================
# ===========================================================================================================================================================================


    if "Version" not in self.bandAmplPhase:
      self.FixAmplPhase()		# Convert to new format Oct 2020
    self.FixAmplPhase2()		# New logic June 2024
    if Hardware.VarDecimGetChoices():	# Hardware can change the decimation.
      self.sample_rate = Hardware.VarDecimSet()	# Get the sample rate.
      self.vardecim_set = self.sample_rate
      try:
        var_rate1, var_rate2 = Hardware.VarDecimRange()
      except:
        var_rate1, var_rate2 = (48000, 960000)
    else:		# Use the sample rate from the config file.
      var_rate1 = None
      self.sample_rate = conf.sample_rate
    if not hasattr(conf, 'playback_rate'):
      if conf.use_sdriq or conf.use_rx_udp:
        conf.playback_rate = 48000
      else:
        conf.playback_rate = conf.sample_rate

# Предварительное создание всего окна (main frame) программы (т.е. с кнопками)
    if conf.window_width > 0:	# fixed width of the main frame
      self.width = conf.window_width
    else: # self.screen_width - разрешение монитора по горизонтали
      #self.width = self.screen_width * 8 // 10 # -------------------------- удалено --- на всю длину монитора ----- 33 RA3PKJ
      self.width = self.screen_width # -------------------------------------- взамен --- на всю длину монитора ----- 33 RA3PKJ
# ----- отключить ручное управление высотой -------------------------------- удалено --- на всю длину монитора ----- 33 RA3PKJ
##    if conf.window_height > 0:	# fixed height of the main frame
##      self.height = conf.window_height
##    else:
##      self.height = self.screen_height * 5 // 10
    self.height = self.screen_height * 5 // 10 # ---------------------------- взамен --- на всю длину монитора ----- 33 RA3PKJ

    if self.main_frame:
      frame = self.main_frame
      szr = frame.GetSizer()
      szr.Clear(True)
      frame.SetSizer(None, True)
      frame.SetSize(wx.Size(self.width, self.height))
    else:
      self.main_frame = frame = QMainFrame(self.width, self.height)
    self.SetTopWindow(frame)
    self.std_out_err.Create(frame)
    if conf.pulse_audio_verbose_output == 0:
      self.std_out_err.Show(False)
    else:
      self.std_out_err.Show(True)
    #w, h = frame.GetSize().Get()
    #ww, hh = frame.GetClientSizeTuple()
    #print ('Main frame: size', w, h, 'client', ww, hh)
    # Find the data width from a list of preferred sizes; it is the width of returned graph data.
    # The graph_width is the width of data_width that is displayed.
      # ----------------------------------------------------------------------- удалено ---- на всю длину монитора ----- 33 RA3PKJ
##    if conf.window_width > 0:
##      wFrame, h = frame.GetClientSize().Get()				# client window width
##      graph = GraphScreen(frame, self.width//2, self.width//2, None)	# make a GraphScreen to calculate borders
##      self.graph_width = wFrame - (graph.width - graph.graph_width)		# less graph borders equals actual graph_width
##      graph.Destroy()
##      del graph
##      if self.graph_width % 2 == 1:		# Both data_width and graph_width are even numbers
##        self.graph_width -= 1
##      width = int(self.graph_width / conf.display_fraction)		# estimated data width
##      for x in fftPreferedSizes:
##        if x >= width:
##          self.data_width = x
##          break
##      else:
##        self.data_width = fftPreferedSizes[-1]
##    else:		# use conf.graph_width to determine the width
##      width = self.screen_width * conf.graph_width		# estimated graph width
##      percent = conf.display_fraction		# display central fraction of total width
##      percent = int(percent * 100.0 + 0.4)
##      width = width * 100 // percent		# estimated data width
##      for x in fftPreferedSizes:
##        if x > width:
##          self.data_width = x
##          break
##      else:
##        self.data_width = fftPreferedSizes[-1]
##      self.graph_width = self.data_width * percent // 100
##      if self.graph_width % 2 == 1:		# Both data_width and graph_width are even numbers
##        self.graph_width += 1
     # ----------------------------------------------------------------------- взамен ---- на всю длину монитора ----- 33 RA3PKJ
# создание верхней области (водопад, график)
    if conf.window_width > 0:
      wFrame = conf.window_width - 15
    else:
      wFrame = MyDisplayWidth - 15
    graph = GraphScreen(frame, self.width//2, self.width//2, None)	# make a GraphScreen to calculate borders
    self.graph_width = wFrame - (graph.width - graph.graph_width)		# less graph borders equals actual graph_width
    graph.Destroy()
    del graph
    if self.graph_width % 2 == 1:		# Both data_width and graph_width are even numbers
      self.graph_width -= 1
    width = int(self.graph_width / conf.display_fraction)		# estimated data width
    for x in fftPreferedSizes:
      if x >= width:
        self.data_width = x
        break
    else:
      self.data_width = fftPreferedSizes[-1]

    #print('graph_width', self.graph_width, 'data_width', self.data_width)
    # The FFT size times the average_count controls the graph refresh rate
    factor = float(self.sample_rate) / conf.graph_refresh / self.data_width
    ifactor = int(factor + 0.5)		# fft size multiplier * average count
    if conf.fft_size_multiplier >= 999:	# Use large FFT and average count 1
      fft_mult = ifactor
      average_count = 1
    elif conf.fft_size_multiplier > 0:		# Specified fft_size_multiplier
      fft_mult = conf.fft_size_multiplier
      average_count = int(factor / fft_mult + 0.5)
      if average_count < 1:
        average_count = 1
    elif var_rate1 is None:		# Calculate an equal split between fft size and average
      fft_mult = 1
      for mult in (32, 27, 24, 18, 16, 12, 9, 8, 6, 4, 3, 2, 1):	# product of small factors
        average_count = int(factor / mult + 0.5)
        if average_count >= mult:
          fft_mult = mult
          break
      average_count = int(factor / fft_mult + 0.5)
      if average_count < 1:
        average_count = 1
    else:		# Calculate a compromise for variable rates
      fft_mult = int(float(var_rate1) / conf.graph_refresh / self.data_width + 0.5)	# large fft_mult at low rate
      if fft_mult > 8:
        fft_mult = 8
      elif fft_mult == 5:
        fft_mult = 4
      elif fft_mult == 7:
        fft_mult = 6
      average_count = int(factor / fft_mult + 0.5)
      if average_count < 1:
        average_count = 1
    self.fft_size = self.data_width * fft_mult
    # Record the basic application parameters
    self.multi_rx_screen = MultiReceiverScreen(frame, self.data_width, self.graph_width)
    if sys.platform == 'win32':
      h = self.main_frame.GetHandle()
    else:
      h = 0
    wisdom_path = os.path.join(self.QuiskFilesDir, 'quisk_wisdom.cache')
    if conf.midi_cwkey_device:
      QS.control_midi(midi_cwkey_note = conf.midi_cwkey_note)
      midi = QS.control_midi(get_in_devices = 1)
      if sys.platform == 'win32':
        for i in range(len(midi)):
          midi[i] = (midi[i], i)
      found = None
      for friendly, device in midi:
        if conf.midi_cwkey_device == friendly:
          found = device
          break
      if found is None:
        for friendly, device in midi:
          if conf.midi_cwkey_device.startswith(friendly) or friendly.startswith(conf.midi_cwkey_device):
            found = device
            break
      if found is None:
        print("Can not find MIDI device", conf.midi_cwkey_device)
      elif sys.platform == 'win32':
        QS.control_midi(client=found)
      else:
       QS.control_midi(device=found)
    QS.record_app(self, conf, self.data_width, self.graph_width, self.fft_size,
                 self.multi_rx_screen.rx_data_width, self.sample_rate, h, wisdom_path)
    # Start wdsp
    self.wdsp = quisk_wdsp.Cwdsp(self)
    self.wdsp_channel = 1
    self.wdsp.open(self.wdsp_channel)
    #print ('data_width %d, FFT size %d, FFT mult %d, average_count %d, rate %d, Refresh %.2f Hz' % (
    #    self.data_width, self.fft_size, self.fft_size / self.data_width, average_count, self.sample_rate,
    #    float(self.sample_rate) / self.fft_size / average_count))
    QS.record_graph(0, 0, 1.0)
    QS.set_tx_audio(vox_level=20, vox_time=self.timeVOX)	# Turn off VOX, set VOX time
    # Make all the screens and hide all but one.  MultiReceiver creates the graph and waterfall screens.
    self.screen = self.multi_rx_screen
    self.graph = self.multi_rx_screen.graph
    self.waterfall = self.multi_rx_screen.waterfall
    width = self.multi_rx_screen.graph.width
    self.config_screen = ConfigScreen(frame, width, self.fft_size)
    self.config_screen.Hide()

    # -------------------------------------------------- добавлено ---------------------------------------- кнопка Hardware --------- 15 RA3PKJ
    self.radios_screen = RadiosScreen(frame, width)
    self.radios_screen.Hide()

    self.scope = ScopeScreen(frame, width, self.data_width, self.graph_width)
    self.scope.Hide()
    self.bandscope_screen = BandscopeScreen(frame, width, self.graph_width, self.graph_width, self.bandscope_clock)
    self.bandscope_screen.Hide()
    self.filter_screen = FilterScreen(frame, self.data_width, self.graph_width)
    self.filter_screen.Hide()
    if self.rate_audio_fft:
      self.audio_fft_screen = AudioFFTScreen(frame, self.data_width, self.graph_width, self.rate_audio_fft)
      self.audio_fft_screen.Hide()
    # --------------------------------------------------- удалено ----------------------------------------- кнопка Hardware --------- 15 RA3PKJ
    #self.help_screen = HelpScreen(frame, width, self.screen_height // 10)
    #self.help_screen.Hide()

    top_screen = TopScreen(frame, width, 23) # --------- добавлено ------------------------------------ создание строки состояния --- 28 RA3PKJ

    self.station_screen = StationScreen(frame, width, conf.station_display_lines)
    self.station_screen.Hide()

    # --- создать vertBox на поле frame
    vertBox = self.vertBox = wx.BoxSizer(wx.VERTICAL)
    frame.SetSizer(vertBox)

    # --- добавить скрины к vertBox
    vertBox.Add(top_screen) # -------------------------- добавлено -------------------------------- создание строки состояния ------- 28 RA3PKJ
    vertBox.Add(self.config_screen, 1, wx.EXPAND)
    vertBox.Add(self.radios_screen, 1, wx.EXPAND) # ---- добавлено -------------------------------------- кнопка Hardware ----------- 15 RA3PKJ
    vertBox.Add(self.multi_rx_screen, 1)
    vertBox.Add(self.scope, 1)
    vertBox.Add(self.bandscope_screen, 1)
    vertBox.Add(self.filter_screen, 1)
    if self.rate_audio_fft:
      vertBox.Add(self.audio_fft_screen, 1)
    #vertBox.Add(self.help_screen, 1)    # -------------- удалено --------------------------------------- кнопка Hardware ----------- 15 RA3PKJ
    vertBox.Add(self.station_screen)

    # Add the spacer
    vertBox.Add(Spacer(frame), 0, wx.EXPAND)

    # ------------------------------------------------- добавлено ------------------------------------------------ реформа кнопок --- 12 RA3PKJ
    # --- план размещения сайзеров (кнопки, слайдеры, окошки)
    vertBox.AddSpacer(5)
    self.bs0 = wx.BoxSizer()
    vertBox.Add(self.bs0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs0a = wx.BoxSizer()
    vertBox.Add(self.bs0a, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs1 = wx.BoxSizer()
    vertBox.Add(self.bs1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(5)
    self.bs2 = wx.BoxSizer()
    vertBox.Add(self.bs2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs2a = wx.BoxSizer()
    vertBox.Add(self.bs2a, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs3 = wx.BoxSizer()
    vertBox.Add(self.bs3, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs4 = wx.BoxSizer()
    vertBox.Add(self.bs4, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs5 = wx.BoxSizer()
    vertBox.Add(self.bs5, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs6 = wx.BoxSizer()
    vertBox.Add(self.bs6, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs7 = wx.BoxSizer()
    vertBox.Add(self.bs7, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    vertBox.AddSpacer(4)
    self.bs8 = wx.BoxSizer()
    vertBox.Add(self.bs8, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
    self.MakeButtons(frame) # --- создание и установка на место органов управления

    # --------------------------------------------- добавлено -------------------- реформа кнопок --- 12 RA3PKJ
    self.config_screen.config.InitRecPlay()
    self.config_screen.config.EnableRecPlay()

    #gap = 2 # ------------------------------------ удалено ----------- дополнительный нижний ряд --- 19 RA3PKJ
    gap = 1 # -------------------------------------- взамен ----------- дополнительный нижний ряд --- 19 RA3PKJ
    gbs = wx.GridBagSizer(gap, gap) # --- двухмерная сетка
    self.gbs = gbs
    vertBox.Add(gbs, flag=wx.EXPAND)
    gbs.SetEmptyCellSize((5, 5)) # --- размер пустой ячейки сетки
    # Add the bottom spacer
    vertBox.AddSpacer(5) # Thanks to Christof, DJ4CM
    # End of vertical box.
    # ------------------------------------------- добавлено ----------- дополнительный нижний ряд --- 19 RA3PKJ
    self.widget_row = 0 # --- нижний дополнительный ряд
    self.button_start_col = 8 # --- начало дополнительного нижнего ряда

# окончательное создание всего окна программы (т.е. с кнопками)
    #--------------------------------------------- удалено -------------- на всю длину монитора ----- 33 RA3PKJ
    #minw = width = self.graph.width # minw - ограничитель минимальной длины
    #maxw = maxh = -1                # maxw - ограничитель максимальной длины
    maxh = -1#ограничитель максимальной высоты не установлен -- взамен -- на всю длину монитора ----- 33 RA3PKJ

    minh = 130 #ограничитель минимальной высоты -- изменено ------------- на всю длину монитора ----- 33 RA3PKJ
    # длина всего окна программы (т.е. с кнопками)
    if conf.window_width > 0:
      minw = width = maxw = conf.window_width
    # ------------------------------------------- добавлено ------------- на всю длину монитора ----- 33 RA3PKJ
    else:
      minw = width = maxw = self.screen_width # self.screen_width - разрешение монитора по горизонтали
# ------------------------------------------------ удалено -------------- на всю длину монитора ----- 33 RA3PKJ
##    # высота всего окна программы (т.е. с кнопками)
##    if conf.window_height > 0:
##      minh = maxh = self.height = conf.window_height
    # ----------------------------------------- добавлено --- запоминание высоты окна при выходе ---- 34 RA3PKJ
    try:
      self.height = configure.Settings[4]["QuiskHeight"]
    except:
      self.height = 500

    self.main_frame.SetSizeHints(minw, minh, maxw, maxh)
    self.main_frame.SetClientSize(wx.Size(width, self.height))

    # ----------------------------------------- добавлено ---------- запоминание позиции окна ------- 35 RA3PKJ
    try:
      self.quisk_posX = configure.Settings[4]["QuiskPositionX"]
      self.quisk_posY = configure.Settings[4]["QuiskPositionY"]
      self.main_frame.SetPosition(wx.Point(self.quisk_posX, self.quisk_posY))
    except:
      self.main_frame.SetPosition(wx.Point(0, 0))

    if hasattr(Hardware, 'pre_open'):       # pre_open() is called before open()
      Hardware.pre_open()

    # ------- установка нижнего ряда
    if self.local_conf.GetWidgets(self, Hardware, conf, frame, gbs, vertBox):
      pass
    elif conf.quisk_widgets:
      self.bottom_widgets = conf.quisk_widgets.BottomWidgets(self, Hardware, conf, frame, gbs, vertBox)

# --------------------------------------------------------------------- удалено ---------- дополнительный нижний ряд ------ 19 RA3PKJ
##    if self.bottom_widgets:		# Extend the sliders to the bottom of the screen
##      try:
##        i = self.bottom_widgets.num_rows_added		# No way to get total rows until ver 2.9 !!
##      except:
##        i = 1
##      rows = self.widget_row + i
##      for i in self.slider_columns:
##        item = gbs.FindItemAtPosition((0, i))
##        item.SetSpan((row, 1))

    self.OpenHardware()
    msg = QS.open_key(port=conf.quisk_serial_port, cts=conf.quisk_serial_cts, dsr=conf.quisk_serial_dsr)
    if msg:
      print(msg)

# ------------------------------------------------- добавлено ------------------- COM-порты для Odyssey ----- 63 RA3PKJ
    if self.cw_com_method == 1: # подключение paddle ключа через внешнюю CW программу
      self.ody_cw_thread1 = OdysseyCWThread1(self.cw_com_method)
      self.ody_cw_thread1.start()
    if self.cw_com_method == 2: # прямое подключение paddle ключа к Quisk через COM порт
      self.ody_cw_thread2 = OdysseyCWThread2(self.cw_com_method)
      self.ody_cw_thread2.start()

    self.OpenSound()
    tune, vfo = Hardware.ReturnFrequency()	# Request initial frequency
    if tune is None or vfo is None:		# Set last-used frequency
      self.bandBtnGroup.SetLabel(self.lastBand, do_cmd=True, direction=0)
    else:			# Set requested frequency
      self.BandFromFreq(tune)
      self.ChangeDisplayFrequency(tune - vfo, vfo)
    # Record filter rate for the filter screen
    self.filter_screen.sample_rate = QS.get_filter_rate(-1, -1)
    self.config_screen.InitBitmap()
    self.screenBtnGroup.SetLabel(conf.default_screen, do_cmd=True)
    frame.Show()
    self.Yield()
    self.sound_thread = SoundThread(self.samples_from_python)
    self.sound_thread.start()
    if self.samples_from_python:
      Hardware.StartSamples()
    if conf.dxClHost:
      # create DX Cluster and register listener for change notification
      self.dxCluster = dxcluster.DxCluster()
      self.dxCluster.start()
    # Create shortcut keys for buttons
    #if conf.button_layout == 'Large screen':# -- удалено -------------- удаление маленького экрана --------- 16 RA3PKJ
    for button in self.modeButns.GetButtons():	# mode buttons
      self.idName2Button[button.idName] = button
      if button.char_shortcut:
        rid = self.QuiskNewId()
        self.main_frame.Bind(wx.EVT_MENU, self.modeButns.Shortcut, id=rid)
        self.accel_list.append(wx.AcceleratorEntry(wx.ACCEL_ALT, ord(button.char_shortcut), rid))
    for button in self.bandBtnGroup.GetButtons():	# band buttons
      self.idName2Button[button.idName] = button
      if button.char_shortcut:
        rid = self.QuiskNewId()
        self.main_frame.Bind(wx.EVT_MENU, self.bandBtnGroup.Shortcut, id=rid)
        self.accel_list.append(wx.AcceleratorEntry(wx.ACCEL_ALT, ord(button.char_shortcut), rid))
# ----------------------------------------------- удалено -------------- удаление маленького экрана --------- 16 RA3PKJ
##    else:	# Small screen
##      for button in self.modeButns.GetButtons():	# mode buttons
##        self.idName2Button[button.idName] = self.modeButns
##      for button in self.bandBtnGroup.GetButtons():	# band buttons
##        self.idName2Button[button.idName] = self.bandBtnGroup
    self.main_frame.SetAcceleratorTable(wx.AcceleratorTable(self.accel_list))
    self.modeButns.SetLabel(self.mode, True)
  #  self.OnTestTimer(None)
    if hasattr(Hardware, 'post_open'):	# post_open() is called after open() and after sound is started
      Hardware.post_open()
    self.StartWsjtx()

    #--------------------------------------------------- удалено ------------- реформа крутилок ------------- 36 RA3PKJ
##    self.midiControls["Tune"]	= (None,		None)
##    self.midiControls["Vol"]	= (self.sliderVol,	self.ChangeVolume)
##    self.midiControls["STo"]	= (self.sliderSto,	self.ChangeSidetone)
##    self.midiControls["Rit"]	= (self.ritScale,	self.OnRitScale)
##    self.midiControls["Ys"]	= (self.sliderYs,	self.ChangeYscale)
##    self.midiControls["Yz"]	= (self.sliderYz,	self.ChangeYzero)
##    self.midiControls["Zo"]	= (self.sliderZo,	self.OnChangeZoom)
    #---------------------------------------------------- взамен ------------- реформа крутилок ------------- 36 RA3PKJ
    # нельзя заменить Rit на RIT, где-то возникает ошибка - по удалённому управлению не происходит движение крутилки на сервере (при этом сообщение о ошибке не появляется)
    self.midiControls["TxLevel"] = (self.sliderTxLevel, self.OnTxLevel) # --------------- добавлено -------- Вынос слайдера TxLevel в главное окно ---------- 41 RA3PKJ
    self.midiControls["DigiTx"] = (self.sliderDigiTxLev, self.OnDigiTxLev) # ------------ добавлено ----- Вынос слайдера Digital TxLevel в главное окно ----- 62 RA3PKJ
    self.midiControls["Vox"] = (self.sliderVOX, self.OnLevelVOX) # ---------------------- добавлено -------- Вынос слайдера VOX в главное окно -------------- 42 RA3PKJ
    self.midiControls["Compr"] = (self.CtrlTxAudioClip, self.OnTxAudioClip) # ----------- добавлено -------- Вынос слайдера Clip в главное окно ------------- 43 RA3PKJ
    self.midiControls["MicTone"] = (self.CtrlTxAudioPreemph, self.OnTxAudioPreemph) # --- добавлено -------- Вынос слайдера PreemPhasis в главное окно ------ 39 RA3PKJ
    self.midiControls["Tune"]	= (None,		None)
    self.midiControls["Volume"]	= (self.sliderVol,	self.ChangeVolume)
    self.midiControls["SideTone"]	= (self.sliderSto,	self.ChangeSidetone)
    self.midiControls["CwSpeed"]	= (self.sliderSpeed,	self.ChangeSpeed) # ----- добавлено ------------------- CW paddle --------------------------- 60 RA3PKJ
    self.midiControls["Rit"]	= (self.ritScale,	self.OnRitScale)
    self.midiControls["Yscale"]	= (self.sliderYs,	self.ChangeYscale)
    self.midiControls["Yshift"]	= (self.sliderYz,	self.ChangeYzero)
    self.midiControls["Zoom"]	= (self.sliderZo,	self.OnChangeZoom)


    bw = self.bottom_widgets
    if hasattr(bw, "sliderLNA"):
      self.midiControls["RfLna"]	= (bw.sliderLNA,	bw.OnLNA)
    self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyHook)
    return True
  def OnStartWsjtx(self, ctrl):
    method = ctrl.GetValue()
    if method[-3:] == "now":
      self.StartWsjtx(method, ctrl)
    else:
      self.local_conf.globals["start_wsjtx"] = method
      self.local_conf.settings_changed = True
  def StartWsjtx(self, method=None, ctrl=None):
    path = self.local_conf.globals.get('path_to_wsjtx', '')
    if not path:
      if sys.platform == 'win32':
        path = "C:\\WSJT\\wsjtx\\bin\\wsjtx.exe"
      else:
        path = "/usr/bin/wsjtx"
    cfg = self.local_conf.globals.get('config_wsjtx', '')
    rig = self.local_conf.globals.get('rig_name_wsjtx', 'quisk')
    if cfg:
      prog = [path, "--rig-name", rig, "--config", cfg]
    else:
      prog = [path, "--rig-name", rig]
    if method is None:
      method = self.local_conf.globals.get("start_wsjtx", "Never")
    if method == "Never":
      return
    if not os.path.isfile(path):
      self.wsjtx_wait = wx.BusyInfo("Path to WSJT-X was not found.")
      wx.CallLater(5000, self.StartWsjtxDone, None)
      if ctrl:
        ctrl.SetText("Never")
      return
    if method == "Main Rx0 on startup":
      self.wsjtx_process[0] = subprocess.Popen(prog, shell=False)
    elif method == "Main Rx0 now":
      if self.wsjtx_process[0] is None or self.wsjtx_process[0].poll() is not None:
        self.wsjtx_wait = wx.BusyInfo("Starting WSJT-X...")
        self.wsjtx_process[0] = subprocess.Popen(prog, shell=False)
      else:
        self.wsjtx_wait = wx.BusyInfo("WSJT-X was already started")
      wx.CallLater(5000, self.StartWsjtxDone, ctrl)
  def StartWsjtxDone(self, ctrl):
    del self.wsjtx_wait
    if ctrl:
      method = self.local_conf.globals.get("start_wsjtx", "Never")
      ctrl.SetText(method)
  #def OnTestTimer(self, event):		# temporary code to switch bands and look for a bug
  #  if event is None:
  #    self.test_time0 = 0
  #    self.test_band = '40'
  #    self.test_timer = wx.Timer(self)
  #    self.Bind(wx.EVT_TIMER, self.OnTestTimer)
  #    self.test_timer.Start(1000, oneShot=True)
  #    return
  #  self.bandBtnGroup.SetLabel(self.test_band, do_cmd=True)
  #  if self.test_band == '40':
  #    self.test_timer.Start(250, oneShot=True)
  #    self.test_band = '30'
  #  else:
  #    self.test_timer.Start(250, oneShot=True)
  #    self.test_band = '40'
  def OpenHardware(self):
    if conf.use_rx_udp and conf.use_rx_udp != 10:
      self.add_version = True		# Add firmware version to config text
    else:
      self.add_version = False
    if conf.use_rx_udp == 10:		# Hermes UDP protocol
      if conf.tx_ip == '':
        conf.tx_ip = Hardware.hermes_ip
      elif conf.tx_ip == 'disable':
        conf.tx_ip = ''
      if conf.tx_audio_port == 0:
        conf.tx_audio_port = conf.rx_udp_port
    elif conf.use_rx_udp:
      conf.rx_udp_decimation = 8 * 8 * 8
      if conf.tx_ip == '':
        conf.tx_ip = conf.rx_udp_ip
      elif conf.tx_ip == 'disable':
        conf.tx_ip = ''
      if conf.tx_audio_port == 0:
        conf.tx_audio_port = conf.rx_udp_port + 2
    # Open the hardware.  This must be called before open_sound().
    self.config_text = Hardware.open()
    if self.config_text:
      self.main_frame.SetConfigText(self.config_text)
    else:
      self.config_text = "Missing config_text"

  def MakeSoundDeviceList(self):
    # Create the list of capture and play devices (play, prefix, description, device, alsa_device, alsa_description).
    # Play is 1 for play, 0 for capture. Prefix is "alsa:", "pulse:", "wasapi:"
    self.sound_devices = []
    if sys.platform == 'win32':
      dev_capt, dev_play = QS.wasapi_sound_devices()
      for description, device, raw in dev_capt:
        if raw:
          self.sound_devices.append((0, 'wasapi:', description, device, '', ''))
      for description, device, raw in dev_play:
        if raw:
          self.sound_devices.append((1, 'wasapi:', description, device, '', ''))
    elif sys.platform == 'darwin':
      # Add PortAudio names
      dev_capt, dev_play = QS.portaudio_sound_devices()
      for name in dev_capt:
        self.sound_devices.append((0, 'portaudio:', name, name, '', ''))
      for name in dev_play:
        self.sound_devices.append((1, 'portaudio:', name, name, '', ''))
    else:
      # Add Alsa names
      dev_capt, dev_play = QS.alsa_sound_devices()
      for name in dev_capt:
        i = name.rfind(" (hw:")
        if i > 5:
          device = name[i + 2 : -1]
          description = name[0:i]
        else:	# should not happen
          device = name
          description = name
        self.sound_devices.append((0, 'alsa:', description, device, device, description))
      for name in dev_play:
        i = name.rfind(" (hw:")
        if i > 5:
          device = name[i + 2 : -1]
          description = name[0:i]
        else:	# should not happen
          device = name
          description = name
        self.sound_devices.append((1, 'alsa:', description, device, device, description))
    if QS.get_params("QUISK_HAVE_PULSEAUDIO"):
      # Add PulseAudio names
      self.sound_devices.append((0, 'pulse:', 'default', 'default', '', ''))
      self.sound_devices.append((1, 'pulse:', 'default', 'default', '', ''))
      dev_capt, dev_play = QS.pulseaudio_sound_devices()	# device, description, alsa description (alsa device) or ""
      for device, description, alsa in dev_capt:
        i = alsa.rfind(" (hw:")
        if i > 5:
          alsa_device = alsa[i + 2 : -1]
          alsa_description = alsa[0:i]
        else:
          alsa_device =  ''
          alsa_description =  ''
        self.sound_devices.append((0, 'pulse:', description, device, alsa_device, alsa_description))
      for device, description, alsa in dev_play:
        i = alsa.rfind(" (hw:")
        if i > 5:
          alsa_device = alsa[i + 2 : -1]
          alsa_description = alsa[0:i]
        else:
          alsa_device =  ''
          alsa_description =  ''
        self.sound_devices.append((1, 'pulse:', description, device, alsa_device, alsa_description))
    if conf.pulse_audio_verbose_output > 2:
      print ("Sound devices:")
      for play, prefix, description, device, alsa_device, alsa_description in self.sound_devices:
        print (prefix, play, description, ';', device, ';', alsa_device, ';', alsa_description, '.')
    # Create the list of sound card names
    self.dev_capt = ['']
    self.dev_play = ['']
    pulse_capt = []
    pulse_play = []
    for play, prefix, description, device, alsa_device, alsa_description in self.sound_devices:
      if sys.platform == 'win32':
        t = description
      elif alsa_device:
        t = "%s%s (%s)" % (prefix, description, alsa_device)
      else:
        t = "%s%s" % (prefix, description)
      if prefix == "pulse:":
        if "QuiskDigital" in t:		# Add these names selectively in configure.py
          pass
        elif play:
          pulse_play.append(t)
        else:
          pulse_capt.append(t)
      else:
        if play:
          self.dev_play.append(t)
        else:
          self.dev_capt.append(t)
    if QS.get_params("QUISK_HAVE_PULSEAUDIO"):
      self.dev_capt += pulse_capt
      self.dev_play += pulse_play
  def SetSoundDevices(self):
    # These are parallel to lists in sound.c: (conf name, is_play, index in sound.c)
    sound_cards = (
        ("name_of_sound_play",		1, 0),
        ("name_of_mic_play",		1, 1),
        ("digital_output_name",		1, 2),
        ("sample_playback_name",	1, 3),
        ("digital_rx1_name",		1, 4),
        ("digital_rx2_name",		1, 5),
        ("digital_rx3_name",		1, 6),
        ("digital_rx4_name",		1, 7),
        ("digital_rx5_name",		1, 8),
        ("digital_rx6_name",		1, 9),
        ("digital_rx7_name",		1, 10),
        ("digital_rx8_name",		1, 11),
        ("digital_rx9_name",		1, 12),
        ("name_of_sound_capt",		0, 0),
        ("microphone_name",		0, 1),
        ("digital_input_name",		0, 2)
        )
    # These must equal the enum in quisk.h
    DEV_DRIVER_NONE = 0
    DEV_DRIVER_PORTAUDIO = 1
    DEV_DRIVER_ALSA = 2
    DEV_DRIVER_PULSEAUDIO = 3
    DEV_DRIVER_DIRECTX = 4
    DEV_DRIVER_WASAPI = 5
    DEV_DRIVER_WASAPI2 = 6
    for name, is_play, index in sound_cards:
      value = getattr(conf, name)
      if not value:
        QS.set_sound_name(index, is_play, DEV_DRIVER_NONE, '', '')
        continue
      if sys.platform == 'win32':
        found_desc, found_dev, a_dev, a_desc = self.GetSoundDevice(is_play, value, "wasapi:")
        if not found_desc:
          found_desc = value
          found_dev = value
        if conf.use_fast_sound:
          if name in ("name_of_sound_play", "name_of_mic_play"):
            windows_driver = DEV_DRIVER_WASAPI2
          else:
            windows_driver = DEV_DRIVER_WASAPI
        else:
          windows_driver = DEV_DRIVER_DIRECTX
        QS.set_sound_name(index, is_play, windows_driver, found_desc, found_dev)
        if conf.pulse_audio_verbose_output > 2:
          print (name, "Windows driver %d" % windows_driver, found_desc, ';', found_dev)
        continue
      if value[0:9] == 'portaudio':
        QS.set_sound_name(index, is_play, DEV_DRIVER_PORTAUDIO, value, '')
        continue
      # strip off ending " (hw:1,0)"
      i = value.rfind(" (hw:")
      if i > 5:
        value = value[0:i]
      if value[0:6] == 'pulse:':
        # Pulse opens devices based only on the device. We must strip off the "pulse:".
        if value[6:].strip() == "default":
          found_desc = value
          found_dev = "default"
        else:
          found_desc, found_dev, a_dev, a_desc = self.GetSoundDevice(is_play, value[6:], "pulse:")
          if not found_desc:
            found_desc = value
            found_dev = value[6:].strip()
        QS.set_sound_name(index, is_play, DEV_DRIVER_PULSEAUDIO, found_desc, found_dev)
        if conf.pulse_audio_verbose_output > 2:
          print (name, "Pulse", found_desc, ';', found_dev)
        continue
      if value[0:5] == 'alsa:':
        # Alsa searches for the description if it starts with "alsa:"; else it opens the device name.
        found_desc, found_dev, a_dev, a_desc = self.GetSoundDevice(is_play, value[5:], "alsa:")
        if not found_desc:
          found_desc = value
          found_dev = value[5:]
        QS.set_sound_name(index, is_play, DEV_DRIVER_ALSA, found_desc, found_dev)
        if conf.pulse_audio_verbose_output > 2:
          print (name, "Alsa driver %d" % DEV_DRIVER_ALSA, found_desc, ';', found_dev)
        continue
      # No initial "alsa:", "pulse:", etc.
      found_desc, found_dev, a_dev, a_desc = self.GetSoundDevice(is_play, value, "pulse:")	# Look for a pulse name
      if not found_desc:
        a_dev = value
        a_desc = value
      QS.set_sound_name(index, is_play, DEV_DRIVER_ALSA, a_desc, a_dev)
      if conf.pulse_audio_verbose_output > 2:
        print (name, "Alsa driver %d" % DEV_DRIVER_ALSA, a_desc, ';', a_dev)
  def GetSoundDevice(self, in_play, in_value, in_prefix):
    if in_prefix == "pulse:" and in_value[0:10] == " Use name ":	# Convert null-sink names "pulse: Use name xxxx"
      dev = in_value[10:]
      if dev[-8:] == ".monitor":
        dev = dev[0:-8]
      else:
        dev = dev + ".monitor"
      found = [in_value[1:], dev, '', '']
      return found
    found = None
    partial = None
    for data in self.sound_devices:
      play, prefix, description, device, alsa_device, alsa_description = data
      if play != in_play:
        continue
      if prefix != in_prefix:
        continue
      if in_value == description or in_value == device:
        found = data
        break
      if in_value in description:
        partial = data
    if found:
      return found[2:]	# description, device, alsa_device, alsa_description
    elif partial:
      return partial[2:]
    else:
      return None, None, None, None
  def OpenSound(self):
    self.MakeSoundDeviceList()
    if hasattr(conf, 'mixer_settings'):
      for dev, numid, value in conf.mixer_settings:
        err_msg = QS.mixer_set(dev, numid, value)
        if err_msg:
          print("Mixer", err_msg)
    QS.capt_channels (conf.channel_i, conf.channel_q)
    QS.play_channels (conf.channel_i, conf.channel_q)
    QS.micplay_channels (conf.mic_play_chan_I, conf.mic_play_chan_Q)
    # Note: Subsequent calls to set channels must not name a higher channel number.
    #       Normally, these calls are only used to reverse the channels.
    self.SetSoundDevices()
    QS.open_sound(0, conf.data_poll_usec, conf.latency_millisecs,
                conf.tx_ip, conf.tx_audio_port,
                conf.mic_sample_rate, conf.mic_channel_I, conf.mic_channel_Q,
				0.7, conf.mic_playback_rate)

  def OnIdle(self, event):
    if self.screen:
      self.screen.OnIdle(event)
  def OnEndSession(self, event):
    event.Skip()
    self.OnBtnClose(event)
  def OnBtnClose(self, event=None):
    #----------------------- добавлено -------------------------- выключение режима TX при закрытии программы -------------- 46 RA3PKJ
    self.close = True
    self.pttButton.SetValue(0, True)
    # -------------------------------------------------------------- добавлено ------- сохранение высоты окна при выходе --- 34 RA3PKJ
    l, self.quisk_height = self.main_frame.GetClientSize().Get() # получить размеры окна на момент закрытия программы
    # сохранение высоты
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    configure.Settings[4]["QuiskHeight"] = self.quisk_height  # сохранение высоты окна
    # -------------------------------------------------------------- добавлено ------------- запоминание позиции окна ------ 35 RA3PKJ
    self.quisk_posX, self.quisk_posY = self.main_frame.GetPosition()
    configure.Settings[4]["QuiskPositionX"] = self.quisk_posX  # сохранение позиции X окна
    configure.Settings[4]["QuiskPositionY"] = self.quisk_posY  # сохранение позиции Y окна
    configure.Settings[4]["Speed_CW"] = Hardware.speed_cw # --------- добавлено ------------------- CW paddle -------------- 60 RA3PKJ

    configure.Settings[4]["CwComMethod"] = self.cw_com_method # ----- добавлено -------------- COM-порты для Odyssey ------- 63 RA3PKJ

    # ----------------------------------------------------------------------------------------------------------- 34 RA3PKJ, 35 RA3PKJ
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False

    # --------------------------------------------------------------- добавлено ---------------- COM-порты для Odyssey ----- 63 RA3PKJ
    try:
      if self.ody_cw_thread1:
        self.ody_cw_thread1.stop()
    except:
      pass
    try:
      if self.ody_cw_thread2:
        self.ody_cw_thread2.stop()
    except:
      pass

    msg = QS.GetQuiskPrintf()
    if msg:
      print(msg, end='')
    QS.close_key()
    QS.set_file_name(record_button=0)	# Turn off file recording
    time.sleep(0.1)
    if self.sound_thread:
      if self.samples_from_python:
        Hardware.StopSamples()
      self.sound_thread.stop()
      for i in range(0, 20):
        if not self.sound_thread.is_alive():
          break
        time.sleep(0.1)
    self.sound_thread = None
    QS.close_rx_udp()
    Hardware.close()
    self.SaveState()
    self.local_conf.SaveState()
    if self.hamlib_socket:
      self.hamlib_socket.close()
      self.hamlib_socket = None
    if self.k4_tcp_socket:
      self.k4_tcp_socket.close()
      self.k4_tcp_socket = None
    if self.dxCluster:
      self.dxCluster.stop()
    if self.hamlib_com1_handler:
      self.hamlib_com1_handler.close()
    if self.hamlib_com2_handler:
      self.hamlib_com2_handler.close()

    # ------------------------------------------------ добавлено ------------------------------- CAT --------------------------- 49 RA3PKJ
    if self.hamlib_com3_handler:
      self.hamlib_com3_handler.close()

    # ------------------------------------------------ изменено -------------------------- инициализация скрытых кнопок -------- 18 RA3PKJ
    # if conf.add_freedv_button:
    QS.freedv_close()

    msg = QS.GetQuiskPrintf()
    if msg:
      print(msg, end='')

  def OnBtnOnOff(self, event):
    if event.GetEventObject().GetValue():	# Start samples
      try:
        wx.BeginBusyCursor()
        time.sleep(2.0)		# delay needed to release sound devices
        self.OnInit()
      finally:
        wx.EndBusyCursor()
    else:	# Stop samples
      try:
        wx.BeginBusyCursor()
        self.OnBtnClose()
        time.sleep(2.0)		# delay needed to release sound devices
      finally:
        wx.EndBusyCursor()
  def FixAmplPhase(self):
    # Convert from [[VFO, freq, ampl, phase], ...] to [[VFO, [[freq, ampl, phase], ...]], ...]
    self.bandAmplPhase["Version"] = {'rx':[]}	# marker for new format
    for band in self.bandAmplPhase:
      if not isinstance(self.bandAmplPhase[band], dict):
        self.bandAmplPhase[band] = {}
      try:
        for rx_tx in self.bandAmplPhase[band]:
          if rx_tx in ('rx', 'tx'):
            data = self.bandAmplPhase[band][rx_tx]
            if data and not isinstance(data[0][1], (list, tuple)):
              lst = []
              for vfo, freq, am, ph in data:
                lst.append([vfo, [[freq, am, ph]]])
              self.bandAmplPhase[band][rx_tx] = lst
      except:
        traceback.print_exc()
        self.bandAmplPhase[band] = {}
  def FixAmplPhase2(self):	# New definition of phase
    if self.bandAmplPhase["Version"]["rx"] == [1]:
      return
    degrad = 360.0 / 2 / math.pi
    for band in self.bandAmplPhase:
      if band == "Version":
        continue
      for rx_tx in self.bandAmplPhase[band]:
        if rx_tx in ('rx', 'tx'):
          data = self.bandAmplPhase[band][rx_tx]
          for item in data:
            vfo = item[0]
            lst_framph = item[1]
            for framph in lst_framph:
              freq, am, ph = framph
              p = math.atan(math.tan(ph / degrad) / (1.0 + am))
              #print ("%5s %3s %8d %8d %8.4f %8.3f %8.3f" % (band, rx_tx, vfo, freq, am, ph, p * degrad))
              framph[2] = p * degrad
    self.bandAmplPhase["Version"]["rx"] = [1]
  def ImmediateChange(self, name):
    if name == "pulse_audio_verbose_output":
      value = getattr(conf, name)
      if value == 0:
        self.std_out_err.Show(False)
      else:
        self.std_out_err.Show(True)
    elif name == "quisk_serial_port":
      QS.open_key(port=conf.quisk_serial_port)
    elif name == "quisk_serial_cts":
      QS.open_key(cts=conf.quisk_serial_cts)
    elif name == "quisk_serial_dsr":
      QS.open_key(dsr=conf.quisk_serial_dsr)
    if hasattr(Hardware, "ImmediateChange"):
      Hardware.ImmediateChange(name)
    QS.ImmediateChange(name)
  def CheckState(self):		# check whether state has changed
    changed = False
    for n in self.StateNames:
      try:
        if getattr(self, n) != self.savedState[n]:
          changed = True
          break
      except:
        changed = True
        break
    return changed
  def SaveState(self):
    state = {}
    for n in self.StateNames:
      state[n] = v = getattr(self, n)
      self.savedState[n] = v
    path = os.path.join(self.QuiskFilesDir, 'quisk_init.json')
    try:
      fp = open(path, "w")
      json.dump(state, fp, indent=2)
      fp.close()
    except:
      pass #traceback.print_exc()
  def Mode2Filters(self, mode):		# return the list of filter bandwidths for each mode
    if mode in ('CWL', 'CWU'):
      return conf.FilterBwCW
    if mode in ('LSB', 'USB'):
      return conf.FilterBwSSB
    if mode == 'AM':
      return conf.FilterBwAM
    if mode in ('FM', 'DGT-FM', 'DGT-IQ'):
      return conf.FilterBwFM
    if mode in ('DGT-U', 'DGT-L'):
      return conf.FilterBwDGT
    if mode[0:4] == 'FDV-':
      return conf.FilterBwFDV
    if mode == 'IMD':
      return conf.FilterBwIMD
    if mode == 'EXT':
      return conf.FilterBwEXT
    return conf.FilterBwSSB
# ------------------------------------------------------------- удалено --------------- вынос из малого окошка -------------- 8 RA3PKJ
##  def OnSmeterRightDown(self, event):
##    try:
##      pos = event.GetPosition()		# works for right-click
##      self.smeter.TextCtrl.PopupMenu(self.smeter_menu, pos)
##    except:
##      btn = event.GetEventObject()	# works for button
##      btn.PopupMenu(self.smeter_menu, (0,0))
##  def OnSmeterMeterA(self, event):
##    self.smeter_avg_seconds = 1.0
##    self.smeter_usage = "smeter"
##    QS.measure_frequency(0)
##  def OnSmeterMeterB(self, event):
##    self.smeter_avg_seconds = 5.0
##    self.smeter_usage = "smeter"
##    QS.measure_frequency(0)
##  def OnSmeterFrequencyA(self, event):
##    self.smeter_usage = "freq"
##    QS.measure_frequency(2)
##  def OnSmeterFrequencyB(self, event):
##    self.smeter_usage = "freq"
##    QS.measure_frequency(10)
##  def OnSmeterAudioA(self, event):
##    self.smeter_usage = "audio"
##    QS.measure_audio(1)
##  def OnSmeterAudioB(self, event):
##    self.smeter_usage = "audio"
##    QS.measure_audio(5)
  def QuiskNewId(self):
    try:
      ref = wx.NewIdRef()
      self.NewIdList.append(ref)
      rid = ref.GetValue()
    except AttributeError:
      rid = wx.NewId()
    return rid
  def MakeAccel(self, button):
    rid = self.QuiskNewId()
    self.main_frame.Bind(wx.EVT_MENU, button.Shortcut, id=rid)
    self.accel_list.append(wx.AcceleratorEntry(wx.ACCEL_ALT, ord(button.char_shortcut), rid))

  # ---------------- ниже функция сделана заново ---------- удалено ----------- реформа кнопок ---- 12 RA3PKJ
  #def MakeButtons(self, frame, gbs):

  # -------------------------------------------------------- взамен ----------- реформа кнопок ---- 12 RA3PKJ
  def MakeButtons(self, frame):
    bh=25 # --- базовый размер высоты окошек частоты
    shortcuts = []

    # --- кнопка On/Off
    b_onoff = b = QuiskCheckbutton(frame, self.OnBtnOnOff, "On", color='#77C077')
    b_onoff.SetValue(True, do_cmd=False)
    self.idName2Button[b.idName] = b

    # --- первое окно частоты
    b_freqdisp = self.freqDisplay = FrequencyDisplay(frame, 99999, bh * 14 // 10)

    # --- окно ввода частоты (Frequency entry)
    e = wx.TextCtrl(frame, -1, '', size=(10, bh), style=wx.TE_PROCESS_ENTER)
    font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL, False, conf.quisk_typeface)
    e.SetFont(font)
    e.SetBackgroundColour(conf.color_entry)
    e.SetForegroundColour(conf.color_entry_txt)
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_freqenter = szr
    szr.Add(e, 1, flag=wx.ALIGN_CENTER_VERTICAL)
    frame.Bind(wx.EVT_TEXT_ENTER, self.FreqEntry, source=e)

    # --- кнопка A<>B
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в sizer
    b_vfoAB = szr
    self.vfoABButton = b = QuiskCheckbutton(frame, self.OnBtnVFOAB, "A<>B")
    self.idName2Button[b.idName] = b
    szr.Add(self.vfoABButton, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.vfoABButton.SetLabel("A<>B")
    self.vfoABButton.Enable(False)
    self.vfoABButton.Refresh()

    # --- второе окно частоты
    b_smeter = self.smeter = FrequencyDisplaySplitRX2(frame, 99999, bh * 14 // 10)

    # --- кнопка Влево (Band down)
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_bandupdown = szr
    #b = QuiskRepeatbutton(frame, self.OnBtnDownBand, conf.Xbtn_text_range_dn, # ------------- удалено -- засветка при зумировании - 31 RA3PKJ
    self.band_down = b = QuiskRepeatbutton(frame, self.OnBtnDownBand, conf.Xbtn_text_range_dn, #взамен -- засветка при зумировании - 31 RA3PKJ
             self.OnBtnUpDnBandDone, use_right=True)
    b.idName = "Band " + b.idName
    self.idName2Button[b.idName] = b
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    # --- кнопка Вправо (Band up)
    #b = QuiskRepeatbutton(frame, self.OnBtnUpBand, conf.Xbtn_text_range_up, # --------------- удалено -- засветка при зумировании - 31 RA3PKJ
    self.band_up = b = QuiskRepeatbutton(frame, self.OnBtnUpBand, conf.Xbtn_text_range_up, # -- взамен -- засветка при зумировании - 31 RA3PKJ
             self.OnBtnUpDnBandDone, use_right=True)
    b.idName = "Band " + b.idName
    self.idName2Button[b.idName] = b
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=1)

    # --- кнопка -5
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_minus5 = szr
    self.Fminus5 = b = QuiskPushbutton(frame, self.OnBtnFminus5, "-5")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fminus5, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fminus5.SetLabel("-5")
    self.Fminus5.Refresh()
    # --- кнопка -3
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_minus3 = szr
    self.Fminus3 = b = QuiskPushbutton(frame, self.OnBtnFminus3, "-3")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fminus3, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fminus3.SetLabel("-3")
    self.Fminus3.Refresh()
    # --- кнопка -1
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_minus1 = szr
    self.Fminus1 = b = QuiskPushbutton(frame, self.OnBtnFminus1, "-1")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fminus1, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fminus1.SetLabel("-1")
    self.Fminus1.Refresh()
    # --- кнопка -0.5
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_minus05 = szr
    self.Fminus05 = b = QuiskPushbutton(frame, self.OnBtnFminus05, "-0.5")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fminus05, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fminus05.SetLabel("-0.5")
    self.Fminus05.Refresh()
    # --- кнопка -F
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_down = szr
    self.Fdown = b = QuiskPushbutton(frame, self.OnBtnFdown, "-F")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fdown, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fdown.SetLabel("-F")
    self.Fdown.Refresh()
    # --- кнопка +F
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_up = szr
    self.Fup = b = QuiskPushbutton(frame, self.OnBtnFup, "+F")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fup, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fup.SetLabel("+F")
    self.Fup.Refresh()
    # --- кнопка +0.5
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_plus05 = szr
    self.Fplus05 = b = QuiskPushbutton(frame, self.OnBtnFplus05, "+0.5")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fplus05, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fplus05.SetLabel("+0.5")
    self.Fplus05.Refresh()
    # --- кнопка +1
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_plus1 = szr
    self.Fplus1 = b = QuiskPushbutton(frame, self.OnBtnFplus1, "+1")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fplus1, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fplus1.SetLabel("+1")
    self.Fplus1.Refresh()
    # --- кнопка +3
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_plus3 = szr
    self.Fplus3 = b = QuiskPushbutton(frame, self.OnBtnFplus3, "+3")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fplus3, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fplus3.SetLabel("+3")
    self.Fplus3.Refresh()
    # --- кнопка +5
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_f_plus5 = szr
    self.Fplus5 = b = QuiskPushbutton(frame, self.OnBtnFplus5, "+5")
    self.idName2Button[b.idName] = b
    szr.Add(self.Fplus5, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Fplus5.SetLabel("+5")
    self.Fplus5.Refresh()

    # --- кнопка Split
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в sizer
    b_newsplit = szr #дать своё имя образцу кнопки
    self.newsplitButton = b = QuiskCheckbutton(frame, self.OnBtnNewSplit, "Split") #создать экземпляр класса QuiskCheckbutton (находится в quisk_widgets.py)
    self.idName2Button[b.idName] = b
    szr.Add(self.newsplitButton, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.newsplitButton.SetLabel("Split")
    self.newsplitButton.Refresh()

    # --- кнопка LockRX
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_lockVFO_RX = szr
    self.lockVFOButton_RX = b = QuiskCheckbutton(frame, self.OnBtnLockVFO_RX, "LockRX")
    self.idName2Button[b.idName] = b
    szr.Add(self.lockVFOButton_RX, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.lockVFOButton_RX.SetLabel("LockRX")
    self.lockVFOButton_RX.Refresh()

    # --- кнопка LockTX
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_lockVFO = szr
    self.lockVFOButton_TX = b = QuiskCheckbutton(frame, self.OnBtnLockVFO_TX, "LockTX")
    self.idName2Button[b.idName] = b
    szr.Add(self.lockVFOButton_TX, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.lockVFOButton_TX.SetLabel("LockTX")
    self.lockVFOButton_TX.Refresh()

    # --- кнопка Step ------------------------------------ добавлено ----------- шаг перестройки ---- 30 RA3PKJ
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_step = szr
    #self.step_btn = b = QuiskPushbutton(frame, self.OnBtnStep, "Step")
    labels_step = ('Step 50', 'Step 100', 'Step 250', 'Step 500', 'Step 1kHz', 'Step 1', 'Step 10', 'Step 25')
    self.step_btn = b = QuiskCycleCheckbutton(frame, self.OnBtnStep, labels_step, conf.color_cycle_btn)
    self.idName2Button[b.idName] = b
    szr.Add(self.step_btn, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    try:
      self.freq_step = configure.Settings[4]["FrequencyStep"]
      if self.freq_step == 1:
        self.step_btn.SetLabel("Step 1")
      elif self.freq_step == 10:
        self.step_btn.SetLabel("Step 10")
      elif self.freq_step == 25:
        self.step_btn.SetLabel("Step 25")
      elif self.freq_step == 50:
        self.step_btn.SetLabel("Step 50")
      elif self.freq_step == 100:
        self.step_btn.SetLabel("Step 100")
      elif self.freq_step == 250:
        self.step_btn.SetLabel("Step 250")
      elif self.freq_step == 500:
        self.step_btn.SetLabel("Step 500")
      elif self.freq_step == 1000:
        self.step_btn.SetLabel("Step 1kHz")
      else:
        self.freq_step = 50
        self.step_btn.SetLabel("Step 50")
    except:
      self.freq_step = 50
      self.step_btn.SetLabel("Step 50")
    self.step_btn.Refresh()

    # --- кнопка Add RX
    self.multi_rx_menu = wx.Menu() # --- создание меню
    item = self.multi_rx_menu.AppendRadioItem(-1, 'Play only')
    self.Bind(wx.EVT_MENU, self.OnMultirxPlayBoth, item)
    item = self.multi_rx_menu.AppendRadioItem(-1, 'Play on left')
    self.Bind(wx.EVT_MENU, self.OnMultirxPlayLeft, item)
    item = self.multi_rx_menu.AppendRadioItem(-1, 'Play on right')
    self.Bind(wx.EVT_MENU, self.OnMultirxPlayRight, item)
    szr = wx.BoxSizer(wx.HORIZONTAL) # --- создание кнопки
    b_addrx = szr
    btn_addrx = QuiskPushbutton(frame, self.multi_rx_screen.OnAddReceiver, "Add Rx")
    btn_addrx = b = WrapMenu(btn_addrx, self.multi_rx_menu)
    self.idName2Button[b.idName] = b
    if not hasattr(Hardware, 'MultiRxCount'):
      btn_addrx.Enable(False)
    szr.Add(btn_addrx, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)

  # --- Frequency Save/Restore
    self.memory_menu = wx.Menu()
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_membtn = szr
    b = QuiskPushbutton(frame, self.OnBtnMemSave, conf.Xbtn_text_mem_add)
    self.idName2Button[b.idName] = b
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    b = self.memNextButton = QuiskPushbutton(frame, self.OnBtnMemNext, conf.Xbtn_text_mem_next)
    self.idName2Button[b.idName] = b
    b.Enable(False)
    self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightClickMemory, b)
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT, border=1)
    b = self.memDeleteButton = QuiskPushbutton(frame, self.OnBtnMemDelete, conf.Xbtn_text_mem_del)
    self.idName2Button[b.idName] = b
    b.Enable(False)
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=1)

    # ---- кнопки f_Before и f_After
    szr = wx.BoxSizer(wx.HORIZONTAL)    # add control to box sizer for centering
    b_short_freq = szr
    b = self.beforeButton = QuiskPushbutton(frame, self.OnBtnBefore, 'f_Before')
    self.idName2Button[b.idName] = b
    b.Enable(0)
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    b = self.afterButton = QuiskPushbutton(frame, self.OnBtnAfter, 'f_After')
    self.idName2Button[b.idName] = b
    b.Enable(0)
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=1)

    # ---- кнопки Favorites
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_fav = szr
    b = self.StationNewButton = QuiskPushbutton(frame, self.OnBtnFavoritesNew, conf.Xbtn_text_fav_add)
    self.idName2Button[b.idName] = b
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    b = self.StationNewButton = QuiskPushbutton(frame, self.OnBtnFavoritesShow, conf.Xbtn_text_fav_recall)
    self.idName2Button[b.idName] = b
    szr.Add(b, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=1)

    # --- кнопки File Record/Play
    b = self.btn_file_record = QuiskCheckbutton(frame, self.OnBtnFileRecord, 'File')
    self.idName2Button[b.idName] = b
    b = self.btnFilePlay = QuiskCheckbutton(frame, self.OnBtnFilePlay, conf.Xbtn_text_file_play)
    self.idName2Button[b.idName] = b
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_file = szr
    szr.Add(self.btn_file_record, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    szr.Add(self.btnFilePlay, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=1)

    # --- кнопки Temp Record and Playback
    b = self.btnTmpRecord = QuiskCheckbutton(frame, self.OnBtnTmpRecord, text=conf.Xbtn_text_rec)
    self.idName2Button[b.idName] = b
    b = self.btnTmpPlay = QuiskCheckbutton(frame, self.OnBtnTmpPlay, 'Back', use_right=True)
    self.idName2Button[b.idName] = b
    b.Enable(0)
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_tmprec = szr
    szr.Add(self.btnTmpRecord, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    szr.Add(self.btnTmpPlay, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=1)

    # --- кнопка RIT
    szr = wx.BoxSizer(wx.HORIZONTAL)	# add control to box sizer for centering
    b_rit = szr
    self.ritButton = b = QuiskCheckbutton(frame, self.OnBtnRit, "RIT")
    self.idName2Button[b.idName] = b
    szr.Add(self.ritButton, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.ritButton.SetLabel("RIT %d" % self.ritFreq)
    self.ritButton.Refresh()

# --------------------------------------------------------------------------------- реформа крутилок ---------------- 36 RA3PKJ
    # --- создание слайдеров

    self.sliderTxLevel = SliderBoxHH(frame, 'TxLevel', self.TxLevel, 0, 100, self.OnTxLevel, display=False, scale=1) # ---- добавлено --- Вынос слайдера TxLevel в главное окно ---------- 41 RA3PKJ
    self.DigiTxLev = conf.digital_tx_level
    self.sliderDigiTxLev = SliderBoxHH(frame, 'DigiTx', self.DigiTxLev, 0, 100, self.OnDigiTxLev, display=False, scale=1) # добавлено -- Вынос слайдера Digital TxLevel в главное окно --- 62 RA3PKJ
    # --------------------------------------------------------------------------------------------------------------------- добавлено --- Вынос слайдера VOX в главное окно -------------- 42 RA3PKJ
    self.sliderVOX = SliderBoxHH(frame, 'Vox', self.levelVOX, -40, 0, self.OnLevelVOX, display=False, scale=1)
    self.sliderVOX.SetValue(-40 - self.levelVOX) # --- сделана прямая зависимость

    self.CtrlTxAudioClip = SliderBoxHH(frame, 'Compr', 5, 0, 20, self.OnTxAudioClip, display=False, scale=1) # ------------ добавлено --- Вынос слайдера Clip в главное окно ------------- 43 RA3PKJ
    self.CtrlTxAudioPreemph = SliderBoxHH(frame, 'MicTone', 0, 0, 100, self.OnTxAudioPreemph, display=False, scale=1) # --- добавлено --- Вынос слайдера PreemPhasis в главное окно ------ 39 RA3PKJ

    self.sliderVol = SliderBoxHH(frame, 'Volume', self.volumeAudio, 0, 1000, self.ChangeVolume, display=False, scale=1)
    self.ChangeVolume()		# set initial volume level
    self.sliderSto = SliderBoxHH(frame, 'SideTone', self.sidetone_volume, 0, 1000, self.ChangeSidetone, display=False, scale=1)
    self.ChangeSidetone()
    self.sliderSpeed = SliderBoxHH(frame, 'CwSpeed', self.speed_cw, 10, 30, self.ChangeSpeed, display=False, scale=1) # ----- добавлено ------------------- CW paddle -------------------- 60 RA3PKJ
    self.sliderYs = SliderBoxHH(frame, 'Yscale', self.y_scale, 0, 160, self.ChangeYscale, display=False, scale=1)
    self.sliderYz = SliderBoxHH(frame, 'Yshift', self.y_zoom, 0, 160, self.ChangeYzero, display=False, scale=1)
    self.sliderZo = SliderBoxHH(frame, 'Zoom', self.zoom_control, 0, 1000, self.OnChangeZoom, display=False, scale=1)
    self.sliderZo.SetValue(0)
    self.ritScale = SliderBoxHH(frame, 'Rit', self.ritFreq, -2000, 2000, self.OnRitScale, display=False, scale=1)
# --------------------------------------------------------------------------------- реформа крутилок ---------------- 36 RA3PKJ

    # ------- не пошло в жизнь, а именно числовые значения, обозначение RIT и b.idName
    # --- создание слайдеров
    # --- display=True это показывать значение %d
##    self.sliderVol = b = SliderBoxHH(frame, 'Volume %d', self.volumeAudio, 0, 1000, self.ChangeVolume, display=True, scale=1)
##    b.idName = 'Volume'
##    self.idName2Button[b.idName] = b
##    self.ChangeVolume()		# set initial volume level
##    self.sliderSto = b = SliderBoxHH(frame, 'SideTone %d', self.sidetone_volume, 0, 1000, self.ChangeSidetone, display=True, scale=1)
##    b.idName = 'SideTone'
##    self.idName2Button[b.idName] = b
##    self.ChangeSidetone()
##    self.sliderYs = b = SliderBoxHH(frame, 'Yscale %d', self.y_scale, 0, 160, self.ChangeYscale, display=True, scale=1)
##    b.idName = 'Yscale'
##    self.idName2Button[b.idName] = b
##    self.sliderYz = b = SliderBoxHH(frame, 'Yshift %d', self.y_zoom, 0, 160, self.ChangeYzero, display=True, scale=1)
##    b.idName = 'Yshift'
##    self.idName2Button[b.idName] = b
##    self.sliderZo = b = SliderBoxHH(frame, 'Zoom %d', self.zoom_control, 0, 1000, self.OnChangeZoom, display=True, scale=1)
##    b.idName = 'Zoom'
##    self.idName2Button[b.idName] = b
##    self.sliderZo.SetValue(0)
##    self.ritScale = b = SliderBoxHH(frame, 'RIT %d', self.ritFreq, -2000, 2000, self.OnRitScale, display=True, scale=1)
##    b.idName = 'RIT'
##    self.idName2Button[b.idName] = b

    # получить при старте скорость CW из файла quisk_settings.py ---- добавлено ---------- CW paddle ---------- 60 RA3PKJ
    try:
      self.speed_cw = configure.Settings[4]["Speed_CW"]
    except:
      self.speed_cw = 18
    Hardware.speed_cw = self.speed_cw
    self.sliderSpeed.SetValue(self.speed_cw) # установить движок слайдера CWspeed

    # ----------------------------------------------- добавлено ------------------- COM-порты для Odyssey ----- 63 RA3PKJ
    try:
      self.cw_com_method = configure.Settings[4]["CwComMethod"]
    except:
      self.cw_com_method = 0

    # --- кнопки диапазонов
    for label in conf.bandLabels:
      if isinstance(label, (list, tuple)):
        label = label[0]
      shortcuts.append(conf.bandShortcuts.get(label, ''))
    self.bandBtnGroup = RadioButtonGroup(frame, self.OnBtnBand, conf.bandLabels, None, shortcuts)
    self.bandBtnGroup.idName = 'bandBtnGroup'
    band_buttons = self.bandBtnGroup.buttons

    # --- кнопка RX2
    self.splitButton = b_rx2 = b = QuiskCheckbutton(frame, self.OnBtnSplit, "RX2")
    self.idName2Button[b.idName] = b
    b.char_shortcut = 'l'
    self.MakeAccel(b)

    # --- кнопка Mute
    b = b_mute = QuiskCheckbutton(frame, self.OnBtnMute, text='Mute')
    self.idName2Button[b.idName] = b
    b.char_shortcut = 'u'
    self.MakeAccel(b) # --- связать горячую клавишу с кнопкой

    # -------------------------------------- удалено -------- реформа мышиного управления шторками ---------- 13 RA3PKJ
    # if conf.mouse_tune_method:		# Mouse motion changes the VFO frequency as in PowerSDR
      # self.splitButton.Enable(False)

    # --- кнопка NR2
    b = b_nr2 = QuiskCheckbutton(frame, self.OnBtnNR2, text='NR2')
    self.idName2Button[b.idName] = b
    if not self.wdsp.version:
      b.Enable(False)

    # --- кнопка AGC
    self.BtnAGC = agc = QuiskCheckbutton(frame, self.OnBtnAGC, 'AGC')
    agc.char_shortcut = 'G'
    self.MakeAccel(agc)
    b = b_agc = self.SliderAGC = WrapSlider(agc, self.OnBtnAGC, display=True)
    self.idName2Button[agc.idName] = b
    self.midiControls["AGCSlider"] = (b, None)
    b.SetDual(True)
    b.SetSlider(value_off=self.levelOffAGC, value_on=self.levelAGC)
    agc.SetValue(True, True)

    # --- кнопка Sqlch
    b = self.BtnSquelch = QuiskCheckbutton(frame, self.OnBtnSquelch, text='Sqlch')
    self.idName2Button[b.idName] = b
    b.char_shortcut = 'q'
    self.MakeAccel(b)
    self.sliderSquelch = b_sqlch = b = WrapSlider(b, self.OnBtnSquelch, display=True)
    self.midiControls["SqlchSlider"] = (self.sliderSquelch, None)
    self.idName2Button[b.idName] = b

    # --- кнопка NB(Noise Blanker)
    self.NB_menu = QuiskMenu("NB_menu")
    for t in ("NB 1", "NB 2", "NB 3"):
      self.NB_menu.AppendRadioItem(t, self.OnMenuNB, t == "NB 1")
    item = self.NB_menu.AppendRadioItem("SNB", self.OnMenuNB)
    if not self.wdsp.version:
      item.Enable(False)
    self.btnNB = QuiskCheckbutton(frame, self.OnBtnNB, text='NB 1')
    self.btnNB.char_shortcut = 'B'
    self.MakeAccel(self.btnNB)
    b_nb = b = WrapMenu(self.btnNB, self.NB_menu)
    self.idName2Button[b.idName] = b

    # --- кнопка Notch
    b_notch = b = QuiskCheckbutton(frame, self.OnBtnAutoNotch, text='Notch')
    self.idName2Button[b.idName] = b
    b.char_shortcut = 'h'
    self.MakeAccel(b)

    # --- кнопка Preamp
    try:
      preamp_labels = Hardware.preamp_labels # посмотреть есть ли для этой кнопки упоминание в файле оборудования
      szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в sizer
      b_preamp = szr #дать своё имя экземпляру кнопки
      self.preampButton = b = QuiskCheckbutton(frame, Hardware.OnBtnPreamp, "Preamp") #создать экземпляр класса QuiskCheckbutton (находится в quisk_widgets.py)
      self.idName2Button[b.idName] = b
      szr.Add(self.preampButton, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
      self.preampButton.SetLabel(preamp_labels)
      self.preampButton.Enable(True)
      self.preampButton.Refresh()
    except:
      pass

    # --- кнопки ATT
    try:
      gain_labels = Hardware.rf_gain_labels
    except:
      gain_labels = ()
    self.BtnRfGain = None
    if gain_labels:
      b_gain = b = self.BtnRfGain = QuiskCycleCheckbutton(frame, Hardware.OnButtonRfGain, gain_labels)
    else:
      b = b_gain = QuiskCheckbutton(frame, None, text='RfGain')
      b.Enable(False)
    self.idName2Button[b.idName] = b

    # --- кнопка Ant
    try:
      ant_labels = Hardware.antenna_labels
    except:
      ant_labels = ()
    if ant_labels:
      b_ant = b = QuiskCycleCheckbutton(frame, Hardware.OnButtonAntenna, ant_labels)
    else:
      b_ant = b = QuiskCheckbutton(frame, None, text='Ant')
      b.Enable(False)
    self.idName2Button[b.idName] = b

# ---- не нужно
##    # --- кнопка Color
##    if 0:	# Display a color chooser
##      b_color = QuiskRepeatbutton(frame, self.OnBtnColor, 'Color', use_right=True)
##    else:
##      b = b_color = QuiskCheckbutton(frame, None, text='Color')
##      b.Enable(False)

    # --- кнопка Test1
    b_test1 = b = self.test1Button = QuiskCheckbutton(frame, self.OnBtnTest1, 'Test 1', color=conf.color_test)
    self.idName2Button[b.idName] = b

    # --- кнопки скринов
    if self.rate_audio_fft:
      t = "Audio FFT"
    elif self.bandscope_clock:		# Hermes UDP protocol
      t = "Bscope"
    else:
      t = "RX Filter"
    labels = (('Graph', 'GraphP1', 'GraphP2'), ('WFall', 'WFallP1', 'WFallP2'), ('Scope', 'Scope'), t, 'Config', 'Hardware') # -- взамен -- кнопка Hardware --- 15 RA3PKJ
    self.screenBtnGroup = RadioButtonGroup(frame, self.OnBtnScreen, labels, conf.default_screen)
    row_screen = self.screenBtnGroup.GetButtons()
    self.screenBtnGroup.idName = "screenBtnGroup"

    # --- кнопка Tune
    bt = self.spotButton = QuiskCheckbutton(frame, self.OnBtnSpot, 'Tune', color=conf.color_test) # ---- изменено --- надписи на кнопках --- 20 RA3PKJ
    b = b_tune = WrapSlider(bt, self.OnBtnSpot, slider_value=self.levelSpot, display=True)
    self.idName2Button[b.idName] = b
    self.midiControls["SpotSlider"] = (b, None)
    if hasattr(Hardware, 'OnSpot'):
      bt.char_shortcut = 'o'
      self.MakeAccel(bt)
    else:
      b.Enable(False)

    # --- кнопка FDX
    b = b_fdx = QuiskCheckbutton(frame, self.OnBtnFDX, 'FDX', color=conf.color_test)
    self.idName2Button[b.idName] = b
    b.char_shortcut = 'X'
    self.MakeAccel(b)

    # --- кнопка PTT
    bt = b = QuiskCheckbutton(frame, self.OnButtonPTT, 'PTT', color='red')
    self.idName2Button[b.idName] = b
    self.pttButton = bt
    b = b_ptt = WrapIndicator(bt, "Tx", "white", 'red')
    self.pttButton.Tx = b

    # --- кнопка VOX
    b = b_vox = QuiskCheckbutton(frame, self.OnButtonVOX, 'VOX')
    self.idName2Button[b.idName] = b
    b.char_shortcut = 'V'
    self.MakeAccel(b)

    # --- кнопка CW Training
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_CWtrain = szr
    self.CWtrainButton = b = QuiskCheckbutton(frame, self.OnBtnCWtrain, "CW Training")
    self.idName2Button[b.idName] = b
    szr.Add(self.CWtrainButton, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.CWtrainButton.SetLabel("CW Training")
    self.CWtrainButton.Refresh()

    # ---- кнопки мод
    mode_names = ['CWL', 'CWU', 'LSB', 'USB', 'AM', 'FM', 'DGT-U', 'DGT-L', 'DGT-FM', 'DGT-IQ', 'FDV-U', 'FDV-L', 'IMD']
    labels = [('CWL', 'CWU'), ('LSB', 'USB'), 'AM', 'FM', ('DGT-U', 'DGT-L', 'DGT-FM', 'DGT-IQ')]
    shortcuts = ['C', 'S', 'A', 'M', 'D']
    count = 5	# There is room for seven buttons

    # ----------------------------------------------------- изменено -------------------------- инициализация скрытых кнопок -------- 18 RA3PKJ
    # if conf.add_freedv_button:
    n_freedv = count
    count += 1
    labels.append('FDV-U')
    shortcuts.append('F')

    n_imd = count
    count += 1
    labels.append('IMD')
    shortcuts.append('I')
    if count < 7 and conf.add_extern_demod:
      count += 1
      labels.append(conf.add_extern_demod)
      mode_names.append(conf.add_extern_demod)
      shortcuts.append('')
    while count < 7:
      count += 1
      labels.append('')
      shortcuts.append('')
    mode_names.sort()
    self.config_screen.favorites.SetModeEditor(mode_names)
    self.modeButns = RadioButtonGroup(frame, self.OnBtnMode, labels, None, shortcuts)
    self.modeButns.buttons[0].idName = "CW U/L"
    self.modeButns.buttons[1].idName = "SSB U/L"
    self.modeButns.buttons[4].idName = "DGT"
    self.modeButns.idName = "modeButns"
    self.freedv_menu_items = {}

# ------------------------------------------------------------- изменено ---------------- инициализация скрытых кнопок ---- 18 RA3PKJ
# ================================================================================================================================
    # if conf.add_freedv_button:
    self.freedv_menu = QuiskMenu("freedv_menu")
    msg = conf.freedv_tx_msg
    QS.freedv_set_options(mode=conf.freedv_modes[0][1], tx_msg=msg, DEBUG=0, squelch=1)
    self.freedv_menu.AppendCheckItem("Monitor", self.OnFreedvMonitor)
    self.freedv_menu.AppendSeparator()
    for mode, index in conf.freedv_modes:
      item = self.freedv_menu.AppendRadioItem(mode, self.OnFreedvMenu, mode == self.freedv_mode)
      self.freedv_menu_items[index] = item
      if mode == self.freedv_mode:	# Restore mode
        QS.freedv_set_options(mode=index)
      if mode in ("Mode 2020", "Mode 2400A", "Mode 2400B"):
        item.Enable(False)
# -------------------------------------------------------------- удалено ----------------- удаление маленького экрана ----- 16 RA3PKJ
##    if conf.button_layout == 'Large screen':
##      b = QuiskCycleCheckbutton(frame, None, ('FDV-U', 'FDV-L'), is_radio=True)
##      b.idName = "FDV"
##      b.char_shortcut = 'F'
##      self.btnFreeDV = WrapMenu(b, self.freedv_menu)
##      self.modeButns.ReplaceButton(n_freedv, self.btnFreeDV)
##    else:
##      self.btnFreeDV = self.modeButns.AddMenu('FDV-U', self.freedv_menu)
# -------------------------------------------------------------- взамен  ----------------- удаление маленького экрана ----- 16 RA3PKJ
    b = QuiskCycleCheckbutton(frame, None, ('FDV-U', 'FDV-L'), is_radio=True)
    b.idName = "FDV"
    b.char_shortcut = 'F'
    self.btnFreeDV = WrapMenu(b, self.freedv_menu)
    self.modeButns.ReplaceButton(n_freedv, self.btnFreeDV)

    try:
      ok = QS.freedv_open()
    except:
      traceback.print_exc()
      ok = 0
    if not ok:
      # conf.add_freedv_button = False # ------------------------ удалено ---------------- инициализация скрытых кнопок ---- 18 RA3PKJ
      self.modeButns.GetButtons()[n_freedv].Enable(0)
# ================================================================================================================================

    val = 500
    QS.set_imd_level(val)
    b = QuiskCheckbutton(frame, None, 'IMD', color=conf.color_test)
    b.char_shortcut = 'I'
    b = WrapSlider(b, self.OnImdSlider, slider_value=val, display=True)
    self.midiControls["IMDSlider"] = (b, None)
    self.modeButns.ReplaceButton(n_imd, b)

    # --- кнопка Help -------- добавлено --- реформа кнопок ---- 12 RA3PKJ
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_Help = szr
    self.Help = QuiskPushbutton(frame, self.OnBtnHelp, "Help")
    szr.Add(self.Help, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.Help.SetLabel("Help")
    self.Help.Refresh()

    # --- кнопки полосы
    labels = ('2000', '2000', '2000', '2000', '2000', '2000')
    self.filterButns = RadioButtonGroup(frame, self.OnBtnFilter, labels, None) # --- создание ряда кнопок полос
    self.filterButns.idName = "filterButns"
    b = QuiskCheckbutton(frame, None, str(self.filterAdjBw1))
    b = WrapSlider(b, self.OnBtnAdjFilter, slider_value=self.filterAdjBw1, wintype='filter')
    self.midiControls["Filter 6Slider"] = (b, None)
    self.filterButns.ReplaceButton(5, b)
    row_width = self.filterButns.GetButtons()

    # --- кнопка SSB RX Offset---------------------------------------- добавлено ------- SSB RX Offset ------ 29 RA3PKJ
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_ssb_offset = szr
    labels_ssb_offset = ('SSBrx Low=200Hz', 'SSBrx Low=250Hz', 'SSBrx Low=300Hz', 'SSBrx Low=0Hz', 'SSBrx Low=50Hz', 'SSBrx Low=100Hz', 'SSBrx Low=150Hz')
    self.ssb_offset = b = QuiskCycleCheckbutton(frame, self.OnBtnOffset, labels_ssb_offset, conf.color_cycle_btn)
    self.idName2Button[b.idName] = b
    szr.Add(self.ssb_offset, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.ssb_offset.Enable(False)
    if self.mode in ('LSB','USB'): # -------------------- срабатывает при запуске программы (потом не работает)
      self.ssb_offset.Enable(True)
    try:
      self.offset = configure.Settings[4]["offset_SSB_bandwidth"]
      if self.offset == 300:
        self.ssb_offset.SetLabel("SSBrx Low=300Hz")
      elif self.offset == 250:
        self.ssb_offset.SetLabel("SSBrx Low=250Hz")
      elif self.offset == 200:
        self.ssb_offset.SetLabel("SSBrx Low=200Hz")
      elif self.offset == 150:
        self.ssb_offset.SetLabel("SSBrx Low=150Hz")
      elif self.offset == 100:
        self.ssb_offset.SetLabel("SSBrx Low=100Hz")
      elif self.offset == 50:
        self.ssb_offset.SetLabel("SSBrx Low=50Hz")
      elif self.offset == 0:
        self.ssb_offset.SetLabel("SSBrx Low=0Hz")
      else:
        self.offset = 200
        self.ssb_offset.SetLabel("SSBrx Low=200Hz")
    except:
      self.offset = 200
      self.ssb_offset.SetLabel("SSBrx Low=200Hz")
    self.ssb_offset.Refresh()

    # --- кнопка SSBtx Low-------------------------------------- добавлено --------------- Кнопка SSBtx Low ------------ 45 RA3PKJ
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_ssb_offset_tx = szr
    labels_ssb_offset_tx = ('SSBtx Low=200Hz', 'SSBtx Low=250Hz', 'SSBtx Low=300Hz', 'SSBtx Low=0Hz', 'SSBtx Low=50Hz', 'SSBtx Low=100Hz', 'SSBtx Low=150Hz')
    self.ssb_offset_tx = b = QuiskCycleCheckbutton(frame, self.OnBtnOffsetTX, labels_ssb_offset_tx, conf.color_cycle_btn)
    self.idName2Button[b.idName] = b
    szr.Add(self.ssb_offset_tx, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.ssb_offset_tx.Enable(False)
    if self.mode in ('LSB','USB'): # -------------------- срабатывает при запуске программы (потом не работает)
      self.ssb_offset_tx.Enable(True)
    try:
      self.offset_tx = configure.Settings[4]["offset_SSB_bandwidthTX"]
      if self.offset_tx == 300:
        self.ssb_offset_tx.SetLabel("SSBtx Low=300Hz")
        QS.set_ssb_low(300)
      elif self.offset_tx == 250:
        self.ssb_offset_tx.SetLabel("SSBtx Low=250Hz")
        QS.set_ssb_low(250)
      elif self.offset_tx == 200:
        self.ssb_offset_tx.SetLabel("SSBtx Low=200Hz")
        QS.set_ssb_low(200)
      elif self.offset_tx == 150:
        self.ssb_offset_tx.SetLabel("SSBtx Low=150Hz")
        QS.set_ssb_low(150)
      elif self.offset_tx == 100:
        self.ssb_offset_tx.SetLabel("SSBtx Low=100Hz")
        QS.set_ssb_low(100)
      elif self.offset_tx == 50:
        self.ssb_offset_tx.SetLabel("SSBtx Low=50Hz")
        QS.set_ssb_low(50)
      elif self.offset_tx == 0:
        self.ssb_offset_tx.SetLabel("SSBtx Low=0Hz")
        QS.set_ssb_low(0)
      else:
        self.offset_tx = 200
        self.ssb_offset_tx.SetLabel("SSBtx Low=200Hz")
        QS.set_ssb_low(200)
    except:
      self.offset_tx = 200
      self.ssb_offset_tx.SetLabel("SSBtx Low=200Hz")
      QS.set_ssb_low(200)
    self.ssb_offset_tx.Refresh()

    # --- кнопка Picture --------------------------- добавлено ---------- картинка на панораме ------- 5 RA3PKJ
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_picture = szr
    self.picture = b = QuiskPushbutton(frame, self.OnBtnPicture, "Picture")
    self.idName2Button[b.idName] = b
    szr.Add(self.picture, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.picture.SetLabel("Picture")
    self.picture.Refresh()
    # --- при старте загрузить картинку
    try:
      self.picture_bmp = configure.Settings[4]["Picture"]
    except:
      self.picture_bmp = "Pano_1.jpg"
    # --- найти все картинки
    import glob
    picture_files = '*.jpg'
    for file in glob.glob(picture_files, recursive=True):
      self.picture_list.append(file)
    self.picture_len = len(self.picture_list)
    try:
      self.picture_index = self.picture_list.index(self.picture_bmp)
    except:
      self.picture_bmp = "Pano_1.jpg"
      self.picture_index = self.picture_list.index(self.picture_bmp)
    self.picture.SetLabel("Picture " + str(self.picture_index + 1))

    # --- кнопка Palette
    szr = wx.BoxSizer(wx.HORIZONTAL) # вставить в Sizer
    b_Palette = szr
    self.PaletteButton = b = QuiskPushbutton(frame, self.OnBtnWaterFallPalette, "Palette")
    self.idName2Button[b.idName] = b
    szr.Add(self.PaletteButton, 1, flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=1)
    self.PaletteButton.SetLabel("Palette")
    self.PaletteButton.Refresh()

    color = 'yellow'

    # -------------------- установка кнопок и окошек в сайзер bs0
    self.bs0.Add(b_onoff, wx.EXPAND)
    self.bs0.Add(b_freqdisp, wx.EXPAND)
    self.bs0.Add(b_freqenter, wx.EXPAND)
    self.bs0.Add(b_vfoAB, wx.EXPAND)
    self.bs0.Add(b_smeter, wx.EXPAND)
    self.bs0.Add(b_bandupdown, wx.EXPAND)
    self.bs0.Add(b_f_minus5, wx.EXPAND)
    self.bs0.Add(b_f_minus3, wx.EXPAND)
    self.bs0.Add(b_f_minus1, wx.EXPAND)
    self.bs0.Add(b_f_minus05, wx.EXPAND)
    self.bs0.Add(b_f_down, wx.EXPAND)
    self.bs0.Add(b_f_up, wx.EXPAND)
    self.bs0.Add(b_f_plus05, wx.EXPAND)
    self.bs0.Add(b_f_plus1, wx.EXPAND)
    self.bs0.Add(b_f_plus3, wx.EXPAND)
    self.bs0.Add(b_f_plus5, wx.EXPAND)

    # -------------------- установка кнопок и окошек в сайзер bs0a
    text = wx.StaticText(frame, label="Frequency Memory")
    text.SetForegroundColour(color)
    self.bs0a.Add(text)
    self.bs0a.AddSpacer(3)
    self.bs0a.Add(b_membtn, wx.EXPAND)
    self.bs0a.AddSpacer(11)
    text = wx.StaticText(frame, label="Short Freq Mem")
    text.SetForegroundColour(color)
    self.bs0a.Add(text)
    self.bs0a.AddSpacer(3)
    self.bs0a.Add(b_short_freq, wx.EXPAND)
    self.bs0a.AddSpacer(11)
    self.bs0a.Add(b_newsplit, wx.EXPAND)
    self.bs0a.Add(b_lockVFO, wx.EXPAND)
    self.bs0a.Add(b_lockVFO_RX, wx.EXPAND)
    self.bs0a.Add(b_step, wx.EXPAND)
    self.bs0a.AddSpacer(10)
    self.bs0a.Add(b_addrx, wx.EXPAND)

    # ----------------------------- установка кнопок в сайзер bs1
    text = wx.StaticText(frame, label="Favorites")
    text.SetForegroundColour(color)
    self.bs1.Add(text)
    self.bs1.AddSpacer(3)
    self.bs1.Add(b_fav, wx.EXPAND)
    self.bs1.AddSpacer(11)
    text = wx.StaticText(frame, label="File Save")
    text.SetForegroundColour(color)
    self.bs1.Add(text)
    self.bs1.AddSpacer(3)
    self.bs1.Add(b_file, wx.EXPAND)
    self.bs1.AddSpacer(11)
    text = wx.StaticText(frame, label="Record")
    text.SetForegroundColour(color)
    self.bs1.Add(text)
    self.bs1.AddSpacer(3)
    self.bs1.Add(b_tmprec, wx.EXPAND)
    self.bs1.AddSpacer(11)
    text = wx.StaticText(frame, label="RIT")
    text.SetForegroundColour(color)
    self.bs1.Add(text)
    self.bs1.AddSpacer(3)
    self.bs1.Add(b_rit, wx.EXPAND)

    # -------------------------- установка слайдеров в сайзер bs2
    self.bs2.AddSpacer(9)
    self.bs2.Add(self.sliderVol, wx.EXPAND)
    self.bs2.AddSpacer(10)
    self.bs2.Add(self.sliderTxLevel, wx.EXPAND) # ---------------------- добавлено ------------- Вынос слайдера TxLevel в главное окно --- 41 RA3PKJ
    self.bs2.AddSpacer(10)
    self.bs2.Add(self.sliderDigiTxLev, wx.EXPAND) # -------------------- добавлено ----------- Вынос слайдера DigiTxLev в главное окно --- 62 RA3PKJ
    self.bs2.AddSpacer(10)
    self.bs2.Add(self.sliderVOX, wx.EXPAND) # -------------------------- добавлено -------------- Вынос слайдера VOX в главное окно ------ 42 RA3PKJ
    self.bs2.AddSpacer(10)
    self.bs2.Add(self.CtrlTxAudioClip, wx.EXPAND) # -------------------- добавлено -------------- Вынос слайдера Clip в главное окно ----- 43 RA3PKJ
    self.bs2.AddSpacer(10)
    self.bs2.Add(self.ritScale, wx.EXPAND)

    # -------------------------- установка слайдеров в сайзер bs2a
    self.bs2a.AddSpacer(10)
    self.bs2a.Add(self.sliderSto, wx.EXPAND)
    self.bs2a.Add(self.sliderSpeed, wx.EXPAND)
    self.bs2a.AddSpacer(9)
    self.bs2a.Add(self.sliderYs, wx.EXPAND)
    self.bs2a.AddSpacer(10)
    self.bs2a.Add(self.sliderYz, wx.EXPAND)
    self.bs2a.AddSpacer(10)
    self.bs2a.Add(self.sliderZo, wx.EXPAND)
    self.bs2a.AddSpacer(10)
    self.bs2a.Add(self.CtrlTxAudioPreemph, wx.EXPAND) # ----------------- добавлено --------- Вынос слайдера PreemPhasis в главное окно --- 39 RA3PKJ

    # ----------------------------- установка кнопок в сайзер bs3
    text = wx.StaticText(frame, label="   Band")
    text.SetForegroundColour(color)
    self.bs3.Add(text)
    self.bs3.AddSpacer(1)
    for b in band_buttons[0:14]:
      self.idName2Button[b.idName] = b
      self.bs3.Add(b, wx.EXPAND)

    # ----------------------------- установка кнопок в сайзер bs4
    text = wx.StaticText(frame, label="       RX")
    text.SetForegroundColour(color)
    self.bs4.Add(text)
    self.bs4.AddSpacer(3)
    self.bs4.Add(b_rx2, wx.EXPAND)
    self.bs4.Add(b_mute, wx.EXPAND)
    self.bs4.Add(b_nr2, wx.EXPAND)
    self.bs4.Add(b_agc, wx.EXPAND)
    self.bs4.Add(b_sqlch, wx.EXPAND)
    self.bs4.Add(b_nb, wx.EXPAND)
    self.bs4.Add(b_notch, wx.EXPAND)
    try:
      preamp_labels = Hardware.preamp_labels # посмотреть есть ли для этой кнопки упоминание в файле оборудования
      self.bs4.Add(b_preamp, wx.EXPAND)
    except:
      pass
    self.bs4.Add(b_gain, wx.EXPAND)
    self.bs4.Add(b_ant, wx.EXPAND)
    #self.bs4.Add(b_color, wx.EXPAND) # --- не нужно
    self.bs4.Add(b_test1, wx.EXPAND)

    # ----------------------------- установка кнопок в сайзер bs5
    text = wx.StaticText(frame, label="Screen")
    text.SetForegroundColour(color)
    self.bs5.Add(text)
    self.bs5.AddSpacer(1)
    for i in range(0, 6):
      b = row_screen[i]
      self.bs5.Add(b, wx.EXPAND)
      self.idName2Button[b.idName] = b
    self.bs5.AddSpacer(11)
    text = wx.StaticText(frame, label="Transmit")
    text.SetForegroundColour(color)
    self.bs5.Add(text)
    self.bs5.AddSpacer(3)
    self.bs5.Add(b_tune, wx.EXPAND)
    self.bs5.Add(b_fdx, wx.EXPAND)
    self.bs5.Add(b_ptt, wx.EXPAND)
    self.bs5.Add(b_vox, wx.EXPAND)

    # ----------------------------- установка кнопок в сайзер bs6
    text = wx.StaticText(frame, label=" CW Training")
    text.SetForegroundColour(color)
    self.bs6.Add(text)
    #self.bs6.AddSpacer(3)
    self.bs6.Add(b_CWtrain, wx.EXPAND)
    text = wx.StaticText(frame, label=" Mode")
    text.SetForegroundColour(color)
    self.bs6.Add(text)
    self.bs6.AddSpacer(3)
    for b in  self.modeButns.GetButtons():
      self.idName2Button[b.idName] = b
      self.bs6.Add(b, wx.EXPAND)
    self.bs6.AddSpacer(11)
    text = wx.StaticText(frame, label="Help")
    text.SetForegroundColour(color)
    self.bs6.Add(text)
    self.bs6.AddSpacer(3)
    self.bs6.Add(b_Help, wx.EXPAND)

    # ----------------------------- установка кнопок в сайзер bs7
    text = wx.StaticText(frame, label="   Filter")
    text.SetForegroundColour(color)
    self.bs7.Add(text)
    self.bs7.AddSpacer(1)
    for i in range(0, 6):
      b = row_width[i]
      if isinstance(b, WrapSlider):
        b.button.idName = "Filter %d" % (i + 1)
      else:
        b.idName = "Filter %d" % (i + 1)
      self.idName2Button[b.idName] = b
      self.bs7.Add(b, wx.EXPAND)
    self.bs7.Add(b_ssb_offset, wx.EXPAND)
    self.bs7.Add(b_ssb_offset_tx, wx.EXPAND)
    self.bs7.AddSpacer(11)
    text = wx.StaticText(frame, label="Design")
    text.SetForegroundColour(color)
    self.bs7.Add(text)
    self.bs7.AddSpacer(2)
    self.bs7.Add(b_picture, wx.EXPAND)
    self.bs7.Add(b_Palette, wx.EXPAND)

    # ----------------------------- установка кнопок в сайзер bs8
    # ------- запасной ряд

  def MeasureAudioVoltage(self):
    # --------------------------------------------- добавлено ------------------- текстовая инфо на панораме для удалёнки ---------- 17 RA3PKJ
    if self.remote_control_head: # --------- Client (пользователь)
      i = 0
      aa = Hardware.GetSmeter()
      str_len = len(aa)
      i = aa.rfind('_')
      i = i + 1
      self.measure_audio_str = aa[i:str_len]
      return

    v = QS.measure_audio(-1)
    t = "%11.3f" % v
    # ------------------------------------------------------------ удалено ---------------------------- вынос из малого окошка ------ 8 RA3PKJ
    #t = t[0:1] + ' ' + t[1:4] + ' ' + t[4:] + ' uV'
    #self.smeter.SetLabel(t)
    self.measure_audio_str = t #строка напряжения аудио # --- взамен образована переменная ------------- вынос из малого окошка ----- 8 RA3PKJ
  def MeasureFrequency(self):
    vfo = Hardware.ReturnVfoFloat()
    if vfo is None:
      vfo = self.VFO
    vfo += Hardware.transverter_offset
# ------------------------- Не надо измерять частоту для второго окошка частоты ---- удалено ----------- вынос из малого окошка ----- 8 RA3PKJ
    #t = '%13.2f' % (QS.measure_frequency(-1) + vfo)
    #t = t[0:4] + ' ' + t[4:7] + ' ' + t[7:] + ' Hz'
    #self.smeter.SetLabel(t)
# ----------------------------------------------------------------- взамен ------------------------  реформа обоих окошек частоты --- 9 RA3PKJ
    # Всего лишь индикация частоты (и SNR) в обоих окошках частоты
    if self.mode in ('FDV-U', 'FDV-L'):
      self.freqDisplay.Display(self.txFreq + self.VFO, '#ECB129') # --- первое окошко частоты
      t = " SNR %3.0f" % self.snr #показать SNR freeDV
      self.smeter.Display_empty(t, '#ECB129') # ----------------------- второе окошко частоты
      self.freedv_flag = True
      return
    else: self.freedv_flag = False
    if self.newsplitButton.GetValue() or self.splitButton.GetValue(): # проверить нажата ли кнопка RX2 или кнопка Split
      self.freqDisplay.Display(self.rxFreq + self.VFO, '#00FF00') # --- первое окошко частоты
      self.smeter.Display(self.txFreq + self.VFO, '#FF5634') # -------- второе окошко частоты
      return
    self.freqDisplay.Display(self.txFreq + self.VFO, '#FF5634') # ----- первое окошко частоты
    self.smeter.Display_empty('-----', '#ECB129') # ------------------- второе окошко частоты

# ------------------------------------------------------------------ удалено -------------  реформа обоих окошек частоты ------------- 9 RA3PKJ
  #def NewDVmeter(self):
    #if conf.add_freedv_button:
      #snr = QS.freedv_get_snr()
      #txt = QS.freedv_get_rx_char()
      #self.graph.ScrollMsg(txt)
      #self.waterfall.ScrollMsg(txt)
    #else:
      #snr = 0.0
    #t = "  SNR %3.0f" % snr
    #self.smeter.SetLabel(t)
# ------------------------------------------------------------------- взамен -------------  реформа обоих окошек частоты ------------- 9 RA3PKJ
  def NewDVmeter(self):
    #if conf.add_freedv_button:# ------------------------------------ изменено ------------ инициализация скрытых кнопок ------------ 18 RA3PKJ
    self.snr = QS.freedv_get_snr()
    txt = QS.freedv_get_rx_char()
    self.graph.ScrollMsg(txt)
    self.waterfall.ScrollMsg(txt)
    # else:
      # self.snr = 0.0

# -------------------------------- удалена функция ----------------------------------------------------- расчёт S-метра -------------- 6 RA3PKJ
##  def NewSmeter(self):
##    self.smeter_db_count += 1		# count for average
##    x = QS.get_smeter()
##    self.smeter_db_sum += x		# sum for average
##    if self.timer - self.smeter_db_time0 > self.smeter_avg_seconds:		# average time reached
##      self.smeter_db = self.smeter_db_sum / self.smeter_db_count
##      self.smeter_db_count = self.smeter_db_sum = 0
##      self.smeter_db_time0 = self.timer
##    if self.smeter_sunits < x:		# S-meter moves to peak value
##      self.smeter_sunits = x
##    else:			# S-meter decays at this time constant
##      self.smeter_sunits -= (self.smeter_sunits - x) * (self.timer - self.smeter_sunits_time0)
##    self.smeter_sunits_time0 = self.timer
##    s = self.smeter_sunits / 6.0	# change to S units; 6db per S unit
##    s += Hardware.correct_smeter	# S-meter correction for the gain, band, etc.
##    if s < 0:
##      s = 0
##    if s >= 9.5:
##      s = (s - 9.0) * 6
##      t = "  S9+%2.0f %7.2f dB" % (s, self.smeter_db)
##    else:
##      t = "  S%.0f  %7.2f dB" % (s, self.smeter_db)
##    self.smeter.SetLabel(t)
# ---------------------------------- добавлена взамен функция ------------------- changed by rolin ------ расчёт S-метра ------------- 6 RA3PKJ
  def NewSmeter(self):
    # --------------------------------------------- добавлено -------------------- текстовая инфо на панораме для удалёнки ---------- 17 RA3PKJ
    if self.remote_control_head: # --------- Client (пользователь)
      i = 0
      ii = 0
      aa = Hardware.GetSmeter()
      i = aa.find('_')
      smeter_sunits_str = aa[0:i]
      i = i + 1
      str_len = len(aa)
      ab = aa[i:str_len]
      i = ab.find('_')
      smeter_db_str = ab[0:i]
      try:
        self.smeter_sunits = float(smeter_sunits_str)
      except:
        pass
      try:
        self.smeter_db = float(smeter_db_str)
      except:
        pass
      return

    self.smeter_db_count += 1		# count for average
    try:
      if Hardware.rf_gain == None:
        x = QS.get_smeter() + Hardware.correct_smeter
      #else: x = QS.get_smeter() + Hardware.correct_smeter - Hardware.rf_gain # S-meter correction for the gain, band, etc # --------------------------- удалено --------- кнопки Pre и ATT --------- 57 RA3PKJ
      else: x = QS.get_smeter() + Hardware.correct_smeter - Hardware.rf_gain - Hardware.preamp_gain # S-meter correction for the gain, band, etc. # ---- взамен ---------- кнопки Pre и ATT --------- 57 RA3PKJ
    except:
      x = QS.get_smeter() + Hardware.correct_smeter  # S-meter correction for the gain, band, etc.
    self.smeter_db_sum += x		# sum for average
    if self.timer - self.smeter_db_time0 > self.smeter_avg_seconds:		# average time reached
      self.smeter_db = self.smeter_db_sum / self.smeter_db_count
      self.smeter_db_count = self.smeter_db_sum = 0
      self.smeter_db_time0 = self.timer
    if self.smeter_sunits < x:		# S-meter moves to peak value
      self.smeter_sunits = x
    else:			# S-meter decays at this time constant
      self.smeter_sunits -= (self.smeter_sunits - x) * (self.timer - self.smeter_sunits_time0)
    self.smeter_sunits_time0 = self.timer

    s = self.smeter_sunits / 6.0	# change to S units; 6db per S unit
    self.hamlib_strength = (s - 9.0) * 6.0	# convert to dB; 0 dB is S9


# ------------------------------------ было у rolin -------- удалено ------------  вынос из малого окошка (s-метр) ------------ 8 RA3PKJ
##    if self.smeter_sunits < -127: # the start of S-scale is -127dbm
##      s = 0
##    else:
##      s = (self.smeter_sunits + 127) / 6.0
##    if s < 0:
##      s = 0
##    if s >= 9.5:
##      s = (s - 9.0) * 6
##      t = "  S9+%2.0f %7.2f dB" % (s, self.smeter_db)
##    else:
##      t = "  S%.0f  %7.2f dB" % (s, self.smeter_db)
##    self.smeter.SetLabel(t)

  def MakeFilterButtons(self, args):
    # Change the filter selections depending on the mode: CW, SSB, etc.
    # Do not change the adjustable filter buttons.
    buttons = self.filterButns.GetButtons()
    for i in range(0, len(buttons) - 1):
      label = str(args[i])
      buttons[i].SetLabel(label)
      buttons[i].Refresh()
      if label:
        buttons[i].Enable(1)
      else:
        buttons[i].Enable(0)
  def MakeFilterCoef(self, rate, N, bw, center):
    """Make an I/Q filter with rectangular passband."""
    center = abs(center)
    lowpass = bw * 24000 // rate // 2
    if lowpass in Filters:
      filtD = Filters[lowpass]
      #print ("Custom filter key %d rate %d bandwidth %d size %d" % (lowpass, rate, bw, len(filtD)))
    else:
      #print ("Window filter key %d rate %d bandwidth %d" % (lowpass, rate, bw))
      if N is None:
        shape = 1.5       # Shape factor at 88 dB
        trans = (bw / 2.0 / rate) * (shape - 1.0)     # 88 dB atten
        N = int(4.0 / trans)
        if N > 1000:
          N = 1000
        N = (N // 2) * 2 + 1
      K = bw * N // rate
      filtD = []
      pi = math.pi
      sin = math.sin
      cos = math.cos
      for k in range(-N//2, N//2 + 1):
        # Make a lowpass filter
        if k == 0:
          z = float(K) / N
        else:
          z = 1.0 / N * sin(pi * k * K / N) / sin(pi * k / N)
        # Apply a windowing function
        if 1:	# Blackman window
          w = 0.42 + 0.5 * cos(2. * pi * k / N) + 0.08 * cos(4. * pi * k / N)
        elif 0:	# Hamming
          w = 0.54 + 0.46 * cos(2. * pi * k / N)
        elif 0:	# Hanning
          w = 0.5 + 0.5 * cos(2. * pi * k / N)
        else:
          w = 1
        z *= w
        filtD.append(z)
    if center:
      # Make a bandpass filter by tuning the low pass filter to new center frequency.
      # Make two quadrature filters.
      filtI = []
      filtQ = []
      tune = -1j * 2.0 * math.pi * center / rate
      NN = len(filtD)
      D = (NN - 1.0) / 2.0
      for i in range(NN):
        z = 2.0 * cmath.exp(tune * (i - D)) * filtD[i]
        filtI.append(z.real)
        filtQ.append(z.imag)
      return filtI, filtQ
    return filtD, filtD
  def SetFilterByMode(self, mode):
    index = self.modeFilter[mode]
    try:
      Lab = self.filterButns.buttons[index].GetLabel()
    except:
      Lab = self.filterButns.buttons[0].GetLabel()
    self.filterButns.SetLabel(Lab, True)
  def GetFilterCenter(self, mode, bandwidth):
    if mode in ('CWU', 'CWL'):
      center = max(conf.cwTone, bandwidth // 2)
    elif mode in ('LSB', 'USB'):
      #center = 300 + bandwidth // 2 # ----------------------------------- удалено ----------------- SSB Offset -------------- 29 RA3PKJ
      center = self.offset + bandwidth // 2 # ---------------------------- взамен ------------------ SSB Offset -------------- 29 RA3PKJ
    elif mode in ('AM',):
      center = 0
    elif mode in ('FM',):
      center = 0
    elif mode in ('DGT-U', 'DGT-L'):
      center = max(1500, bandwidth // 2)
    elif mode in ('DGT-IQ', 'DGT-FM'):
      center = 0
    elif mode in ('FDV-U', 'FDV-L'):
      if bandwidth <= 3000:
        center = 1500
      else:
        center = bandwidth // 2
    elif mode in ('IMD',):
      center = 300 + bandwidth // 2
    else:
      center = 300 + bandwidth // 2
    if mode in ('CWL', 'LSB', 'DGT-L', 'FDV-L'):
      center = - center
    return center
  def OnBtnAdjFilter(self, event):
    btn = event.GetEventObject()
    bw = int(btn.GetLabel())
    self.filterAdjBw1 = bw
    if self.filterButns.GetIndex() == 5:
      self.OnBtnFilter(event)
  def OnBtnFilter(self, event, bw=None):
    if event is None:	# called by application
      self.filterButns.SetLabel(str(bw))
    else:		# called by button
      btn = event.GetEventObject()
      bw = int(btn.GetLabel())
    index = self.filterButns.GetIndex()
    mode = self.mode
    frate = QS.get_filter_rate(Mode2Index.get(mode, 3), bw)
    bw = min(bw, frate // 2)
    self.filter_bandwidth = bw
    center = self.GetFilterCenter(mode, bw)
    # save and restore filter when changing modes
    if mode in ('CWU', 'CWL'):
      self.modeFilter['CW'] = index
    elif mode in ('LSB', 'USB'):
      self.modeFilter['SSB'] = index
    elif mode in ('AM',):
      self.modeFilter['AM'] = index
    elif mode in ('FM',):
      self.modeFilter['FM'] = index
    elif mode in ('DGT-U', 'DGT-L'):
      self.modeFilter['DGT'] = index
    elif mode in ('DGT-IQ', 'DGT-FM'):
      self.modeFilter['DGT'] = index
    elif mode in ('FDV-U', 'FDV-L'):
      self.modeFilter['FDV'] = index
    elif mode in ('IMD',):
      self.modeFilter['IMD'] = index
    filtI, filtQ = self.MakeFilterCoef(frate, None, bw, center)
    lower_edge = center - bw // 2
    QS.set_filters(filtI, filtQ, bw, lower_edge, 0)
    self.multi_rx_screen.graph.filter_mode = mode
    self.multi_rx_screen.graph.filter_bandwidth = bw
    self.multi_rx_screen.graph.filter_center = center
    self.multi_rx_screen.waterfall.pane1.filter_mode = mode
    self.multi_rx_screen.waterfall.pane1.filter_bandwidth = bw
    self.multi_rx_screen.waterfall.pane1.filter_center = center
    self.multi_rx_screen.waterfall.pane2.filter_mode = mode
    self.multi_rx_screen.waterfall.pane2.filter_bandwidth = bw
    self.multi_rx_screen.waterfall.pane2.filter_center = center
    if self.screen is self.filter_screen:
      self.screen.NewFilter()
  def OnFreedvMonitor(self, event):
    for item in self.freedv_menu.GetMenuItems():
      if item.GetKind() == wx.ITEM_CHECK:
        if item.IsChecked():
          QS.set_params(freedv_monitor=1)
        else:
          QS.set_params(freedv_monitor=0)
        break
  def OnFreedvMenu(self, event):
    text = ''
    for item in self.freedv_menu.GetMenuItems():
      kind = item.GetKind()
      if kind != wx.ITEM_RADIO:
        continue
      if item.IsChecked():
        text = item.GetItemLabel()
        break
    for mode, index in conf.freedv_modes:
      if mode == text:
        break
    else:
      print ("Failure in OnFreedvMenu")
      return
    mode = QS.freedv_set_options(mode=index)
    if mode == index:
      self.freedv_mode = text
    elif not self.remote_control_slave:		# change to new mode failed
      self.freedv_menu_items[mode].Check(1)
      pos = (self.width//2, self.height//2)
      if index == 8:
        dlg = wx.MessageDialog(self.main_frame, "Quisk does not install %s. Please install a system-wide codec2." % text, "FreeDV Modes", wx.OK, pos)
      else:
        dlg = wx.MessageDialog(self.main_frame, "No codec2 support for " + text, "FreeDV Modes", wx.OK, pos)
      dlg.ShowModal()
    else:
      self.freedv_menu_items[mode].Check(1)
      print ("FreeDV change mode failed.")
    self.OnChangeFilter()
  def OnChangeFilter(self):
    # Used by OnFreedvMenu because the FreeDV mode may change the filter sample rate
    bw = int(self.filterButns.GetLabel())
    # We can not use QS.get_filter_srate() because the FreeDV mode is not changed yet.
    if self.freedv_mode in ("Mode 2400A", "Mode 2400B"):
      frate = 48000;
    else:
      frate = 8000;
    bw = min(bw, frate // 2)
    self.filter_bandwidth = bw
    center = self.GetFilterCenter(self.mode, bw)
    filtI, filtQ = self.MakeFilterCoef(frate, None, bw, center)
    lower_edge = center - bw // 2
    QS.set_filters(filtI, filtQ, bw, lower_edge, 0)
    self.multi_rx_screen.graph.filter_bandwidth = bw
    self.multi_rx_screen.graph.filter_center = center
    self.multi_rx_screen.waterfall.pane1.filter_bandwidth = bw
    self.multi_rx_screen.waterfall.pane1.filter_center = center
    self.multi_rx_screen.waterfall.pane2.filter_bandwidth = bw
    self.multi_rx_screen.waterfall.pane2.filter_center = center
    if self.screen is self.filter_screen:
      self.screen.NewFilter()
  def OnBtnHelp(self, event):
    if event.GetEventObject().GetValue():
      self.OnBtnScreen(None, 'Help')
    else:
      self.OnBtnScreen(None, self.screenBtnGroup.GetLabel())
  def OnBtnScreen(self, event, name=None):
    if event is not None:
      win = event.GetEventObject()
      name = win.GetLabel()
    self.screen.Hide()
    self.station_screen.Hide()
    if name == 'Config':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.config_screen.FinishPages()
      self.screen = self.config_screen
    elif name[0:5] == 'Graph':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.screen = self.multi_rx_screen
      self.screen.ChangeRxZero(True)
      self.screen.SetTxFreq(self.txFreq, self.rxFreq)
      self.freqDisplay.Display(self.VFO + self.txFreq, '#ECB129') # --- добавлен цвет --- реформа обоих окошек частоты ---------- 9 RA3PKJ
      self.screen.PeakHold(name)
      self.station_screen.Show()
    elif name[0:5] == 'WFall':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.screen = self.multi_rx_screen
      self.screen.ChangeRxZero(False)
      self.screen.SetTxFreq(self.txFreq, self.rxFreq)
      self.freqDisplay.Display(self.VFO + self.txFreq, '#ECB129') # --- добавлен цвет --- реформа обоих окошек частоты ---------- 9 RA3PKJ
      self.screen.PeakHold(name)
      sash = self.screen.GetSashPosition()
      self.station_screen.Show()
    elif name == 'Scope':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      if win.direction:				# Another push on the same button
        self.scope.running = 1 - self.scope.running		# Toggle run state
      else:				# Initial push of button
        self.scope.running = 1
      self.screen = self.scope
    elif name == 'RX Filter':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.screen = self.filter_screen
      self.freqDisplay.Display(self.screen.txFreq, '#ECB129') # ------- добавлен цвет --- реформа обоих окошек частоты ---------- 9 RA3PKJ
      self.screen.NewFilter()
    elif name == 'Bscope':
      self.bandscope_flag = True # -------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.screen = self.bandscope_screen
      self.screen.SetTxFreq(self.txFreq, self.rxFreq)
    elif name == 'Audio FFT':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.screen = self.audio_fft_screen
      self.freqDisplay.Display(self.screen.txFreq, '#ECB129') # --- добавлен цвет ------- реформа обоих окошек частоты ---------- 9 RA3PKJ
    # -------------------------------------------------------------------------- удалено ------------- кнопка Hardware --------- 15 RA3PKJ
    #elif name == 'Help':
      #self.screen = self.help_screen
    # ------------------------------------------------------------------------- добавлено ------------ кнопка Hardware --------- 15 RA3PKJ
    elif name == 'Hardware':
      self.bandscope_flag = False # ------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.radios_screen.FinishPages()
      self.screen = self.radios_screen

    self.screen.Show()
    self.vertBox.Layout()	# This destroys the initialized sash position!
    self.sliderYs.SetValue(self.screen.y_scale)
    self.sliderYz.SetValue(self.screen.y_zero)
    #self.sliderZo.SetValue(self.screen.zoom_control) # ------------------------- удалено ------------- кнопка Hardware --------- 15 RA3PKJ
    if name[0:5] == 'WFall':
      self.bandscope_flag = False # -------------------------- добавлено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
      self.screen.SetSashPosition(sash)
  def OnBtnFileRecord(self, event):
    record = event.GetEventObject().GetValue()
    self.config_screen.config.OnFileRecordButton(record)
  def ChangeYscale(self, event=None):
    self.screen.ChangeYscale(self.sliderYs.GetValue())
    if self.screen == self.multi_rx_screen:
      if self.multi_rx_screen.rx_zero == self.waterfall:
        self.wfallScaleZ[self.lastBand] = (self.waterfall.y_scale, self.waterfall.y_zero)
        self.wfallGrScaleZ[self.lastBand] = (self.waterfall.pane1.y_scale, self.waterfall.pane1.y_zero)
      elif self.multi_rx_screen.rx_zero == self.graph:
        self.graphScaleZ[self.lastBand] = (self.graph.y_scale, self.graph.y_zero)
  def ChangeYzero(self, event=None):
    self.screen.ChangeYzero(self.sliderYz.GetValue())
    if self.screen == self.multi_rx_screen:
      if self.multi_rx_screen.rx_zero == self.waterfall:
        self.wfallScaleZ[self.lastBand] = (self.waterfall.y_scale, self.waterfall.y_zero)
        self.wfallGrScaleZ[self.lastBand] = (self.waterfall.pane1.y_scale, self.waterfall.pane1.y_zero)
      elif self.multi_rx_screen.rx_zero == self.graph:
        self.graphScaleZ[self.lastBand] = (self.graph.y_scale, self.graph.y_zero)
  def OnChangeZoom(self, event=None):
    zoom_control = self.sliderZo.GetValue()
    if self.screen == self.bandscope_screen:
      self.bandscope_screen.ChangeZoom(zoom_control)
      self.bandscope_screen.SetTxFreq(self.txFreq, self.rxFreq)
      return
    # The display runs from f1 to f2. The original sample rate is "rate".
    # The new effective sample rate is rate * zoom.
    # f1 = deltaf + rate * (1 - zoom) / 2
# ----------------------------------------------------------------------- удалено --------------- засветка при зумировании --------- 31 RA3PKJ
##    if zoom_control < 50:
##      self.zoom = 1.0	# change back to not-zoomed mode
##      self.zoom_deltaf = 0
##      self.zooming = False
##    else:
##      a = 1000.0 * self.sample_rate / (self.sample_rate - 2500.0)
##      self.zoom = 1.0 - zoom_control / a
##      if not self.zooming:		# set deltaf when zoom mode starts
##        center = self.multi_rx_screen.graph.filter_center
##        freq = self.rxFreq + center
##        self.zoom_deltaf = freq # --- при зумировании deltaf служит для совпадения шторки с реальным звуком
##        self.zooming = True
    # -------------------------------------------------------------------- взамен --------------- засветка при зумировании --------- 31 RA3PKJ
    d = self.sample_rate // 10 # --- взять кусок, который будет зеркально, т.е. -кусок и +кусок относительно средней (нулевой) линии
    if self.rxFreq < -d:
      self.band_down.SendCommand(self.OnBtnDownBand) # --- уйти влево по частоте (переместить шторку вправо)
      self.OnBtnUpDnBandDone(True) # --- переместить звук вслед за шторкой
    elif self.rxFreq > d:
      self.band_up.SendCommand(self.OnBtnUpBand) # --- уйти вправо по частоте (переместить шторку влево)
      self.OnBtnUpDnBandDone(True) # --- переместить звук вслед за шторкой
    else:
      if zoom_control < 50:
        self.zoom = 1.0	# change back to not-zoomed mode
        self.zoom_deltaf = 0
        self.zooming = False
      else:
        a = 1000.0 * self.sample_rate / (self.sample_rate - 2500.0)
        self.zoom = 1.0 - zoom_control / a
        if not self.zooming:		# set deltaf when zoom mode starts
          center = self.multi_rx_screen.graph.filter_center
          freq = self.rxFreq + center
          self.zoom_deltaf = freq # --- при зумировании deltaf служит для совпадения шторки с реальным звуком
          self.zooming = True

    zoom = self.zoom # --- степень зумирования панорамы, минимально 1.0
    deltaf = self.zoom_deltaf
    self.graph.ChangeZoom(zoom, deltaf, zoom_control)
    self.waterfall.ChangeZoom(zoom, deltaf, zoom_control)
    self.screen.SetTxFreq(self.txFreq, self.rxFreq)
    self.station_screen.Refresh()

# --------------------------------- удалено ------------------------ Вынос слайдера VOX в главное окно ------- 42 RA3PKJ
##  def OnLevelVOX(self, event):
##    self.levelVOX = event.GetEventObject().GetValue()
##    if self.useVOX:
##      QS.set_tx_audio(vox_level=self.levelVOX)
# --------------------------------- взамен ------------------------- Вынос слайдера VOX в главное окно ------- 42 RA3PKJ
  def OnLevelVOX(self, event=None):
    self.levelVOX = self.sliderVOX.GetValue()
    self.levelVOX = -40 - self.levelVOX # --- перевернуть зависимость
    if self.useVOX:
      QS.set_tx_audio(vox_level=self.levelVOX)

  def OnTimeVOX(self, event):
    self.timeVOX = event.GetEventObject().GetValue()
    QS.set_tx_audio(vox_time=self.timeVOX)
  def OnButtonVOX(self, event):
    self.useVOX = event.GetEventObject().GetValue()
    if self.useVOX:
      QS.set_tx_audio(vox_level=self.levelVOX)
    else:
      QS.set_tx_audio(vox_level=20)
      if self.pttButton.GetValue():
        self.pttButton.SetValue(0, True)
  def OnButtonPTT(self, event):
    if self.file_play_source == 12 and self.btnFilePlay.GetValue():	# playing CQ file
      self.btnFilePlay.SetValue(False, False)
      self.file_play_state = 0	# Not playing a file
      QS.set_record_state(3)
    btn = event.GetEventObject()

    #----------------------- добавлено -------------------------- выключение режима TX при закрытии программы -------------- 46 RA3PKJ
    if self.close == True:
      QS.set_PTT(0)
      Hardware.OnButtonPTT(event)
      self.close = False
      return

    if btn.GetValue():
      QS.set_PTT(1)
      self.ssb_offset_tx.Enable(False)  # ----------------------------- добавлено ----------------- Кнопка SSBtx Low ------- 45 RA3PKJ
    else:
      QS.set_PTT(0)
      self.ssb_offset_tx.Enable(True)  # ------------------------------ добавлено ----------------- Кнопка SSBtx Low ------- 45 RA3PKJ
    Hardware.OnButtonPTT(event)
  def SetPTT(self, value):
    self.pttButton.SetValue(value, False)
    if value:
      QS.set_PTT(1)
    else:
      QS.set_PTT(0)
    event = wx.PyEvent()
    event.SetEventObject(self.pttButton)
    Hardware.OnButtonPTT(event)

# --------------------------------- удалено ------------------------ Вынос слайдера Clip в главное окно ------------------- 43 RA3PKJ
##  def OnTxAudioClip(self, event):
##    v = event.GetEventObject().GetValue()
##    if self.mode in ('USB', 'LSB'):
##      self.txAudioClipUsb = v
##    elif self.mode == 'AM':
##      self.txAudioClipAm = v
##    elif self.mode == 'FM':
##      self.txAudioClipFm = v
##    elif self.mode in ('FDV-U', 'FDV-L'):
##      self.txAudioClipFdv = v
##    else:
##      return
##    QS.set_tx_audio(mic_clip=v)
# --------------------------------- взамен ------------------------- Вынос слайдера Clip в главное окно ------------------- 43 RA3PKJ
  def OnTxAudioClip(self, event=None):
    v = self.CtrlTxAudioClip.slider.GetValue()
    if self.mode in ('USB', 'LSB'):
      self.txAudioClipUsb = v
    elif self.mode == 'AM':
      self.txAudioClipAm = v
    elif self.mode == 'FM':
      self.txAudioClipFm = v
    elif self.mode in ('FDV-U', 'FDV-L'):
      self.txAudioClipFdv = v
    else:
      return
    QS.set_tx_audio(mic_clip=v)

# --------------------------------- удалено ------------------------ Вынос слайдера PreemPhasis в главное окно ------------- 39 RA3PKJ
##  def OnTxAudioPreemph(self, event):
##    v = event.GetEventObject().GetValue()
##    if self.mode in ('USB', 'LSB'):
##      self.txAudioPreemphUsb = v
##    elif self.mode == 'AM':
##      self.txAudioPreemphAm = v
##    elif self.mode == 'FM':
##      self.txAudioPreemphFm = v
##    elif self.mode in ('FDV-U', 'FDV-L'):
##      self.txAudioPreemphFdv = v
##    else:
##      return
##    QS.set_tx_audio(mic_preemphasis = v * 0.01)
# --------------------------------- взамен ------------------------- Вынос слайдера PreemPhasis в главное окно ------------- 39 RA3PKJ
  def OnTxAudioPreemph(self, event=None):
    v = self.CtrlTxAudioPreemph.slider.GetValue()
    if self.mode in ('USB', 'LSB'):
      self.txAudioPreemphUsb = v
    elif self.mode == 'AM':
      self.txAudioPreemphAm = v
    elif self.mode == 'FM':
      self.txAudioPreemphFm = v
    elif self.mode in ('FDV-U', 'FDV-L'):
      self.txAudioPreemphFdv = v
    else:
      return
    QS.set_tx_audio(mic_preemphasis = v * 0.01)

  def SetTxAudio(self):
    if self.mode[0:3] in ('CWL', 'CWU', 'FDV', 'DGT'):
      self.CtrlTxAudioClip.slider.Enable(False)
      self.CtrlTxAudioPreemph.slider.Enable(False)
    else:
      self.CtrlTxAudioClip.slider.Enable(True)
      self.CtrlTxAudioPreemph.slider.Enable(True)
    if self.mode in ('USB', 'LSB'):
      clp = self.txAudioClipUsb
      pre = self.txAudioPreemphUsb
    elif self.mode == 'AM':
      clp = self.txAudioClipAm
      pre = self.txAudioPreemphAm
    elif self.mode == 'FM':
      clp = self.txAudioClipFm
      pre = self.txAudioPreemphFm
    else:
      clp = 0
      pre = 0
    QS.set_tx_audio(mic_clip=clp, mic_preemphasis=pre * 0.01)
    self.CtrlTxAudioClip.SetValue(clp)
    self.CtrlTxAudioPreemph.SetValue(pre)
  def OnBtnMute(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      QS.set_volume(0)
    else:
      QS.set_volume(self.audio_volume)
  def OnMultirxPlayBoth(self, event):
    QS.set_multirx_play_method(0)
  def OnMultirxPlayLeft(self, event):
    QS.set_multirx_play_method(1)
  def OnMultirxPlayRight(self, event):
    QS.set_multirx_play_method(2)
  def OnBtnDecimation(self, event=None, rate=None):
    if event:
      i = event.GetSelection()
      rate = Hardware.VarDecimSet(i)
    self.vardecim_set = rate
    if rate != self.sample_rate:
      self.sample_rate = rate
      self.multi_rx_screen.ChangeSampleRate(rate)
      QS.change_rate(rate, 1)
      #print ('FFT size %d, FFT mult %d, average_count %d, rate %d, Refresh %.2f Hz' % (
      #  self.fft_size, self.fft_size / self.data_width, average_count, rate,
      #  float(rate) / self.fft_size / average_count))
      tune = self.txFreq
      vfo = self.VFO
      self.txFreq = self.VFO = -1		# demand change
      self.ChangeHwFrequency(tune, vfo, 'NewDecim')

  # ------------------------------------------------------------------------ добавлено ---- Вынос слайдера TxLevel в главное окно --- 41 RA3PKJ
  def OnTxLevel(self, event=None):
    application.tx_level = self.sliderTxLevel.GetValue()
    application.Hardware.SetTxLevel()

  # --------------------------------------------------------------------- добавлено - Вынос слайдера Digital TxLevel в главное окно - 62 RA3PKJ
  def OnDigiTxLev(self, event=None):
    application.digital_tx_level = self.sliderDigiTxLev.GetValue()
    application.Hardware.SetTxLevel()

  def ChangeVolume(self, event=None):
    # Caution: event can be None
    value = self.sliderVol.GetValue()
    self.volumeAudio = value
    # Simulate log taper pot
    B = 50.0		# This controls the gain at mid-volume
    x = (B ** (value/1000.0) - 1.0) / (B - 1.0)		# x is 0.0 to 1.0
    #print ("Vol %3d   %10.6f" % (value, x))
    self.audio_volume = x	# audio_volume is 0 to 1.000
    QS.set_volume(x)
  def ChangeSidetone(self, event=None):
    # Caution: event can be None
    value = self.sliderSto.GetValue()
    self.sidetone_volume = value
    # Simulate log taper pot
    B = 50.0		# This controls the gain at mid-volume
    x = (B ** (value/1000.0) - 1.0) / (B - 1.0)		# x is 0.0 to 1.0
    self.sidetone_0to1 = x
    QS.set_sidetone(value, x, self.ritFreq, conf.keyupDelay)
    if hasattr(Hardware, 'ChangeSidetone'):
      Hardware.ChangeSidetone(x)

  # обработчик слайдера CWspeed --------------------------------------------------- добавлено --------------- CW paddle ------------- 60 RA3PKJ
  def ChangeSpeed(self, event=None):
    self.speed_cw = self.sliderSpeed.GetValue()
    try:
      Hardware.speed_cw = self.speed_cw
      Hardware.NewUdpStatus()
    except:
      pass

  def OnRitScale(self, event=None):	# Called when the RIT slider is moved
    # Caution: event can be None
    value = self.ritScale.GetValue()
    self.ritButton.SetLabel("RIT %d" % value)
    self.ritButton.Refresh()
    if self.ritButton.GetValue():
      value = int(value)
      self.ritFreq = value
      self.graph.ritFreq = value
      self.waterfall.pane1.ritFreq = value
      self.waterfall.pane2.ritFreq = value
      QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
      QS.set_sidetone(self.sidetone_volume, self.sidetone_0to1, self.ritFreq, conf.keyupDelay)

  # ------------------------------------------------------------------------------- добавлено -------------- реформа кнопок ---------- 12 RA3PKJ
  # ------------------------------------------------------------------------------- добавлено -------------- выбор водопада ---------- 25 RA3PKJ
  def OnBtnWaterFallPalette(self, event): # обработчик нажатия кнопки Palette
    try:
      if configure.Settings[1] == "ConfigFileRadio":
        pass
      else:
        self.multi_rx_screen.ChangePalette()
    except:
      pass
  # ------------------------------------------------------------------------------- добавлено -------------- реформа кнопок ---------- 12 RA3PKJ
  def OnBtnVFOAB(self, event): # обработчик нажатия кнопки A<>B
    rx = self.rxFreq
    self.rxFreq = self.txFreq
    self.ChangeHwFrequency(rx, self.VFO, 'FreqEntry')
  # ------------------------------------------------------------------------------- добавлено -------------- реформа кнопок ---------- 12 RA3PKJ
  def OnBtnLockVFO_RX(self, event): # обработчик нажатия кнопки LockRX
    self.lock_vfo_RX = self.lockVFOButton_RX.GetValue() # See that button turn On or Off?
    if self.lock_vfo_RX:
      self.split_lockrx = True #глобальный флаг для операций мыши на панораме
    else:
      self.split_lockrx = False
    self.lockVFOButton_RX.Refresh()
  # ------------------------------------------------------------------------------- добавлено -------------- реформа кнопок ---------- 12 RA3PKJ
  def OnBtnLockVFO_TX(self, event): # обработчик нажатия кнопки LockTX
    self.lock_vfo = self.lockVFOButton_TX.GetValue() # See that button turn On or Off?
    if self.lock_vfo:
      self.split_locktx = True #глобальный флаг для операций мыши на панораме
    else:
      self.split_locktx = False
    self.lockVFOButton_TX.Refresh()

  # ------------------------------------------------------------------------------- добавлено ------ кнопки f_Before и f_After ------- 51 RA3PKJ
  def OnBtnBefore(self, event):
    self.beforeButton.Enable(0)
    self.afterButton.Enable(1)
    self.ChangeHwFrequency(self.f_before_1, self.f_before_2, 'MouseWheel')
  def OnBtnAfter(self, event):
    self.afterButton.Enable(0)
    self.beforeButton.Enable(1)
    self.ChangeHwFrequency(self.f_after_1, self.f_after_2, 'MouseWheel')

# ---------------------------------------------------------- удалено -------------- чистка кнопки Split и перевод её на RX2 ---------- 10 RA3PKJ
##  def OnBtnSplit(self, event):	# Called when the Split check button is pressed
##    self.split_rxtx = self.splitButton.GetValue()
##    if self.split_rxtx:
##      if self.split_offset == 0:
##        if self.mode in ("CWL", "CWU"):
##          self.split_offset = 1000
##        else:
##          self.split_offset = 3000
##      QS.set_split_rxtx(self.split_rxtx_play)
##      self.txFreq = self.rxFreq + self.split_offset
##      self.ChangeHwFrequency(self.txFreq, self.VFO, 'OnSplit', event=event, rx_freq=self.rxFreq)
##    else:
##      QS.set_split_rxtx(0)
##      self.split_offset = self.txFreq - self.rxFreq
##      self.txFreq = self.rxFreq
##      self.ChangeHwFrequency(self.txFreq, self.VFO, 'OnSplit', event=event)
##    self.screen.SetTxFreq(self.txFreq, self.rxFreq)
 # ----------------------------------------------------------- взамен -------------- чистка кнопки Split и перевод её на RX2 ---------- 10 RA3PKJ
  def OnBtnSplit(self, event):
    aa = self.newsplitButton.GetValue() #See that Split button turn On or Off?
    if aa == False:
      self.split_rxtx = self.splitButton.GetValue() #See that RX2 button turn On or Off?
      if self.split_rxtx: #if button turn On
        self.vfoABButton.Enable(True)

      # --- чтобы избежать возможного совпадения между частотой Rx и частотой Tx при запуске Quisk
        if self.txFreq > -3000 and self.txFreq < 3000 and self.oldRxFreq == 0:
          self.rxFreq = self.txFreq - 4000
        else:
          self.rxFreq = self.oldRxFreq

        # --- если частота rx выходит за пределы sample_rate, то переместить частоту rx в область sample_rate
        d = self.sample_rate * 49 // 100
        if self.rxFreq < -d:
          self.rxFreq = -d
        elif self.rxFreq > d:
          self.rxFreq = d

        #QS.set_split_rxtx(self.split_rxtx_play) # --- не использовать переменную self.split_rxtx_play
        QS.set_split_rxtx(2) # --- передать в dll значение для её переменной split_rxtx = 2

      else: #if button turn off
        self.vfoABButton.Enable(False)
        #QS.set_split_rxtx(self.split_rxtx_play) # --- не использовать переменную self.split_rxtx_play
        QS.set_split_rxtx(0) # --- передать в dll значение для её переменной split_rxtx = 0
        self.oldRxFreq = self.rxFreq
        self.rxFreq = self.txFreq

      self.screen.SetTxFreq(self.txFreq, self.rxFreq) # --- self.screen это текущий скрин (GraphScreen и другое)
      QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq) # --- передать в dll значения двух переменных

    else:
      self.splitButton.SetValue(False) # RX2 button turn off (чтобы не допускать параллельное функционирование кнопок Split и RX2)

  # ----------------------------------------------------------------------------- добавлено ---------------- реформа кнопок ---------- 12 RA3PKJ
  def OnBtnFminus5(self, event):
    self.ChangeHwFrequency(self.txFreq - 5000, self.VFO, 'MouseMotion', event=event)
  def OnBtnFminus3(self, event):
    self.ChangeHwFrequency(self.txFreq - 3000, self.VFO, 'MouseMotion', event=event)
  def OnBtnFminus1(self, event):
    self.ChangeHwFrequency(self.txFreq - 1000, self.VFO, 'MouseMotion', event=event)
  def OnBtnFminus05(self, event):
    self.ChangeHwFrequency(self.txFreq - 500, self.VFO, 'MouseMotion', event=event)
  def OnBtnFdown(self, event):
    self.ChangeHwFrequency(self.txFreq - self.freq_step, self.VFO, 'MouseMotion', event=event)
  def OnBtnFup(self, event):
    self.ChangeHwFrequency(self.txFreq + self.freq_step, self.VFO, 'MouseMotion', event=event)
  def OnBtnFplus05(self, event):
    self.ChangeHwFrequency(self.txFreq + 500, self.VFO, 'MouseMotion', event=event)
  def OnBtnFplus1(self, event):
    self.ChangeHwFrequency(self.txFreq + 1000, self.VFO, 'MouseMotion', event=event)
  def OnBtnFplus3(self, event):
    self.ChangeHwFrequency(self.txFreq + 3000, self.VFO, 'MouseMotion', event=event)
  def OnBtnFplus5(self, event):
    self.ChangeHwFrequency(self.txFreq + 5000, self.VFO, 'MouseMotion', event=event)

  # ----------------------------------------------------------------------------- добавлено ---------------- реформа кнопок ---------- 12 RA3PKJ
  def OnBtnNewSplit(self, event): # for the Split (disable RX-sound at TX frequency)
      aa = self.splitButton.GetValue() #проверить кнопку RX2, т.к. нельзя включать Split, если нажата RX2
      if aa == False:
        self.new_split = self.newsplitButton.GetValue() #проверить нажата или отжата кнопка Split после клика
        if self.new_split == False: #кнопка отжата после клика
          self.lockVFOButton_RX.SetValue(False)
          self.lockVFOButton_RX.Enable(False)
          self.vfoABButton.Enable(False)
          # Rx и Tx меняются местами
          rx = self.rxFreq
          self.rxFreq = self.txFreq
          self.ChangeHwFrequency(rx, self.VFO, 'FreqEntry')
          QS.set_split_rxtx(0)
          self.oldRxFreq = self.rxFreq
          self.rxFreq = self.txFreq

        self.split_rxtx = self.new_split # --- использовать те же методы, что и для кнопки RX2

        if self.new_split: #кнопка нажата после клика
          self.lockVFOButton_RX.Enable(True)
          self.vfoABButton.Enable(True)
          if self.mode in ("CWL", "CWU"):
            self.rxFreq = self.txFreq + 1000 # Rx и Tx ниже поменяются местами
          else:
            self.rxFreq = self.txFreq + 5000 # Rx и Tx ниже поменяются местам

          QS.set_split_rxtx(0)
          # Rx и Tx меняются местами
          tx = self.rxFreq
          self.rxFreq = self.txFreq
          self.ChangeHwFrequency(tx, self.VFO, 'FreqEntry')

        self.screen.SetTxFreq(self.txFreq, self.rxFreq)
        QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)

      else:
        self.newsplitButton.SetValue(False) #выключить нажимаемую сейчас кнопку Split, т.к. оказалось, что уже включена кнопка RX2

# ------------------------------------------------------------- удалено ------------ чистка кнопки Split и перевод её на RX2 ---------- 10 RA3PKJ
##  def OnMenuSplitPlay1(self, event):
##    self.split_rxtx_play = 1
##    if self.split_rxtx:
##      QS.set_split_rxtx(1)
##  def OnMenuSplitPlay2(self, event):
##    self.split_rxtx_play = 2
##    if self.split_rxtx:
##      QS.set_split_rxtx(2)
##  def OnMenuSplitPlay3(self, event):
##    self.split_rxtx_play = 3
##    if self.split_rxtx:
##      QS.set_split_rxtx(3)
##  def OnMenuSplitPlay4(self, event):
##    self.split_rxtx_play = 4
##    if self.split_rxtx:
##      QS.set_split_rxtx(4)
##  def OnMenuSplitLock(self, event):
##    menu = self.split_menu
##    if menu.IsItemChecked('Lock Tx, Split Rx'):
##      self.split_locktx = True
##      self.split_lockrx = False
##      self.SplitButton.SetLabel("SplitRx")
##    elif menu.IsItemChecked('Lock Rx, Split Tx'):
##      self.split_locktx = False
##      self.split_lockrx = True
##      self.SplitButton.SetLabel("SplitTx")
##    else:
##      self.split_locktx = False
##      self.split_lockrx = False
##      self.SplitButton.SetLabel("Split")
##    self.SplitButton.Refresh()
##  def OnMenuSplitRev(self, event):	# Called when the Split Reverse button is pressed
##    if self.split_rxtx:
##      self.ChangeHwFrequency(self.rxFreq, self.VFO, 'FreqEntry', rx_freq=self.txFreq)

  def OnBtnRit(self, event=None):	# Called when the RIT check button is pressed
    # Caution: event can be None
    if self.ritButton.GetValue():
      self.ritFreq = self.ritScale.GetValue()
    else:
      self.ritFreq = 0
    self.graph.ritFreq = self.ritFreq
    self.waterfall.pane1.ritFreq = self.ritFreq
    self.waterfall.pane2.ritFreq = self.ritFreq
    QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
    QS.set_sidetone(self.sidetone_volume, self.sidetone_0to1, self.ritFreq, conf.keyupDelay)
  def SetRit(self, freq):
    if freq:
      self.ritButton.SetValue(1)
    else:
      self.ritButton.SetValue(0)
    self.ritScale.SetValue(freq)
    self.ritButton.SetLabel("RIT %d" % freq)
    self.ritButton.Refresh()
    self.OnBtnRit()
  def OnBtnFDX(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      QS.set_fdx(1)
      if hasattr(Hardware, 'OnBtnFDX'):
        Hardware.OnBtnFDX(1)
    else:
      QS.set_fdx(0)
      if hasattr(Hardware, 'OnBtnFDX'):
        Hardware.OnBtnFDX(0)
  def OnImdSlider(self, event):
    value = event.GetEventObject().slider_value
    QS.set_imd_level(value)
  def OnBtnSpot(self, event):
    btn = event.GetEventObject()
    self.levelSpot = btn.slider_value
    if btn.GetValue():
      value = btn.slider_value
    else:
      value = -1
    QS.set_spot_level(value)
    Hardware.OnSpot(value)
    # ----------------------------------------------------- изменено -------------------------- инициализация скрытых кнопок -------- 18 RA3PKJ
    #if conf.spot_button_keys_tx:
    Hardware.OnButtonPTT(event)
    if btn.GetValue():
      QS.set_key_down(1)
    else:
      QS.set_key_down(0)

  def OnBtnTmpRecord(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      self.btnTmpPlay.Enable(0)
      QS.set_record_state(0)
    else:
      self.btnTmpPlay.Enable(1)
      QS.set_record_state(1)
  def OnBtnTmpPlay(self, event):
    btn = event.GetEventObject()
    if btn.direction == 1:	# left click
      if btn.GetValue():
        if QS.is_key_down() and conf.mic_sample_rate != conf.playback_rate:
          self.btnTmpPlay.SetValue(False, False)
        else:
          self.btnTmpRecord.Enable(0)
          QS.set_record_state(2)
          self.tmp_playing = True
      else:
        self.btnTmpRecord.Enable(1)
        QS.set_record_state(3)
        self.tmp_playing = False
    else:	# right click
      btn.SetValue(False)
      dr, fn = os.path.split(self.file_name_rec_tmp)
      dlg = wx.FileDialog(self.main_frame, 'Choose WAV file', dr, fn, style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT, wildcard="Wave files (*.wav)|*.wav")
      if dlg.ShowModal() == wx.ID_OK:
        path = dlg.GetPath()
        if path[-4:].lower() != '.wav':
          path = path + '.wav'
        self.file_name_rec_tmp = path
        QS.tmp_record_save(path)
      dlg.Destroy()
  def OnBtnFilePlay(self, event):
    btn = event.GetEventObject()
    enable = btn.GetValue()
    self.config_screen.config.OnFilePlayButton(enable)
    if enable:
      self.file_play_state = 1	# Start playing a file
      if self.file_play_source == 10:	# Play speaker audio file
        QS.set_record_state(5)
      elif self.file_play_source == 11:	# Play sample file
        QS.set_record_state(6)
      elif self.file_play_source == 12:	# Play CQ file
        QS.set_record_state(5)
        self.SetPTT(True)
    else:
      self.file_play_state = 0	# Not playing a file
      QS.set_record_state(3)
      if self.file_play_source == 12:	# Play CQ file
        self.SetPTT(False)
  def TurnOffFilePlay(self):
    self.btnFilePlay.SetValue(False, False)
    self.file_play_state = 0	# Not playing a file
    QS.set_record_state(3)
  def OnBtnTest1(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      QS.add_tone(10000)
    else:
      QS.add_tone(0)
  def OnBtnTest2(self, event):
    return
  def OnBtnColorDialog(self, event):
    btn = event.GetEventObject()
    dlg = wx.ColourDialog(self.main_frame)
    dlg.GetColourData().SetChooseFull(True)
    if dlg.ShowModal() == wx.ID_OK:
      data = dlg.GetColourData()
      print (data.GetColour().Get(False))
      btn.text_color = data.GetColour().Get(False)
      btn.Refresh()
    dlg.Destroy()

# ------------------------------------ удалено --------- обработчик удалённой кнопки Color --- 32 RA3PKJ
##  def OnBtnColor(self, event):
##    if not self.color_list:
##      clist = wx.lib.colourdb.getColourInfoList()
##      self.color_list = [(0, clist[0][0])]
##      self.color_index = 0
##      for i in range(1, len(clist)):
##        if  self.color_list[-1][1].replace(' ', '') != clist[i][0].replace(' ', ''):
##          #if 'BLUE' in clist[i][0]:
##            self.color_list.append((i, clist[i][0]))
##    btn = event.GetEventObject()
##    if btn.shift:
##      del self.color_list[self.color_index]
##    else:
##      self.color_index += btn.direction
##    if self.color_index >= len(self.color_list):
##      self.color_index = 0
##    elif self.color_index < 0:
##      self.color_index = len(self.color_list) -1
##    color = self.color_list[self.color_index][1]
##    print(self.color_index, color)
##    #self.main_frame.SetBackgroundColour(color)
##    #self.main_frame.Refresh()
##    #self.screen.Refresh()
##    #btn.SetBackgroundColour(color)
##    btn.text_color = color
##    btn.Refresh()

  def OnBtnAGC(self, event):
    btn = self.BtnAGC
    self.levelOffAGC = btn.slider_value_off
    self.levelAGC = btn.slider_value_on
    value = btn.GetValue()
    if value:
      level = self.levelAGC
    else:
      level = self.levelOffAGC
    # Simulate log taper pot.  Volume is 0 to 1.
    x = (10.0 ** (float(level) * 0.003000434077) - 0.99999) / 1000.0
    QS.set_agc(x * conf.agc_max_gain)
  def OnBtnSquelch(self, event=None):
    btn = self.BtnSquelch
    value = btn.GetValue()
    if self.mode == 'FM':
      self.levelSquelch = btn.slider_value
      if value:
        QS.set_squelch(self.levelSquelch / 12.0 - 120.0)
      else:
        QS.set_squelch(-999.0)
    elif self.mode[0:3]  == 'FDV':
      if value:
        QS.freedv_set_squelch_en(1)
      else:
        QS.freedv_set_squelch_en(0)
    else:
      self.levelSquelchSSB = btn.slider_value
      if value:
        QS.set_ssb_squelch(1, self.levelSquelchSSB)
      else:
        QS.set_ssb_squelch(0, self.levelSquelchSSB)
  def OnBtnAutoNotch(self, event):
    if event.GetEventObject().GetValue():
      QS.set_auto_notch(1)
    else:
      QS.set_auto_notch(0)
  def OnBtnNR2(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      self.wdsp.put(self.wdsp.SetRXAEMNRRun, self.wdsp_channel, 1)
      QS.wdsp_set_parameter(self.wdsp_channel, in_use=1)
    else:
      self.wdsp.put(self.wdsp.SetRXAEMNRRun, self.wdsp_channel, 0)
  def OnMenuNB(self, event):
    # menu is ("NB 1", "NB 2", "NB 3", "SNB")
    for item in self.NB_menu.GetMenuItems():
      if item.IsChecked():
        text = item.GetItemLabel()
        self.btnNB.SetLabel(text)
        self.btnNB.Refresh()
        break
    self.OnBtnNB(None)
  def OnBtnNB(self, event):
    text = self.btnNB.GetLabel()
    if self.btnNB.GetValue():	# Noise blanker On
      if text == "SNB":
        QS.set_noise_blanker(0)
        self.wdsp.put(self.wdsp.SetRXASNBARun, self.wdsp_channel, 1)
        QS.wdsp_set_parameter(self.wdsp_channel, in_use=1)
      else:
        self.wdsp.put(self.wdsp.SetRXASNBARun, self.wdsp_channel, 0)
        index = int(text[-1])
        QS.set_noise_blanker(index)
    else:	# Noise blanker Off
      QS.set_noise_blanker(0)
      self.wdsp.put(self.wdsp.SetRXASNBARun, self.wdsp_channel, 0)
  def FreqEntry(self, event):
    freq = event.GetString()
    win = event.GetEventObject()
    win.Clear()
    if not freq:
      return
    try:
      freq = str2freq (freq)
    except ValueError:
      pass
    else:
      tune = freq % 10000
      vfo = freq - tune
      self.BandFromFreq(freq)
      self.ChangeHwFrequency(tune, vfo, 'FreqEntry')
  def ChangeHwFrequency(self, tune, vfo, source='', band='', event=None, rx_freq=None):
    """Change the VFO and tuning frequencies, and notify the hardware.

    tune:    the new tuning frequency in +- sample_rate/2;
    vfo:     the new vfo frequency in Hertz; this is the RF frequency at zero Hz audio
    source:  a string indicating the source or widget requesting the change;
    band:    if source is "BtnBand", the band requested;
    event:   for a widget, the event (used to access control/shift key state).
    rx_freq: the new changed value of App.rxFreq, the receive frequency in +- sample_rate/2

    Try to update the hardware by calling Hardware.ChangeFrequency().
    The hardware will reply with the updated frequencies which may be different
    from those requested; use and display the returned tune and vfo.
    """
    #print ("ChangeHW", source, tune, vfo, vfo + tune)
    if not self.split_rxtx:
      self.rxFreq = tune	# rxFreq must be correct before the call to Hardware.ChangeFrequency()
    elif rx_freq is not None:
      self.rxFreq = rx_freq
    rx_offset = self.rxFreq - tune
    if self.screen == self.bandscope_screen:
      freq = vfo + tune
      tune = freq % 10000
      vfo = freq - tune
      tune, vfo = Hardware.ChangeFrequency(vfo + tune, vfo, source, band, event)
      self.ChangeDisplayFrequency(tune - vfo, vfo, rx_freq is not None)
    elif conf.fixed_tune_offset:
      # Tune with the VFO and keep a constant audio offset from the center. Tx tune is always conf.fixed_tune_offset.
      tune_freq = vfo + tune
      self.rxFreq = conf.fixed_tune_offset + rx_offset
      if source == "BtnUpDown":
        tune_freq = vfo + conf.fixed_tune_offset
      else:
        vfo = tune_freq - conf.fixed_tune_offset
      tune_freq, vfo = Hardware.ChangeFrequency(tune_freq, vfo, source, band, event)
      self.ChangeDisplayFrequency(tune_freq - vfo, vfo, True)
    else:
      tune, vfo = Hardware.ChangeFrequency(vfo + tune, vfo, source, band, event)
      self.ChangeDisplayFrequency(tune - vfo, vfo, rx_freq is not None)
  def ChangeDisplayFrequency(self, tune, vfo, new_rxfreq=False):
    'Change the frequency displayed by Quisk'
    change = 0
    if tune != self.txFreq or new_rxfreq:
      change = 1
      self.txFreq = tune
      if not self.split_rxtx:
        self.rxFreq = self.txFreq
      if self.screen == self.bandscope_screen:
        self.screen.SetFrequency(tune + vfo)
      else:
        self.screen.SetTxFreq(self.txFreq, self.rxFreq)
      QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
    if vfo != self.VFO:
      change = 1
      self.VFO = vfo
      self.graph.SetVFO(vfo)
      self.waterfall.SetVFO(vfo)
      self.station_screen.Refresh()
    if change:
      if (conf.name_of_sound_capt or conf.name_of_mic_play) and QS.get_params("softrock_correct_active") == 0:
        ampl, phase = self.GetAmplPhase('rx')
        QS.set_ampl_phase(ampl, phase, 0)
        ampl, phase = self.GetAmplPhase('tx')
        QS.set_ampl_phase(ampl, phase, 1)
      #self.freqDisplay.Display(self.txFreq + self.VFO) # -------- удалено --------- реформа мышиного управления шторками -------- 13 RA3PKJ
      self.fldigi_new_freq = self.txFreq + self.VFO
    return change
  def ChangeRxTxFrequency(self, rx_freq=None, tx_freq=None):
    if not self.split_rxtx and not tx_freq:
      tx_freq = rx_freq
    if tx_freq:
      tune = tx_freq - self.VFO
      d = self.sample_rate * 45 // 100
      if -d <= tune <= d:	# Frequency is on-screen
        vfo = self.VFO
      else:					# Change the VFO
        vfo = (tx_freq // 5000) * 5000 - 5000
        tune = tx_freq - vfo
        self.BandFromFreq(tx_freq)
      self.ChangeHwFrequency(tune, vfo, 'FreqEntry')
    if rx_freq and self.split_rxtx:
      tune = rx_freq - self.VFO
      self.ChangeHwFrequency(self.txFreq, self.VFO, 'FreqEntry', rx_freq=tune)

# ------------------------------------------------------------------------------ добавлено ------------------ CW Training ---------- 52 RA3PKJ
  def OnBtnCWtrain(self, event):
    if self.CWtrainButton.GetValue(): # кнопка нажата
      self.cts_old = conf.quisk_serial_cts
      self.dsr_old = conf.quisk_serial_dsr
      if conf.quisk_serial_cts[0:4] == "PTT " and conf.quisk_serial_dsr[0:4] == "PTT ":
        return
      if conf.quisk_serial_cts == "PTT when high":
        conf.quisk_serial_cts = "CW when high"
        conf.quisk_serial_dsr = "None"
      elif conf.quisk_serial_cts == "PTT when low":
        conf.quisk_serial_cts = "CW when low"
        conf.quisk_serial_dsr = "None"
      elif conf.quisk_serial_dsr == "PTT when high":
        conf.quisk_serial_dsr = "CW when high"
        conf.quisk_serial_cts = "None"
      elif conf.quisk_serial_dsr == "PTT when low":
        conf.quisk_serial_dsr = "CW when low"
        conf.quisk_serial_cts = "None"
      else:
        return
    else: # кнопка отпущена
      conf.quisk_serial_cts = self.cts_old
      conf.quisk_serial_dsr = self.dsr_old
    self.ImmediateChange("quisk_serial_cts")
    self.ImmediateChange("quisk_serial_dsr")

  def OnBtnMode(self, event):
    mode = self.modeButns.GetLabel()

    # -------------------------------------------------------------------------- добавлено ----------------- SSB RX Offset --------- 29 RA3PKJ
    # -------------------------------------------------------------------------- добавлено ---------------- Кнопка SSBtx Low ------- 45 RA3PKJ
    if mode in ('LSB','USB'):
      self.ssb_offset.Enable(True) #кнопки смещения полосы SSB
      self.ssb_offset_tx.Enable(True)
    else:
      self.ssb_offset.Enable(False)
      self.ssb_offset_tx.Enable(False)

    delta = 0	# Change frequency so switch between CW and SSB keeps tone constant
    if self.mode == 'USB':
      if mode in ('CWL', 'CWU'):
        delta = 1
    elif self.mode == 'LSB':
      if mode in ('CWL', 'CWU'):
        delta = -1
    elif self.mode in ('CWL', 'CWU'):
      if mode == 'USB':
        delta = -1
      elif mode == 'LSB':
        delta = 1
    if delta:
      delta *= conf.cwTone
      self.ChangeRxTxFrequency(self.rxFreq + delta + self.VFO, self.txFreq + delta + self.VFO)
    Hardware.ChangeMode(mode)
    self.mode = mode
    self.MakeFilterButtons(self.Mode2Filters(mode))
    QS.set_rx_mode(Mode2Index.get(mode, 3))
    if mode == 'CWL':
      self.SetRit(conf.cwTone)
    elif mode == 'CWU':
      self.SetRit(-conf.cwTone)
    else:
      self.SetRit(0)
    if mode in ('CWL', 'CWU'):
      self.SetFilterByMode('CW')
    elif mode in ('LSB', 'USB'):
      self.SetFilterByMode('SSB')
    elif mode == 'AM':
      self.SetFilterByMode('AM')
    elif mode == 'FM':
      self.SetFilterByMode('FM')
    elif mode[0:4] == 'DGT-':
      self.SetFilterByMode('DGT')
    elif mode[0:4] == 'FDV-':
      self.SetFilterByMode('FDV')
    elif mode == 'IMD':
      self.SetFilterByMode('IMD')
    elif mode == conf.add_extern_demod:
      self.SetFilterByMode(conf.add_extern_demod)
    self.sliderSquelch.DeleteSliderWindow()
    if mode == 'FM':
      self.sliderSquelch.SetSlider(self.levelSquelch)
    else:
      self.sliderSquelch.SetSlider(self.levelSquelchSSB)
    self.OnBtnSquelch()
    if mode not in ('FDV-L', 'FDV-U'):
      self.graph.SetDisplayMsg()
      self.waterfall.SetDisplayMsg()
    self.SetTxAudio()
  def MakeMemPopMenu(self):
    self.memory_menu.Destroy()
    self.memory_menu = wx.Menu()
    for data in self.memoryState:
      txt = FreqFormatter(data[0])
      item = self.memory_menu.Append(-1, txt)
      self.Bind(wx.EVT_MENU, self.OnPopupMemNext, item)
  def OnPopupMemNext(self, event):
    frq = self.memory_menu.GetLabel(event.GetId())
    frq = frq.replace(' ','')
    frq = int(frq)
    for freq, band, vfo, txfreq, mode in self.memoryState:
      if freq == frq:
        break
    else:
      return
    if band == self.lastBand:	# leave band unchanged
      self.modeButns.SetLabel(mode, True)
      self.ChangeHwFrequency(txfreq, vfo, 'FreqEntry')
    else:		# change to new band
      self.bandState[band] = (vfo, txfreq, mode)
      self.bandBtnGroup.SetLabel(band, do_cmd=True)
  def OnBtnMemSave(self, event):
    frq = self.VFO + self.txFreq
    for i in range(len(self.memoryState)):
      data = self.memoryState[i]
      if data[0] == frq:
        self.memoryState[i] = (self.VFO + self.txFreq, self.lastBand, self.VFO, self.txFreq, self.mode)
        return
    self.memoryState.append((self.VFO + self.txFreq, self.lastBand, self.VFO, self.txFreq, self.mode))
    self.memoryState.sort()
    self.memNextButton.Enable(True)
    self.memDeleteButton.Enable(True)
    self.MakeMemPopMenu()
    self.station_screen.Refresh()
  def OnBtnMemNext(self, event):
    frq = self.VFO + self.txFreq
    for freq, band, vfo, txfreq, mode in self.memoryState:
      if freq > frq:
        break
    else:
      freq, band, vfo, txfreq, mode = self.memoryState[0]
    if band == self.lastBand:	# leave band unchanged
      self.modeButns.SetLabel(mode, True)
      self.ChangeHwFrequency(txfreq, vfo, 'FreqEntry')
    else:		# change to new band
      self.bandState[band] = (vfo, txfreq, mode)
      self.bandBtnGroup.SetLabel(band, do_cmd=True)
  def OnBtnMemDelete(self, event):
    frq = self.VFO + self.txFreq
    for i in range(len(self.memoryState)):
      data = self.memoryState[i]
      if data[0] == frq:
        del self.memoryState[i]
        break
    self.memNextButton.Enable(bool(self.memoryState))
    self.memDeleteButton.Enable(bool(self.memoryState))
    self.MakeMemPopMenu()
    self.station_screen.Refresh()
  def OnRightClickMemory(self, event):
    event.Skip()
    pos = event.GetPosition()
    self.memNextButton.PopupMenu(self.memory_menu, pos)
  def OnBtnFavoritesShow(self, event):
    self.screenBtnGroup.SetLabel("Config", do_cmd=False)
    self.screen.Hide()
    self.config_screen.FinishPages()
    self.screen = self.config_screen
    self.config_screen.notebook.SetSelection(2)
    self.screen.Show()
    self.vertBox.Layout()    # This destroys the initialized sash position!
  def OnBtnFavoritesNew(self, event):
    self.config_screen.favorites.AddNewFavorite()
    self.OnBtnFavoritesShow(event)

  # ---- обработчик нажатия кнопки Picture ---------------------------- добавлено --------------------- картинка на панораме ------ 5 RA3PKJ
  def OnBtnPicture(self, event):
    # --- выбрать следующую картинку
    if self.picture_index in range (self.picture_len - 1):
      self.picture_index = self.picture_index + 1
    else: self.picture_index = 0
    self.picture_bmp = self.picture_list[self.picture_index]
    self.picture.SetLabel("Picture " + str(self.picture_index + 1))
    # --- сохранить выбор
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    configure.Settings[4]["Picture"] = self.picture_bmp
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False

  # ------------------------------------------------------------------- добавлено ------------------------- шаг перестройки ------- 30 RA3PKJ
  def OnBtnStep(self, event):
    step_label = self.step_btn.GetLabel()
    if step_label == 'Step 1':
      self.freq_step = 1
    elif step_label == 'Step 10':
      self.freq_step = 10
    elif step_label == 'Step 25':
      self.freq_step = 25
    elif step_label == 'Step 50':
      self.freq_step = 50
    elif step_label == 'Step 100':
      self.freq_step = 100
    elif step_label == 'Step 250':
      self.freq_step = 250
    elif step_label == 'Step 500':
      self.freq_step = 500
    elif step_label == 'Step 1kHz':
      self.freq_step = 1000
    else:
      self.step_btn.SetLabel("Step 50")
      self.freq_step = 50
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    configure.Settings[4]["FrequencyStep"] = self.freq_step
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False

  # ------------------------------------------------------------------------------- добавлено ----------------- SSB RX Offset ------- 29 RA3PKJ
  def OnBtnOffset(self, event):
    ssb_offset_label = self.ssb_offset.GetLabel()
    if ssb_offset_label == 'SSBrx Low=300Hz':
      self.offset = 300
    elif ssb_offset_label == 'SSBrx Low=250Hz':
      self.offset = 250
    elif ssb_offset_label == 'SSBrx Low=200Hz':
      self.offset = 200
    elif ssb_offset_label == 'SSBrx Low=150Hz':
      self.offset = 150
    elif ssb_offset_label == 'SSBrx Low=100Hz':
      self.offset = 100
    elif ssb_offset_label == 'SSBrx Low=50Hz':
      self.offset = 50
    elif ssb_offset_label == 'SSBrx Low=0Hz':
      self.offset = 0
    else:
      self.ssb_offset.SetLabel("SSBrx Low=200Hz")
      self.offset = 200
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    configure.Settings[4]["offset_SSB_bandwidth"] = self.offset
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False

    # --- через RadioButtonGroup.SetLabel (quisk_widgets.py) происходит вызов здесь функции OnBtnFilter для перерисовки фильтра
    index = self.filterButns.GetIndex() # --- индекс кнопки текущей полосы фильтра
    try:
      Lab = self.filterButns.buttons[index].GetLabel() # --- значение полосы на кнопке
    except:
      Lab = self.filterButns.buttons[0].GetLabel()
    self.filterButns.SetLabel(Lab, True) # --- перерисовать фильтр (шторку)

  # ----------------------------------------------------------------------- добавлено ----------------- Кнопка SSBtx Low ------- 45 RA3PKJ
  def OnBtnOffsetTX(self, event):
    ssb_offset_label_tx = self.ssb_offset_tx.GetLabel()
    if ssb_offset_label_tx == 'SSBtx Low=300Hz':
      self.offset_tx = 300
      QS.set_ssb_low(300)
    elif ssb_offset_label_tx == 'SSBtx Low=250Hz':
      self.offset_tx = 250
      QS.set_ssb_low(250)
    elif ssb_offset_label_tx == 'SSBtx Low=200Hz':
      self.offset_tx = 200
      QS.set_ssb_low(200)
    elif ssb_offset_label_tx == 'SSBtx Low=150Hz':
      self.offset_tx = 150
      QS.set_ssb_low(150)
    elif ssb_offset_label_tx == 'SSBtx Low=100Hz':
      self.offset_tx = 100
      QS.set_ssb_low(100)
    elif ssb_offset_label_tx == 'SSBtx Low=50Hz':
      self.offset_tx = 50
      QS.set_ssb_low(50)
    elif ssb_offset_label_tx == 'SSBtx Low=0Hz':
      self.offset_tx = 0
      QS.set_ssb_low(0)
    else:
      self.ssb_offset_tx.SetLabel("SSBtx Low=200Hz")
      self.offset_tx = 200
      QS.set_ssb_low(200)
    self.StatePath = os.path.join(conf.DefaultConfigDir, "quisk_settings.json")
    configure.Settings[4]["offset_SSB_bandwidthTX"] = self.offset_tx
    self.settings_changed = True
    configure.Configuration.SaveState(self)
    self.settings_changed = False

    # --- через RadioButtonGroup.SetLabel (quisk_widgets.py) происходит вызов здесь функции OnBtnFilter для перерисовки фильтра
    index = self.filterButns.GetIndex() # --- индекс кнопки текущей полосы фильтра
    try:
      Lab = self.filterButns.buttons[index].GetLabel() # --- значение полосы на кнопке
    except:
      Lab = self.filterButns.buttons[0].GetLabel()
    self.filterButns.SetLabel(Lab, True) # --- перерисовать фильтр (шторку)

  # --------------------------------------------------------------------------------- добавлено ------------- реформа кнопок ---- 12 RA3PKJ
  def OnBtnEmpty(self, event):
    pass
  # --------------------------------------------------------------------------------- добавлено ------------- реформа кнопок ---- 12 RA3PKJ
  def OnBtnHelp(self, event): # --------- обработчик нажатия кнопки Help
    import webbrowser
    webbrowser.open("help.html") # ---------- открыть в браузере

  def OnBtnBand(self, event):
    band = self.lastBand	# former band in use
    try:
      f1, f2 = conf.BandEdge[band]
      if f1 <= self.VFO + self.txFreq <= f2:
        self.bandState[band] = (self.VFO, self.txFreq, self.mode)
    except KeyError:
      pass
    btn = event.GetEventObject()
    band = btn.GetLabel()	# new band
    self.lastBand = band
    try:
      vfo, tune, mode = self.bandState[band]
    except KeyError:
      vfo, tune, mode = (1000000, 0, 'LSB')
    if band == '60':
      if self.mode in ('CWL', 'CWU'):
        freq60 = []
        for f in conf.freq60:
          freq60.append(f + 1500)
      else:
        freq60 = conf.freq60
      freq = vfo + tune
      if btn.direction:
        vfo = self.VFO
        if 5100000 < vfo < 5600000:
          if btn.direction > 0:		# Move up
            for f in freq60:
              if f > vfo + self.txFreq:
                freq = f
                break
            else:
              freq = freq60[0]
          else:			# move down
            l = list(freq60)
            l.reverse()
            for f in l:
              if f < vfo + self.txFreq:
                freq = f
                break
              else:
                freq = freq60[-1]
      half = self.sample_rate // 2 * self.graph_width // self.data_width
      while freq - vfo <= -half + 1000:
        vfo -= 10000
      while freq - vfo >= +half - 5000:
        vfo += 10000
      tune = freq - vfo
    elif band == 'Time':
      vfo, tune, mode = conf.bandTime[btn.index]
    self.modeButns.SetLabel(mode, True)
    self.txFreq = self.VFO = -1		# demand change
    self.ChangeBand(band)
    self.ChangeHwFrequency(tune, vfo, 'BtnBand', band=band)
    if band in ('Time', 'Audio') or conf.tx_level.get(band, 127) == 0:
      self.pttButton.Enable(False)
    else:
      self.pttButton.Enable(True)
  def BandFromFreq(self, frequency):	# Change to a new band based on the frequency
    if self.screen == self.bandscope_screen:
      return
    try:
      f1, f2 = conf.BandEdge[self.lastBand]
      if f1 <= frequency <= f2:
        return						# We are within the current band
    except KeyError:
      f1 = f2 = -1
    # Frequency is not within the current band.  Save the current band data.
    if f1 <= self.VFO + self.txFreq <= f2:
      self.bandState[self.lastBand] = (self.VFO, self.txFreq, self.mode)
    # Change to the correct band based on frequency.
    for band in conf.BandEdge:
      f1, f2 = conf.BandEdge[band]
      if f1 <= frequency <= f2:
        self.lastBand = band
        self.bandBtnGroup.SetLabel(band, do_cmd=False)
        try:
          vfo, tune, mode = self.bandState[band]
        except KeyError:
          vfo, tune, mode = (0, 0, 'LSB')
        self.modeButns.SetLabel(mode, True)
        self.ChangeBand(band)
        break
  def ChangeBand(self, band):
    if self.remote_control_head:
      self.Hardware.RemoteCtlSend(f'JsonAppFunc;{json.dumps(("ChangeBand", band))}\n')
    Hardware.ChangeBand(band)
    s, z = self.graphScaleZ.get(band, (conf.graph_y_scale, conf.graph_y_zero))
    self.waterfall.SetPane1(self.wfallGrScaleZ.get(band, (s, z)))
    self.waterfall.SetPane2(self.wfallScaleZ.get(band, (conf.waterfall_y_scale, conf.waterfall_y_zero)))
    self.graph.ChangeYscale(s)
    self.graph.ChangeYzero(z)
    if self.screen == self.multi_rx_screen and self.multi_rx_screen.rx_zero in (self.waterfall, self.graph):
      self.sliderYs.SetValue(self.screen.y_scale)
      self.sliderYz.SetValue(self.screen.y_zero)
  def OnBtnUpDnBandDelta(self, event, is_band_down):
    sample_rate = int(self.sample_rate * self.zoom)
    oldvfo = self.VFO
    btn = event.GetEventObject()
    if btn.direction > 0:		# left button was used, move a bit
      d = int(sample_rate // 9)
    else:						# right button was used, move to edge
      d = int(sample_rate * 45 // 100)
    if is_band_down:
      d = -d
    vfo = self.VFO + d
    if sample_rate > 40000:
      vfo = (vfo + 5000) // 10000 * 10000	# round to even number
      delta = 10000
    elif sample_rate > 5000:
      vfo = (vfo + 500) // 1000 * 1000
      delta = 1000
    else:
      vfo = (vfo + 50) // 100 * 100
      delta = 100
    if oldvfo == vfo:
      if is_band_down:
        d = -delta
      else:
        d = delta
    else:
      d = vfo - oldvfo
    self.VFO += d
    self.txFreq -= d
    self.rxFreq -= d
    # Set the display but do not change the hardware
    self.graph.SetVFO(self.VFO)
    self.waterfall.SetVFO(self.VFO)
    self.station_screen.Refresh()
    self.screen.SetTxFreq(self.txFreq, self.rxFreq)
    #self.freqDisplay.Display(self.txFreq + self.VFO) # -------------- удалено ---- реформа мышиного управления шторками ---- 13 RA3PKJ
  def OnBtnDownBand(self, event):
    self.band_up_down = 1
    self.OnBtnUpDnBandDelta(event, True)
  def OnBtnUpBand(self, event):
    self.band_up_down = 1
    self.OnBtnUpDnBandDelta(event, False)
  def OnBtnUpDnBandDone(self, event):
    self.band_up_down = 0
    tune = self.txFreq
    vfo = self.VFO
    self.txFreq = self.VFO = -1		# Force an update
    self.ChangeHwFrequency(tune, vfo, 'BtnUpDown')
  def SearchFreqAmPh(self, freq, data, index):
    # If index is -1, search data for the VFO frequency.
    # Otherwise, search in the frequencies for the VFO at index.
    # The list must be sorted. Search for a bracket lst[i] <= freq <= lst[i + 1]
    # Return 0, 1 for freq <= lst[0]; return len(lst) - 2, len(lst) - 1 for freq >= lst[-1]
    # Also return the length.
    if index < 0:	# VFO frequency is at data[i][0]
      items = data
    else:		# The Rx/Tx frequency for the VFO at index is data[index][1][i][0]
      items = data[index][1]
    length = len(items)
    if length == 0:
      return 0, 0, 0
    if length == 1:
      return 1, 0, 0
    f1 = items[0][0]
    if freq <= f1:	# before first frequency
      return length, 0, 1
    for i in range(1, length):
      f1 = items[i - 1][0]
      f2 = items[i][0]
      if f1 <= freq <= f2:
        return length, i - 1, i
    return length, length - 2, length - 1 	# after last frequency
  def GetAmplPhase(self, rx_tx):
    band = self.lastBand
    data = self.bandAmplPhase.get(band, {})
    data = data.get(rx_tx, [])
    if not data:	# No corrections for this band
      return 0.0, 0.0
    if rx_tx == 'rx':
      Freq0 = self.rxFreq
    else:
      Freq0 = self.txFreq
    nVFO, iVfo1, iVfo2 = self.SearchFreqAmPh(self.VFO, data, -1)
    #print ('iVfo1', iVfo1, 'iVfo2', iVfo2)
    nFreqV1, iV1F1, iV1F2 = self.SearchFreqAmPh(Freq0, data, iVfo1)
    #print ('    V1', iV1F1, iV1F2, data[iVfo1][1][iV1F1])
    if iVfo1 == iVfo2:
      nFreqV2 = nFreqV1
      iV2F1 = iV1F1
      iV2F2 = iV1F2
    else:
      nFreqV2, iV2F1, iV2F2 = self.SearchFreqAmPh(Freq0, data, iVfo2)
      #print ('    V2', iV2F1, iV2F2, data[iVfo2][1][iV2F1])
    #print ("nVFO", nVFO, "nFreq", nFreqV1, nFreqV2)
    try:	# guard against divide by zero
      if nVFO == 1:
        if nFreqV1 == 1:		# duplicate old logic
          freq, ampl, phase = data[iVfo1][1][0]
          #print ("new %10.6f %10.6f" % (ampl, phase))
        else:	# linear interpolation/extrapolation of Freq0
          freq1, ampl1, phase1 = data[iVfo1][1][iV1F1]
          freq2, ampl2, phase2 = data[iVfo1][1][iV1F2]
          t = (Freq0 - freq1) / (freq2 - freq1)	# linear interpolation
          ampl =  (1.0 - t) * ampl1  +  t * ampl2
          phase = (1.0 - t) * phase1 +  t * phase2
          #print ("new %10.6f %10.6f" % (ampl, phase))
      elif nFreqV1 == 1 and nFreqV2 == 1:		# duplicate old logic
        fVfo1 = data[iVfo1][0]	# linear interpolation/extrapolation of self.VFO
        fVfo2 = data[iVfo2][0]
        freq1, ampl1, phase1 = data[iVfo1][1][0]
        freq2, ampl2, phase2 = data[iVfo2][1][0]
        t = (self.VFO - fVfo1) / (fVfo2 - fVfo1)
        ampl =  (1.0 - t) * ampl1  +  t * ampl2
        phase = (1.0 - t) * phase1 +  t * phase2
        #print ("new %10.6f %10.6f" % (ampl, phase))
      else:
        fVfo1 = data[iVfo1][0]
        fVfo2 = data[iVfo2][0]
        freq11, ampl11, phase11 = data[iVfo1][1][iV1F1]
        freq12, ampl12, phase12 = data[iVfo1][1][iV1F2]
        freq21, ampl21, phase21 = data[iVfo2][1][iV2F1]
        freq22, ampl22, phase22 = data[iVfo2][1][iV2F2]
        #print ("Freq0", Freq0)
        #print ("Try Vfo 1 %d freq %d %d" % (fVfo1, freq11, freq12))
        #print ("Try Vfo 2 %d freq %d %d" % (fVfo2, freq21, freq22))
        if freq11 == freq21 and freq12 == freq22:	# rectangular box: bilinear interpolation
          #print ("Vfo %d %d %d freq %d %d %d" % (fVfo1, self.VFO, fVfo2, freq11, Freq0, freq12))
          t = (Freq0 - freq11) / (freq12 - freq11)
          u = (self.VFO - fVfo1) / (fVfo2 - fVfo1)
          #print ("%10.4f %10.4f" % (t, u))
          #print (ampl11, ampl12, ampl22, ampl21)
          #print (phase11, phase12, phase22, phase21)
          ampl =  (1.0 - t) * (1.0 - u) * ampl11  + t * (1.0 - u) * ampl12  + t * u * ampl22  + (1.0 - t) * u * ampl21
          phase = (1.0 - t) * (1.0 - u) * phase11 + t * (1.0 - u) * phase12 + t * u * phase22 + (1.0 - t) * u * phase21
          #print ('Box', fVfo1, fVfo2, freq11, freq12)
          #print ("new B %10.6f %10.6f" % (ampl, phase))
        else:	# linear interpolation/extrapolation of Freq0 at nearest VFO
          if abs(self.VFO - fVfo1) <= abs(self.VFO - fVfo2):
            nFreq = nFreqV1	# Use VFO 1
            freq1, ampl1, phase1 = data[iVfo1][1][iV1F1]
            #print ('Vfo1', fVfo1, freq1)
            if nFreq > 1:
              freq2, ampl2, phase2 = data[iVfo1][1][iV1F2]
          else:			# Use VFO 2
            nFreq = nFreqV2
            freq1, ampl1, phase1 = data[iVfo2][1][iV2F1]
            #print ('Vfo2', fVfo2, freq1)
            if nFreq > 1:
              freq2, ampl2, phase2 = data[iVfo2][1][iV2F2]
          if nFreq == 1:
            ampl, phase = ampl1, phase1
            #print ("new %10.6f %10.6f" % (ampl, phase))
          else:	# linear interpolation/extrapolation of Freq0
            #print ('Lin', freq1, freq2)
            t = (Freq0 - freq1) / (freq2 - freq1)	# linear interpolation
            ampl =  (1.0 - t) * ampl1  +  t * ampl2
            phase = (1.0 - t) * phase1 +  t * phase2
            #print ("new %10.6f %10.6f" % (ampl, phase))
    except:
      traceback.print_exc()
      return 0.0, 0.0
    #print ("new %10.6f %10.6f" % (ampl, phase))
    return ampl, phase
  def PostStartup(self):	# called once after sound attempts to start
    self.config_screen.OnGraphData(None)	# update config in case sound is not running
    #txt = self.sound_thread.config_text		# change config_text if StartSamples() returns a string
    #if txt:
    #  self.config_text = txt
    #  self.main_frame.SetConfigText(txt)
  def FldigiPoll(self):		# Keep Quisk and Fldigi frequencies equal; control Fldigi PTT from Quisk
    if self.fldigi_server is None:
      return
    if self.fldigi_new_freq:	# Our frequency changed; send to fldigi
      try:
        self.fldigi_server.main.set_frequency(float(self.fldigi_new_freq))
      except:
        # traceback.print_exc()
        pass
      self.fldigi_new_freq = None
      self.fldigi_timer = time.time()
      return
    try:
      freq = self.fldigi_server.main.get_frequency()
    except:
      # traceback.print_exc()
      return
    else:
      freq = int(freq + 0.5)
    try:
      rxtx = self.fldigi_server.main.get_trx_status()	# returns rx, tx, tune
    except:
      return
    if time.time() - self.fldigi_timer < 0.3:		# If timer is small, change originated in Quisk
      self.fldigi_rxtx = rxtx
      self.fldigi_freq = freq
      return
    if self.fldigi_freq != freq:
      self.fldigi_freq = freq
      #print "Change freq", freq
      self.ChangeRxTxFrequency(None, freq)
      self.fldigi_new_freq = None
    if self.fldigi_rxtx != rxtx:
      self.fldigi_rxtx = rxtx
      #print 'Fldigi changed to', rxtx
      if rxtx == 'rx':
        self.pttButton.SetValue(0, True)
      else:
        self.pttButton.SetValue(1, True)
      self.fldigi_timer = time.time()
    else:
      if QS.is_key_down():
        if rxtx == 'rx':
          self.fldigi_server.main.tx()
          self.fldigi_timer = time.time()
      else:	# key is up
        if rxtx != 'rx':
          self.fldigi_server.main.rx()
          self.fldigi_timer = time.time()
  def HamlibPoll(self):		# Poll for Hamlib and K4 TCP commands
    if self.hamlib_socket:
      try:		# Poll for new client connections.
        conn, address = self.hamlib_socket.accept()
      except socket.error:
        pass
      else:
        # print ('Connection from', address)
        self.hamlib_clients.append(HamlibHandlerRig2(self, conn, address))
      for client in self.hamlib_clients:	# Service existing clients
        if not client.Process():		# False return indicates a closed connection; remove the handler for this client
          self.hamlib_clients.remove(client)
          # print ('Remove', client.address)
          break
    if self.k4_tcp_socket:
      try:		# Poll for new client connections.
        conn, address = self.k4_tcp_socket.accept()
      except socket.error:
        pass
      else:
        # print ('Connection from', address)
        self.k4_tcp_clients.append(ElecraftK4Handler(self, conf, conn, address))
      for client in self.k4_tcp_clients:	# Service existing clients
        if not client.Process():		# False return indicates a closed connection; remove the handler for this client
          self.k4_tcp_clients.remove(client)
          # print ('Remove', client.address)
          break
  def OnKeyHook(self, event):
    event.Skip()
    if conf.hot_key_ptt_if_hidden:	# Hot key PTT operates even if Quisk is hidden
      return	# Poll key with HotKeyPoll()
    ptt1 = conf.hot_key_ptt1
    if not ptt1:
      return
    if 97 <= ptt1 <= 122:       # Lower case
      ptt1 -= 32        # Convert to upper case
    if event.GetKeyCode() == ptt1:
      ptt2 = conf.hot_key_ptt2
      hit = False
      if ptt2 is None or ptt2 == wx.ACCEL_NORMAL:
        hit = True
      elif ptt2 == wx.ACCEL_SHIFT:
        hit = event.ShiftDown()
      elif ptt2 == wx.ACCEL_CTRL:
        hit = event.ControlDown()
      elif ptt2 == wx.ACCEL_ALT:
        hit = event.AltDown()
      elif ptt2 == wx.ACCEL_SHIFT | wx.ACCEL_CTRL:
        hit = event.ShiftDown() and event.ControlDown()
      else:
        hit = True
      if hit:		# Repeated key press events will occur
        self.hot_key_ptt_pressed = True
  def HotKeyPoll(self):		# This is only used if the hot key DOES work when Quisk is hidden.
    if self.QuiskGetKeyState(conf.hot_key_ptt1):
      ptt2 = conf.hot_key_ptt2
      if ptt2 is None or ptt2 == wx.ACCEL_NORMAL:
        self.hot_key_ptt_is_down = True
      elif ptt2 == wx.ACCEL_SHIFT:
        self.hot_key_ptt_is_down = wx.GetKeyState(wx.WXK_SHIFT)
      elif ptt2 == wx.ACCEL_CTRL:
        self.hot_key_ptt_is_down = wx.GetKeyState(wx.WXK_CONTROL)
      elif ptt2 == wx.ACCEL_ALT:
        self.hot_key_ptt_is_down = wx.GetKeyState(wx.WXK_ALT)
      elif ptt2 == wx.ACCEL_SHIFT | wx.ACCEL_CTRL:
        self.hot_key_ptt_is_down = wx.GetKeyState(wx.WXK_SHIFT) and wx.GetKeyState(wx.WXK_CONTROL)
      else:
        self.hot_key_ptt_is_down = True
    else:
      self.hot_key_ptt_is_down = False
    if self.hot_key_ptt_is_down and not self.hot_key_ptt_was_down:
      self.hot_key_ptt_pressed = True
  def OnReadSound(self):	# called at frequent intervals
    #if sys.platform == 'win32':
    #  self.main_frame.Update()
    if self.hamlib_com1_handler:
      self.hamlib_com1_handler.Process()
    if self.hamlib_com2_handler:
      self.hamlib_com2_handler.Process()

    # --------------------------------------------------------------------- добавлено -------------------- CAT --------------------------- 49 RA3PKJ
    if self.hamlib_com3_handler:
      self.hamlib_com3_handler.Process()

    if self.use_fast_heart_beat:
      Hardware.FastHeartBeat()
    if self.poll_gui_control:
      Hardware.PollGuiControl()
    if conf.do_repeater_offset:
      hold = QS.tx_hold_state(-1)
      if hold == 2:	# Tx is being held for an FM repeater TX frequency shift
        rdict = self.config_screen.favorites.RepeaterDict
        freq = self.txFreq + self.VFO
        freq = ((freq + 500) // 1000) * 1000
        if freq in rdict:
          offset, tone = rdict[freq]
          QS.set_ctcss(tone)
          Hardware.RepeaterOffset(offset)
          for i in range(100):
            time.sleep(0.010)
            if Hardware.RepeaterOffset():
              break
        QS.tx_hold_state(3)
      elif hold == 4:	# No delay necessary on key up
        Hardware.RepeaterOffset(0)
        QS.set_ctcss(0)
        QS.tx_hold_state(1)
    if QS.is_key_down() and not self.tx_inhibit:	# Tx indicator
      if not self.tx_indicator:
        self.tx_indicator = True
        self.pttButton.Tx.TurnOn(True)
    else:
      if self.tx_indicator:
        self.tx_indicator = False
        self.pttButton.Tx.TurnOn(False)
    if True:	# Manage the PTT button using serial port, VOX, hot keys, WAV file play, PTT button, MIDI, CAT
      ptt_button_down = self.pttButton.GetValue()
      ptt = None
      if conf.quisk_serial_cts[0:4] == "PTT " or conf.quisk_serial_dsr[0:4] == "PTT ":
        old = self.serial_ptt_active
        if self.file_play_state == 0:
          if QS.get_params("serial_ptt"):
            ptt = True
            self.serial_ptt_active = True
          elif self.serial_ptt_active:
            ptt = False
            self.serial_ptt_active = False
        elif self.file_play_state == 2 and QS.get_params("serial_ptt"):
          self.TurnOffFilePlay()
          ptt = True
          self.serial_ptt_active = True
        if self.remote_control_head and old != self.serial_ptt_active:
          Hardware.RemoteCtlSend('PTT;%d\n' % self.serial_ptt_active)
      if self.useVOX:
        if self.file_play_state == 0:
          if QS.is_vox():
            ptt = True
            self.vox_ptt_active = True
          elif self.vox_ptt_active:
            ptt = False
            self.vox_ptt_active = False
        elif self.file_play_state == 2 and QS.is_vox():			# VOX tripped between file play repeats
          self.TurnOffFilePlay()
          ptt = True
          self.vox_ptt_active = True
      if self.file_play_state == 2 and QS.is_key_down():			# hardware key between file play repeats
        if time.time() > self.file_play_timer - self.file_play_repeat + 0.25:	# pause to allow key state to change
          self.TurnOffFilePlay()
          ptt = False
      if conf.hot_key_ptt1 and self.screen != self.config_screen:
        if conf.hot_key_ptt_if_hidden:	# hot key PTT operates even if Quisk is hidden
          self.HotKeyPoll()
        if conf.hot_key_ptt_toggle:
          if self.hot_key_ptt_pressed:	# Key down event was received
            ptt = not ptt_button_down
            if ptt:
              self.TurnOffFilePlay()
        else:
          if self.hot_key_ptt_pressed:	# Multiple key down events are being received
            ptt = True
            self.hot_key_ptt_active = True
            if not ptt_button_down:
              self.TurnOffFilePlay()
          elif self.hot_key_ptt_active and not self.QuiskGetKeyState(conf.hot_key_ptt1):
            ptt = False
            self.hot_key_ptt_active = False
        self.hot_key_ptt_was_down = self.hot_key_ptt_is_down
        self.hot_key_ptt_pressed = False
      if self.tx_inhibit:
        ptt = False
      if ptt is True and not ptt_button_down:
        self.SetPTT(True)
      elif ptt is False and ptt_button_down:
        self.SetPTT(False)
    if self.want_RxTx:
      x = QS.is_key_down()	# Must be 0 or 1
      if self.old_RxTx != x:
        self.old_RxTx = x
        Hardware.OnChangeRxTx(x)
    self.timer = time.time()
    if self.bandscope_clock:		# Hermes UDP protocol
      data = QS.get_bandscope(self.bandscope_clock, self.bandscope_screen.zoom, float(self.bandscope_screen.zoom_deltaf))
      if data and self.screen == self.bandscope_screen:
        self.screen.OnGraphData(data)
    if self.screen == self.scope:
      # Get raw data, not FFT
      data = QS.get_graph(0, 1.0, 0)
      if data:
        self.scope.OnGraphData(data)			# Send message to draw new data
        return 1		# we got new graph/scope data
    elif self.screen == self.audio_fft_screen:
      QS.get_graph(2, self.zoom, float(self.zoom_deltaf))	# discard data
      audio_data = QS.get_audio_graph()		# Display the audio FFT
      if audio_data:
        self.screen.OnGraphData(audio_data)
    else:
      data = QS.get_graph(1, self.zoom, float(self.zoom_deltaf))	# get FFT data
      if data:
        #T('')
        if self.remote_control_slave: # Если Quisk на стороне Server (железо трансивера), то он отсылает показание в Client (пользователь)
          #Hardware.RemoteCtlSend("M;%s\n" % self.smeter.GetLabel()) # --- удалено ---- текстовая инфо на панораме для удалёнки ---------- 17 RA3PKJ
          # -------------------------------------------------------------- взамен ----- текстовая инфо на панораме для удалёнки ---------- 17 RA3PKJ
          Hardware.RemoteCtlSend("M;%s\n" % (str(self.smeter_sunits) + '_' + str(self.smeter_db) + '_' + self.measure_audio_str))

        # ------------------------------------------------------- удалено ------------- текстовая инфо на панораме для удалёнки ---------- 17 RA3PKJ
        #if self.remote_control_head:
          #self.smeter.SetLabel(Hardware.GetSmeter())

        # --------------------------------------------------------------- удалено ----------------- вынос из малого окошка ---------------- 8 RA3PKJ
        #elif self.screen == self.bandscope_screen:
          #d = QS.get_hermes_adc()	# ADC level from bandscope, 0.0 to 1.0
          #if d < 1E-10:
            #d = 1E-10
          #self.smeter.SetLabel(" ADC %.0f%% %.0fdB" % (d * 100.0, 20 * math.log10(d)))
        #elif self.smeter_usage == "smeter":		# update the S-meter
          #if self.mode in ('FDV-U', 'FDV-L'):
            #self.NewDVmeter()
          #else:
            #self.NewSmeter()
        #elif self.smeter_usage == "freq":
          #self.MeasureFrequency()	# display measured frequency
        #else:
          #self.MeasureAudioVoltage()		# display audio voltage
        # ----------------------------------------------------------------------- взамен ------------- вынос из малого окошка ------------- 8 RA3PKJ
        if self.mode in ('FDV-U', 'FDV-L'):
          self.NewDVmeter() # ------------------------------- оставить FreeDV SNR в малом окошке
        self.NewSmeter()
        self.MeasureFrequency()     #функция измерения частоты
        self.MeasureAudioVoltage()    #функция измерения напряжения

        if self.screen == self.config_screen:
          pass
        elif self.screen == self.radios_screen: # ------------------------------------- добавлено ------------- кнопка Hardware ---------- 15 RA3PKJ
          pass
        elif self.screen == self.bandscope_screen:
          pass
        else:
          self.screen.OnGraphData(data)			# Send message to draw new data
        #T('graph data')
        #application.Yield()
        #T('Yield')
        return 1		# We got new graph/scope data
    data, index = QS.get_multirx_graph()	# get FFT data for sub-receivers
    if data:
      self.multi_rx_screen.OnGraphData(data, index)
    if QS.get_overrange():
      self.clip_time0 = self.timer
      self.freqDisplay.Clip(1)
    if self.clip_time0:
      if self.timer - self.clip_time0 > 1.0:
        self.clip_time0 = 0
        self.freqDisplay.Clip(0)
    if self.timer - self.heart_time0 > 0.10:	# call hardware to perform background tasks:
      self.heart_time0 = self.timer
      Hardware.HeartBeat()
      if conf.hermes_lite2_enable:
        self.tx_inhibit = QS.get_params('quisk_tx_inhibit')
      else:
        self.tx_inhibit = 0
      if self.tx_inhibit != self.old_tx_inhibit:
        self.old_tx_inhibit = self.tx_inhibit
        self.graph.display.Refresh()
        self.waterfall.pane1.display.Refresh()
      if self.tx_inhibit and self.spotButton.GetValue():
        self.spotButton.SetValue(0, True)
      msg = QS.GetQuiskPrintf()
      if msg:
        print(msg, end='')
      if self.screen == self.config_screen:
        self.screen.OnGraphData()			# Send message to draw new data
      if self.add_version and Hardware.GetFirmwareVersion() is not None:
        self.add_version = False
        self.config_text = "%s, firmware version 1.%d" % (self.config_text, Hardware.GetFirmwareVersion())
        self.main_frame.SetConfigText(self.config_text)
      if not self.band_up_down:
        # Poll the hardware for changed frequency.  This is used for hardware
        # that can change its frequency independently of Quisk; eg. K3.
        tune, vfo = Hardware.ReturnFrequency()
        if tune is not None and vfo is not None:
          self.BandFromFreq(tune)
          self.ChangeDisplayFrequency(tune - vfo, vfo)
        self.FldigiPoll()
        self.HamlibPoll()
        if self.dxCluster:
          if self.dxCluster.Poll():
            self.station_screen.Refresh()
      if self.timer - self.slowheart_time0 > 0.5:
        self.slowheart_time0 = self.timer
        if self.w_phase:
          self.w_phase.SlowHeartBeat()
      if self.timer - self.save_time0 > 20.0:
        self.save_time0 = self.timer
        if self.CheckState():
          self.SaveState()
        self.local_conf.SaveState()
      if self.tmp_playing and QS.set_record_state(-1):	# poll to see if playback is finished
        self.btnTmpPlay.SetValue(False, True)
      if self.file_play_state == 0:
        pass
      elif self.file_play_state == 1:
        if QS.set_record_state(-1):		# poll to see if playback is finished
          if  self.file_play_source == 12 and self.file_play_repeat:	# repeat the CW message
            self.file_play_state = 2	# Waiting for the timer to expire, and start another playback
            self.file_play_timer = self.timer + self.file_play_repeat
            self.SetPTT(False)
          else:
            self.btnFilePlay.SetValue(False, True)
      elif self.file_play_state == 2:
        if self.timer >= self.file_play_timer:
          QS.set_record_state(5)		# Start another playback
          self.file_play_state = 1
          self.SetPTT(True)
  def OnReadMIDI(self, byts):
    for byt in byts:
      if byt & 0x80:		# this is a status byte and the start of a new message
        self.midi_message = [byt]
      else:
        self.midi_message.append(byt)
      if len(self.midi_message) == 3:
        if self.config_midi_window:
          self.config_midi_window.OnNewMidiNote(self.midi_message)
    if self.midi_handler is None:
      if hasattr(conf, 'MidiHandler'):
        self.midi_handler = conf.MidiHandler(self, conf)
      else:
        import midi_handler
        self.midi_handler = midi_handler.MidiHandler(self, conf)
    self.midi_handler.OnReadMIDI(byts)

def main():
  """If quisk is installed as a package, you can run it with quisk.main()."""
  App()
  application.MainLoop()

if __name__ == '__main__':
  main()

