# SweepSense Python Library

This readme goes over the implementation of the SweepSense python library. It is intended to
be a plug-and-play solution. A demonstration of 2.4 GHz ISM band scanning is available along
with the library.

## Dependencies

1. GNURadio 3.7 or Newer
2. pickle
3. pandas

Note that the library is compatible only with **Python3**.

## Overview

The library contains some pre-built GNURadio flowgraphs and wrapper functions that integrate
them.

### Flowgraphs

1. **cal_block**: This flowgraph implements calibration capture for the unsweeping process.
2. **sweep_block**: This flowgraph implements the sweeping capture. 
3. **comb_block**: This flowgraph is used to combine various calibration files for generating a multi-band calibration.

Each of these flowgraphs have in-built reconfigurations set by the parameter *mode*. Refer to the documentation
within the code to understand what the parameter modifies for each flowgraph.

### Flowgraph Functions

These functions are ones that the user directly interacts with:

1. **calibrate**(*options*): Calls the **cal_block** flowgraph and collects calibration data.
2. **sweep**(*options*): Calls the **sweep_block** flowgraph and collects data using the SweepSense radio.

*options* is an object with many parameters. Documentation in the code specifies every field and its use.

### Misc Functions

1. combine_cal: This function is called by the **calibrate** function to combine all the calibration files.
2. step_size_metrics: This function is called to compute some internal parameters based on the ones supplied
by the user. It will clean up illegal inputs and throw errors in case it cannot do so.
3. load_obj: Load a configuration object from a file.
4. save_obj: Save a configuration object.
5. demo_init: Initialization used for NSDI 2019 demo.


## Example Take Off Point

STEP 1: Import the library:

```import gr_sweepsense as ss1```    

Using the command ```help(ss1)``` will fetch the classes and functions in ```ss1```. Function docstrings included.

STEP 2: Load demo configuration objects. (This also creates a 4 GB ramdisk and therefore requires sudo permission).
We write files to a ramdisk to reduce latency and minimize stream errors.   

```[cal_opt, sweep_opt] = ss1.demo_init()```    


STEP 3: Obtain calibration samples and combines them according to the list in ```script_files/freq_list_demo.txt```   

```ss1.calibrate(cal_opt)```

NOTE: Remove all connections from all antenna ports for before this step. The calibration samples are by default 
obtained using TX-RX leakage.

STEP 4: Perform SweepSense capture. 

```ss1.sweep(sweep_opt)```

### Modifying for your Application

STEP 1: Compute the required register values for Reg 1,2,6 and 9. (Refer the fpga_src documentation)   
STEP 2: Decide on the set of calibration frequencies (spaced apart by sample rate). List them in a file.   
STEP 3: Create your own configuration object or modify the example object with the items in STEP 1 and STEP 2.

## Licence

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