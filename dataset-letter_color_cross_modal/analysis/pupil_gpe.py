#!/usr/bin/env python
# encoding: utf-8
"""
================================================
Pupil analyses gradient prediction error
O.Colizoli 2019
================================================
"""

import os, sys, subprocess
import pandas as pd
import numpy as np
import scipy as sp
import seaborn as sns
import shutil
from shutil import copyfile
import re # regular expression
from copy import deepcopy
import matplotlib
import matplotlib.pyplot as plt
from lmfit import minimize, Parameters, Parameter, report_fit
from fir import FIRDeconvolution
import mne
import scipy.stats as stats

import functions_jw_GLM
from IPython import embed as shell # for debugging
## SEE JW's eye signal operator script for original preprocessing functions

# plot settings
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
sns.set(style='ticks', font='Arial', font_scale=1, rc={
    'axes.linewidth': 1,
    'axes.labelsize': 7,
    'axes.titlesize': 7,
    'xtick.labelsize': 6,
    'ytick.labelsize': 6,
    'legend.fontsize': 6,
    'xtick.major.width': 1,
    'ytick.major.width': 1,
    'text.color': 'Black',
    'axes.labelcolor':'Black',
    'xtick.color':'Black',
    'ytick.color':'Black',} )
sns.plotting_context()

# common functions
def cluster_sig_bar_1samp(array, x, yloc, color, ax, threshold=0.05, nrand=5000, cluster_correct=True):
    # permutation-based cluster correction on time courses, then plots the stats as a bar in yloc
    if yloc == 1:
        yloc = 10
    if yloc == 2:
        yloc = 20
    if yloc == 3:
        yloc = 30
    if yloc == 4:
        yloc = 40
    if yloc == 5:
        yloc = 50

    if cluster_correct:
        whatever, clusters, pvals, bla = mne.stats.permutation_cluster_1samp_test(array, n_permutations=nrand, n_jobs=10)
        for j, cl in enumerate(clusters):
            if len(cl) == 0:
                pass
            else:
                if pvals[j] < threshold:
                    for c in cl:
                        sig_bool_indices = np.arange(len(x))[c]
                        xx = np.array(x[sig_bool_indices])
                        try:
                            xx[0] = xx[0] - (np.diff(x)[0] / 2.0)
                            xx[1] = xx[1] + (np.diff(x)[0] / 2.0)
                        except:
                            xx = np.array([xx - (np.diff(x)[0] / 2.0), xx + (np.diff(x)[0] / 2.0),]).ravel()
                        ax.plot(xx, np.ones(len(xx)) * ((ax.get_ylim()[1] - ax.get_ylim()[0]) / yloc)+ax.get_ylim()[0], color, alpha=1, linewidth=2.5)
    else:
        p = np.zeros(array.shape[1])
        for i in range(array.shape[1]):
            p[i] = sp.stats.ttest_rel(array[:,i], np.zeros(array.shape[0]))[1]
        sig_indices = np.array(p < 0.05, dtype=int)
        sig_indices[0] = 0
        sig_indices[-1] = 0
        s_bar = zip(np.where(np.diff(sig_indices)==1)[0]+1, np.where(np.diff(sig_indices)==-1)[0])
        for sig in s_bar:
            ax.hlines(((ax.get_ylim()[1] - ax.get_ylim()[0]) / yloc)+ax.get_ylim()[0], x[int(sig[0])]-(np.diff(x)[0] / 2.0), x[int(sig[1])]+(np.diff(x)[0] / 2.0), color=color, alpha=1, linewidth=2.5)
            

