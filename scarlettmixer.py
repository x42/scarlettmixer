#!/usr/bin/python

## Focusrite(R) Scarlett 18i6 mixer control (firmware v305)
#
# Copyright (C) 2013 Robin Gareus <robin@gareus.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# requires https://github.com/walac/pyusb
import usb.core
import usb.util
import sys
import math

#### connect to hardware ######################################################
def detach_kernel_driver(self, dev_handle, intf):
  _check(_lib.usb_detach_kernel_driver_np(dev_handle, intf))

device = usb.core.find(idVendor= 0x1235, idProduct=0x8004)

if device is None:
  raise ValueError('Device not found')

#device.set_configuration()

#### send USB URB ctrl commands ###############################################
def ctrl_send(wValue, wIndex, data):
  try:
    assert device.ctrl_transfer(0x21, 0x01, wValue, wIndex, data) == len(data)
  except:
    raise ValueError('request failed')

def ctrl_cmd(cmd, wValue, wIndex, data):
  try:
    assert device.ctrl_transfer(0x21, cmd, wValue, wIndex, data) == len(data)
  except:
    raise ValueError('request failed')

def ctrl_req(cmd, wValue, wIndex, data):
  try:
    rv = device.ctrl_transfer(0xa1, cmd, wValue, wIndex, data)
    return rv;
  except:
    raise ValueError('request failed')

#### DOC ######################################################################
#
# The protocol was reverse engineered by looking at communication between
# Scarlett MixControl (v 1.2.128.0) and the Focusrite(R) Scarlett 18i6 (firmware
# v305) using wireshark and usbmon in January 2013.
#
# As for linux-kernel device support see
# http://permalink.gmane.org/gmane.linux.alsa.devel/102747
# it was merged into linus' tip pre Linux-3.8
# http://git.kernel.org/?p=linux/kernel/git/torvalds/linux.git;a=commitdiff;h=1762a59d8e8b5e99f6f4a0f292b40f3cacb108ba
#
#
#<ditaa>
# /--------------\     18chn
# | Hardware  in +--+--------+---------------\
# \--------------/  |        |               |
#                   |        |               v 18chn
#                   |        |         +-----------+
#                   |        |         | PC    DAW |
#                   |        |         +-----+--=--+
#                   |        |               | 6chn
#                   |        |       /-------+
#                   |        |       |       |
#                   |        v       v       |
#                   |      +-----------+     |
#                   |      | Mixer     |     |
#                   |      |    Router |     |
#                   |      +-----+-----+     |
#                   |            |           |
#                   |            | 18chn     |
#                   |            v           |
#                   |      +-----------+     |
#                   |      | Mixer     |     |
#                   |      |    Matrix |     |
#                   |      |           |     |
#                   |      | 18x6 Gain |     |
#                   |      |   stages  |     |
#                   |      +-----+-----+     |
#                   |            |           |
#                   | 18chn      | 6chn      | 6chn
#                   v            v           v
#                 +----------------------------+
#                 |           Router           |
#                 +--------------+-------------+
#                                |
#                                | 6chn
#                                v
#                 +----------------------------+
#                 |      Master Gain Ctrl      |
#                 +--------------+-------------+
#                                |
# /--------------\     6chn      |
# | Hardware out |<--------------/
# \--------------/
#</ditaa>
#
# PC/PCM (USB)
#   - read 18 PCM signals (8 analog + 10 digial inputs)
#   - write 6 PCM signals -- called "DAW"
#
# Device internal routing:
#
# 1) matrix-mixer: 18 in -> 6 out (18 * 6 gain stages), one to one relationship
#   - each of the 18 inputs can be re-assigned. Choose from "sigsrc" (24 options)
#     the 6 DAW PCM signals or one of the 18 physical inputs.
#   - the mixer has 6 outputs M1..M6
#
#    mixer_set_source()
#    mixer_set_gain()
#
# 2) routing, 6x6 switch-board, 6 inputs -> 6 output one to many relationship
#   - each of the 6 ins can be chosen from 'mixbus'
#     mix-busses include all of the 18 inputs, 6 DAW and the matrix-mixer-out M1..6
#     (30 options == 18 ins + 6 PCM + 6 matrix-mix)
#   - the six available output routes are Monitor1,2 Phones1,2 SPDIF1,2
#
#   A source can be connected to multiple destinations. but each destination
#   can have only one source.
#
#    bus_set_source()
#
# 3) master gain and route mute:
#    the analog outputs of the switch-board can be attenuated or muted independently
#   - master gain + mute for all routes
#   - attenuation + mute for Monitor1,2 and Phones1,2
#
#   sw_mute_bus()
#   att_postroute()
#   att_out_master(), att_out_monitor(),  att_out_phones()
#
# generic switches and control
#  - choose clock source: sw_clocksource()
#  - select impedance of input1,2: sw_impedance()
#  - store current settings to hardware: cfg_save_settings_to_hardware()
#
#
# MISC:
# - set samplerate
#   ctrl_send(0x0100, 0x2900, [0x80, 0xbb, 0x00, 0x00]) # 48000 = 0xbb80
# - save settings to hardware
#  ctrl_cmd(0x03, 0x005a, 0x3c00, [0xa5])
#
# USB URB commands overview
#  wIndex
#  0x0100  Analog Input line/instrument impedance switch, wValue=0x0901 + channel, data=Line/Inst (2bytes)
#  0x0a00  Master Volume, wValue=0x0200+bus data(2bytes); Bus Mute/Unmute wValue=0x0100+bus, data(2bytes)
#  0x2800  Clock source, wValue=0x0100, data=int,spdif,adat (1byte)
#  0x2900  Set Sample-rate, wValue=0x0100 data=samle-rate(4bytes)
#  0x3200  Assign mixer inputs, wValue=0x0600 + mixer-channel, data=input-to-connect(2bytes)
#  0x3300  Routing table, wValue=bus, data=input-to-connect(2bytes)
#  0x3400  ?? (clear mixer -- force assignment) used during factory-reset
#  0x3c00  Matrix Mixer gains, wValue=mixer-node  data=gain(2bytes)
#


