#!/usr/bin/env python2
# -*- coding: utf-8 -*-
######################################################################
# gr-sweepsense Python Library
# Version: 1.0
# Authors: Raghav Subbaraman (rsubbaraman@eng.ucsd.edu), Yeswanth Guddeti (yguddeti@eng.ucsd.edu)
# 
# Description: This library contains python code to interface
# with SweepSense USRPs. Composed of multiple GNURadio flowgraphs
# perform various functions such as calibration and sweep data
# capture. Simple wrapper functions exist for the flowgraphs
# along with saved configuration objects for easy use.
# 
# Dependencies:
# 	1. GNURadio 
# 	2. pickle
# 	3. pandas
#
# Changelog:
# 	1. October 31 2019: Script created in library form (v1.0)
######################################################################

from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import gr
from gnuradio import uhd
from gnuradio import analog
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
from optparse import OptionParser
from gnuradio import analog
from gnuradio import filter

from sys import stderr, exit

from pprint import pprint
import time
import pickle
import os
import shutil
import pmt

import pandas as pd

class sweep_block(gr.top_block):

	def __init__(self,options):
		gr.top_block.__init__(self, "Top Block")

		##################################################
		# Blocks
		##################################################

		# Calibrating so do not need a sink (empty calibration)
		if options.mode == 1 or options.mode == 2 or options.mode == 10:
			# addr0 is of sweeper
			self.usrp_source = uhd.usrp_source(
			",".join(("addr0=192.168.10.2,addr1=192.168.20.3", "")),
			uhd.stream_args(
			cpu_format="fc32",
			channels=range(2),
			),
			)
			if options.mode == 2:
				self.usrp_sink = uhd.usrp_sink(
					",".join(("addr0=192.168.10.2,addr1=192.168.20.3", "")),
					uhd.stream_args(
						cpu_format="fc32",
						channels=range(2),
						),
					)
		elif options.mode == 3 or options.mode == 0 or options.mode == 30:
			# device_addr is of sweeper
			self.usrp_source = uhd.usrp_source(
			",".join(("addr0=192.168.10.3", "")),
			uhd.stream_args(
			cpu_format="fc32",
			channels=range(1),
			),
			)
		else:
			stderr.write("You gave me an option I do not know about\n")
			exit(1)

		# Initialization code for controlling the DAC output 
		self.chan = 0
		self.unit = uhd.dboard_iface.UNIT_TX
		self.dac = uhd.dboard_iface.AUX_DAC_A
		self.iface = self.usrp_source.get_dboard_iface(self.chan)
		#self.iface.write_aux_dac_config(32)				
		self.iface.write_aux_dac(self.unit, self.dac, 0.2)

		# Configure frequency band registers (depending on daughter board)
		# Channel 1 on MIMO cable is the sweeper USRP
		usrp_info = self.usrp_source.get_usrp_info(0)
		db_name = usrp_info["rx_subdev_name"]
		user_reg_1 = 0
		user_reg_2 = 0
		print("NAME: " + db_name)
		if (db_name.find("SBX") != -1):
			# The following two registers can be configured for frequency band
			# 2.4 GHz comes in 16 and 24
			# for all 37 bands, put 4294967295 in reg 1 and 31 in reg 2 
			stderr.write("Detected SBX DB...\n")
			user_reg_1 = 48 # frequncy bit array for first 32 bands  #32-band6#64-band7
			user_reg_2 = 0 # frequency bit array for next 5 bands
		elif (db_name.find("CBX") != -1):
			# 2.4 GHz
			stderr.write("Detected CBX DB...\n")
			user_reg_1 = options.band1 # frequncy bit array for first 32 bands
			user_reg_2 = options.band2 # frequency bit array for next 32 bands
			rf_div = options.rf_div # RfOut divider for VCO
		else:
			stderr.write("Error: Unknown daughterboard: %s\n" % db_name)
			exit(1)

		# Chirp enable
		self.usrp_source.set_user_register(3,1,0)

		self.usrp_source.set_user_register(1,user_reg_1,0) 
		self.usrp_source.set_user_register(2,user_reg_2,0)
		self.usrp_source.set_user_register(6,rf_div,0)
		#Address 5 -Clk divider
		self.usrp_source.set_user_register(5,4,0)

		#self.usrp_source.set_user_register(6,1,0) # RF divider to give 400-4.4GHz range. Valid values are 1,2,4,8 and 16.	
		# The following are the new registers that need to be set
		# for the updated hardware code.
		# register 4 = jump value - 12 bit number	
		self.usrp_source.set_user_register(4,options.step,0)
		# register 7 = start_ramp - 12 bit number
		self.usrp_source.set_user_register(7,621,0)
		# register 8 = end_ramp - 12 bit number
		self.usrp_source.set_user_register(8,3103,0)

		self.usrp_source.set_user_register(6,options.rf_div,0)

		if len(options.filename)==0:
			# No filenames given -- just connect to a null source
			self.null_sink0 = blocks.null_sink(gr.sizeof_gr_complex*1)
			# Connections
			self.connect((self.usrp_source,0),(self.null_sink0,0))
			if options.mode == 1:
				self.null_sink1 = blocks.null_sink(gr.sizeof_gr_complex*1)
				self.connect((self.usrp_source,1),(self.null_sink1,0))

		elif len(options.filename)>=1:
			if options.mode == 1 or options.mode == 10:
				# Synchronous reception : creates two time synced files
				# options.filename[0] is the string containing the ground truth rx samples
				# options.filename[1] is the string containing the SweepSense rx samples
				# options.filename[2] is the string containing the name of the calibration file

				# Setting params for sweeper
				self.usrp_source.set_gain(options.rgain, 0)
				self.usrp_source.set_antenna("RX2", 0)
				self.usrp_source.set_bandwidth(options.samp, 0)

				# self.usrp_sink.set_gain(options.tgain,0)
				# self.usrp_sink.set_antenna("TX/RX",0)
				# self.usrp_sink.set_center_freq(2212e6,0)
				# self.usrp_sink.set_bandwidth(options.txsamp,0)

				# Setting params for ground truth
				self.usrp_source.set_samp_rate(options.samp)
				self.usrp_source.set_gain(options.rgain, 1)
				self.usrp_source.set_antenna("TX/RX", 1)
				self.usrp_source.set_center_freq(options.txfreq, 1)
				self.usrp_source.set_bandwidth(options.samp, 1)
				self.usrp_source.set_clock_source("mimo", 1)
				self.usrp_source.set_time_source("mimo", 1)

				# Initialize USRP sink
				# self.usrp_sink.set_samp_rate(options.txsamp)
				# self.usrp_sink.set_gain(options.tgain,1)
				# self.usrp_sink.set_antenna("RX2",1)
				# self.usrp_sink.set_center_freq(options.txfreq,1)
				# self.usrp_sink.set_bandwidth(options.txsamp,1)
				# self.usrp_sink.set_clock_source("mimo",1)
				# self.usrp_sink.set_time_source("mimo",1)
				# We are using a MIMO cable 2 USRP setup to transmit (but not sure why we need two transmitters)

				# Null sinks for the slave source
				# self.null_source_2 = blocks.null_source(gr.sizeof_gr_complex*1)
				# self.null_source_3 = blocks.null_source(gr.sizeof_gr_complex*1)

				# Sample blockers
				# to do, add M in N here
				self.blocks_head_0 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				self.blocks_head_1 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				# self.blocks_head_2 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				# self.blocks_head_3 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)

				# file blocks
				self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_gr_complex*1,options.filename[0],False)
				self.blocks_file_sink_1 = blocks.file_sink(gr.sizeof_gr_complex*1,options.filename[1],False)
				self.blocks_file_sink_0.set_unbuffered(False)
				self.blocks_file_sink_1.set_unbuffered(False)
			
				if options.mode == 1:
					# Mode for compensated
					self.blocks_file_src_cal = blocks.file_source(gr.sizeof_gr_complex*1, options.filename[2], True)

				if options.mode == 10:
					# Mode for uncompensated
					self.blocks_file_src_cal = analog.sig_source_c(0, analog.GR_CONST_WAVE, 0, 0, 1)


				# conjugate multiplier for compensation
				self.blocks_mult_conj = blocks.multiply_conjugate_cc(1)

				# Connections
				self.connect((self.usrp_source,1),(self.blocks_head_0,0))
				self.connect((self.usrp_source,0),(self.blocks_mult_conj,0)) # sweeper to multiply
				self.connect((self.blocks_file_src_cal,0),(self.blocks_mult_conj,1)) # cal to multiply

				self.connect((self.blocks_mult_conj,0),(self.blocks_head_1,0)) # multiply to head
				# self.connect((self.null_source_2,0),(self.blocks_head_2,0))
				# self.connect((self.null_source_3,0),(self.blocks_head_3,0))

				self.connect((self.blocks_head_0,0),(self.blocks_file_sink_0,0))
				self.connect((self.blocks_head_1,0),(self.blocks_file_sink_1,0))
				# self.connect((self.blocks_head_2,0),(self.usrp_sink,0))
				# self.connect((self.blocks_head_3,0),(self.usrp_sink,1))

			elif options.mode == 3 or options.mode == 30:
				# SweepSense standalone reception : creates a single received file
				# options.filename[0] is the string containing the name of the file you want to store to
				# options.filename[1] is the string containing the name of the calibration file
				# Setting params for sweeper
				self.usrp_source.set_gain(options.rgain, 0)
				self.usrp_source.set_antenna("RX2", 0)
				self.usrp_source.set_bandwidth(options.samp, 0)
				self.usrp_source.set_samp_rate(options.samp)

				# Sample blockers
				self.blocks_head_1 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				self.blocks_skiphead_0 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)

				# file blocks
				self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_gr_complex*1,options.filename[0],False)
				self.blocks_file_sink_0.set_unbuffered(False)

				if options.mode == 3:
					# compensated signal
					self.blocks_file_src_cal = blocks.file_source(gr.sizeof_gr_complex*1, options.filename[1], True)

				if options.mode == 30:
					# the following is for getting uncompensated stuff
					self.blocks_file_src_cal = analog.sig_source_c(0, analog.GR_CONST_WAVE, 0, 0, 1)
				
				
							
				# conjugate multiplier for compensation
				self.blocks_mult_conj = blocks.multiply_conjugate_cc(1)

				# DC Blocker
				self.dc_blocker_xx_0 = filter.dc_blocker_cc(256, False)

				# Keep M in N
				
				self.blocks_keep_m_in_n_0 = blocks.keep_m_in_n(gr.sizeof_gr_complex, options.sweep_time*options.num_bands, options.sweep_time*options.num_bands*options.inN, 0)

				# Connections
				self.connect((self.usrp_source,0),(self.dc_blocker_xx_0,0)) # sweeper to DC block
				self.connect((self.dc_blocker_xx_0,0),(self.blocks_mult_conj,0)) # DC block to multiply conj
				# self.connect((self.usrp_source,0),(self.blocks_mult_conj,0)) # sweeper to DC block
				self.connect((self.blocks_file_src_cal,0),(self.blocks_mult_conj,1)) # cal to multiply

				# no realtime calib - just receive:
				#self.connect((self.dc_blocker_xx_0,0),(self.blocks_head_1,0))

				self.connect((self.blocks_mult_conj,0),(self.blocks_skiphead_0,0)) # multiply to head
				#self.connect((self.blocks_skiphead_0,0),(self.blocks_head_1,0))

				self.connect((self.blocks_skiphead_0,0),(self.blocks_keep_m_in_n_0 ,0))
				self.connect((self.blocks_keep_m_in_n_0,0),(self.blocks_head_1,0))

				self.connect((self.blocks_head_1,0),(self.blocks_file_sink_0,0))

			elif options.mode == 2:
				# This mode sends pilots on normal USRP & receives through sweeper

				# Setting params for sweeper
				self.usrp_source.set_gain(options.rgain, 0)
				self.usrp_source.set_antenna("RX2", 0)
				self.usrp_source.set_bandwidth(options.samp, 0)

				self.usrp_sink.set_gain(options.tgain,0)
				self.usrp_sink.set_antenna("TX/RX",0)
				self.usrp_sink.set_center_freq(options.txfreq-100e6,0) # tune to some off band frequency to prevent interference
				self.usrp_sink.set_bandwidth(options.txsamp,0)

				# Initialize USRP sink - transmitter
				self.usrp_sink.set_samp_rate(options.txsamp)
				self.usrp_sink.set_gain(options.tgain,1)
				self.usrp_sink.set_antenna("TX/RX",1)
				self.usrp_sink.set_center_freq(options.txfreq,1)
				self.usrp_sink.set_bandwidth(options.txsamp,1)
				self.usrp_sink.set_clock_source("mimo",1)
				self.usrp_sink.set_time_source("mimo",1)

				self.usrp_source.set_samp_rate(options.samp)
				self.usrp_source.set_gain(options.rgain, 1)
				self.usrp_source.set_antenna("RX2", 1)
				self.usrp_source.set_center_freq(options.txfreq, 1)
				self.usrp_source.set_bandwidth(options.samp, 1)
				self.usrp_source.set_clock_source("mimo", 1)
				self.usrp_source.set_time_source("mimo", 1)

				# Null sinks for the slave source
				self.null_sink_0 = blocks.null_sink(gr.sizeof_gr_complex*1)
				self.null_source_2 = blocks.null_source(gr.sizeof_gr_complex*1)

				# Skip heads

				self.blocks_skiphead_0 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)
				self.blocks_skiphead_1 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)

				self.blocks_skiphead_2 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)
				self.blocks_skiphead_3 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)

				# Sample blockers
				self.blocks_head_0 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				self.blocks_head_1 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				self.blocks_head_2 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)
				self.blocks_head_3 = blocks.head(gr.sizeof_gr_complex*1,options.maxsamp)


				# TODO: add squelch to get only good signals from calibration - we need to get the values of the squelch as well

				# file blocks
				# options.filename[0] is used to store the received calibration tone
				# transmitted tone is 10 kHz offset from the actual centre frequency as below:
				self.blocks_file_source_3 = analog.sig_source_c(options.samp, analog.GR_COS_WAVE, 10000, 1, 0) # using complex cosine
				self.blocks_file_sink_1 = blocks.file_sink(gr.sizeof_gr_complex*1,options.filename[0],False)
				self.blocks_file_sink_1.set_unbuffered(False)

				# Connections
				self.connect((self.usrp_source,1),(self.blocks_skiphead_2,0))
				self.connect((self.usrp_source,0),(self.blocks_skiphead_0,0))
				self.connect((self.blocks_file_source_3,0),(self.blocks_skiphead_1,0))
				self.connect((self.null_source_2,0),(self.blocks_skiphead_3,0))

				self.connect((self.blocks_skiphead_2,0),(self.blocks_head_0,0))
				self.connect((self.blocks_skiphead_3,0),(self.blocks_head_2,0))

				self.connect((self.blocks_skiphead_0,0),(self.blocks_head_1,0))
				self.connect((self.blocks_skiphead_1,0),(self.blocks_head_3,0))

				self.connect((self.blocks_head_0,0),(self.null_sink_0,0))
				self.connect((self.blocks_head_1,0),(self.blocks_file_sink_1,0))
				self.connect((self.blocks_head_3,0),(self.usrp_sink,1))
				self.connect((self.blocks_head_2,0),(self.usrp_sink,0))

