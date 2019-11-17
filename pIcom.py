#!/usr/bin/python3

import os
import sys
import serial
import numpy as np

class Radio():

    """ Basic radio information.  The parent object for Icom radio classes  """

    def __init__(self):
        self._frequency = 146.520
        self._transmitting = False
        self._baudrate = 19200
        self._port = '/dev/ttyUSB0'
        self._serial = None

    def setBaud(self, baud):
        self._baudrate = baud

    def setPort(self, port):
        self._port = port

    def connect(self):

        """ Base function to connect serial device  """

        if self._serial is not None:
            self.disconnect()

        self._serial = serial.Serial(self._port, baudrate=self._baudrate)

    def disconnect(self):

        """ Base function to disconnect serial device """
        if self._serial is not None:
            self._serial.flush()
            self._serial.close()

        self._serial = None

    def sendCmd(self,cmd):
        """ Send the command, plus and subcommands and/or data to the radio """

        ## TODO: Can we use struct here?
        for c in cmd:
            self._serial.write(bytes([c]))
        resp = self.readResponse()
        if resp != cmd:
            print("Error: Initial response does not match command!\n")

    def readResponse(self):
        """ Read the response from the radio  
            MUST READ TWICE TO GET RESPONSE.  First
            response is a copy of the command sent 
        """
        c = 0
        reply = []
        while c != 0xfd:
            d = self._serial.read(1)
            if (len(d) > 0):
                c = d[0]
            reply.append(c)

        if len(reply) == 6:
            if reply[4] == 0xfb:
                print("Command OK!")
            elif reply[4] == 0xfa:
                print("Command No Good!")
        else:
            resp = ''
            for c in reply:
                resp += '%02x ' %c
            #print(resp)
        return reply

    def convert_from_bcd(self, bcd):
        """ convert the response bcd data to integer  """
        place, decimal = 1, 0
        while bcd > 0:
            nibble = bcd & 0xf
            decimal += nibble * place
            bcd >>= 4
            place *= 10
        return decimal

    def convert_to_bcd(self, decimal):
        """ convert the decimal to bcd  """
        place, bcd = 0, 0
        while decimal > 0:
            nibble = int(decimal % 10)
            bcd += nibble << place
            decimal /= 10
            place += 4
        return bcd