#### ENUMS ####################################################################

def enum(**enums):
  return type('Enum', (), enums)

impedance = enum(LINEIN=0, INSTRUMENT=1)
clocksource = enum(INTERNAL=1, SPDIF=2, ADAT=3)
mute = enum(UNMUTE = [0x00, 0x00], MUTE = [0x01, 0x00])

# signal sources that can be connected to Matrix-Mixer Inputs
sigsrc = enum(
    OFF     = 0xff,
    # DAW -- PCM signal sent by the computer
    DAW1    = 0x00, DAW2    = 0x01,
    DAW3    = 0x02, DAW4    = 0x03,
    DAW5    = 0x04, DAW6    = 0x05,

    # Analog inputs
    ANALG1  = 0x06, ANALG2  = 0x07,
    ANALG3  = 0x08, ANALG4  = 0x09,
    ANALG5  = 0x0a, ANALG6  = 0x0b,
    ANALG7  = 0x0c, ANALG8  = 0x0d,

    # Digital inputs
    SPDIF1  = 0x0e, SPDIF2  = 0x0f,
    ADAT1   = 0x10, ADAT2   = 0x11,
    ADAT3   = 0x12, ADAT4   = 0x13,
    ADAT5   = 0x14, ADAT6   = 0x15,
    ADAT7   = 0x16, ADAT8   = 0x17
    )

# matrix mixer outputs
mixmat = enum(
    M1  = 0x00, M2  = 0x01,
    M3  = 0x02, M4  = 0x03,
    M5  = 0x04, M6  = 0x05
    )