class cal_block(gr.top_block):

    def __init__(self,options,filename):
        gr.top_block.__init__(self, "Top Block")

        ##################################################
        # Blocks
        ##################################################
        self.usrp_source = uhd.usrp_source(
        	",".join(("addr=192.168.10.3", "")),
        	uhd.stream_args(
        		cpu_format="fc32",
        		channels=range(1),
        	),
        )
        if options.mode !=2 :
            self.uhd_usrp_sink_0 = uhd.usrp_sink(
                ",".join(("addr=192.168.10.3", "")),
                uhd.stream_args(
                    cpu_format="fc32",
                    channels=range(1),
                    ),
                )

        # Initialization code for controlling the DAC output 
        self.chan = 0
        self.unit = uhd.dboard_iface.UNIT_TX
        self.dac = uhd.dboard_iface.AUX_DAC_A
        self.iface = self.usrp_source.get_dboard_iface(self.chan)
        #self.iface.write_aux_dac_config(32)                
        self.iface.write_aux_dac(self.unit, self.dac, 0.2)

        # Configure frequency band registers (depending on daughter board)
        # Channel 1 on MIMO cable is the sweeper USRP
        usrp_info = self.usrp_source.get_usrp_info(0)
        db_name = usrp_info["rx_subdev_name"]
        user_reg_1 = 0
        user_reg_2 = 0
        print("NAME: " + db_name)
        if (db_name.find("SBX") != -1):
            # The following two registers can be configured for frequency band
            # 2.4 GHz comes in 16 and 24
            # for all 37 bands, put 4294967295 in reg 1 and 31 in reg 2 
            stderr.write("Detected SBX DB...\n")
            user_reg_1 = 48 # frequncy bit array for first 32 bands  #32-band6#64-band7
            user_reg_2 = 0 # frequency bit array for next 5 bands
        elif (db_name.find("CBX") != -1):
            # 2.4 GHz
            stderr.write("Detected CBX DB...\n")
            user_reg_1 = options.band1 # frequncy bit array for first 32 bands
            user_reg_2 = options.band2 # frequency bit array for next 32 bands
        else:
            stderr.write("Error: Unknown daughterboard: %s\n" % db_name)
            exit(1)


        # Set chirp enable:
        self.usrp_source.set_user_register(3,1,0)

        # Set bands of interest
        self.usrp_source.set_user_register(1,user_reg_1,0) 
        self.usrp_source.set_user_register(2,user_reg_2,0)
        #Address 5 -Clk divider
        self.usrp_source.set_user_register(5,4,0)

        #self.usrp_source.set_user_register(6,1,0) # RF divider to give 400-4.4GHz range. Valid values are 1,2,4,8 and 16.  
        # The following are the new registers that need to be set
        # for the updated hardware code.
        # register 4 = jump value - 12 bit number   
        self.usrp_source.set_user_register(4,options.step,0)
        # register 7 = start_ramp - 12 bit number
        self.usrp_source.set_user_register(7,621,0)
        # register 8 = end_ramp - 12 bit number
        self.usrp_source.set_user_register(8,3103,0)
        # RF Divider parameters
        self.usrp_source.set_user_register(6,options.rf_div,0)

        # Set source parameters
        self.usrp_source.set_antenna("RX2")
        self.usrp_source.set_samp_rate(options.samp)
        self.usrp_source.set_bandwidth(options.samp, 0)
        self.usrp_source.set_gain(options.rgain, 0)

        if options.mode !=2:
        # Set sink parameters
            self.uhd_usrp_sink_0.set_samp_rate(10e6)
            self.uhd_usrp_sink_0.set_center_freq(options.txfreq, 0)
            self.uhd_usrp_sink_0.set_gain(options.tgain, 0)
            self.uhd_usrp_sink_0.set_antenna('TX/RX', 0)
            self.uhd_usrp_sink_0.set_bandwidth(25e6, 0)
            # signal gen blocker
            self.blocks_head_0 = blocks.head(gr.sizeof_gr_complex*1, options.inN*options.maxsamp+options.skip)
            # Signal Source
            self.analog_sig_source_x_0 = analog.sig_source_c(options.samp, analog.GR_CONST_WAVE, 0, 0, 1)

        self.usrp_source.set_clock_source('internal', 0)
        self.usrp_source.set_time_now(uhd.time_spec(time.time()), uhd.ALL_MBOARDS)

        # Skip Heads
        self.blocks_skiphead_0 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)

        # Block Heads
        self.blocks_head_1 = blocks.head(gr.sizeof_gr_complex*1, options.maxsamp)

        # File meta sink
        pmt_a = pmt.make_dict()
        self.blocks_file_sink_0 = blocks.file_meta_sink(gr.sizeof_gr_complex*1, filename[0], options.samp, 1, blocks.GR_FILE_FLOAT, True, options.sweep_time,  pmt_a, True)
        self.blocks_file_sink_0.set_unbuffered(False)

        # Keep M in N
        self.blocks_keep_m_in_n_0 = blocks.keep_m_in_n(gr.sizeof_gr_complex, options.sweep_time*options.num_bands, options.sweep_time*options.num_bands*options.inN, 0)

        ##################################################
        # Connections
        ##################################################

        # Sweeper RX Flow
        self.connect((self.usrp_source, 0), (self.blocks_skiphead_0))
        self.connect((self.blocks_skiphead_0),(self.blocks_keep_m_in_n_0, 0))
        self.connect((self.blocks_keep_m_in_n_0),(self.blocks_head_1, 0))

        #self.connect((self.blocks_skiphead_0),(self.blocks_head_1, 0))
        self.connect((self.blocks_head_1, 0), (self.blocks_file_sink_0, 0))

        if options.mode !=2:
        # Tone TX Flow
            self.connect((self.analog_sig_source_x_0, 0), (self.blocks_head_0, 0))
            self.connect((self.blocks_head_0, 0), (self.uhd_usrp_sink_0, 0))

