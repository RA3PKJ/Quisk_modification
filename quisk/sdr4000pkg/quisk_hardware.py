# -*- coding: utf-8 -*- #added by RA3PKJ - строчка добавилась после того, как начал писать комментарии на русском языке ----------------------------------

# Please do not change this hardware control module for Quisk.
# It provides USB control of SoftRock hardware.

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import sys, struct, time, traceback, math
from quisk_hardware_model import Hardware as BaseHardware
import _quisk as QS

# All USB access is through control transfers using pyusb.
#   byte_array      = dev.ctrl_transfer (IN,  bmRequest, wValue, wIndex, length, timeout)
#   len(string_msg) = dev.ctrl_transfer (OUT, bmRequest, wValue, wIndex, string_msg, timeout)

# Define the name of the hardware and the items on the hardware screen (see quisk_conf_defaults.py):
################ Receivers SDR-4000, The special radio that I own
## hardware_file_name Hardware file path, rfile
# This is the file that contains the control logic for each radio.
#hardware_file_name = 'sdr4000pkg/quisk_hardware.py'

try:
  import usb
  import usb.core, usb.util
except:
  if sys.platform == 'win32':
    dlg = wx.MessageDialog(None, "The Python pyusb module is required but not installed. Do you want me to install it?",
      "Install Python pyusb", style = wx.YES|wx.NO)
    if dlg.ShowModal() == wx.ID_YES:
      import subprocess
      subprocess.call([sys.executable, "-m", "pip", "install", "pyusb"])
      try:
        import usb
        import usb.core, usb.util
      except:
        dlg = wx.MessageDialog(None, "Installation of Python pyusb failed. Please install it by hand.",
           "Installation failed", style=wx.OK)
        dlg.ShowModal()
  else:
    dlg = wx.MessageDialog(None, "The Python pyusb module is required but not installed. Please install package python-usb.",
      "Install Python pyusb", style = wx.OK)
    dlg.ShowModal()

DEBUG = 0

# Thanks to Ethan Blanton, KB8OJH, for this patch for the Si570 (many SoftRocks):
# These are used by SetFreqByDirect(); see below.
# The Si570 DCO must be clamped between these values
SI570_MIN_DCO = 4.85e9
SI570_MAX_DCO = 5.67e9
# The Si570 has 6 valid HSDIV values.  Subtract 4 from HSDIV before
# stuffing it.  We want to find the highest HSDIV first, so start
# from 11.
SI570_HSDIV_VALUES = [11, 9, 7, 6, 5, 4]


##IN = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
##OUT = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)


UBYTE2 = struct.Struct('<H')
UBYTE4 = struct.Struct('<L')	# Thanks to Sivan Toledo