# signal sources that can be used as input to the router
# Note: this is concatenation of  (sigsrc + mixmat)
mixbus = enum(
    OFF     = 0xff,
    # Matrix Mixer Outputs
    M1      = 0x18, M2      = 0x19,
    M3      = 0x1a, M4      = 0x1b,
    M5      = 0x1c, M6      = 0x1d,

    # DAW -- PCM signal sent by the computer
    DAW1    = 0x00, DAW2    = 0x01,
    DAW3    = 0x02, DAW4    = 0x03,
    DAW5    = 0x04, DAW6    = 0x05,

    # Analog inputs
    ANALG1  = 0x06, ANALG2  = 0x07,
    ANALG3  = 0x08, ANALG4  = 0x09,
    ANALG5  = 0x0a, ANALG6  = 0x0b,
    ANALG7  = 0x0c, ANALG8  = 0x0d,

    # Digital inputs
    SPDIF1  = 0x0e, SPDIF2  = 0x0f,
    ADAT1   = 0x10, ADAT2   = 0x11,
    ADAT3   = 0x12, ADAT4   = 0x13,
    ADAT5   = 0x14, ADAT6   = 0x15,
    ADAT7   = 0x16, ADAT8   = 0x17
    )

#router output names
route = enum(
    MONITOR_LEFT = 0, MONITOR_RIGHT = 1,
    PHONES_LEFT  = 2, PHONES_RIGHT  = 3,
    SPDIF_LEFT   = 4, SPDIF_RIGHT   = 5
    )

#post-routing gain stage || hardware outputs
sigout = enum(
    MASTER = 0,
    MONITOR_LEFT = 1, MONITOR_RIGHT = 2,
    PHONES_LEFT  = 3, PHONES_RIGHT  = 4
    )

###############################################################################
#### helper functions - decibel calc ##########################################

##calculate attenuation for buses
# @param value dB  -infty .. 0 ; effective range -128..0 (default is 0)
# @return little endian hex representation
def att_to_hex(value):
  if (value <= -128):
    return [0x00, 0x80]
  if (value >= 0):
    return [0x00, 0x00]
  val = int(math.floor(65536.5 + 256.0 * value))
  return [(val&0xff), (val>>8)]

##caluvalet gain for mixer channel faders
# @param value dB  -infty .. +6 ; effective range -128..6 (default is 0dB)
# @return little endian hex representation
def gain_to_hex(value):
  value= int(math.floor(value+.5))
  if (value <= -128):
    return [0x00, 0x80]
  elif (value > 6):
    return [0x00, 0x06]
  elif (value >= 0):
    return [0x00, 0x00 + value]
  else:
    return [0x00, (0x100 + value)]


###############################################################################
###############################################################################


#### 18i6 config   ############################################################

## save current config on the 18i6 to be restored after power-cycles
def cfg_save_settings_to_hardware():
  ctrl_cmd(0x03, 0x005a, 0x3c00, [0xa5])


#### 18i6 switches ############################################################

## configure channel impedance
# @param channel 0,1
# @padam mode enum impedance
def sw_impedance(chn, mode):
  ctrl_send(0x0901 + chn, 0x0100, [mode, 0x00])

## set the clock source
# @param src: enum clocksource
def sw_clocksource(src):
  ctrl_send(0x0100, 0x2800, [src])


#### 18i6 bus gains ###########################################################

## mute/unmute bus
# @param bus: enum sigout -- 0: master;  1,2:monitor(L,R); 3,4: phones(L,R)
# @param onoff: enum mute
def sw_mute_bus(bus, onoff):
  if (bus < 0 or bus > 4):
    return
  ctrl_send(0x0100 + bus, 0x0a00, onoff)

## set bus attenuation
# @param bus: enum sigout -- 0: master;  1,2:monitor(L,R); 3,4: phones(L,R)
# @param gain -infty .. 0 dB
def att_postroute(bus, gain):
  if (bus < 0 or bus > 4):
    return
  ctrl_send(0x0200 + bus, 0x0a00, att_to_hex(gain))


## attenuate master out signal
# @param gain -infty .. 0 dB
def att_out_master(gain):
  att_postroute(sigout.MASTER, att_to_hex(gain))

## attenuate monitor output signal
# @param left -infty .. 0 dB
# @param right -infty .. 0 dB
def att_out_monitor(left, right):
  att_postroute(sigout.MONITOR_LEFT,  att_to_hex(left))
  att_postroute(sigout.MONITOR_RIGHT, att_to_hex(right))

## attenuate phones output signal
# @param left -infty .. 0 dB
# @param right -infty .. 0 dB
def att_out_phones(left, right):
  att_postroute(sigout.PHONES_LEFT,  att_to_hex(left))
  att_postroute(sigout.PHONES_RIGHT, att_to_hex(right))