class comb_block(gr.top_block):
	def __init__(self,options,filename):
		gr.top_block.__init__(self, "Top Block")

		##################################################
		# Blocks
		##################################################
		self.dc_blocker_xx_0_0 = filter.dc_blocker_cc(32, True)
		self.dc_blocker_xx_0 = filter.dc_blocker_cc(32, True)

		self.blocks_throttle_0 = blocks.throttle(gr.sizeof_gr_complex*1, 20000000,True)
		self.blocks_skiphead_0 = blocks.skiphead(gr.sizeof_gr_complex*1, options.skip)
		self.blocks_null_sink_0 = blocks.null_sink(gr.sizeof_float*1)
		self.blocks_magphase_to_complex_0 = blocks.magphase_to_complex(1)
		self.blocks_head_0 = blocks.head(gr.sizeof_gr_complex*1, options.maxsamp)
		self.blocks_file_source_0_0 = blocks.file_source(gr.sizeof_gr_complex*1, filename[0], True)
		self.blocks_file_source_0 = blocks.file_source(gr.sizeof_gr_complex*1, filename[1], True)
		self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_gr_complex*1, filename[2], False)
		self.blocks_file_sink_0.set_unbuffered(False)
		self.blocks_complex_to_magphase_0 = blocks.complex_to_magphase(1)
		self.blocks_add_xx_0 = blocks.add_vcc(1)
		#self.analog_const_source_x_0 = analog.sig_source_f(0, analog.GR_CONST_WAVE, 0, 0, 1)

		self.blocks_complex_to_mag_0 = blocks.complex_to_mag(1)
		self.blocks_threshold_ff_0 = blocks.threshold_ff(0.01, 0.04, 0)

		##################################################
		# Connections
		##################################################

		self.connect((self.blocks_file_source_0, 0), (self.dc_blocker_xx_0, 0))    
		self.connect((self.blocks_file_source_0_0, 0), (self.dc_blocker_xx_0_0, 0))    

		self.connect((self.dc_blocker_xx_0, 0), (self.blocks_add_xx_0, 0))    
		self.connect((self.dc_blocker_xx_0_0, 0), (self.blocks_add_xx_0, 1))
		self.connect((self.blocks_add_xx_0, 0), (self.blocks_throttle_0, 0)) 

		self.connect((self.blocks_throttle_0, 0), (self.blocks_skiphead_0, 0))    
		self.connect((self.blocks_skiphead_0, 0), (self.blocks_head_0, 0))

		self.connect((self.blocks_head_0, 0), (self.blocks_complex_to_magphase_0, 0))

		# tap for power analysis
		self.connect((self.blocks_head_0, 0), (self.blocks_complex_to_mag_0, 0))
		self.connect((self.blocks_complex_to_mag_0, 0), (self.blocks_threshold_ff_0, 0))


		self.connect((self.blocks_complex_to_magphase_0, 1), (self.blocks_magphase_to_complex_0, 1))    
		self.connect((self.blocks_complex_to_magphase_0, 0), (self.blocks_null_sink_0, 0)) 

		#self.connect((self.analog_const_source_x_0, 0), (self.blocks_magphase_to_complex_0, 0))
		self.connect((self.blocks_threshold_ff_0, 0), (self.blocks_magphase_to_complex_0, 0))

		# in case you want to just add
		#self.connect((self.blocks_complex_to_magphase_0, 0), (self.blocks_magphase_to_complex_0, 0))

		self.connect((self.blocks_magphase_to_complex_0, 0), (self.blocks_file_sink_0, 0))

