# -*- coding: utf-8 -*- #added by RA3PKJ - строчка добавилась после того, как начал писать комментарии на русском языке ----------------------------------
# This provides access to a remote radio.  See ac2yd/remote_common.py and .pdf files for documentation.

from ac2yd.control_common import ControlCommon

class Hardware(ControlCommon):
  def __init__(self, app, conf):
    ControlCommon.__init__(self, app, conf)
    self.hard_radio = "softrock" # --------------------- добавлено --- встраивание своих CAT-команд для аппаратной панели --- 53 RA3PKJ
  def RadioInit(self):	# Send initial parameters not covered by CommonInit()
    pass
  def SetTxLevel(self): # --------------------------------------------------- добавлено --- реформа удалённого управления --- 37 RA3PKJ
    pass
