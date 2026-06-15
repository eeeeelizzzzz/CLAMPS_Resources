
"""
Created on Jan 5 2021

@author: elizabeth.smith/jacob.carlin
"""
"""
This is a multi-instrument fuzzy logic PBL height detection algorithm developed
for using CLAMPS Doppler wind lidar and thermodynamic (AERI) profiles. This 
algorithm was developed from the basis set forth in Bonin et al. (2018).
 https://doi.org/10.1175/JTECH-D-17-0159.1
"""
#########################################################
#All the imports
#########################################################
import netCDF4 as nc
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from scipy.interpolate import RegularGridInterpolator
from scipy.special import erf
import scipy.optimize as sp
import scipy.signal as ss
import pandas as pd
from siphon.catalog import TDSCatalog
from datetime import datetime, timezone, timedelta
from suntime import Sun
# import cmocean as cm #can use for additional colorbars, 
# opted to remove for simplicty 

#this is making the plots pretty!
plt.style.use('bmh')
#this is making the font big enough to read
plt.rcParams['font.size'] = 16
plt.rcParams['font.family'] = 'PT Sans'
x_tick_labels = ['00','03','06','09','12','15','18','21','00']

#################################################################################################################

#########################################################
#FUNCTIONS
#########################################################


################ ES temporal variance profiles ##############
def calcSigma(stare_t, stare_z, stare_field, window=.25):
    """
    This function computes the variance of a field within a specified time window.
    Adapted from existing ESmith code for variance of CLAMPS data.
    
    Args:
        stare_t (array): 1-D array of times [hr]
        stare_z (array): 1-D array of heights [km]
        stare_field (array): 2-D array of field to compute variance of
        window (float): Time window for computing variance [h] (Default = 0.25)
        
    Returns:
        var_field (array): 2-D array of variances over specified window
        time_axis (array): 1-D array of new times
    """
    
    time_axis = np.arange(0, stare_t[-1], window) # New time axis
    var_field = np.full((len(time_axis), len(stare_z)), np.nan) # Variance over window
    prev_index = 0 # previous index for looping below
    for j in range(0, len(stare_z)):
        work = stare_field[:, j]
        for i in range(0, len(time_axis) - 1):
            X = np.where(stare_t < time_axis[i+1])[0]
            if X.size < 1:
                continue
            end = X[-1]
            var_field[i, j] = np.nanvar(work[prev_index:end])
            prev_index = end
            
    return var_field, time_axis

  
##########################################################


################### ES Moving Avg ##########################
def moving_average(a, n=3):
    """
    This function calculates a moving average over some window.
    
    Args:
        a (array): 1-D array of field
        n (int): Window size, default 3 point
    Returns:
        ret (array): 1-D array of averaged field
    """
    
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    
    return ret[n - 1:] / n

  
##########################################################
 

################ ES uv frm spd/dir########################
def uv_from_spd_dir(speed, wdir):
    """
    This function computes the u- and v-components of the wind
    given speed and direction.
    
    Args:
        speed (array): Wind speeds
        wdir (array): Wind direction in degrees
    Returns:
        u (array): u-component of the wind
        v (array): v-components of the wind
    """
    
    wdir = np.deg2rad(wdir)
    u = -speed * np.sin(wdir)
    v = -speed * np.cos(wdir)
    
    return u, v
  
  
##########################################################


##########################################################
def find_closest(A, target):
    """
    This function finds the index of the closest value to a 
    target value with a specified array.
    Source: Jeremy Gibbs (NOAA-NSSL)
    
    Args:
        A (array): Data to search for closest value
        target (float): Value being searched for
    Returns:
        idx (int): Index of A with value closest to target.
    """

    idx = A.searchsorted(target) # A must be sorted
    idx = np.clip(idx, 1, len(A)-1)
    left = A[idx-1]
    right = A[idx]
    idx -= target - left < right - target
    
    return idx
  
  
##########################################################



##########################################################
#our fuzzy functions start here -- we wrote them all
##########################################################