class Hardware(BaseHardware):
  def __init__(self, app, conf):
    BaseHardware.__init__(self, app, conf)
    self.usb_dev = None
    self.endpoint_in = None #-----------------------------------------------------------------------------
    self.endpoint_out = None #-------------------------------------------------------------------------------------
    self.tx_control = 0
    self.vfo = None
    self.mode = None
    self.band = None
    self.data_out = [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]#-------------------------
    self.repeater_freq = None		# original repeater output frequency
    try:
      self.repeater_delay = conf.repeater_delay		# delay for changing repeater frequency in seconds
    except:
      self.repeater_delay = 0.25
    self.repeater_time0 = 0			# time of repeater change in frequency
    self.ptt_button = 0
    self.si570_i2c_address = conf.si570_i2c_address

  def open(self):			# Called once to open the Hardware
    global usb
    try:
      # find our device
      self.usb_dev = usb.core.find(idVendor=self.conf.usb_vendor_id, idProduct=self.conf.usb_product_id)
      self.usb_dev.set_configuration()
      cfg = self.usb_dev.get_active_configuration()
      hid_intf = usb.util.find_descriptor(cfg, bInterfaceClass = 3) # находим дескриптор интерфейса
      # если интерфейс найден, то находим обе конечные точки (IN, OUT)
      if hid_intf is not None:
        self.endpoint_in = hid_intf[0] # конечная точка EP1 IN
        self.endpoint_out = hid_intf[1] # конечная точка EP1 OUT (это не одна и та же точка, что выше)
        text = 'Capture from SDR-4000 on USB'
    except:
      wx.MessageBox('SDR-4000 not found')
      text = 'SDR-4000 not found'
    return text

  def close(self):			# Called once to close the Hardware
    pass
  def ChangeFrequency(self, tune, vfo, source='', band='', event=None):
    if self.usb_dev and self.vfo != vfo:
      if self.conf.si570_direct_control:
        if self.SetFreqByDirect(vfo - self.transverter_offset):
          self.vfo = vfo
      elif self.SetFreqByValue(vfo - self.transverter_offset):
         self.vfo = vfo
      if DEBUG:
        print ('Change to', vfo)
        print ('Run freq', self.GetFreq())
    return tune, vfo
  def ChangeBand(self, band):
    # band is a string: "60", "40", "WWV", etc.
    BaseHardware.ChangeBand(self, band)
    self.band = band
    self.SetTxLevel()
  def ChangeMode(self, mode):
    # mode is a string: "USB", "AM", etc.
    BaseHardware.ChangeMode(self, mode)
    self.mode = mode
    QS.set_cwkey(0)
    self.SetTxLevel()
  def SetTxLevel(self):
    tx_level = self.conf.tx_level.get(self.band, 70)
    if self.mode[0:3] in ('DGT', 'FDV'):			# Digital modes; change power by a percentage
      reduc = self.application.digital_tx_level
    else:
      reduc = self.application.tx_level
    tx_level = int(tx_level * reduc / 100.0 + 0.5)
    if tx_level < 0:
      tx_level = 0
    elif tx_level > 100:
      tx_level = 100
    QS.set_mic_out_volume(tx_level)
    if DEBUG: print("Change tx_level to", tx_level)
  def ReturnFrequency(self):
    # Return the current tuning and VFO frequency.  If neither have changed,
    # you can return (None, None).  This is called at about 10 Hz by the main.
    # return (tune, vfo)	# return changed frequencies
    return None, None		# frequencies have not changed
  def RepeaterOffset(self, offset=None):	# Change frequency for repeater offset during Tx
    if offset is None:		# Return True if frequency change is complete
      if time.time() > self.repeater_time0 + self.repeater_delay:
        return True
    elif offset == 0:			# Change back to the original frequency
      if self.repeater_freq is not None:
        self.repeater_time0 = time.time()
        self.ChangeFrequency(self.repeater_freq, self.repeater_freq, 'repeater')
        self.repeater_freq = None
    else:			# Shift to repeater input frequency
      self.repeater_time0 = time.time()
      self.repeater_freq = self.vfo
      vfo = self.vfo + int(offset * 1000)	# Convert kHz to Hz
      self.ChangeFrequency(vfo, vfo, 'repeater')
    return False




  def HeartBeat(self):	# Called at about 10 Hz by the main-----------------------------------------------------------------------
    # Read data from the device
    try:
      data = self.usb_dev.read(self.endpoint_in.bEndpointAddress, self.endpoint_in.wMaxPacketSize)
      if data[1] & 0x80 == 0: # ---- вход PTT
        QS.set_PTT(1)
      else:
        QS.set_PTT(0)
      if data[1] & 0x08 == 0: # ---- вход Mute
        QS.set_volume(0)
      else:
        QS.set_volume(self.application.audio_volume)
      if data[2]: # ADC
        pass
      if data[3]: # ADC
        pass
    except:
      pass

  def OnSpot(self, level):
    self.usb_dev.write(self.endpoint_out.bEndpointAddress, self.data_out, 1000)

  def OnButtonRfGain(self, event):
    pass
#    # The HiQSDR attenuator is five bits: 2, 4, 8, 10, 20 dB
#    btn = event.GetEventObject()
#    n = btn.index
#    self.HiQSDR_Connector_X1 &= ~0x10	# Mask in the preamp bit
#    if n == 0:		# 0dB
#      self.HiQSDR_Attenuator = 0
#      self.rf_gain = 0
#    elif n == 1:	# +10
#      self.HiQSDR_Attenuator = 0
#      self.HiQSDR_Connector_X1 |= 0x10
#      self.rf_gain = 10
#    elif n == 2:	# -10
#      self.HiQSDR_Attenuator = 0x08
#      self.rf_gain = -10
#    elif n == 3:	# -20
#      self.HiQSDR_Attenuator = 0x10
#      self.rf_gain = -20
#    elif n == 4:	# -30
#      self.HiQSDR_Attenuator = 0x18
#      self.rf_gain = -30
#    else:
#      self.HiQSDR_Attenuator = 0
#      self.rf_gain = 0
#      print ('Unknown RfGain')
#    self.NewUdpStatus()

  def OnChangeRxTx(self, is_tx):	# Called by Quisk when changing between Rx and Tx. "is_tx" is 0 or 1
    pass