class pupilPreprocess(object):
    """pupilPreprocessing"""
    def __init__(self, subject, edf, experiment_name, project_directory, eye, break_trials, msgs, tolkens, sample_rate, tw_blinks):
        self.subject = str(subject)
        self.experiment_name = experiment_name
        self.alias = edf
        self.project_directory = project_directory
        self.base_directory = os.path.join(self.project_directory, self.subject)
        self.create_folder_hierarchy()
        self.gazeOutputFileName = os.path.join(self.base_directory, 'raw', edf + '.gaz')
        self.messageOutputFileName = os.path.join(self.base_directory, 'raw', edf + '.msg')
        self.standardOutputFileName = os.path.join(self.base_directory, 'raw', edf + '.asc')
        self.eye = eye
        self.break_trials = break_trials
        self.msgs = msgs
        self.tolkens = tolkens
        self.sample_rate = sample_rate
        self.time_window_blinks = tw_blinks
        self.add_base = True # make false if regressing out blinks, saccades
       
    def create_folder_hierarchy(self):
        """createFolderHierarchy does... guess what."""
        this_dir = self.project_directory
        for d in [self.subject]:
            try:
                this_dir = os.path.join(this_dir, d)
                os.mkdir(this_dir)
            except OSError:
                pass

        for p in ['raw',
         'processed',
         'figs',
         'log']:
            try:
                os.mkdir(os.path.join(self.base_directory, p))
            except OSError:
                pass
    
    def import_raw_data(self, edf_file, log_file, alias):
        """import_raw_data loops across edf_files and their respective aliases and copies and renames them into the raw directory."""        
        # EDF file
        src = edf_file
        dst = os.path.join(self.base_directory,'raw','{}.edf'.format(alias))
        copyfile(src, dst)
        # Behavioral log file
        src = log_file
        dst = os.path.join(self.base_directory,'log','{}_events.csv'.format(alias))
        copyfile(src, dst)
            

    def convert_edfs(self,):
        # converts the EDF file to ASC using the edf2asc executable (as part of the EyeLink desktop application)
        # splits the ASC file into messages and gaze data (samples only)
              
        # terminal commands
        # ./edf2asc Feedback_S2_gpe.edf 
        # ./edf2asc -e Feedback_S2_gpe.edf # gets messages only
        # ./edf2asc -s Feedback_S2_gpe.edf # gets samples only
        # Events/messages 
        input_edf = os.path.join(self.base_directory, 'raw', self.alias+'.edf')
        cmd = './edf2asc -e -y {}'.format(input_edf)
        subprocess.call( cmd, shell=True, bufsize=0,)
        # saves as 'asc' by default, rename file 
        shutil.move(self.standardOutputFileName, self.messageOutputFileName)
        # Samples/gaze
        cmd = './edf2asc -s -miss 0.0001 -vel -y {}'.format(input_edf)
        subprocess.call( cmd, shell=True, bufsize=0,)
        # saves as 'asc' by default, rename file 
        shutil.move(self.standardOutputFileName, self.gazeOutputFileName)
        # ASC file
        cmd = './edf2asc {}'.format(input_edf)
        subprocess.call( cmd, shell=True, bufsize=0,)
    
    def read_trials(self,):
        # For each message in msgs, get timestamp from .msg file

        # TASK MARKERS
        self.msgs_markers = [] # make global variable
        # loop through msgs, then loops through file lines
        for m in self.msgs:
            this_marker = []
            mfd = open(self.messageOutputFileName, 'r')
            for x in mfd: # loop through lines
                if m in x:
                    this_marker.append(x)
            self.msgs_markers.append(this_marker)  # save all markers
            mfd.close()

        # EYE MOVEMENTS MARKERS
        self.tolken_markers = [] # make global variable
        # loop through tolkens, then loops through file lines
        for m in self.tolkens:
            this_marker = []
            mfd = open(self.messageOutputFileName, 'r')
            for x in mfd: # loop through lines
                if m in x:
                    # print(x)
                    this_marker.append(x)
            self.tolken_markers.append(this_marker)  # save all markers
            mfd.close()
        
        ## GET ONLY TIME STAMPS OUT OF STRINGS
        # MARKERS
        self.msgs_markers_timestamps = [] # make global variable
        # get start and stop timestamps (first and second markers)
        ts = re.search('MSG\t(.+?) start', self.msgs_markers[0][0])
        self.msgs_markers_timestamps.append(ts.group(1))
        
        ts = re.search('MSG\t(.+?) stop', self.msgs_markers[1][0])
        self.msgs_markers_timestamps.append(ts.group(1))
        
        # trial phases
        for m in self.msgs_markers[2:]: # start/stop already done above
            this_marker = []
            for marker in m:
                ts = re.search('MSG\t(.+?) trial', marker)
                if ts:
                    this_marker.append(ts.group(1))
            self.msgs_markers_timestamps.append(this_marker)
                            
        ## GET ONLY TIME STAMPS OUT OF STRINGS, BEGIN AND END TIMES
        # TOLKENS (eye movements)
        self.msgs_tolkens_timestamps_begin = [] # make global variable
        self.msgs_tolkens_timestamps_end = []   # GET TIMESTAMP
        for m in self.tolken_markers: # trial markers
            this_marker_begin = []
            this_marker_end = []
            for marker in m:
                ts1 = re.search('{} (.+?)\t'.format(self.eye), marker) # Right or Left eye,first timestamp is beginning of event
                if ts1:
                    this_marker_begin.append(ts1.group(1).strip(' ')) # strips extra white spaces
                    ts0 = re.search('\t(.+)', marker) # get number of samples
                    # ts2 = re.search('\t(.+?)\t', ts0.group(1)) # ESACC duration
                    ts2 = re.search('(.+?)\t', ts0.group(1)) # ESACC/EBLINK end timestamp
                    # if not ts2:
 #                        # ts2 = re.search('\t(.+)', ts0.group(1)) # EBLINK duration
 #                        ts2 = re.search('\t(.+)', ts0.group(1)) # EBLINK timestamp
 #                        shell()
                    this_marker_end.append(ts2.group(1).strip(' ')) # strips extra white spaces
            self.msgs_tolkens_timestamps_begin.append(this_marker_begin)
            self.msgs_tolkens_timestamps_end.append(this_marker_end) # number of samples
        
    def extract_pupil(self,):
        ### EXTRACT PUPIL DATA by timestamps
        # first column time stamp, 4th column is pupil data
        # saves pupil time series and eye events in one numpy array, phases in another
        
        self.read_trials() # RUN FIRST
        pupil_data = pd.read_csv(self.gazeOutputFileName, header=None, sep='\t',usecols=[0,3], names=['timestamp','pupil'])
        
        t1 = int(self.msgs_markers_timestamps[0]) # start
        t2 = int(self.msgs_markers_timestamps[1]) - t1 # stop
        pupil_data['ts_adjusted'] = np.array(pupil_data['timestamp']) - t1
        # get pupil time course between start and stop
        TS = deepcopy(pupil_data.loc[(pupil_data['ts_adjusted'] >= 0) & (pupil_data['ts_adjusted'] < t2)].reset_index()) 
        PHASES = pd.DataFrame()
        # MARKERS
        # loop through trial messages and add to time series data frame
        
        msgs = self.msgs[2:] # skip first 2, start/stop
        # loop each type of marker
        for i,m in enumerate(self.msgs_markers_timestamps[2:]):
            # loop each row of data frame, and check if time stamp in markers list (and +1, because sometimes off by 1 sample)
            m = np.array(m,dtype=int)
            this_phase = []
            for r in range(len(TS)):
                this_t = int(TS.loc[r]['timestamp'])
                # this_phase.append((this_t in m) or (this_t+1 in m)) # if timestamp matches, mark current row with 1
                this_phase.append(this_t in m) # if timestamp matches, mark current row with 1
            PHASES[msgs[i]] = np.array(this_phase, dtype=int)
            
            # check that # tags = # trials
            print('msg = {}, N trials = {}, N timestamps found = {}'.format(msgs[i],len(m),np.sum(PHASES[msgs[i]])))

        # TOLKENS (eye movements)
        # loop each type of tolken, make a column for BEGIN and END of events
        for i,m in enumerate(self.msgs_tolkens_timestamps_begin): 
            
            ## HERE LOOP BEGIN THEN END, timestamps for both
            ## BEGIN POINTS
            # loop each row of data frame, and check if time stamp in markers list
            m = np.array(m,dtype=int)
            m_end = np.array(self.msgs_tolkens_timestamps_end[i],dtype=int)
            timestamps = np.array(TS['timestamp'])
                    
            # Sometimes blinks start before TS dataframe, if this is true, 'starts' begin at first timestamp, drop the 'ends'
            m[m < timestamps[0]] = timestamps[0]    
            m_end[m_end < timestamps[0]] = 0   
            m[m_end < timestamps[0]] = 0    # also drop starts where ends comes earlier
            
            this_phase_begin = [] # save as boolean for each sample 
            this_phase_end = []
            for r in range(len(TS)):
                # STARTS
                this_phase_begin.append(timestamps[r] in m) # is this current sample in the tolken
                # ENDS
                this_phase_end.append(timestamps[r] in m_end)
    
            TS[self.tolkens[i]] = np.array(this_phase_begin, dtype=int)
            TS[self.tolkens[i]+'_END'] = np.array(this_phase_end, dtype=int) # initialize column
            
            # check that # tags = # trials
            print('tolken = {}, N trials = {}, N timestamps found = {}'.format(self.tolkens[i],len(m),np.sum(TS[self.tolkens[i]])))
            print('tolken = {}, N trials = {}, N timestamps found = {}'.format(self.tolkens[i]+'_END',len(m_end),np.sum(TS[self.tolkens[i]+'_END'])))
            
        ## SAVE EXTRACTED AND LOCKED TIMESERIES DATA
        # columns =['timestamp', 'pupil', 'ts_adjusted','ESACC','ESACC_END','EBLINK','EBLINK_END']
        TS.drop(['index'],axis=1,inplace=True)
        np.save(os.path.join(self.base_directory,'processed',self.alias+'.npy'), np.array(TS))
        # save phase data separately, so can use same script for all experiments
        np.save(os.path.join(self.base_directory,'processed',self.alias+'_phases.npy'), np.array(PHASES))
        print('Pupil data saved: {}'.format(os.path.join(self.base_directory,'processed',self.alias+'.npy')))
    
    def preprocess_pupil(self,):
        # Carries out pupil preprocessing steps
        # Current pupil time course is always 'self.pupil'
        # Saves time series at each stage with labels, global variables  (e.g. self.pupil_interp)
        
        cols1=['timestamp','pupil','ts_adjusted','ESACC','ESACC_END','EBLINK','EBLINK_END'] # before preprocessing
        cols2=['timestamp','pupil','ts_adjusted','ESACC','ESACC_END','EBLINK','EBLINK_END','pupil_interp','pupil_bp','pupil_clean','pupil_psc']
        
        try:
            self.TS = pd.DataFrame(np.load(os.path.join(self.base_directory,'processed',self.alias+'.npy')),columns=cols2)
        except:
            self.TS = pd.DataFrame(np.load(os.path.join(self.base_directory,'processed',self.alias+'.npy')),columns=cols1)

        self.pupil_raw = np.array(self.TS['pupil'])
        self.pupil = self.pupil_raw
        
        self.interpolate_blinks()           # linear interpolation, time window 0.1 before to 0.1 after blink
        self.interpolate_blinks_peaks()     # uses derivative to detect events mised by eyelink, linear interpolation, time window 0.1 before to 0.1 after blink
        self.bandpass_filter()              # third-order Butterworth, 0.01-6Hz
        self.regress_blinks_saccades()      # use deconvolution to remove blink + saccade events
        # self.extract_blocks()               # cuts out each block before normalization
        self.percent_signal_change()        # converts to percent signal change
        self.plot_pupil()                   # plots the pupil in all stages

        # save all pupil stages
        # 1: raw, 2: blink interpolated, 3: bandpass, 4: deconvolution, 5: percent signal change
        self.TS['pupil_interp']  = self.pupil_interp
        self.TS['pupil_bp']      = self.pupil_bp # band passed
        self.TS['pupil_clean']   = self.pupil_clean
        self.TS['pupil_psc']     = self.pupil_psc
        np.save(os.path.join(self.base_directory,'processed',self.alias+'.npy'), np.array(self.TS))
        print('Pupil data preprocessed')
        
    def interpolate_blinks(self,):
        """
        Modified from JW's function
        interpolate_blinks interpolates blink periods with method, which can be spline or linear.
        The results are stored in self.pupil_interp, without affecting the self.pupil_raw_... variables
        After calling this method, additional interpolation may be performed by calling self.interpolate_blinks2()
        """
        time_window = self.time_window_blinks # in seconds
        method = 'linear'
        lin_interpolation_points = [[-1*self.sample_rate*time_window],[self.sample_rate*time_window]]
        coalesce_period = int(0.75*self.sample_rate)  # what is this for? beginning and end of time series?
               
        # set all missing data to 0:
        self.pupil[self.pupil<1] = 0

        self.blink_starts_EL = self.TS[self.TS['EBLINK'] == 1.0].index.tolist()
        self.blink_ends_EL = self.TS[self.TS['EBLINK_END'] == 1.0].index.tolist()
        # blinks to work with -- preferably eyelink!
        
        # Sometimes there are more starts than stops, because extends passed time series cutouts
        if len(self.blink_starts_EL) > len(self.blink_ends_EL): 	
            self.blink_starts_EL = self.blink_starts_EL[:len(self.blink_ends_EL)]
            
        for i in range(len(self.blink_starts_EL)):
            self.pupil[int(self.blink_starts_EL[i]):int(self.blink_ends_EL[i])] = 0 # set all eyelink-identified blinks to 0:

        # we do not want to start or end with a 0:
        self.pupil_interp = deepcopy(self.pupil[:])

        self.pupil_interp[:coalesce_period] = np.mean(self.pupil_interp[np.where(self.pupil_interp > 0)[0][:1000]])
        self.pupil_interp[-coalesce_period:] = np.mean(self.pupil_interp[np.where(self.pupil_interp > 0)[0][-1000:]])

        # detect zero edges (we just created from blinks, plus missing data):
        zero_edges = np.arange(self.pupil_interp.shape[0])[:-1][np.diff((self.pupil_interp<1))]
        if zero_edges.shape[0] == 0:
            pass
        else:
            zero_edges = zero_edges[:int(2 * np.floor(zero_edges.shape[0]/2.0))].reshape(-1,2)

        try:
            self.blink_starts = zero_edges[:,0]
            self.blink_ends = zero_edges[:,1]
        except: # in case there are no blinks!
            self.blink_starts = np.array([coalesce_period/2.0])
            self.blink_ends = np.array([(coalesce_period/2.0)+10])

        # check for neighbouring blinks (coalesce_period, default is 500ms), and string them together:
        start_indices = np.ones(self.blink_starts.shape[0], dtype=bool)
        end_indices = np.ones(self.blink_ends.shape[0], dtype=bool)
        for i in range(self.blink_starts.shape[0]):
            try:
                if self.blink_starts[i+1] - self.blink_ends[i] <= coalesce_period:
                    start_indices[i+1] = False
                    end_indices[i] = False
            except IndexError:
                pass

        # these are the blink start and end samples to work with:
        if sum(start_indices) > 0:
            self.blink_starts = self.blink_starts[start_indices]
            self.blink_ends = self.blink_ends[end_indices]
        else:
            self.blink_starts = None
            self.blink_ends = None

        # do actual interpolation:
        if sum(start_indices) > 0:
            points_for_interpolation = np.array([self.blink_starts, self.blink_ends], dtype=int).T + np.array(lin_interpolation_points).T
            for itp in points_for_interpolation:
                itp = [int(x) for x in itp]
                self.pupil_interp[itp[0]:itp[-1]] = np.linspace(self.pupil_interp[itp[0]], self.pupil_interp[itp[-1]], itp[-1]-itp[0])
    
        self.pupil = self.pupil_interp
        print('pupil blinks interpolated from EyeLink events')
    
    def detect_peaks(self, x, mph=None, mpd=1, threshold=0, edge='rising', kpsh=False, valley=False, show=False, ax=None):

    	"""Detect peaks in data based on their amplitude and other features.
    	Parameters
    	----------
    	x : 1D array_like
    		data.
    	mph : {None, number}, optional (default = None)
    		detect peaks that are greater than minimum peak height.
    	mpd : positive integer, optional (default = 1)
    		detect peaks that are at least separated by minimum peak distance (in
    		number of data).
    	threshold : positive number, optional (default = 0)
    		detect peaks (valleys) that are greater (smaller) than `threshold`
    		in relation to their immediate neighbors.
    	edge : {None, 'rising', 'falling', 'both'}, optional (default = 'rising')
    		for a flat peak, keep only the rising edge ('rising'), only the
    		falling edge ('falling'), both edges ('both'), or don't detect a
    		flat peak (None).
    	kpsh : bool, optional (default = False)
    		keep peaks with same height even if they are closer than `mpd`.
    	valley : bool, optional (default = False)
    		if True (1), detect valleys (local minima) instead of peaks.
    	show : bool, optional (default = False)
    		if True (1), plot data in matplotlib figure.
    	ax : a matplotlib.axes.Axes instance, optional (default = None).
    	Returns
    	-------
    	ind : 1D array_like
    		indeces of the peaks in `x`.
    	Notes
    	-----
    	The detection of valleys instead of peaks is performed internally by simply
    	negating the data: `ind_valleys = detect_peaks(-x)`

    	The function can handle NaN's 
    	See this IPython Notebook [1]_.
    	References
    	----------
    	.. [1] http://nbviewer.ipython.org/github/demotu/BMC/blob/master/notebooks/DetectPeaks.ipynb
    	Examples
    	--------
    	>>> from detect_peaks import detect_peaks
    	>>> x = np.random.randn(100)
    	>>> x[60:81] = np.nan
    	>>> # detect all peaks and plot data
    	>>> ind = detect_peaks(x, show=True)
    	>>> print(ind)
    	>>> x = np.sin(2*np.pi*5*np.linspace(0, 1, 200)) + np.random.randn(200)/5
    	>>> # set minimum peak height = 0 and minimum peak distance = 20
    	>>> detect_peaks(x, mph=0, mpd=20, show=True)
    	>>> x = [0, 1, 0, 2, 0, 3, 0, 2, 0, 1, 0]
    	>>> # set minimum peak distance = 2
    	>>> detect_peaks(x, mpd=2, show=True)
    	>>> x = np.sin(2*np.pi*5*np.linspace(0, 1, 200)) + np.random.randn(200)/5
    	>>> # detection of valleys instead of peaks
    	>>> detect_peaks(x, mph=0, mpd=20, valley=True, show=True)
    	>>> x = [0, 1, 1, 0, 1, 1, 0]
    	>>> # detect both edges
    	>>> detect_peaks(x, edge='both', show=True)
    	>>> x = [-2, 1, -2, 2, 1, 1, 3, 0]
    	>>> # set threshold = 2
    	>>> detect_peaks(x, threshold = 2, show=True)
    	"""

    	x = np.atleast_1d(x).astype('float64')
    	if x.size < 3:
    		return np.array([], dtype=int)
    	if valley:
    		x = -x
    	# find indices of all peaks
    	dx = x[1:] - x[:-1]
    	# handle NaN's
    	indnan = np.where(np.isnan(x))[0]
    	if indnan.size:
    		x[indnan] = np.inf
    		dx[np.where(np.isnan(dx))[0]] = np.inf
    	ine, ire, ife = np.array([[], [], []], dtype=int)
    	if not edge:
    		ine = np.where((np.hstack((dx, 0)) < 0) & (np.hstack((0, dx)) > 0))[0]
    	else:
    		if edge.lower() in ['rising', 'both']:
    			ire = np.where((np.hstack((dx, 0)) <= 0) & (np.hstack((0, dx)) > 0))[0]
    		if edge.lower() in ['falling', 'both']:
    			ife = np.where((np.hstack((dx, 0)) < 0) & (np.hstack((0, dx)) >= 0))[0]
    	ind = np.unique(np.hstack((ine, ire, ife)))
    	# handle NaN's
    	if ind.size and indnan.size:
    		# NaN's and values close to NaN's cannot be peaks
    		ind = ind[np.in1d(ind, np.unique(np.hstack((indnan, indnan-1, indnan+1))), invert=True)]
    	# first and last values of x cannot be peaks
    	if ind.size and ind[0] == 0:
    		ind = ind[1:]
    	if ind.size and ind[-1] == x.size-1:
    		ind = ind[:-1]
    	# remove peaks < minimum peak height
    	if ind.size and mph is not None:
    		ind = ind[x[ind] >= mph]
    	# remove peaks - neighbors < threshold
    	if ind.size==True and threshold > 0:
    		dx = np.min(np.vstack([x[ind]-x[ind-1], x[ind]-x[ind+1]]), axis=0)
    		ind = np.delete(ind, np.where(dx < threshold)[0])
    	# detect small peaks closer than minimum peak distance
    	if ind.size==True and mpd > 1:
    		ind = ind[np.argsort(x[ind])][::-1]  # sort ind by peak height
    		idel = np.zeros(ind.size, dtype=bool)
    		for i in range(ind.size):
    			if not idel[i]:
    				# keep peaks with the same height if kpsh is True
    				idel = idel | (ind >= ind[i] - mpd) & (ind <= ind[i] + mpd) \
    					& (x[ind[i]] > x[ind] if kpsh else True)
    				idel[i] = 0  # Keep current peak
    		# remove the small peaks and sort back the indices by their occurrence
    		ind = np.sort(ind[~idel])

    	if show:
    		if indnan.size:
    			x[indnan] = np.nan
    		if valley:
    			x = -x
    		_plot(x, mph, mpd, threshold, edge, valley, ax, ind)

    	return ind
        
    def interpolate_blinks_peaks(self,):
        
        """
        interpolate_blinks_peaks performs linear interpolation around peaks in the rate of change of
        the pupil size.
        
        The results are stored in self.interpolated_pupil, without affecting the self.raw_... variables.
        
        This method is typically called after an initial interpolation using self.interpolateblinks(),
        consistent with the fact that this method expects the self.interpolated_... variables to already exist.
        """
        time_window = self.time_window_blinks
        lin_interpolation_points = [[-1*self.sample_rate*time_window],[self.sample_rate*time_window]]
        coalesce_period = int(0.75*self.sample_rate)
        
        # we do not want to start or end with a 0:
        self.pupil_interp = deepcopy(self.pupil[:])
        
        interpolated_time_points = np.zeros(len(self.pupil))
        self.pupil_diff = (np.diff(self.pupil_interp) - np.diff(self.pupil_interp).mean()) / np.diff(self.pupil_interp).std() # derivative of time series
        peaks_down = self.detect_peaks(self.pupil_diff, mph=10, mpd=1, threshold=None, edge='rising', kpsh=False, valley=False, show=False, ax=False)
        peaks_up = self.detect_peaks(self.pupil_diff*-1, mph=10, mpd=1, threshold=None, edge='rising', kpsh=False, valley=False, show=False, ax=False)
        peaks = np.sort(np.concatenate((peaks_down, peaks_up)))
        
        if len(peaks) > 0:
            # prepare:
            # peak_starts = np.sort(np.concatenate((peaks-1, self.blink_starts)))
            # peak_ends = np.sort(np.concatenate((peaks+1, self.blink_ends)))
            peak_starts = np.sort((peaks-1))
            peak_ends = np.sort((peaks+1))
            start_indices = np.ones(peak_starts.shape[0], dtype=bool)
            end_indices = np.ones(peak_ends.shape[0], dtype=bool)
            for i in range(peak_starts.shape[0]):
                try:
                    if peak_starts[i+1] - peak_ends[i] <= coalesce_period:
                        start_indices[i+1] = False
                        end_indices[i] = False
                except IndexError:
                    pass
            peak_starts = peak_starts[start_indices]
            peak_ends = peak_ends[end_indices] 
            
            # interpolate:
            points_for_interpolation = np.array([peak_starts, peak_ends], dtype=int).T + np.array(lin_interpolation_points).T
            for itp in points_for_interpolation:
                itp = [int(x) for x in itp]
                self.pupil_interp[itp[0]:itp[-1]] = np.linspace(self.pupil_interp[itp[0]], self.pupil_interp[itp[-1]], itp[-1]-itp[0])
                interpolated_time_points[itp[0]:itp[-1]] = 1
            # for regressing out
            self.blink_starts = peak_starts
            self.blink_ends = peak_ends
        # interpolated pupil
        self.pupil = self.pupil_interp
        print('pupil blinks interpolated from derivative')
       
    def bandpass_filter(self,):
        # Bandpass filtering
        # 3rd order butterworth 0.01 to 6 Hz
        from scipy.signal import butter, filtfilt
        N = 3 # order
        Nyquist = 0.5*self.sample_rate
        bpass = [0.01,6] # Hz
        Wn = np.true_divide(bpass,Nyquist) # [low,high]
        
        # This way adds curved artifact to timeseries
        # b,a = butter(N, Wn, btype='bandpass')   # define filter
        # y = filtfilt(b, a, self.pupil)          # apply filter

        # Following JW's scripts
        # low pass
        b,a = butter(N,Wn[1],btype='lowpass') # enter high cutoff value
        self.pupil_lp = filtfilt(b, a, self.pupil.astype('float64'))
        
        # high pass
        b,a = butter(N,Wn[0],btype='highpass') # enter low cutoff value
        self.pupil_hp = filtfilt(b, a, self.pupil.astype('float64')) 
        
        # bandpassed
        self.pupil_bp = self.pupil_hp - (self.pupil-self.pupil_lp)
        # baseline pupil
        self.pupil_baseline = self.pupil_lp - self.pupil_bp

        self.pupil = self.pupil_bp
        print('pupil bandpass filtered butterworth')
    
    def regress_blinks_saccades(self,):
        # Blinks and saccades estimated with deconvolution
        # Then removed via linear regression
        
        plot_IRFs = True # plot for each subject the deconvolved responses in fig folder
        self.add_base = False
        # params:
        downsample_rate = 100
        new_sample_rate = self.sample_rate / downsample_rate
        interval = 5 # seconds to estimate kernels
        
        # get times, blinks, saccs
        self.timepoints = np.array(self.TS['ts_adjusted'],dtype=int)
        self.blink_starts_EL = self.TS[self.TS['EBLINK'] == 1.0].index.tolist() # blink starts with respect to pupil adjusted time series
        self.blink_ends_EL = self.TS[self.TS['EBLINK_END'] == 1.0].index.tolist()
        self.sac_starts_EL = self.TS[self.TS['ESACC'] == 1.0].index.tolist() # saccade starts with respect to pupil adjusted time series
        self.sac_ends_EL = self.TS[self.TS['ESACC_END'] == 1.0].index.tolist()
        
        # CHECK starts and ends equal size, otherwise trim
        if len(self.blink_starts_EL) > len(self.blink_ends_EL): 	
            self.blink_starts_EL = self.blink_starts_EL[:len(self.blink_ends_EL)]
        if len(self.sac_starts_EL) > len(self.sac_ends_EL): 	
            self.sac_starts_EL = self.sac_starts_EL[:len(self.sac_ends_EL)]
            
        # events:
        blinks = np.array(self.blink_ends_EL) / self.sample_rate # use ends because interpolated at starts
        blinks = blinks[blinks>25]
        blinks = blinks[blinks<((self.timepoints[-1]-self.timepoints[0])/self.sample_rate)-interval]

        if blinks.size == 0:
            blinks = np.array([0.5])

        sacs = np.array(self.sac_ends_EL) / self.sample_rate
        sacs = sacs[sacs>25]
        sacs = sacs[sacs<((self.timepoints[-1]-self.timepoints[0])/self.sample_rate)-interval]
        events = [blinks, sacs]
        event_names = ['blinks','saccades']
        
        #######################
        #### Deconvolution ####
        #######################
        # first, we initialize the object
        fd = FIRDeconvolution(
                    signal = self.pupil, 
                    events = events, # blinks, saccades
                    event_names = event_names, 
                    sample_frequency = self.sample_rate, # Hz
                    deconvolution_frequency = downsample_rate, # Hz
                    deconvolution_interval = [0, interval] # 0 = stim_onset - 1
                    )

        # we then tell it to create its design matrix
        fd.create_design_matrix()

        # perform the actual regression, in this case with the statsmodels backend
        fd.regress(method = 'lstsq')

        # and partition the resulting betas according to the different event types
        fd.betas_for_events()
        fd.calculate_rsq()
        response = fd.betas_per_event_type.squeeze() # response[0] blinks, response[1] saccades

        self.blink_response = response[0].ravel()
        self.sac_response = response[1].ravel()
    
        # demean (baseline correct)
        self.blink_response = self.blink_response - self.blink_response[:int(0.2*new_sample_rate)].mean()
        self.sac_response = self.sac_response - self.sac_response[:int(0.2*new_sample_rate)].mean()
        
        if plot_IRFs:    
            fig = plt.figure(figsize=(4,4))
            ax = fig.add_subplot(111)
            
            # R-squared value
            rsquared = fd.rsq
            # Add error bars
            fd.bootstrap_on_residuals(nr_repetitions=1000)
            # plot subject
            try:
                plot_time = response[0].shape[-1] # for x-axis
            except:
                plot_time = response.shape[-1]

            for b in range(fd.betas_per_event_type.shape[0]):
                ax.plot(np.arange(plot_time), fd.betas_per_event_type[b], label=event_names[b])

            for i in range(fd.bootstrap_betas_per_event_type.shape[0]):
                mb = fd.bootstrap_betas_per_event_type[i].mean(axis = -1)
                sb = fd.bootstrap_betas_per_event_type[i].std(axis = -1)

                ax.fill_between(np.arange(plot_time), 
                                mb - sb, 
                                mb + sb,
                                color = 'k',
                                alpha = 0.1)

            ax.set_xticks([0,plot_time])
            ax.set_xticklabels([0,interval]) # removed 1 second from events
            ax.set_xlabel('Time from event (s)')
            ax.set_title('r2={}'.format(round(rsquared[0],2)))
            ax.legend()
            sns.despine(offset=10, trim=True)
            plt.tight_layout()
            # Save figure
            fig.savefig(os.path.join(self.base_directory,'figs',self.alias+'_Deconvolution.pdf'))

        # fit:
        # ----
        # define objective function: returns the array to be minimized        
        def double_pupil_IRF(params, x):
            s1 = params['s1']
            s2 = params['s2']
            n1 = params['n1']
            n2 = params['n2']
            tmax1 = params['tmax1']
            tmax2 = params['tmax2']
            return s1 * ((x**n1) * (np.e**((-n1*x)/tmax1))) + s2 * ((x**n2) * (np.e**((-n2*x)/tmax2)))
            
        def double_pupil_IRF_ls(params, x, data):
            s1 = params['s1'].value
            s2 = params['s2'].value
            n1 = params['n1'].value
            n2 = params['n2'].value
            tmax1 = params['tmax1'].value
            tmax2 = params['tmax2'].value
            model = s1 * ((x**n1) * (np.e**((-n1*x)/tmax1))) + s2 * ((x**n2) * (np.e**((-n2*x)/tmax2)))
            return model - data
            
        # create data to be fitted
        x = np.linspace(0,interval,len(self.blink_response))
        
        # create a set of Parameters
        params = Parameters()
        params.add('s1', value=-1, min=-np.inf, max=-1e-25)
        params.add('s2', value=1, min=1e-25, max=np.inf)
        params.add('n1', value=10, min=9, max=11)
        params.add('n2', value=10, min=8, max=12)
        params.add('tmax1', value=0.9, min=0.5, max=1.5)
        params.add('tmax2', value=2.5, min=1.5, max=4)

        # do fit, here with powell method:
        data = self.blink_response
        blink_result = minimize(double_pupil_IRF_ls, params, method='powell', args=(x, data))
        self.blink_fit = double_pupil_IRF(blink_result.params, x)
        data = self.sac_response
        sac_result = minimize(double_pupil_IRF_ls, params, method='powell', args=(x, data))
        self.sac_fit = double_pupil_IRF(sac_result.params, x)

        # upsample:
        x = np.linspace(0,interval,interval*self.sample_rate)
        blink_kernel = double_pupil_IRF(blink_result.params, x)
        sac_kernel = double_pupil_IRF(sac_result.params, x)

        # regress out from original timeseries with GLM:
        event_1 = np.ones((len(blinks),3))
        event_1[:,0] = blinks
        event_1[:,1] = 0
        event_2 = np.ones((len(sacs),3))
        event_2[:,0] = sacs
        event_2[:,1] = 0
        GLM = functions_jw_GLM.GeneralLinearModel(input_object=self.pupil, event_object=[event_1, event_2], sample_dur=1.0/self.sample_rate, new_sample_dur=1.0/self.sample_rate)
        GLM.configure(IRF=[blink_kernel, sac_kernel], regressor_types=['stick', 'stick'],)
        # why only the first and last are of interest? convolution function: event1-IRF1, event1-IFR2, event2-IRF1, event2-IRF2|
        GLM.design_matrix = np.vstack((GLM.design_matrix[0], GLM.design_matrix[3])) 
        GLM.execute()
        
        self.GLM_measured = GLM.working_data_array
        self.GLM_predicted = GLM.predicted
        self.GLM_r, self.GLM_p = sp.stats.pearsonr(self.GLM_measured, self.GLM_predicted)
        
        # clean data:
        self.pupil_clean = GLM.residuals + self.pupil_baseline.mean() # CLEANED DATA + MEAN added back
        # final timeseries:
        self.pupil = self.pupil_clean 
        print('pupil blinks and saccades removed with linear regression')
    
    def extract_blocks(self,):
        # cuts out the blocks before normalization (after drift correction)
        # breaks by trial number (easiest)
        # self.pupil_blocks is a list with each block as element
        # afterwards, pass to # signal change the concatenate
        
        # phases
        phases = pd.DataFrame(np.load(os.path.join(self.base_directory,'processed',self.alias+'_phases.npy')),columns=self.msgs[2:])
        phase_idx = phases[phases['phase 1'] == 1.0].index.tolist() # locked to break
        # loop through trials, cut out blocks (all different sizes, save as separate arrays)
        r = len(phase_idx)
        self.pupil_blocks = [] # push into list w/ length = # blocks
        self.baseline_blocks = [] # need the baseline pupil in case don't regress out blinks
        for BLOCK,b in enumerate(self.break_trials):
            this_block = []
            this_base = []
            if BLOCK > 0:  # if not first block, get section
                b1 = self.break_trials[BLOCK-1]
                this_block = self.pupil[phase_idx[b1]:phase_idx[b]] # middle blocks 
                this_base = self.pupil_baseline[phase_idx[b1]:phase_idx[b]]
            else:
                this_block = self.pupil[:phase_idx[b]] # first block
                this_base = self.pupil_baseline[:phase_idx[b]] 
            self.pupil_blocks.append(this_block)
            self.baseline_blocks.append(this_base)
        # last block (i.e. 1 block more than # breaks)
        b = self.break_trials[-1:][0] 
        self.pupil_blocks.append(self.pupil[phase_idx[b]:])        
        self.baseline_blocks.append(self.pupil_baseline[phase_idx[b]:])
        
        print('pupil blocks extracted for normalization: No. blocks = {}'.format(len(self.pupil_blocks)))       
    
    def percent_signal_change(self,):
        # Converts processed pupil to percent signal change with respect to mean of current run
        # (timeseries/median*100)-100 # alternative to mean
        # normalize each block separately because subjects moved their heads, then concatenate again
        
        try: # with blocks
            pupil_psc = [] # to be concatenated
            for BLOCK,this_pupil in enumerate(self.pupil_blocks):
                this_pupil = np.array(this_pupil)
                this_base = np.array(self.baseline_blocks[BLOCK])
                if self.add_base: # did not regress out blinks/saccades            
                    this_pupil = this_pupil + this_base.mean() # need to add back mean
                pupil_psc.append( (this_pupil/np.mean(this_pupil)*100)-100 )
            # concantenate
            self.pupil_psc = np.concatenate(pupil_psc)
            if len(self.pupil_psc) == len(self.pupil):
                print('CORRECT LENGTH')
        except: # single time series, no blocks
            self.pupil_psc = (self.pupil/np.mean(self.pupil)*100)-100
        self.pupil = self.pupil_psc
        print('pupil converted percent signal change')
        
    def plot_pupil(self,):               
        # plots the pupil in all stages
        # 1: raw, 2: blink interpolated, 3: temporal filtering, 4: blinks/saccades removed, 5: percent signal change
        # pupil is downsampled for plotting
        # saved in 'figs' folder
        from scipy.signal import decimate
        downsample_rate = 20 # 20 Hz
        downsample_factor = self.sample_rate / downsample_rate # 50
         
        # Make a figure
        fig = plt.figure(figsize=(20,10))
        
        # RAW
        try:
            ax = fig.add_subplot(511)
            pupil = self.pupil_raw
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df = pd.DataFrame(pupil)
            df.columns = ['raw']
            sns.lineplot(data=df,legend='full',ax=ax)
        except:
            pass
        
        # BLINK INTERPOLATED
        try: 
            ax = fig.add_subplot(512)
            pupil = self.pupil_interp
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df = pd.DataFrame(pupil)
            df.columns = ['blink interpolated']
            sns.lineplot(data=df,legend='full',ax=ax)
        except:
            pass

        # BANDPASS FILTERED
        try: 
            # add columns to df for filtered
            ax = fig.add_subplot(513)
            
            pupil = self.pupil_lp
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df = pd.DataFrame(pupil)
            df.columns = ['low pass']
            
            pupil = self.pupil_hp
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df['high pass'] = pupil
            
            pupil = self.pupil_bp
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df['band pass'] = pupil
            
            pupil = self.pupil_baseline
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df['baseline'] = pupil
            
            sns.lineplot(data=df,legend='full',ax=ax)
            
        except:
            pass
            
        # CLEAN: BLINKS & SACCADES REMOVED
        try: 
            ax = fig.add_subplot(514)
            pupil = self.pupil_clean
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df = pd.DataFrame(pupil)
            df.columns = ['clean deconv.']
            sns.lineplot(data=df,legend='full',ax=ax)
        except:
            pass
            
        # PSC
        try: 
            ax = fig.add_subplot(515)
            pupil = self.pupil_psc
            pupil = decimate(pupil, int(downsample_factor), ftype='fir')
            df = pd.DataFrame(pupil)
            df.columns = ['perc. signal change']
            sns.lineplot(data=df,legend='full',ax=ax)
        except:
            pass
              
        sns.despine(offset=10, trim=True)
        plt.tight_layout()
        # Save figure
        fig.savefig(os.path.join(self.base_directory,'figs',self.alias+'.pdf'))
        
    