def step_size_metrics(options):
    """Compute sweep_time and other metrics in the configuration object.

    This function ensures that all delays, total number of samples etc are multiples of the 
    sweep_time (in number of samples).

    Call this function to clean up the configurations object and ensure it conforms to rules
    before using the object.
    """
    band1 = bin(options.band1)
    band2 = bin(options.band2)
    num_bands = band1.count('1')+band2.count('1')
    df = pd.read_csv('./script_files/step_sizes.csv') 
    samp_step_vec = df['samp_sep'];
    ind = 1
    for row in samp_step_vec:
        if options.step == ind:
        	if(row==0):
        		print('Sweep Time data for this step size not available. Exiting')
        		exit(-1)
        	else:
        		sweep_time = row
        		options.sweep_time = sweep_time
        		options.num_bands = num_bands
        		options.maxsamp = (int(options.maxsamp/(sweep_time*num_bands))+1)*sweep_time*num_bands;
        		options.skip = (int(options.skip/(sweep_time*num_bands))+1)*sweep_time*num_bands;
        		print("Num Bands: "+ str(options.num_bands)+"("+str(options.band1)+","+str(options.band2)+")")
        		print("Step Size: "+ str(row) +", Sweep Time: "+ str(options.sweep_time)+", maxsamp: "+str(options.maxsamp))
        		print("Skip samples: "+ str(options.skip))
        		break
        ind = ind+1
    return options