##########################################################
def find_peaks(vals, num_peaks=5):
    """
    This function finds x number of highest peak values from a 1D arrary.
    
    Args: 
        vals (array): 1-D array of values 
        num_peaks (int): default 5, number of peaks desired
        
    Returns:
        ret (array): 1-D array of peak indicies
    """
    
    temp = np.argpartition(-vals, num_peaks)
    result_args = temp[:num_peaks]
    
    return result_args
  
  
##########################################################


##########################################################
def mean_u(ws, t, z, new_t, lo=.1, hi=1.):
  """
  This function computes a mean wind speed over a layer.
  
  Args:
      ws (array): 2-D windspeed (time, height)
      t (array): 1-D time
      z (array): 1-D height
      new_t (array): 1-D array of desired output time
      lo (float): default = 0.1, lower limit for averaging layer, [km]
      hi (float): default = 1.0, upper limit for averaging layer, [km]
  
  Returns:
        mean_u (array): 1-D array of layer averaged windspeed
  """
  mean_U = np.full(ws.shape[0], np.nan)
  lo_ind = np.where(z > lo)[0][0] - 1
  hi_ind = np.where(z > hi)[0][0]
  for i in range(ws.shape[0]):
    mean_U[i] = np.nanmean(ws[i, lo_ind:hi_ind]) 
  f = interp1d(t, mean_U, fill_value="extrapolate")
  mean_u = f(new_t)
  
  return mean_u


##########################################################


##########################################################
def HF_varcalc(field, time, height):
  """
  This function computes the high frequency variance fields. It first
  does a high-pass filter, then uses the calcSigma function to get
  varaince.
  
  Args:
      field (array): 2-D field for which high frequency variance is needed
                       [time, height]
      time (array): 1-D array of time
      height (array): 1-D array of height
  
  Returns:
      filt_field (array): 2-D field of same shape as field after high-pass filter
      HFsigw (array): 2-D array of the high frequency variance computed from filt_field
      HFsigw_t (array): 1-D array of new time axis for HFsigw
  """
  
  filt_field = np.full(field.shape,np.nan)
  HFThresh = 0.01667 #this frequency is corresponding to a 1 min period
                     # any freq higher than this is considered high frequency
  order = 6
  b, a = ss.butter(order, HFThresh, btype='lowpass', output='ba')
  # note this is lowpass, but data-lowpass == highpass and vice-versa 
  for i in range(len(height)):
      field_nan = field[:,i]
      field_nan[np.isnan(field[:, i])] = 0.0
      filt = ss.filtfilt(b, a, field_nan)      
      filt_field[:, i] = field[:, i] - filt
  HFsigw, HFsigw_t = calcSigma(time, height, filt_field, window=0.166) #computing the 
  # vertical velocity variance from raw w in 5 min=.083 (10=0.166)windows
  HFsigw[np.where(HFsigw > 5)] = np.nan
  return filt_field, HFsigw, HFsigw_t
  
  
##########################################################


##########################################################
def fuzzify(var_input, bound_low, bound_high):
  """
  This function produces membership values given appropriate cutoffs for 
  the fuzzy logic application (half-trapezoidal).
  
  Args:
      var_input (array): values for which the membership function is needed
      bound_low (float): x1 value, lower bound for membership, below which = 1
      bound_high (float): x2 value, upper bound for membership, above which = 0
  
  Returns:
      var_output (array): array same shape as var_input holding membership values
  """
  # Create output array 
  var_output = np.zeros_like(var_input) 
  # Keeps nans where the are from input values
  var_output[np.isnan(var_input)] = np.nan
  # set values based on x1, x2 bounds provided
  var_output[var_input > bound_high] = 1.0
  var_output[var_input < bound_low] = 0.0
  # set values between 0,1 given slope between bound points
  slope = 1.0 / (bound_high - bound_low)
  g = np.logical_and((var_input >= bound_low), (var_input <= bound_high))
  var_output[g] = slope * (var_input[g] - bound_low)
  # Clean up output and force to be between (0, 1)
  var_output = np.clip(var_output, 0.0, 1.0)
  
  return var_output


