# SweepSense

This repository contains FPGA source code and GNURadio+UHD (Python3) based
API for the prototype SweepSense implementation in our paper:   

[Guddeti, Y., Subbaraman, R., Khazraee, M., Schulman, A., & Bharadia, D. (2019). 
Sweepsense: Sensing 5 ghz in 5 milliseconds with low-cost radios. 
In 16th USENIX Symposium on Networked Systems Design and Implementation (NSDI 19) (pp. 317-330).](https://www.usenix.org/conference/nsdi19/presentation/guddeti "Go to paper!")

This readme explains the overall architecture briefly, goes through the folder structure and displays the license.
For full technical details and evaluations are available in the extended paper.

## Overview

We propose a new receiver architecture for spectrum sensing radios where sampling
is done along with quick sweeping of the center frequency. This is motivated by
the intuition that a sweeping radio may miss lesser transmissions than one that
sequentially tunes to different bands.

![][par_shift]

We implement this using an open loop VCO fed with a sawtooth voltage waveform. The
output of the VCO is used to drive a mixer and implement the sweeping radio.

![][sweep_arch]

The architecture has been prototyped on a USRP N210 with a CBX daughterboard.


![VCO Core Sweeping Architecture][vco_core_swp]


Downconverting while sweeping introduces distortions in the signal, which we remove
using an "unsweeping" process and is discussed in the paper.


[sweep_arch]: ./docs/figure_2.png "Sweep Receiver Architecture"
[vco_core_swp]: ./docs/freqsynth.png "VCO Core Sweeping Architecture"
[par_shift]: ./docs/figure_1.png "Paradigm Shift"

## Example Results

![][ism_cap]

A SweepSense capture of the 2.4 GHz ISM band showing WiFi and Bluetooth transmissions. 
We get close to 100 MHz bandwidth with only a 25 MSps radio.

[ism_cap]: ./docs/figure_3.png "Paradigm Shift"


## Folder Structure

1. fpga_src - Folder containing the fpga patch for the USRP N210 required to implement SweepSense.   
2. python_scripts - Folder containing the UHD-GNURadio api and demo codes to get started.
3. docs - Images for markdown documentation.

## Get in Touch!

If you have any questions or suggestions, please get in touch with the authors of the paper:

yguddeti@eng.ucsd.edu    
rsubbaraman@eng.ucsd.edu    
[WCSNG UC San Diego](http://wcsng.ucsd.edu/)  
[Sysnet UC San Diego](https://www.sysnet.ucsd.edu/sysnet/)

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