def calibrate(options,top_block_cls = cal_block):
	"""Wrapper function for SweepSense calibration process.

	Inputs: 
		1. options (object)
		2. top_block_cls (default is cal_block)
	Outputs:
		None

	This function instantiates a cal_block flowgraph and runs it with the given options. It reads a list of
	frequencies from a file and gathers calibration data for each of those frequencies by looping the
	flowgraph for every item in the list. Used for self (TX to RX leakage) calibration.

	After saving the calibration samples for every frequency, it calls the combine_cal function to combine all
	the calibration samples into a single file as described in the paper.

	Attributes of options:
		1. band1: Bitmap for lower VCO bands to sweep. (int32)

			The VCO bands to sweep are encoded in two 32 bit variables
			band1 and band2 (lower and higher respectively). Within
			the variables, the LSB is of lowest frequency. The span of
			each VCO band has been characterised and is available using
			the documentation.

		2. band2: Bitmap for higher VCO bands to sweep. (int32)

		3. filename: List of path strings for required files. (list)

			[<filename_0>, <save_path>]
			
			<filename_0> (str)
				Path to a text file with the list of center frequencies for calibration data capture.
				Each frequency is separated by a newline. 
				Example: './script_files/freq_list.txt'

			<save_path> (str)
				Path to a folder where the captured calibration samples can be stored.
				Example: '/mnt/ramdisk'

		4. inN: Subsample sweeps. One sweep in every 'inN' sweeps is saved. (int)
		
		5. maxsamp: Maximum number of samples to be captured. (int)

		6. mode: Enables different flowgraph operation modes. (int)

			mode 1: Self calibration using leakage between the TX and RX chains on the SweepSense 
			daughterboard.
			mode 2: Reserved. 

		7. num_bands: Total number of VCO bands enabled in both band1 and band2. (int)
			Can be computed using the step_size_metrics() function.

		8. rf_div: Value of the RF divider in the daughterboard. (1 or 2)

			For CBX: 1 for 3 GHz - 6 GHz, 2 for 1.5 GHz - 3 GHz
		
		9. rgain: Receive gain (dB) of all receive chains. (float)

		10. samp: Sampling rate of all chains. (int)
		
		11. self_name: Path to save this object (str)
		
		12. skip: Number of samples to skip before capturing the first valid sample. (int)

		13. step: Voltage step size for the sweep. (int)
		
		14. sweep_time: Number of samples per voltage sweep. (int)
			Can be computed using the step_size_metrics() function.

		15. tgain: Transmit gain (dB) for all receive chains. (float)
		
		16. transmitter: Reserved

		17. txfreq: Reserved

		18. txsamp: Transmitter sampling frequency wherever applicable (float)
	"""
	cal_tone_list = open(options.filename[0],"r")
	cal_tone_save = open(options.filename[0][0:-4]+'_op.txt',"w+")
	filename1 = ['a','b'];
	f1 = cal_tone_list.readlines()
	for entry in f1:
		options.txfreq = int(entry)
		file = [options.filename[0],options.filename[0]]
		file[0] = options.filename[1] + str(int(entry)) + '_step_'+ str(options.step) + '_sweeped_tone.dat'
		cal_tone_save.write(file[0]+'\n')
		print("Sending calibration tone at " + str(entry.strip()) + " Hz")
		if options.mode == 2:
			raw_input("Press Enter to start capture of tone at "+ str(entry.strip()) + " Hz\n")
		start_time = time.time()
		print("Start Time: " + str(start_time))
		if(options.mode == 2):
			dummy_a=raw_input("Press Enter to continue... "+file[0]+"\n")
		tb = top_block_cls(options,file)
		tb.start()
		tb.wait()
		end_time = time.time()
	print("Total Elapsed: " + str(end_time - start_time) + "seconds")
	print("Calibration capture complete")
	cal_tone_save.close()
	cal_tone_list.close()
	filename1[0] = options.filename[0][0:-4]+'_op.txt'
	filename1[1] = options.filename[1]+'combined_rt_cal.dat'
	combine_cal(options,filename1)