##########################################################


##########################################################
def fuzzGrid(input_var, input_x, input_y, start_time=0., end_time=1440., low_z = 0.01):
  """
  This function regrids input to 10-min/10-m grid
  
  Args:
      input_var (array): 2-D array field to be regridded
      input_x (array): 1-D x-axis of input_var
      input_y (array): 1-D y-axis of input_var
      start_time (int): the beginning of the desired output time array (default 0 min)
      end_time (int): the end of the desired output time array (default 1440 min)
      low_z (int): the lowest index of the desired output height array (lowest lidar height, default 10 m)
      
  Returns:
      output_var (array): 2-D array field now on 10-min/10-m grid
  """
  
  # Define function characterizing original data grid
  f = RegularGridInterpolator(points=[input_x, input_y], values=input_var)#, bounds_error=False, fill_value=np.nan)
  
  x_new = np.arange(start_time, end_time+10., 10.) # Interpolate to 10-min intervals
  y_new = np.arange(low_z,4.001,0.01) # Interpolate to 10-m intervals
  
  #check the end of the file to see if the end time is too early (15 min allowance)
  diff=x_new[-1]-input_x[-1]
  if diff> 0:
      if diff<0.26: # if the input time ends 15 min or less earlier than the desired time axis
          input_x[-1]=x_new[-1] #set it to the end of the desired time axis
      else: #if it ends more than 15 min earlier than the time axis
          print('THIS FILE IS TOO SHORT YO... Figure it out.') #we do nothing and print a message
          #the below code will fail in this case. Should we add an exit? 
          
  g,h = np.meshgrid(y_new,x_new)
  G=g.reshape((np.prod(g.shape),))
  H=h.reshape((np.prod(h.shape),))
  coords=zip(H,G)
  pts = list(coords)
  pts = np.asarray(pts)
  output = f(pts) # Interpolate to new grid points
  output_var = output.reshape(np.shape(g)) # Reshape to new array size
  
  return output_var


##########################################################



##########################################################
def run_haar_wavelet(profile, z, haarDilationLength=100):
  """
  Perform a Haar wavelet analysis on a given profile at heights z.
  Default haarDilationLength 
  
  Args:
    profile: Data profile to perform wavelet analysis on.
    z: Attendant height vector [km]
    haarDilationLength = Size of Haar wavelet window (default = 100 m)
    
  Returns:
  	Wavelet transform
  """
  
  # Compute the number of dilation gates
  z = z * 1e3 # Convert to m
  rGateSize = np.ediff1d(z)
  numDilationGates = int(np.ceil(haarDilationLength / (2 * rGateSize))[0])
  
  # Define Haar wavelet function
  haar_func = np.full((2 * int(numDilationGates) + 1,), np.nan)
  haar_func[0:numDilationGates] = 1;
  haar_func[numDilationGates] = 0
  haar_func[(numDilationGates+1):2*numDilationGates+1] = -1

  # Convolve the wavelet over all range gates
  nHeights = len(z)
  w_trans = np.full((nHeights), 0, dtype='float')
  for j in range(numDilationGates, nHeights - numDilationGates):
    for k in range(0, len(haar_func)):
      tmp = ((1./haarDilationLength) * rGateSize[j] * haar_func[k] * profile[j - numDilationGates + k])
      if ~np.isnan(tmp):
        w_trans[j] += tmp

  return w_trans


