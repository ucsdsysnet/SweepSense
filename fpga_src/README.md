# SweepSense
This repo contains FPGA code for adding chirp functionality to USRP N210 with 
CBX daughter board, after the required hardware modification.

This README explains how to use the patch to add chirp functionality to an USRP
N210 module, and also how to configure the chirp. The patch was generated after
commit [e57dfe075c8056a5afe5528c1bc21e92b5149379](https://github.com/EttusResearch/fpga/commit/e57dfe075c8056a5afe5528c1bc21e92b5149379) of the EttusResearch fpga repository. 

## Overview

SweepSense logic and a sawtooth waveform generator have been added to the original
fpga source of USRP N210. Various user registers are used to control the logic
and other parameters of system operation. These are described in detail in the next
section.

![FPGA Arch Overview][image1]


![Register Mapping][image2]

[image1]: ../docs/FPGA_arch_over.png
[image2]: ../docs/fpga_reg_map.png


## Detailed Description and Installation

### Hardware Modification

Modification to be made on the CBX board (https://files.ettus.com/schematics/cbx/CBX.pdf): Desolder R125 (Page 3). Connect pin 52 of J6 receptacle on CBX (Page 5) to pin 20 of U23 (Page 3) through a 5k Ohm resistor.

### FPGA Source Compilation and Register Space

To apply the patch go to fpga-src folder and do:
    $ git apply Chirp_for_N210.patch

uhd_rx_cfile_chirp is an example modification to uhd_rx_cfile to configure the
chirp module. Details of configuration is explained bellow. 

The patch adds 3 modules in fpga-src/usrp2/control_lib/ and update the Makefile
in that folder to include those.  Moreover, it would edit the top module
located at fpga-src/usrp2/top/N2x0/u2plus_core.v to add the chirp module.
It modifies the fpga-src/usrp2/timing/time_compare.v module to improve
its timing, as well as remove extra MAP properties for the Xilinx ISE in the
Makefile. Finally, the gpio_atr is modified slightly to keep the VCO chip on
CBX always active.

There is a compiler directive to determine whether to use chirp code in
u2plus_core.v.
`define CHIRP

To use and configure the chirp capability you only need to set some registers
from the host. For example, you can add this to init function in uhd_rx_cfile
which is in python.

    def __init__(self, options, filename):
        ...
        self._u.set_user_register(3, 0, 0)
        ...

In set_user_register the first argument is address, second is a 32bit value,
and third argument needs to be 0.

Here is the mapping of different registers to their function for chirp, and an
example value:

Register 1:
One-hot representation of desired frequency bands to be captured. This is the
32 lower bands. Note that this bands would be saved for the rf_division factor
set by register 6.

        self._u.set_user_register(1, 0xFFFFFFFF, 0)

Register 2:
One-hot representation of desired frequency bands to be captured. This is the
rest of the bands, which is 32 for CBX (total 64 bands). Note that this bands
would be saved for the rf_division factor set by register 6.

        self._u.set_user_register(2, 0x0000000F, 0)

* If registers 1 and 2 are both set to 0 for a rf_divider, it is considered
that only the first channel is selected.

Register 3:
Enabling or disabling the chirp. Writing a 1 would enable it and writing a 0
would make the system work in normal mode.

        self._u.set_user_register(3, 0, 0)

Register4:
Sets the step size for chirp:

        self._u.set_user_register(4, 256, 0)

Register 5:
set the clock division ratio for SPI clock. 4 means SPI clock is high for 
4 clock cycles and low for 4 clock cycles, or has 8x lower frequency than 
the system clock. 

        self._u.set_user_register(5, 4, 0)

Register 6:
Chirp rf divider selector for register 1 and 2. It is a 8 bit value which can
be only powers of 2, from 1 to 128 for CBX. Any other value is ignored and
default value of 2 is selected.

        self._u.set_user_register(6, 2, 0)

Register 7:
Chirp ramp start

        self._u.set_user_register(7, 0x26D, 0)

Register 8:
Chirp ramp end

        self._u.set_user_register(8, 0xC1D, 0)

Register 9:
One-hot representation of desired rf_divider values to loop through. The
lowest 8 bits represent each rf_divider. By default it is set to 2, meaning
only rf_divider of 2.
* If this register is set to zero, it is considered that the rf_div of 1 is
selected.

        self._u.set_user_register(9, 3, 0)

Chirp driver cycles through the selected rf_divider values in a round robin
manner and for each rf_divider it would cycle through the selected frequency
bands.

## VCO Band Mapping

**Register 6 (RF Divider)**:   
Register 6 = 1 for 3 GHz - 6 GHz   
Register 6 = 2 for 1.5 GHz - 3 GHz

**Registers 1 and 2 (VCO Band Select)**:  
Once the correct RF divider has been chosen. The 64 bit VCO band select value has to be
written to registers 1 and 2 (32 bits each). This value can be obtained from the MAX2870
datasheet, but we have put down approximate practical values below:


![][vco1]
![][vco2]
![][vco3]
![][vco4]

[vco1]: ../docs/2_3Ghz_VCObandmap.png
[vco2]: ../docs/3_4GHZ_VCObandmap.png
[vco3]: ../docs/4_5Ghz_VCObandmap.png
[vco4]: ../docs/5_6Ghz_VCObandmap.png

## License

Apache 2.0:

   Copyright 2019 The Regents of the University of California

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