def combine_cal(options,filename,top_block_cls=comb_block):
	"""Wrapper function for combining multiple calibration sample files.

	Note: The end-user need not directly interact with this function

	Inputs: 
		1. options (object)
		2. filename (list)
		2. top_block_cls (default is comb_block)
	Outputs:
		None

	This function instantiates a comb_block flowgraph and runs it with the given options.
	It reads the list of files 

	Attributes of options:
		
		1. maxsamp: Maximum number of samples in the combined file. (int)
			(reserved)

		2. num_bands: Total number of VCO bands enabled in both band1 and band2. (int)
			Can be computed using the step_size_metrics() function.

		3. skip: Number of samples to skip before using the first sample in the captured file. (int)

		4. step: Voltage step size for the sweep. (int)
		
		5. sweep_time: Number of samples per voltage sweep. (int)
			Can be computed using the step_size_metrics() function.

	filename:
		[<filename_0>, <output_file_path>]

		filename_0 (str):
			Path to text file where each line is a path to one of the captured calibration samples.
			The calibrate() function generates this file.

		output_file_path (str):
			Full path (including filename) to where the combined calibration data needs to be saved.

	"""
	cal_tone_list = open(filename[0],"r")
	f1 = cal_tone_list.readlines()
	options.maxsamp = options.num_bands * options.sweep_time
	for entry in f1:
		entrya = entry.strip();
		if f1.index(entry) == 0:
			file = [entrya,entrya,filename[1]+'_temp.dat']
		else:
			file = [entrya,filename[1]+'_temp.dat',filename[1]+'_combined.dat']
		print("Now processing "+entrya)
		tb = top_block_cls(options,file)
		tb.start()
		tb.wait()
		if f1.index(entry) != 0:
			os.remove(filename[1]+'_temp.dat')
			time.sleep(0.1)
			os.rename(filename[1]+'_combined.dat',filename[1]+'_temp.dat')
			time.sleep(0.1)
	os.rename(filename[1]+'_temp.dat',filename[1])
	time.sleep(0.1)
	cal_tone_list.close()
	print("Calibration combine complete.")