##########################################################
def calc_haar_membership(profile, z, BLhgt_i):
  """
  This function dynamically computes membership functions based on haar wavelet transfrom as computed
  by the run_haar_wavelet function.
  Membership = 1 at all levels below the lowest considered peak. Membership = 0 at all levels above 
  the highest considered peak. For each peak in between, the membership function decreases in steps.
  D(mem)/dz)=peak value/(sum of all retained peak values).  See Bonin et al. (2018) for details. 
  
  Args: 
      profile (array): 1-D profile of transformed wavelet profile
      z (array): 1-D height data
      BLhgt_i (float): first-guess PBL height at this time (km)
      
  Returns:
      prof_fuzz (array): same shape as profile holding membership values based on haar wavelet method
      top5_hgt (list): list of heights of the retained peaks used in membership function
  """
  heights = z

  #find top five peaks in cD output
  top5_idx = np.sort(find_peaks(profile))
  #print('Top5', top5_idx)

  top5_hgt = heights[top5_idx]
  top5_val = profile[top5_idx]
  
  prof_fuzz = np.full(heights.shape, np.nan) 
  
  
  # Eliminate peaks outside +/- 25% of round one Zi (BLhgt_i is scalar PBL height at this time)
  upperlim = 1.25 * BLhgt_i  # km
  lowerlim = 0.75 * BLhgt_i  # km
    
  if np.any((top5_hgt <= upperlim) & (top5_hgt >= lowerlim)):
  # Retain only points within +/- 25% of Zi
      top5_val = top5_val[(top5_hgt <= upperlim) & (top5_hgt >= lowerlim)]
      top5_hgt = top5_hgt[(top5_hgt <= upperlim) & (top5_hgt >= lowerlim)]
  else:
      return prof_fuzz, []
  
  if len(top5_hgt) >= 1:
    top5_idx = np.full(top5_hgt.shape, np.nan)
    for j in range(len(top5_hgt)):
      top5_idx[j] = find_closest(heights, top5_hgt[j])
      
  top5_idx = top5_idx[(top5_hgt <= upperlim) & (top5_hgt >= lowerlim)]

  # Get highest andlowest maxima heights
  if len(top5_idx) == 0:
      return prof_fuzz, top5_hgt
  if len(top5_idx) == 1:
    top_hgt = top5_hgt
    bot_hgt = top5_hgt
  else:
    top_hgt = max(top5_hgt)
    bot_hgt = min(top5_hgt)

  # Membership = 1 at all levels below the lowest considered peak. 
  # Membership = 0 at all levels above the highest considered peak. 
  # For each peak in between, the membership function decreases in 
  # steps = peak value/(sum of all retained peak values).  
    
  for j in range(len(heights)):
    if (heights[j] > top_hgt):
      prof_fuzz[j] = 0.0
    elif (heights[j] < bot_hgt):
      prof_fuzz[j] = 1.0
    else: # interpolate membership function
      if j in top5_idx:
        tmp_idx = np.where(top5_idx == j)[0][0] # Grab index of current height within top5_idx
        scaling = top5_val[tmp_idx] / np.sum(top5_val)
        prof_fuzz[j] = prof_fuzz[j-1] - scaling
      else:
        prof_fuzz[j] = prof_fuzz[j-1]
  
  return prof_fuzz, top5_hgt 
##########################################################


##########################################################
def BLhgtFiltSmooth(BLhgt_vals, window=7):
    """
    This function takes a timeseries of PBL heights from the fuzzy logic algorithm
    and smooths them via a triangle weighted function. It provides the smoothed 
    timeseries and a timeseries of the range of values that went into each mean. It
    also removes outlier values based on day-long standard deviation filter.
  
    Args:
      BLhgt_vals (1-D array): values of BLhgt from fuzzy logic algorithm 
      window (int): the number of values included in the rolling mean, default 7
  
    Returns:
      BLhgt_sm (1-D array): smoothed BL hgts
      BLhgt_sm_range (2-D array): [time, level (bottom=0, top=1)] range of values that go into mean
    """
    BLhgt=BLhgt_vals
    #standard deviation based filter
    BL_std = np.nanstd(BLhgt)
    for j in range(len(BLhgt)):
        if BLhgt[j]>BLhgt[j]+BL_std:
            BLhgt[j]=np.nan
        if BLhgt[j]<BLhgt[j]-BL_std:
            BLhgt[j]=np.nan
    
    #triangle mean over +- 30 min (7 points or defined by window)
    BLdf = pd.DataFrame(BLhgt)
    BLhgts = BLdf.rolling(7, center=True, win_type='triang',min_periods=1).mean()
    #BLhgt_sm_upper = BLdf.rolling(7, center=True,min_periods=1).max()
    #BLhgt_sm_lower = BLdf.rolling(7, center=True,min_periods=1).min()
    BLhgts_sm_std = BLdf.rolling(7, center=True,min_periods=1).std()
    
    BLhgt_sm = BLhgts.values
    BLhgt_sm = BLhgt_sm.ravel()
    #BLhgt_sm_upper = BLhgt_sm_upper.values
    #BLhgt_sm_upper = BLhgt_sm_upper.ravel()
    #BLhgt_sm_lower = BLhgt_sm_lower.values
    #BLhgt_sm_lower = BLhgt_sm_lower.ravel()
    BLhgt_sm_std = BLhgts_sm_std.values
    BLhgt_sm_std = BLhgt_sm_std.ravel()
        
    #BLhgt_sm_range = np.vstack((BLhgt_sm_lower, BLhgt_sm_upper)).T
    #BLhgt_sm_range = np.vstack((BLhgt_sm-BLhgt_sm_std, BLhgt_sm+BLhgt_sm_std)).T
    
    return BLhgt_sm, BLhgt_sm_std