#### matrix mixer  ############################################################

## connect signal-source to input of mixer-matix
# @param src enum sigsrc -- signal source: all inputs + DAW or off
# @param mixin mixer-matrix input-channel 0..17
def mixer_set_source(src, mixin):
  if (mixin < 0 or mixin > 0x11):
    return
  ctrl_send(0x0600 + mixin, 0x3200, [src, 0x00])

## set mixer-matrix gain
# @param chn input channel 0..17  -- corresponds to "mixin" of \ref mixer_set_source
# @param bus output bus 0..5  -- use enum mixmat
# @param gain -infty..+6 dB  (default is 0dB)
def mixer_set_gain(chn, bus, gain):
  if (bus < 0 or bus > 5):
    return
  if (chn < 0 or chn > 17):
    return
  mtx = (chn<<3) + (bus&0x07)
  ctrl_send(0x0100 + mtx, 0x3c00, gain_to_hex(gain))


#### routing table ############################################################

## connect output of mixer-matrix to the input of route.
# Note: only one mixer-bus can be connected to a bus at a given time.
# @param route enum route -- destination route
# @param mix enum mixbus -- mixer-matrix output or 'off
def bus_set_source(route, mixout):
  if (route < 0 or route > 5):
    return
  ctrl_send(route, 0x3300, [mixout, 0x00])

###############################################################################
#### FACTORY RESET ############################################################
def factory_reset():

  # ?? -- clear assignments, disconnect matrix I/O ??
  for i in range(18):
    ctrl_send(0x0000 + i , 0x3400, [0x06 + i, 0x00])

  # set bus outs
  bus_set_source(0, mixbus.M1)
  bus_set_source(1, mixbus.M2)
  bus_set_source(2, mixbus.M1)
  bus_set_source(3, mixbus.M2)
  bus_set_source(4, mixbus.OFF)
  bus_set_source(5, mixbus.OFF)

  ## Mixer config

  #Analog in
  for i in range(8):
    mixer_set_source(0x06 + i, i)
  #ADAT
  for i in range(6):
    mixer_set_source(0x10 + i, 8+i)
  #SPDIF
  mixer_set_source(0x0e, 0x0e)
  mixer_set_source(0x0f, 0x0f)
  #DAW
  mixer_set_source(0x00, 0x10)
  mixer_set_source(0x01, 0x11)

  for i in range(18):
    for o in range(6):
      g = -200
      if ((i%2) == o):
         g = 0
      mixer_set_gain(i, o, g);

  sw_mute_bus(sigout.MONITOR_LEFT, mute.UNMUTE)
  sw_mute_bus(sigout.MONITOR_RIGHT, mute.UNMUTE)
  sw_mute_bus(sigout.PHONES_LEFT, mute.UNMUTE)
  sw_mute_bus(sigout.PHONES_RIGHT, mute.UNMUTE)

  sw_impedance(0, impedance.LINEIN)
  sw_impedance(1, impedance.LINEIN)

  # ?? hi/lo gain for the 8i6 inputs 3,4 ??
  ctrl_send(0x0803, 0x0100, [0x00, 0x00])
  ctrl_send(0x0804, 0x0100, [0x00, 0x00])

def zero_settings():
  for i in range(18):
    for o in range(6):
      mixer_set_gain(i, o, -200);

  for i in range(18):
    ctrl_send(0x0000 + i , 0x3400, [0x06 + i, 0x00])

  for i in range(6):
    bus_set_source(i, mixbus.OFF)

  for i in range(18):
    mixer_set_source(sigsrc.OFF, i);

  sw_mute_bus(sigout.MONITOR_LEFT, mute.UNMUTE)
  sw_mute_bus(sigout.MONITOR_RIGHT, mute.UNMUTE)
  sw_mute_bus(sigout.PHONES_LEFT, mute.UNMUTE)
  sw_mute_bus(sigout.PHONES_RIGHT, mute.UNMUTE)


###############################################################################
#### PEAK METER ###############################################################

def val16_to_db(v):
    if (v == 0):
      return float('-inf')
    else:
      return float(20.0 * math.log(v / 65536.0, 10))