def sweep(options,top_block_cls = sweep_block):
	"""Wrapper function for SweepSense data capture.

	Inputs: 
		1. options (object)
		2. top_block_cls (default is sweep_block)
	Outputs:
		None

	This function instantiates a sweep_block flowgraph and runs it with the given options.
	Attributes of options:
		1. band1: Bitmap for lower VCO bands to sweep. (int32)

			The VCO bands to sweep are encoded in two 32 bit variables
			band1 and band2 (lower and higher respectively). Within
			the variables, the LSB is of lowest frequency. The span of
			each VCO band has been characterised and is available using
			the function #TODO#

		2. band2: Bitmap for higher VCO bands to sweep. (int32)

		3. filename: List of path strings for saving/reading data. (list)

			The usage of this variable depends on the 'mode' attribute.
			Refer to usage of 'mode' for context.

			mode 1: [<path_to_normal_rx_samples>, <path_to_sweepsense_rx_samples>, <path_to_calibration_data>]
			mode 10: [<path_to_normal_rx_samples>, <path_to_sweepsense_rx_samples>]
			mode 2: [<path_to_save_calibration_data>]
			mode 3: [<path_to_sweepsense_rx_samples>, <path_to_calibration_data>]
			mode 30: [<path_to_sweepsense_rx_samples>]

			example:
			mode 3: ['/mnt/ramdisk/ism_sweep_samples.dat', '/mnt/ramdisk/calibration_samples.dat']

		4. inN: Subsample sweeps. One sweep in every 'inN' sweeps is saved. (int)
		
		5. maxsamp: Maximum number of samples to be captured. (int)

		6. mode: Enables different flowgraph operation modes. (int)

			mode 1: Synchronised reception using one SweepSense USRP and one OTS USRP. MIMO cable used.
			This mode is useful for comparing between a normal receiver and SweepSense. The SweepSense
			samples gathered in this mode are compensated in the flowgraph itself. Path to calibration
			samples required.

			mode 10: Same as mode 1, but the SweepSense samples gathered are not compensated in the 
			flowgraph.

			mode 2: Uses an OTS USRP to provide the calibration tone for the SweepSense receiver. This
			mode is used to gather calbiration data when two USRPs are available.

			mode 3: Use the SweepSense USRP as a standalone receiver. Samples gathered in this mode 
			are compensated in the flowgraph itself. Path to calibration samples required.
			mode 30: Same as mode 3, but samples gathered are not compensated in the flowgraph.

		7. num_bands: Total number of VCO bands enabled in both band1 and band2. (int)
			Can be computed using the step_size_metrics() function.

		8. rf_div: Value of the RF divider in the daughterboard. (1 or 2)

			For CBX: 1 for 3 GHz - 6 GHz, 2 for 1.5 GHz - 3 GHz
		
		9. rgain: Receive gain (dB) of all receive chains. (float)

		10. samp: Sampling rate of all chains. (int)
		
		11. self_name: Path to save this object (str)
		
		12. skip: Number of samples to skip before capturing the first valid sample. (int)

		13. step: Voltage step size for the sweep. (int)
		
		14. sweep_time: Number of samples per voltage sweep. (int)
			Can be computed using the step_size_metrics() function.

		15. tgain: Transmit gain (dB) for all receive chains. (float)
		
		16. transmitter: Unused (reserved)

		17. txfreq: Transmitter frequency for all transmit chains (float)

		18. txsamp: Transmitter sampling frequency wherever applicable (float)
	"""

	start_time = time.time()
	print("Start Time: " + str(start_time))
	tb = top_block_cls(options)
	tb.start()
	tb.wait()
	end_time = time.time()
	print("Total Elapsed: " + str(end_time - start_time) + "seconds")