class trials(object):
    def __init__(self,subjects,experiment_name,project_directory,sample_rate,phases,time_locked,time_locked_phases,pupil_step_lim,baseline_window,pupil_time_of_interest):
        self.subjects = subjects
        self.exp = experiment_name
        self.project_directory = project_directory
        self.figure_folder = os.path.join(project_directory, 'figures')
        self.sample_rate = sample_rate
        self.phases = phases
        ##############################    
        # Pupil time series information:
        ##############################
        self.time_locked = time_locked
        self.time_locked_phases = time_locked_phases
        self.pupil_step_lim = pupil_step_lim # size of pupil trials in seconds with respect to first event, first element should max = 0!
        self.baseline_window = baseline_window # seconds before event of interest
        self.pupil_time_of_interest = pupil_time_of_interest     # test on all data
        # For plotting
        self.downsample_rate = 20 # 20 Hz
        self.downsample_factor = self.sample_rate / self.downsample_rate
        
        if not os.path.isdir(self.figure_folder):
            os.mkdir(self.figure_folder)
    
    def tsplot(self, ax, data, **kw):
        # replacing seaborn tsplot
        x = np.arange(data.shape[1])
        est = np.mean(data, axis=0)
        sd = np.std(data, axis=0)
        cis = self.bootstrap(data)
        ax.fill_between(x,cis[0],cis[1],alpha=0.2,**kw) # debug double label!
        ax.plot(x,est,**kw)
        ax.margins(x=0)
    
    def bootstrap(self, data, n_boot=10000, ci=68):
        # bootstrap confidence interval for new tsplot
        boot_dist = []
        for i in range(int(n_boot)):
            resampler = np.random.randint(0, data.shape[0], data.shape[0])
            sample = data.take(resampler, axis=0)
            boot_dist.append(np.mean(sample, axis=0))
        b = np.array(boot_dist)
        s1 = np.apply_along_axis(stats.scoreatpercentile, 0, b, 50.-ci/2.)
        s2 = np.apply_along_axis(stats.scoreatpercentile, 0, b, 50.+ci/2.)
        return (s1,s2)
    
    def event_related_subjects(self):
        # Cuts out time series of pupil data locked to time points of interest
        # Saves events as numpy arrays per subject in dataframe folder/subjects per event of interest
        # Rows = trials x kernel length
        cols=['timestamp','pupil','ts_adjusted','ESACC','ESACC_END','EBLINK','EBLINK_END','pupil_interp','pupil_bp','pupil_clean','pupil_psc']
        
        # loop through each type of event to lock events to...
        for t,time_locked in enumerate(self.time_locked):
            pupil_step_lim = self.pupil_step_lim[t]
            for s,subj in enumerate(self.subjects):
                TS = pd.DataFrame(np.load(os.path.join(self.project_directory,subj,'processed','{}_{}.npy'.format(subj,self.exp))),columns=cols)
                # USE PERCENT SIGNAL CHANGE PUPIL
                pupil = np.array(TS['pupil_psc']) 
                # get indices of phases with respect to full time series
                phases = pd.DataFrame(np.load(os.path.join(self.project_directory,subj,'processed','{}_{}_phases.npy'.format(subj,self.exp))),columns=self.phases)
                phase_idx = phases[phases[self.time_locked_phases[t]] == 1.0].index.tolist() # locked to feedback
                # loop through trials, cut out events
                r = len(phase_idx)
                c = int((pupil_step_lim[1]-pupil_step_lim[0])*self.sample_rate)
                SAVE_TRIALS = np.zeros((r,c))
                SAVE_TRIALS[SAVE_TRIALS==0] = np.nan # better than zeros for missing data
                for trial,t_idx in enumerate(phase_idx):
                    # t_idx is location of phase 1 of current trial
                    # This works because pupil_step_lim[0] is negative
                    this_pupil = pupil[int(t_idx+(pupil_step_lim[0]*self.sample_rate)):int(t_idx+(pupil_step_lim[1]*self.sample_rate))] 
                    SAVE_TRIALS[trial,:len(this_pupil)] = this_pupil # sometimes not enough data at the end
                np.save(os.path.join(self.project_directory,subj,'processed','{}_{}_{}_pupil_events.npy'.format(subj,self.exp,time_locked)), SAVE_TRIALS)
                print('subject {}, {} events extracted'.format(subj,time_locked))
        print('sucess: event_related_subjects')
    
    def event_related_baseline_correction(self):
        # Baseline correction on evoked responses, saves baseline pupil in behav log file
        # resp_locked baselines are with respect the the FEEDBACK, therefore, always run feedback first. 
        # save mean baselines per trial, and then use those for response locked
                      
        # loop through each type of event to lock events to...
        for t,time_locked in enumerate(self.time_locked):
            
            pupil_step_lim = self.pupil_step_lim[t]
            
            for s,subj in enumerate(self.subjects):
                
                P = np.load(os.path.join(self.project_directory,subj,'processed','{}_{}_{}_pupil_events.npy'.format(subj,self.exp,time_locked)))
                behav_file = os.path.join(self.project_directory,subj,'log','{}_{}_events.csv'.format(subj,self.exp))
                B = pd.read_csv(behav_file)
                B.drop(['Unnamed: 0'],axis=1,inplace=True)
                
                if 'resp' in time_locked: # get baselines from data frame, locked to stimulus not response!
                    B['pupil_baseline_'+time_locked] = B['pupil_baseline_feed_locked']
                    this_base = B['pupil_baseline_'+time_locked]
                    # save resp_locked baselines
                    B.to_csv(behav_file)
                    # remove baseline mean from each time point for current trial
                    for trial in range(len(P)):
                        P[trial] = P[trial]-this_base[trial]
                else: # compute and save stim_locked baselines
                    SAVE_TRIALS = []
                    for trial in range(len(P)):
                        # in seconds
                        base_start = -pupil_step_lim[0]-self.baseline_window
                        base_end = base_start + self.baseline_window
                        # in sample rate units
                        base_start = int(base_start*self.sample_rate)
                        base_end = int(base_end*self.sample_rate)
                        # mean within baseline window
                        this_base = np.mean(P[trial,base_start:base_end]) 
                        SAVE_TRIALS.append(this_base)
                        # remove baseline mean from each time point for current trial
                        P[trial] = P[trial]-this_base
                    # save stim_locked baselines
                    B['pupil_baseline_'+time_locked] = np.array(SAVE_TRIALS)
                    B.to_csv(behav_file)
                    
                # save baseline corrected events and baseline means too!
                np.save(os.path.join(self.project_directory,subj,'processed','{}_{}_{}_pupil_events_basecorr.npy'.format(subj,self.exp,time_locked)), P)
                
                print('subject {}, {} events baseline corrected'.format(subj,time_locked))
        print('success: event_related_baseline_correction')
    
    def plot_event_related(self):
        # Plots mean response per event type, across the group (standard error)
        # Tests response against 0 (cluster-permutation test)
        # Use baseline corrected time series!
                      
        # loop through each type of event to lock events to...
        for t,time_locked in enumerate(self.time_locked):
            pupil_step_lim = self.pupil_step_lim[t]
            pupil_time_of_interest = self.pupil_time_of_interest[t]
            
            # make a figure
            GROUP = [] # length = # subjects
            for s,subj in enumerate(self.subjects):
                P = np.load(os.path.join(self.project_directory,subj,'processed','{}_{}_{}_pupil_events_basecorr.npy'.format(subj,self.exp,time_locked)))
                GROUP.append(np.nanmean(P,axis=0))
                    
            # Downsample pupil data for plotting
            GROUP = sp.signal.decimate(np.array(GROUP), int(self.downsample_factor), ftype='fir')
            
            # Make a figure
            fig = plt.figure(figsize=(4,4))
            ax = fig.add_subplot(111)
            
            # plot 
            try:
                sns.tsplot(GROUP, condition=time_locked, value='Pupil response\n(% signal change)', color='black', alpha=1, lw=1, ls='-', ax=ax)
            except:
                self.tsplot(ax, GROUP, color='k', label=time_locked)
            # ADD STATS HERE
            cluster_sig_bar_1samp(array=GROUP, x=pd.Series(range(GROUP.shape[-1])), yloc=1, color='red', ax=ax, threshold=0.05, nrand=5000, cluster_correct=False)
            cluster_sig_bar_1samp(array=GROUP, x=pd.Series(range(GROUP.shape[-1])), yloc=1, color='black', ax=ax, threshold=0.05, nrand=5000, cluster_correct=True)
            
            ax.axvline(int(abs(pupil_step_lim[0]*self.downsample_rate)), lw=0.25, alpha=0.5, color = 'k') # Add vertical line at t=0
            ax.axhline(0, lw=0.25, alpha=0.5, color = 'k') # Add horizontal line at t=0
            
            # determine time points x-axis given sample rate            
            event_onset = int(abs(pupil_step_lim[0]*self.downsample_rate))
            end_sample = int((pupil_step_lim[1] - pupil_step_lim[0])*self.downsample_rate)
            mid_point = int(np.true_divide(end_sample-event_onset,2) + event_onset)
            
            # Shade time of interest in grey, will be different for events
            tw_begin = int(event_onset + (pupil_time_of_interest[0]*self.downsample_rate))
            tw_end = int(event_onset + (pupil_time_of_interest[1]*self.downsample_rate))
            ax.axvspan(tw_begin,tw_end, facecolor='k', alpha=0.1)
            
            xticks = [event_onset,mid_point,end_sample]
            # Figure parameters
            ax.set_xticks(xticks)
            ax.set_xticklabels([0,np.true_divide(pupil_step_lim[1],2),pupil_step_lim[1]])
            ax.legend(loc='best')
            ax.set_xlabel('Time from event (s)')
            sns.despine(offset=10, trim=True)
            plt.tight_layout()
            # Save figure
            fig.savefig(os.path.join(self.figure_folder, '{}_mean_response_{}.pdf'.format(self.exp,time_locked)))
        print('success: plot_event_related_time_window')
    
    def plot_event_related_subjects(self):
        # FOR EACH SUBJECT Plots mean response per event type, across the group (standard error)
        # One figure per time_locked condition
        # Tests response against 0 (cluster-permutation test)
        # Use baseline corrected time series!
            
        # loop through each type of event to lock events to...
        for t,time_locked in enumerate(self.time_locked):
            pupil_step_lim = self.pupil_step_lim[t]
            pupil_time_of_interest = self.pupil_time_of_interest[t]
            
            # Make a figure
            fig = plt.figure(figsize=(16,32))

            for s,subj in enumerate(self.subjects):
                M = np.load(os.path.join(self.project_directory,subj,'processed','{}_{}_{}_pupil_events_basecorr.npy'.format(subj,self.exp,time_locked)))
                ax = fig.add_subplot(10,6,s+1)
                
                # Downsample pupil data for plotting
                M = sp.signal.decimate(np.array(M), int(self.downsample_factor), ftype='fir')
                # plot 
                try:
                    sns.tsplot(M, condition=time_locked, color='black', alpha=1, lw=1, ls='-', ax=ax)
                except:
                    self.tsplot(ax, M, color='k', label=time_locked)
                # ADD STATS HERE
                cluster_sig_bar_1samp(array=M, x=pd.Series(range(M.shape[-1])), yloc=1, color='red', ax=ax, threshold=0.05, nrand=5000, cluster_correct=False)
                cluster_sig_bar_1samp(array=M, x=pd.Series(range(M.shape[-1])), yloc=1, color='black', ax=ax, threshold=0.05, nrand=5000, cluster_correct=True)
            
                ax.axvline(int(abs(pupil_step_lim[0]*self.downsample_rate)), lw=0.25, alpha=0.5, color = 'k') # Add vertical line at t=0
                ax.axhline(0, lw=0.25, alpha=0.5, color = 'k') # Add horizontal line at t=0
            
                # determine time points x-axis given sample rate
                event_onset = int(abs(pupil_step_lim[0]*self.downsample_rate))
                end_sample = int((pupil_step_lim[1] - pupil_step_lim[0])*self.downsample_rate)
                mid_point = int(np.true_divide(end_sample-event_onset,2) + event_onset)
            
                # Shade time of interest in grey, will be different for events
                tw_begin = int(event_onset + (pupil_time_of_interest[0]*self.downsample_rate))
                tw_end = int(event_onset + (pupil_time_of_interest[1]*self.downsample_rate))
                ax.axvspan(tw_begin,tw_end, facecolor='k', alpha=0.1)
            
                xticks = [event_onset,mid_point,end_sample]
                # Figure parameters
                ax.set_xticks(xticks)
                ax.set_xticklabels([0,np.true_divide(pupil_step_lim[1],2),pupil_step_lim[1]])
                # ax.legend(loc='best')
                ax.set_xlabel('Time from event (s)')
                ax.set_title(subj)
            sns.despine(offset=10, trim=True)
            plt.tight_layout()
            # Save figure
            fig.savefig(os.path.join(self.figure_folder, '{}_mean_response_{}_subjects.pdf'.format(self.exp,time_locked)))
        print('success: plot_event_related_time_window_subjects')
        
    def phasic_pupil(self):
        # Extracts phasic pupil in self.pupil_time_of_interest, saves in behav log file
        
        # loop through each type of event to lock events to...
        for t,time_locked in enumerate(self.time_locked):
            pupil_step_lim = self.pupil_step_lim[t]
            pupil_time_of_interest = self.pupil_time_of_interest[t]
            
            for s,subj in enumerate(self.subjects):
                P = np.load(os.path.join(self.project_directory,subj,'processed','{}_{}_{}_pupil_events_basecorr.npy'.format(subj,self.exp,time_locked)))
                behav_file = os.path.join(self.project_directory,subj,'log','{}_{}_events.csv'.format(subj,self.exp))
                B = pd.read_csv(behav_file)
                SAVE_TRIALS = []
                for trial in range(len(P)):
                    # in seconds
                    phase_start = -pupil_step_lim[0] + pupil_time_of_interest[0]
                    phase_end = -pupil_step_lim[0] + pupil_time_of_interest[1]
                    # in sample rate units
                    phase_start = int(phase_start*self.sample_rate)
                    phase_end = int(phase_end*self.sample_rate)
                    # mean within phasic time window
                    this_phasic = np.nanmean(P[trial,phase_start:phase_end]) 
                    SAVE_TRIALS.append(this_phasic)
                # save phasics
                B['pupil_{}'.format(time_locked)] = np.array(SAVE_TRIALS)
                B.drop(['Unnamed: 0'],axis=1,inplace=True)
                B.to_csv(behav_file)
                print('subject {}, {} phasic pupil extracted {}'.format(subj,time_locked,pupil_time_of_interest))
        print('success: phasic_pupil')