##########################################################


##########################################################
def findBLhgt(BL_logical,gate_min):
    """
    This function takes a 2 D logical array relecting BL membership in/out (1/0) status and
    a min usuable lidar range gate and finds the BL hgt based on that membership. 
  
    Args:
      BLlogical (2-D array): values of BL logical membership, 1=in 0=out 
      gate_min (int): index (in y, interp, space) of lowest useable lidar range gate
  
    Returns:
      BLhgt (1-D array): top of layer where BL membership is at least .5 (top of layer of 1s) attached
      to the surface.
     """
    BLhgt = np.full(np.shape(BL_logical)[0], np.nan)
    for j in range(len(BLhgt)):  # Loop through times
        starting_search = np.where(BL_logical[j, :] == 1)[0]
        if len(starting_search) == np.count_nonzero(np.isnan(starting_search)):
            #there are no ones, so nothing is "in" the BL
            continue
        elif starting_search[0]>gate_min+2: #beyond 2 gates of the useable range gates
            #bottom of ones layer (mixed layer) is elevated
            print("ELEVATED LAYER DETECTED... skipping")
            continue
        spots = np.where(BL_logical[j, starting_search[0]:] != 1)[0]
        if len(spots) == np.count_nonzero(np.isnan(spots)):
            continue
        else:
            BLhgt[j] = y[spots[0]]
    return BLhgt

##########################################################


##########################################################
def xcorr(x, y, scale='none'):
    """
    This function comes from Tyler Bell (CIWRO/NSSL) and computes a 
    correlation between x and y.
    
    Args:
      x (array): values for correlation calculation
      y (array): values for correlation calculation
                 if y==x, auto-correlation!
    
    Returns:
      corr (): correlation values
      lags (): lags
    """
    # Pad shorter array if signals are different lengths
    if x.size > y.size:
        pad_amount = x.size - y.size
        y = np.append(y, np.repeat(0, pad_amount))
    elif y.size > x.size:
        pad_amount = y.size - x.size
        x = np.append(x, np.repeat(0, pad_amount))
        
    corr = np.correlate(x, y, mode='full')  # scale = 'none'
    lags = np.arange(-(x.size - 1), x.size)
    if scale == 'biased':
        corr = corr / x.size
    elif scale == 'unbiased':
        corr /= (x.size - abs(lags))
    elif scale == 'coeff':
        corr /= np.sqrt(np.dot(x, x) * np.dot(y, y))
    return corr, lags


##########################################################