class Icom7100(Radio):

    """ The Icom 7100 Radio Class.  Implements the Icom 7100
        radio functionality for use through a serial port.
    """
    ## Set some IC7100 communication defaults
    PREAMBLE = [0xfe,0xfe]
    TRANSCEIVER_ADDR = [0x88]
    CONTROLLER_ADDR = [0xe0]
    EOM = [0xfd]

    def __init__(self):
        super().__init__()
        self._memBank = ""
        self._memNum = 1
        self._baudrate = 19200
        self._port = '/dev/ttyUSB0'

    def buildCommand(self,cmd, subcmd=None, data=None):
        """ Build the command to pass to the radio
            PARAMETERS:
                      cmd: the hex command to send
                      subcmd: the hex subcommand to send, if required
                      data: the data in hex to send, if required
             RETURNS:
                    ncmd: list of cmd values to send
        """

        ## TODO: Change to use struct
        base_cmd = self.PREAMBLE + self.TRANSCEIVER_ADDR + self.CONTROLLER_ADDR 
        ncmd = base_cmd + cmd
        if subcmd is not None:
            ncmd += subcmd
        if data is not None:
            ncmd += data
        ncmd += self.EOM
        return ncmd

    def turnOn(self):
        """ Turn on the IC7100 Radio.  Command adjusted to baud rate """

        preamble_rpts = {19200:25,
                         9600:13,
                         4800:17,
                         1200:3,
                         300:2}
        on_prefix = [self.PREAMBLE[0]] * preamble_rpts[self._baudrate]
        cmd = [0x18]
        subcmd = [0x01]
        on_cmd = on_prefix + self.buildCommand(cmd,subcmd) 
        self.sendCmd(on_cmd)
        ## clear the response
        self.readResponse()

    def turnOff(self):
        """ Turn off the IC7100 radio. """

        cmd = [0x18]
        subcmd = [0x00]
        off_cmd = self.buildCommand(cmd, subcmd)
        self.sendCmd(off_cmd)
        ## clear the response
        self.readResponse()

    def selectVFO(self, c='A'):
        """ Select the VFO mode.
            PARAMETERS:
                        str c: The VFO to select, A or B
        """

        cmd = [0x07]
        subcmd = None
        if c.upper() == 'A':
            subcmd = [0x00]
        elif c.upper() == 'B':
            subcmd = [0x01]

        if subcmd is not None:
            ncmd = self.buildCommand(cmd,subcmd)
            self.sendCmd(ncmd)
            ## clear the response
            self.readResponse()
        else:
            print("Error: Incorrect channel provided.  Must provide A or B")

    def selectMemory(self):
        """ Select the Memory mode.  """

        cmd = [0x08]
        ncmd = self.buildCommand(cmd)
        self.sendCmd(ncmd)
        ## clear the response
        self.readResponse()

    def selectMemBank(self, b='A'):
        """ select the Memory Bank.
            PARAMETERS:
                        str b: the Memory Bank to select, A, B, C, D, or E
        """

        cmd = [0x08]
        subcmd = [0xa0]
        mem_banks = {'A':0x01,'B':0x02,'C':0x03,'D':0x04,'E':0x05}
        data = [mem_banks[b.upper()]]
        ncmd = self.buildCommand(cmd, subcmd, data)
        self.sendCmd(ncmd)
        ## clear the response
        self.readResponse()

    def selectMemChannel(self,c=None):
        """ Select the channel in the selected Memory Bank
            Channels 0 - 99 == 0xnn
            Channels 1A/B, 2A/B, 3A/B, 144/430 are 0x01 0xnn
            PARAMETERS:
                       str or int c: the channel as a string or int
                                     need both to handle special channels
        """
        chan_dict = {'1A':[0x01, 0x00],
                     '1B':[0x01, 0x01],
                     '2A':[0x01, 0x02],
                     '2B':[0x01, 0x03],
                     '3A':[0x01, 0x04],
                     '3B':[0x01, 0x05],
                     '144-C1':[0x01, 0x06],
                     '144-C2':[0x01, 0x07],
                     '430-C1':[0x01, 0x08],
                     '430-C2':[0x01, 0x09]}
        ichannel = None
        cmd = [0x08]
        if c is not None:
            if type(c) != int and type(c) != str:
                print("Error: Channel must be an integer or String")
            else:
                if type(c) == int and c <= 99:
                    channel = '0x%s' %str(c)
                    ichannel = [int(channel,0)]
                elif type(c) == str:
                    if c.upper() not in chan_dict.keys():
                        print("Error: Unexpected String received")
                    else:
                        ichannel = chan_dict[c.upper()]
        if ichannel is not None:
            ncmd = self.buildCommand(cmd, ichannel) #self.PREAMBLE + self.TRANSCEIVER_ADDR + self.CONTROLLER_ADDR + cmd + ichannel + self.EOM
            self.sendCmd(ncmd)
            ## clear the response
            self.readResponse()
        else:
            print("Error: No Channel Provided")

    def readOpFreq(self):
        """ Read the current frequency from the radio  """
        cmd = [0x03]
        ncmd = self.buildCommand(cmd) #self.PREAMBLE + self.TRANSCEIVER_ADDR + self.CONTROLLER_ADDR + cmd + self.EOM
        self.sendCmd(ncmd)
        ## read the frequency data message
        resp = self.readResponse()
        ## convert bcd response to readable frequency
        ## documentation says 5 values in response represent the frequency
        ## first 6 are message sent, last 1 is EOM
        ## freq response is not in correct order
        ## 1          2          3            4          5
        ## 10hz, 1hz  1khz,100hz 100khz,10khz 10mhz,1mhz 1ghz,100mhz  -- 1ghz is always 0

        freqs = []
        for i in range(9,4,-1):
            freqs.append(self.convert_from_bcd(resp[i]))
        freq_c = np.array([1e7,1e5,1e3,10,1])
        print(freqs)
        freq = np.array(freqs)
        freq = np.sum(freq*freq_c)
        print(freq)
        ## TODO: format freq to match XXX.XXX.xx

    def setOpFreq(self,freq):
        """ Set the operating frequency  
            PARAMETERS: 
                       freq: the frequency in MHz
        """
        cmd = [0x00]
        ## Freq needs to be written into the bcd format
        ## first, convert to string  and zfill
        nfreq = str(freq).zfill(8)
        ## now split the string into the correct order for bcd
        tarr = [nfreq[-1],nfreq[-3:-1],nfreq[-5:-3],nfreq[-7:-5],nfreq[0]]
        data = []
        ## convert to bcd
        for i in range(len(tarr)):
            data.append(self.convert_to_bcd(int(tarr[i])))
        ncmd = self.buildCommand(cmd, data=data)
        self.sendCmd(ncmd)

    def readOpMode(self):
        """ Read the current Operating Mode  """
        cmd = [0x04]
        ncmd = self.buildCommand(cmd)
        self.sendCmd(ncmd)
        ## read the op mode response
        resp = self.readResponse()
        ## first response is the operating mode, 2nd is filter
        ## 00:LSB 01:USB 02:AM 03:CW 04:RTTY 05: FM 06: WFM 07:CWR 08:RTTY-R 17:DV
        ## 01:Filt1 02:Filt2 03:Filt3
        op_mode = self.convert_from_bcd(resp[5])
        filt = self.convert_from_bcd(resp[6])
        print(resp)
        print(op_mode)
        print(filt)

    def setOpMode(self,mode=None):
        """ Set the Operating Mode  """
        mode_dict = {'LSB':[0x00],
                     'USB':[0x01],
                     'AM':[0x02],
                     'CW':[0x03],
                     'RTTY':[0x04],
                     'FM':[0x05],
                     'WFM':[0x06],
                     'CW-R':[0x07],
                     'RTTY-R':[0x08],
                     'DV':[0x17]}
        cmd = [0x06]
        if mode is not None and mode.upper() in mode_dict:
            data = mode_dict[mode]
            ncmd = self.buildCommand(cmd,data=data)
            self.sendCmd(ncmd)
            ## clear the response
            self.readResponse()

    def setRx(self):
        """ set the transceiver to receive  """
        cmd = [0x1C]
        subcmd = [0x00]
        data = [0x00]
        ncmd = self.buildCommand(cmd, subcmd, data)
        self.sendCmd(ncmd)
        ## clear the response
        self.readResponse()

    def setTx(self):
        """ set the transceiver to transmit  """
        cmd = [0x1C]
        subcmd = [0x00]
        data = [0x01]
        ncmd = self.buildCommand(cmd, subcmd, data)
        self.sendCmd(ncmd)
        ## clear the response
        self.readResponse()