#    if not self.usb_dev:
#      return
#    try:
#      self.usb_dev.ctrl_transfer(IN, 0x50, is_tx, 0, 3)
#    except usb.core.USBError:
#      if DEBUG: traceback.print_exc()
#      try:
#        self.usb_dev.ctrl_transfer(IN, 0x50, is_tx, 0, 3)
#      except usb.core.USBError:
#        if DEBUG: traceback.print_exc()
#      else:
#        if DEBUG: print("OnChangeRxTx", is_tx)
#    else:
#      if DEBUG: print("OnChangeRxTx", is_tx)
  def GetStartupFreq(self):	# return the startup frequency / 4
    pass
#    if not self.usb_dev:
#      return 0
#    ret = self.usb_dev.ctrl_transfer(IN, 0x3C, 0, 0, 4)
#    s = ret.tobytes()
#    freq = UBYTE4.unpack(s)[0]
#    freq = int(freq * 1.0e6 / 2097152.0 / 4.0 + 0.5)
#    return freq
  def GetFreq(self):	# return the running frequency / 4
    pass
#    if not self.usb_dev:
#      return 0
#    ret = self.usb_dev.ctrl_transfer(IN, 0x3A, 0, 0, 4)
#    s = ret.tobytes()
#    freq = UBYTE4.unpack(s)[0]
#    freq = int(freq * 1.0e6 / 2097152.0 / 4.0 + 0.5)
#    return freq
  def SetFreqByValue(self, freq):
    pass
#    freq = int(freq/1.0e6 * 2097152.0 * 4.0 + 0.5)
#    if freq <= 0:
#      return
#    s = UBYTE4.pack(freq)
#    try:
#      self.usb_dev.ctrl_transfer(OUT, 0x32, self.si570_i2c_address + 0x700, 0, s)
#    except usb.core.USBError:
#      if DEBUG: traceback.print_exc()
#    else:
#      return True
  def SetFreqByDirect(self, freq):	# Thanks to Ethan Blanton, KB8OJH
    pass
#    if freq == 0.0:
#      return False
#    # For now, find the minimum DCO speed that will give us the
#    # desired frequency; if we're slewing in the future, we want this
#    # to additionally yield an RFREQ ~= 512.
#    freq = int(freq * 4)
#    dco_new = None
#    hsdiv_new = 0
#    n1_new = 0
#    for hsdiv in SI570_HSDIV_VALUES:
#      n1 = int(math.ceil(SI570_MIN_DCO / (freq * hsdiv)))
#      if n1 < 1:
#        n1 = 1
#      else:
#        n1 = ((n1 + 1) // 2) * 2
#      dco = (freq * 1.0) * hsdiv * n1
#      # Since we're starting with max hsdiv, this can only happen if
#      # freq was larger than we can handle
#      if n1 > 128:
#        continue
#      if dco < SI570_MIN_DCO or dco > SI570_MAX_DCO:
#        # This really shouldn't happen
#        continue
#      if not dco_new or dco < dco_new:
#        dco_new = dco
#        hsdiv_new = hsdiv
#        n1_new = n1
#    if not dco_new:
#      # For some reason, we were unable to calculate a frequency.
#      # Probably because the frequency requested is outside the range
#      # of our device.
#      return False		# Failure
#    rfreq = dco_new / self.conf.si570_xtal_freq
#    rfreq_int = int(rfreq)
#    rfreq_frac = int(round((rfreq - rfreq_int) * 2**28))
#    # It looks like the DG8SAQ protocol just passes r7-r12 straight
#    # To the Si570 when given command 0x30.  Easy enough.
#    # n1 is stuffed as n1 - 1, hsdiv is stuffed as hsdiv - 4.
#    hsdiv_new = hsdiv_new - 4
#    n1_new = n1_new - 1
#    s = struct.Struct('>BBL').pack((hsdiv_new << 5) + (n1_new >> 2),
#                                   ((n1_new & 0x3) << 6) + (rfreq_int >> 4),
#                                   ((rfreq_int & 0xf) << 28) + rfreq_frac)
#    self.usb_dev.ctrl_transfer(OUT, 0x30, self.si570_i2c_address + 0x700, 0, s)
#    return True		# Success
  def PollCwKey(self):  # Called frequently by Quisk to check the CW key status
    pass
#    if not self.usb_dev:
#      return
#    if self.mode not in ('CWU', 'CWL'):
#      return
#    try:		# Test key up/down state
#      ret = self.usb_dev.ctrl_transfer(IN, 0x51, 0, 0, 1)
#    except:
#      QS.set_cwkey(0)
#      if DEBUG: traceback.print_exc()
#    else:
#      # bit 0x20 is the tip, bit 0x02 is the ring (ring not used)
#      if ret[0] & 0x20 == 0:		# Tip: key is down
#        QS.set_cwkey(1)
#      else:			# key is up
#        QS.set_cwkey(0)