##########################################################        
def lenshow(x, freq=1, tau_min=3, tau_max=12, plot=False):
    """
    This function comes from Tyler Bell (CIWRO/NSSL)    
    Reads in a timeseries. Freq is in Hz. Default taus are from avg values 
    from Bonin Dissertation (2015)
    Returns avg w'**2 and avg error'**2
    """
    # Find the perturbation of x
    mean = np.mean(x)
    prime = x - mean
    # Get the autocovariance 
    acorr, lags = xcorr(prime, prime, scale='unbiased')
    acov = acorr# * var
    # Extract lags > 0
    lags = lags[int(np.ceil(len(lags)/2)):] * freq
    acov = acov[int(np.ceil(len(acov)/2)):]
    # Define the start and end lags
    lag_start = int(tau_min / freq)
    lag_end = int(tau_max / freq)
    # Fit the structure function
    fit_funct = lambda p, t: p[0] - p[1]*t**(2./3.) 
    err_funct = lambda p, t, y: fit_funct(p, t) - y
    p1, success = sp.leastsq(err_funct, [1, .001], args=(lags[lag_start:lag_end], acov[lag_start:lag_end]))
    if plot:
        new_lags = np.arange(tau_min, tau_max)
        plt.plot(lags, acov)
        plt.plot(new_lags, fit_funct(p1, new_lags), 'gX')
        plt.plot(0, fit_funct(p1, 0), 'gX')
        plt.xlim(0, tau_max+20)
        plt.xlabel("Lag [s]")
        plt.ylabel("$M_{11} [m^2s^{-2}$]")
    return p1[0], acov[0] - p1[0]

  
##########################################################


##########################################################
def lenshowVar(time, height, vertvel, intensity, window=.25):
    """
    This function applied the Lenshow method to vertical velocity data. Calls
    Tyler Bell's lenshow function (which calls his correlate fucntion). Note 
    vertical velocity data should not be filtered/have nans yet
    
    Args:
        time (array): 1-D array of times
        height (array): 1-D array of heights
        vertvel (array): 2-D array of vertical velocity observations
        intensity (array): 2-D array of intensity (SNR+1)
        window (float): Time window for computing variance [h] (Default = 0.25)
    Returns:
        sigw (array): 2-D array of vertical velocity variance (new time res.)
        sigw_t (array): 1-D array new time resolution
    """
    #rename variables because I am a bad coder
    HR=time
    Z=height
    w=vertvel
    snr = intensity
    # provide an initial index for slicing
    prev_idx = 0
    # New time axis
    lenshow_t = np.arange(0, HR[-1], window)
    # interpolate snr to the new time axis for filtering later
    snr_l=np.full((lenshow_t.shape[0],Z.shape[0]),np.nan)
    for ii in range(len(Z)):
        snr_l[:,ii] = np.interp(lenshow_t,HR,snr[:,ii])
    # array for sigw 
    lenshow_sigw = np.full((lenshow_t.shape[0],Z.shape[0]),np.nan)
    # loop over all heights
    for j in range(0,len(Z)):
        # loop over all NEW times (stepping via window)
        for i in range(len(lenshow_t)-1):
            # find the index of the last time for the relevant averaging window
            last = np.where(HR < lenshow_t[i+1])[0]
            # if this search turns up nothing, go to the next loop step without doing anythong
            if last.size < 1:
                continue
            # the final index for slicing is the end of the averaging window
            last_idx = last[-1]
            # slice the w field using the indicies we've found to define the averaging window
            work_data = w[prev_idx:last_idx,j]
            # if all w data in this slice is nan, set the first index for the next step to the current last index
            # amd go on to the next loop step
            if np.isnan(work_data).all():
                prev_idx = last[-1]
                continue
            # Use the lenshow method which is inside Tyler Bell's function. 
            # We only want the first return (2nd is avg w)
            std = lenshow(work_data)[0]
            lenshow_sigw[i,j]=std
            # set the first index for the next step to the current last index
            prev_idx = last_idx
    
    # now we want to filter the output of the lenshow-ed vert velocity by SNR
    # this cutoff value is hardcoded and less restrictive than usual since 
    # lenshow already does some 'filtering' of its own in effect
    lenshow_sigw[np.where(snr_l<1.0075)] = np.nan
    
    return lenshow_sigw, lenshow_t
  
  
##########################################################