def load_obj(filename):
	"""Loads an object.

	Input: filename (string)
	Returns: object loaded from filename

	Uses pickle load object at the path specfied by string filename.
	"""
	file_pi2 = open(filename, 'rb') 
	options = pickle.load(file_pi2)
	file_pi2.close()
	return options

def save_obj(options):
	"""Saves the object options.

	Input: options
	Save file destination should be included in the
	object itself as options.self_name.

	Uses pickle to dump the object.
	"""
	filehandler = open(options.self_name, 'wb') 
	pickle.dump(options, filehandler)
	filehandler.close()
	print("Saved Configurations to: "+options.self_name)
	print("Contents: ")
	print(options)

def demo_init():
	"""Demo initialization script.

	Output:
		1. List containing calibration and sweep configuration objects
		as [calibration_configuration, sweep_configuration]
	
	1. Creates a RAM filesystem at /mnt/ramdisk (needs sudo)
	2. Loads calibration and sweep options as objects
	"""

	print('Removing old RAM filesystems...')

	os.system("sudo umount /mnt/ramdisk")

	os.system("sudo rmdir /mnt/ramdisk")

	print('Creating a RAM filesystem for streaming applications...')

	os.system("sudo mkdir /mnt/ramdisk")

	os.system("sudo mount -t tmpfs -o size=4G tmpfs /mnt/ramdisk")

	print('Created and mounted 4 Gigabyte RAM filesystem at /mnt/ramdisk/.')

	print('Loading configuration opjects...')
	cal_opt = load_obj('./script_files/cal_opt_demo.dat')
	sweep_opt = load_obj('./script_files/sweep_opt_demo.dat')
	print("Calibration Options:")
	pprint(vars(cal_opt))
	print("Sweep Options:")
	pprint(vars(sweep_opt))

	print("Demo Init Complete.")
	return [cal_opt,sweep_opt]