def twobyte_to_db(hi, lo):
    return val16_to_db(((hi&0xff)<<8) + (lo&0xff))

def query_peak():
  indb = []
  mixd = []
  dawd = []
  ins = ctrl_req(0x03, 0x0000, 0x3c00, 36);
  daw = ctrl_req(0x03, 0x0003, 0x3c00, 12);
  mix = ctrl_req(0x03, 0x0001, 0x3c00, 16);

  for i in range(18):
    indb.append(twobyte_to_db(ins[2*i+1], ins[2*i]))
  for i in range(6):
    dawd.append(twobyte_to_db(daw[2*i+1], daw[2*i]))
  for i in range(8):
    mixd.append(twobyte_to_db(mix[2*i+1], mix[2*i]))

  return {'input': indb, 'daw': dawd, 'mixer': mixd}



###############################################################################
#### EXAMPLE USAGE ############################################################

sw_impedance(0, impedance.LINEIN)
sw_impedance(1, impedance.LINEIN)

sw_clocksource(clocksource.INTERNAL)

# this bypasses the matrix-mixer altogether
# just route computer's PCM 1,2 to monitor and phones.
bus_set_source(route.MONITOR_LEFT,  mixbus.DAW1)
bus_set_source(route.MONITOR_RIGHT, mixbus.DAW1)

bus_set_source(route.PHONES_LEFT,   mixbus.DAW1)
bus_set_source(route.PHONES_RIGHT,  mixbus.DAW1)

bus_set_source(route.SPDIF_LEFT,  mixbus.OFF)
bus_set_source(route.SPDIF_RIGHT, mixbus.OFF)

# make sure the outputs are not muted
sw_mute_bus(sigout.MASTER, mute.UNMUTE)
sw_mute_bus(sigout.MONITOR_LEFT, mute.UNMUTE)
sw_mute_bus(sigout.MONITOR_RIGHT, mute.UNMUTE)
sw_mute_bus(sigout.PHONES_LEFT, mute.UNMUTE)
sw_mute_bus(sigout.PHONES_RIGHT, mute.UNMUTE)

# do not attenuate the outputs
att_out_master(0)
att_out_monitor(0, 0)
att_out_phones(0, 0)


### mixer example ###
# route in1 -> phones2(right) with gain -6dB
# and   in2 -> phones1(left)  with gain +1dB
if 0:
  # disconnect defaults:
  # if ANALG1 is already connected to chn0, it can not be connected to chn1
  # also if chn1 already has a connection it won't be changed
  mixer_set_source(sigsrc.OFF, 0)
  mixer_set_source(sigsrc.OFF, 1)

  # zero gains
  mixer_set_gain(0, mixmat.M1, -128);
  mixer_set_gain(0, mixmat.M2, -128);
  mixer_set_gain(1, mixmat.M1, -128);
  mixer_set_gain(1, mixmat.M2, -128);

  #instead of the above,
  #we could simply disconnect all inputs and zero all faders..
  zero_settings()

  # re-assign in2 -> matrix-ch0, in1 -> matrix-ch1
  mixer_set_source(sigsrc.ANALG2, 0)
  mixer_set_source(sigsrc.ANALG1, 1)

  # matrix ch0 -> bus M1  w/ gain +1dB
  mixer_set_gain(0, mixmat.M1, 1);
  # matrix ch1 -> bus M2  w/ gain -6dB
  mixer_set_gain(1, mixmat.M2, -6);

  # route matrix-out to output
  bus_set_source(route.PHONES_LEFT,  mixbus.M1)
  bus_set_source(route.PHONES_RIGHT, mixbus.M2)


#cfg_save_settings_to_hardware()
#sys.exit(0)

# print peaks
for i in range(10000):
  pk = query_peak();
  for i in range(8):
      print "%.1f" % pk['input'][i],
  print '|',
  for i in range(6):
      print "%.1f" % pk['daw'][i],
  print '|',
  for i in range(6):
      print "%.1f" % pk['mixer'][i],
  print '\r',

sys.exit(0)

# vim: set ts=2 sw=2 et:
