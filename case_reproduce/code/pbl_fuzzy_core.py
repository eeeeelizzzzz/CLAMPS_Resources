##################################################################################################################
#fuzzy logic
##################################################################################################################

#dict for x1,x2, weight vals for various inputs -- for membership functions
# x1,x2 vals defined by bonin et al 2018
membership_vals = {'wVar': {'lo': 0.02,
                            'hi': 0.08,
                            'wt': 1.0},
                   'HFwVar': {'lo': 0.0025,
                              'hi': 0.01,
                              'wt': 1.0},
                   'snr': {'wt': 2.0},
                   'snrVar': {'wt': 2.0},
                   'uv': {'wt': 2.0},
                   'wv': {'wt': 2.0},
                   'pt': {'wt': 2.0}}


    
# Compute high frequency variance 
HFw, HFwVar, HFt = HF_varcalc(w, HR, Z)
HFwVar[np.where(HFwVar<.0001)]=np.nan #this was pulling first guess down with all zeros otherwise
U = mean_u(ws, HRv, Zv, HFt, lo=.1, hi=1.)
# tip: if you run into an error where U (or ws rather) has a bad shape, check to see if you have a wonky extra 
# lidar file on the day you are trying to process. That can result in funny things. Remove the wonky file if so.
for i in range(len(Z)):
    HFwVar[:,i] = HFwVar[:,i] / U #normalize by mean wind speed to prevent removal of large eddies
                   
##########################################################
# 1st generation steps: 
#########################################################
  
# Perform fuzzification to membership values (0, 1)
wVar_fuzz = fuzzify(sigw, membership_vals['wVar']['lo'], membership_vals['wVar']['hi'])
wVarHF_fuzz = fuzzify(HFwVar, membership_vals['HFwVar']['lo'], membership_vals['HFwVar']['hi'])

# Interpolate to common grid for AERI and DL data
wVar_fuzz_intp = fuzzGrid(wVar_fuzz, sigw_t, Z, start_time = start_time, end_time = end_time, low_z=lower_limit)
wVarHF_fuzz_intp = fuzzGrid(wVarHF_fuzz, sigw_t, Z, start_time = start_time, end_time = end_time, low_z=lower_limit)

# Add weights and calculate aggregate value
wVar_fuzz_intp_wt = np.full(wVar_fuzz_intp.shape, np.nan)
wVar_fuzz_intp_wt[~np.isnan(wVar_fuzz_intp)] = membership_vals['wVar']['wt']

wVarHF_fuzz_intp_wt = np.full(wVarHF_fuzz_intp.shape, np.nan)
wVarHF_fuzz_intp_wt[~np.isnan(wVarHF_fuzz_intp)] = membership_vals['HFwVar']['wt']

# Compute time-weighted membership function for incorporating AERI data
sun = Sun(sun_lat, sun_lon) #sun for given lat lon, "actual code" block
sunup = sun.get_sunrise_time(timestamp).replace(tzinfo=timezone.utc).timestamp()
sundown = sun.get_sunset_time(timestamp).replace(tzinfo=timezone.utc).timestamp()
prev_sundown = sun.get_sunset_time(timestamp - timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp()
next_sundown = sun.get_sunset_time(timestamp + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp()

real_sunup = sunup
real_sundown = sundown
real_prev_sundown = prev_sundown
real_next_sundown = next_sundown

sunup_offset = -20 * 60.
sundown_offset = -20 * 60.

sunup += sunup_offset
sundown += sundown_offset
prev_sundown += sundown_offset
next_sundown += sundown_offset

# Span membership weights through full processing window (multi-day safe).
_membership_span_s = int(max(end_time - start_time, 1440.0) * 60.0) + 7200
membership_times = np.arange(base_time, base_time + _membership_span_s, 600)
membership_value_vec = np.full(len(membership_times), np.nan)
transition_half_window = 3600 # 30-min [in s] for a 1-h total transition window centered on sunup/sundown

# Nighttime
if sundown < sunup:
    g = np.where(np.logical_and(membership_times > (sundown + transition_half_window),
                                membership_times < (sunup - transition_half_window)))
else: # sunrise for date comes first
    g = np.where(np.logical_and(membership_times > (prev_sundown + transition_half_window),
                               membership_times < (sunup - transition_half_window)))
membership_value_vec[g] = 2.0 


# Daytime
if sundown < sunup:
    g = np.where(np.logical_and(membership_times < (next_sundown - transition_half_window),
                               membership_times > (sunup + transition_half_window)))
else:
    g = np.where(np.logical_and(membership_times < (sundown - transition_half_window),
                               membership_times > (sunup + transition_half_window)))    
membership_value_vec[g] = 0.0 

# Transition zones
# Dawn
g = np.where(np.abs(membership_times - sunup) <= transition_half_window)[0]
membership_value_vec[g] = -erf((membership_times[g] - sunup) / 1200.) + 1.0 
# 1200.0 (20-min periods) gets to vals = (0, 2) at (-1 hr, +1 hr)

# Dusk
g = np.where(np.abs(membership_times - sundown) <= transition_half_window)[0]
membership_value_vec[g] = erf((membership_times[g] - sundown) / 1200.) + 1.0

g = np.where(np.abs(membership_times - next_sundown) <= transition_half_window)[0]
membership_value_vec[g] = erf((membership_times[g] - next_sundown) / 1200.) + 1.0

g = np.where(np.abs(membership_times - prev_sundown) <= transition_half_window)[0]
membership_value_vec[g] = erf((membership_times[g] - prev_sundown) / 1200.) + 1.0


# interpolating
f = interp1d((membership_times - base_time)/60., membership_value_vec) # Convert time to minutes vec
# compute the T gradient in an array
T_grad=np.full(T.shape,np.nan)
T_grad[:,:-1]=np.diff(T,axis=1) #vertical temperature gradients
# fuzzify the T gradient
inv_bin = fuzzGrid(T_grad, t_a, Za, start_time = start_time, end_time = end_time, low_z=lower_limit)
# prepare and array for the T gradient weighting
inv_fuzz_wt = np.full(inv_bin.shape, np.nan)
inv_fuzz = np.full(inv_bin.shape, np.nan)
# this list is a holder for debug plotting purposes
inversion=[]
# looping over times
for i in range(len(x)):
    asign = np.sign(inv_bin[i,:]) #find sign of gradient vals
    signchange = ((np.roll(asign, 1) - asign) != 0).astype(int) #return 1 for sign change, 0 for not
    signchange[0]=0 #setting since numpy.roll does a circular shift, so if the last element has different 
    # sign than the first, the first element in the signchange array will be 1
    #note -1, +1, and 0 are all considered unique signs here
    inversion_idx = np.where(signchange==1)[0]
    if inversion_idx.size < 1:
        # if there are no sign changes, we skip this loop and move on 
        inversion.append(np.nan)
        continue
    else:
        inversion_idx=inversion_idx[0]
    if y[inversion_idx] > 1.25: #above 1.25 km
      	# we don't want want to retain any info about elevated inversions, so if the inversion
        # identified is above 1.25, we break out and move foward with the time loop
        inversion.append(np.nan)
        continue 
    else:
        # use inversion index to define membership in the boundary layer
        inv_fuzz[i,:inversion_idx+1] = 1.0 # in the boundary layer
        inv_fuzz[i,inversion_idx+1:] = 0 # outside the boundary layer
    inv_fuzz_wt[i, :] = f(x[i]) # apply weighting as defined above
    inversion.append(y[inversion_idx])

# visualize Inversion Weighting and the sunset/rise times
if inv_check == True:
    plt.figure(figsize=(18,6))
    plt.plot((membership_times-base_time)/3600.,membership_value_vec, lw=6, color='k',label='Inversion Weight')
    plt.axvline((real_sunup-base_time)/3600.,ls='--',color='grey')
    plt.axvline((real_sundown-base_time)/3600.,ls='--',color='grey')
    #plt.legend()
    plt.title(str(platform)+' '+str(date_label))#+' Inversion Weight as a Function of Sunrise/Sunset')
    plt.xticks(np.arange(0,24.1,3),x_tick_labels)
    plt.xlim(0,24.1)
    plt.xlabel('Hour [UTC]')
    plt.ylim(0,2.1)
    plt.ylabel('Height AGL [km]')
    if show_me == True:
        plt.show()
    else:
        plt.savefig(path_to_plots+date_label+'_InvWeight_'+platform+'.png')
        plt.close()
    
    # visualize Inversion Height and the sunset/sunrsise times
    plt.figure(figsize=(18,6))
    plt.plot(x/60.,inversion, lw=6, color='k',label='Inversion Height')
    plt.axvline((real_sunup-base_time)/3600.,ls='--',color='grey')
    plt.axvline((real_sundown-base_time)/3600.,ls='--',color='grey')
    #plt.legend()
    plt.title(str(platform)+' '+str(date_label))#+' Inversion Weight as a Function of Sunrise/Sunset')
    plt.xticks(np.arange(0,24.1,3),x_tick_labels)
    plt.xlim(0,24.1)
    plt.xlabel('Hour [UTC]')
    plt.ylim(0,2.1)
    plt.ylabel('Height AGL [km]')
    if show_me == True:
        plt.show()
    else:
        plt.savefig(path_to_plots+date_label+'_InvHeight_'+platform+'.png')
        plt.close()
  
# Compute overall aggregate values
sum_fuzz = np.zeros_like(wVar_fuzz_intp_wt)
for i in range(np.shape(wVar_fuzz_intp_wt)[0]):
  for j in range(np.shape(wVar_fuzz_intp_wt)[1]):
      sum_fuzz[i, j] = ((np.nansum((wVar_fuzz_intp[i, j] * wVar_fuzz_intp_wt[i, j], 
                                    wVarHF_fuzz_intp[i, j] * wVarHF_fuzz_intp_wt[i, j],
                                    inv_fuzz[i, j] * inv_fuzz_wt[i, j]))) / 
                        (np.nansum((wVar_fuzz_intp_wt[i, j],
                                    wVarHF_fuzz_intp_wt[i, j],
                                    inv_fuzz_wt[i, j]))))       

# Compute overall aggregate values for overnight mechanical only terms (zero out fuzzwt)
sum_fuzz_ovn_mech = np.zeros_like(wVar_fuzz_intp_wt)
for i in range(np.shape(wVar_fuzz_intp_wt)[0]):
  for j in range(np.shape(wVar_fuzz_intp_wt)[1]):
      sum_fuzz_ovn_mech[i, j] = ((np.nansum((wVar_fuzz_intp[i, j] * wVar_fuzz_intp_wt[i, j], 
                                    wVarHF_fuzz_intp[i, j] * wVarHF_fuzz_intp_wt[i, j],
                                    inv_fuzz[i, j] * 0))) / 
                        (np.nansum((wVar_fuzz_intp_wt[i, j],
                                    wVarHF_fuzz_intp_wt[i, j],
                                    0))))    

# Compute overall aggregate values for overnight buoyant only terms (zero out var wts)
sum_fuzz_ovn_buoy = np.zeros_like(wVar_fuzz_intp_wt)
for i in range(np.shape(wVar_fuzz_intp_wt)[0]):
  for j in range(np.shape(wVar_fuzz_intp_wt)[1]):
      sum_fuzz_ovn_buoy[i, j] = ((np.nansum((wVar_fuzz_intp[i, j] * 0, 
                                    wVarHF_fuzz_intp[i, j] * 0,
                                    inv_fuzz[i, j] * inv_fuzz_wt[i, j]))) / 
                        (np.nansum((0,
                                    0,
                                    inv_fuzz_wt[i, j]))))                   

# Codifying BL status using 0.5 threshold of mem aggregrate (1=in, 0=out)
BL_thresh = 0.5
BL_logical = np.full(wVar_fuzz_intp.shape,np.nan)
BL_logical_ob = np.full(wVar_fuzz_intp.shape,np.nan)
BL_logical_om = np.full(wVar_fuzz_intp.shape,np.nan)
BL_logical[sum_fuzz >= BL_thresh] = 1.0
BL_logical[sum_fuzz < BL_thresh] = 0.0
BL_logical_om[sum_fuzz_ovn_mech >= BL_thresh] = 1.0
BL_logical_om[sum_fuzz_ovn_mech < BL_thresh] = 0.0
BL_logical_ob[sum_fuzz_ovn_buoy >= BL_thresh] = 1.0
BL_logical_ob[sum_fuzz_ovn_buoy < BL_thresh] = 0.0
BLhgt = findBLhgt(BL_logical,gate_min)
BLhgt_ob = findBLhgt(BL_logical_ob,gate_min)
BLhgt_om = findBLhgt(BL_logical_om,gate_min)

#smoothing BL height and defining variability based on standard deviation 
BLhgt_sm, BLhgt_sm_range = BLhgtFiltSmooth(BLhgt, window=7)
BLhgt_sm = np.array(BLhgt_sm, copy=True)
BLhgt_sm_range = np.array(BLhgt_sm_range, copy=True)
BLhgt_om_sm, BLhgt_om_sm_range = BLhgtFiltSmooth(BLhgt_om, window=7)
BLhgt_om_sm = np.array(BLhgt_om_sm, copy=True)
BLhgt_om_sm_range = np.array(BLhgt_om_sm_range, copy=True)
BLhgt_ob_sm, BLhgt_ob_sm_range = BLhgtFiltSmooth(BLhgt_ob, window=7)
BLhgt_ob_sm = np.array(BLhgt_ob_sm, copy=True)
BLhgt_ob_sm_range = np.array(BLhgt_ob_sm_range, copy=True)



#%%
if plot_me == True:
    #########################################################
    # Plot first generation aggregrate
    #########################################################
    plt.figure(figsize=(18,6))
    plt.pcolormesh(x,y,sum_fuzz.transpose(),vmin=0,vmax=1,cmap='inferno')
    plt.plot(x,BLhgt,marker='o',ls='none', color='lightpink',markeredgecolor='purple',zorder=1000,alpha=.5)
    plt.plot(x,BLhgt_sm,color='purple',lw=5)
    plt.plot(x,BLhgt_sm,color='lightpink',lw=3)
    plt.colorbar(label='Aggregrate 1st Gen')
    plt.ylim(0.06,2.75)
    #plt.ylim(0,2)
    plt.xticks(np.arange(0,1440.1,180),x_tick_labels)
    plt.xlim(0.0,1440.1)
    plt.title(str(platform)+' '+str(date_label))
    plt.xlabel('Hour [UTC]')
    plt.ylabel(' Height AGL [km]')
    if show_me == True:
        plt.show()
    else:
        plt.savefig(path_to_plots+date_label+'_FirstGenAg_'+platform+'.png')
        plt.close()
#%%

print('First Gen. Fuzzy Complete')
##########################################################
# 2nd generation steps: 
#########################################################

# Regridding
snr_bin = fuzzGrid(snr, HR*60., Z, start_time = start_time, end_time = end_time, low_z=lower_limit)
sigsnr_bin = fuzzGrid(sigsnr, sigsnr_t*60., Z, start_time = start_time, end_time = end_time, low_z=lower_limit)
u_bin = fuzzGrid(u, HRv*60., Zv, start_time = start_time, end_time = end_time, low_z=lower_limit)
v_bin = fuzzGrid(v, HRv*60., Zv, start_time = start_time, end_time = end_time, low_z=lower_limit)
pt_bin = fuzzGrid(pt, HRa*60., Za, start_time = start_time, end_time = end_time, low_z=lower_limit)
wv_bin = fuzzGrid(wv, HRa*60., Za, start_time = start_time, end_time = end_time, low_z=lower_limit)

# Membership arrays
snr_fuzz = np.full(snr_bin.shape, np.nan)
sigsnr_fuzz = np.full(sigsnr_bin.shape,np.nan)
uv_fuzz = np.full(u_bin.shape, np.nan)
pt_fuzz = np.full(pt_bin.shape, np.nan)
wv_fuzz = np.full(wv_bin.shape, np.nan)

# Haar wavelet arrays for visualization
x_wave_shape = snr_bin.shape[0]
y_wave = np.linspace(min(y),max(y),len(y))
y_wave_shape = len(y_wave)
snr_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)
sigsnr_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)
u_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)
v_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)
uv_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)
pt_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)
wv_fuzz_wavelet = np.full((x_wave_shape, y_wave_shape), np.nan)    

# Loop through times
snr_wavelet_peak_hgts = []
sigsnr_wavelet_peak_hgts = []
uv_wavelet_peak_hgts = []
pt_wavelet_peak_hgts = []
wv_wavelet_peak_hgts = []
for i in range(len(x)):
  snr_fuzz_wavelet[i,:] = run_haar_wavelet(snr_bin[i, :], y)
  snr_fuzz[i, :], hgts = calc_haar_membership(snr_fuzz_wavelet[i, :], y[:], BLhgt_sm[i])
  snr_wavelet_peak_hgts.append(hgts)
  
  sigsnr_fuzz_wavelet[i, :] = run_haar_wavelet(sigsnr_bin[i, :], y)
  sigsnr_fuzz[i, :], hgts = calc_haar_membership(sigsnr_fuzz_wavelet[i, :], y[:], BLhgt_sm[i])
  sigsnr_wavelet_peak_hgts.append(hgts)
  
  # u & v will be passed through wavelet then the vector magnitude of the wavelet transform
  # is used in the membership function computation process
  u_fuzz_wavelet[i, :] = run_haar_wavelet(u_bin[i, :], y)
  v_fuzz_wavelet[i, :] = run_haar_wavelet(v_bin[i, :], y)
  uv_fuzz_wavelet[i, :] = np.sqrt(u_fuzz_wavelet[i, :]**2 + v_fuzz_wavelet[i, :]**2)
  uv_fuzz[i, :], hgts = calc_haar_membership(uv_fuzz_wavelet[i, :], y[:], BLhgt_sm[i])
  uv_wavelet_peak_hgts.append(hgts)     
  
  pt_fuzz_wavelet[i, :] = run_haar_wavelet(pt_bin[i, :], y)
  pt_fuzz[i, :], hgts = calc_haar_membership(pt_fuzz_wavelet[i, :], y[:], BLhgt_sm[i])
  pt_wavelet_peak_hgts.append(hgts)
  
  wv_fuzz_wavelet[i, :] = run_haar_wavelet(wv_bin[i, :], y)
  wv_fuzz[i, :], hgts = calc_haar_membership(wv_fuzz_wavelet[i, :], y[:], BLhgt_sm[i])
  wv_wavelet_peak_hgts.append(hgts)
      
# Create 2D arrays of weights for each variable
snr_fuzz_wt = np.full(snr_fuzz.shape, np.nan)
snr_fuzz_wt[~np.isnan(snr_fuzz)] = membership_vals['snr']['wt']

sigsnr_fuzz_wt = np.full(sigsnr_fuzz.shape, np.nan)
sigsnr_fuzz_wt[~np.isnan(sigsnr_fuzz)] = membership_vals['snrVar']['wt']

uv_fuzz_wt = np.full(uv_fuzz.shape, np.nan)
uv_fuzz_wt[~np.isnan(uv_fuzz)] = membership_vals['uv']['wt'] 

pt_fuzz_wt = np.full(pt_fuzz.shape, np.nan)
pt_fuzz_wt[~np.isnan(pt_fuzz)] = membership_vals['pt']['wt']

wv_fuzz_wt = np.full(wv_fuzz.shape, np.nan)
wv_fuzz_wt[~np.isnan(wv_fuzz)] = membership_vals['wv']['wt']

# creating 2nd generation aggregate! 
sum_fuzz_2 = np.zeros_like(snr_fuzz_wt)
for i in range(np.shape(snr_fuzz_wt)[0]):
  for j in range(np.shape(snr_fuzz_wt)[1]):
      sum_fuzz_2[i, j] = ((np.nansum((wVar_fuzz_intp[i, j] * wVar_fuzz_intp_wt[i, j], 
                                     wVarHF_fuzz_intp[i, j] * wVarHF_fuzz_intp_wt[i, j],
                                     inv_fuzz[i, j] * inv_fuzz_wt[i, j],
                                     snr_fuzz[i, j] * snr_fuzz_wt[i, j],
                                     sigsnr_fuzz[i, j] * sigsnr_fuzz_wt[i, j],
                                     uv_fuzz[i, j] * uv_fuzz_wt[i, j],
                                     pt_fuzz[i, j] * pt_fuzz_wt[i, j],
                                     wv_fuzz[i, j] * wv_fuzz_wt[i, j]))) / 
                          (np.nansum((wVar_fuzz_intp_wt[i, j],
                                             wVarHF_fuzz_intp_wt[i, j],
                                             inv_fuzz_wt[i, j],
                                             snr_fuzz_wt[i, j],
                                             sigsnr_fuzz_wt[i, j],
                                             uv_fuzz_wt[i, j],
                                             pt_fuzz_wt[i, j],
                                             wv_fuzz_wt[i, j]))))
      
# creating 2nd generation aggregate! 
sum_fuzz_ovn_mech2 = np.zeros_like(snr_fuzz_wt)
for i in range(np.shape(snr_fuzz_wt)[0]):
  for j in range(np.shape(snr_fuzz_wt)[1]):
      sum_fuzz_ovn_mech2[i, j] = ((np.nansum((wVar_fuzz_intp[i, j] * wVar_fuzz_intp_wt[i, j], 
                                     wVarHF_fuzz_intp[i, j] * wVarHF_fuzz_intp_wt[i, j],
                                     inv_fuzz[i, j] * 0,
                                     snr_fuzz[i, j] * snr_fuzz_wt[i, j],
                                     sigsnr_fuzz[i, j] * sigsnr_fuzz_wt[i, j],
                                     uv_fuzz[i, j] * uv_fuzz_wt[i, j],
                                     pt_fuzz[i, j] * 0,
                                     wv_fuzz[i, j] * 0))) / 
                          (np.nansum((wVar_fuzz_intp_wt[i, j],
                                             wVarHF_fuzz_intp_wt[i, j],
                                             0,
                                             snr_fuzz_wt[i, j],
                                             sigsnr_fuzz_wt[i, j],
                                           uv_fuzz_wt[i, j],
                                             0,
                                             0))))
      
# creating 2nd generation aggregate! 
sum_fuzz_ovn_buoy2 = np.zeros_like(snr_fuzz_wt)
for i in range(np.shape(snr_fuzz_wt)[0]):
  for j in range(np.shape(snr_fuzz_wt)[1]):
      sum_fuzz_ovn_buoy2[i, j] = ((np.nansum((inv_fuzz[i, j] * inv_fuzz_wt[i, j],
                                     pt_fuzz[i, j] * pt_fuzz_wt[i, j],
                                     wv_fuzz[i, j] * wv_fuzz_wt[i, j]))) / 
                          (np.nansum((inv_fuzz_wt[i, j],
                                             pt_fuzz_wt[i, j],
                                             wv_fuzz_wt[i, j]))))


# Codifying BL status using 0.5 threshold of mem aggregrate (1=in, 0=out)
BL_thresh = 0.5
BL_logical_2 = np.full(snr_fuzz_wt.shape,np.nan)
BL_logical_ob2 = np.full(wVar_fuzz_intp.shape,np.nan)
BL_logical_om2 = np.full(wVar_fuzz_intp.shape,np.nan)
BL_logical_2[sum_fuzz_2 >= BL_thresh] = 1.0
BL_logical_2[sum_fuzz_2 < BL_thresh] = 0.0
BL_logical_om2[sum_fuzz_ovn_mech2 >= BL_thresh] = 1.0
BL_logical_om2[sum_fuzz_ovn_mech2 < BL_thresh] = 0.0
BL_logical_ob2[sum_fuzz_ovn_buoy2 >= BL_thresh] = 1.0
BL_logical_ob2[sum_fuzz_ovn_buoy2 < BL_thresh] = 0.0
BLhgt_2 = findBLhgt(BL_logical_2,gate_min)
BLhgt_om2 = findBLhgt(BL_logical_om2,gate_min)
BLhgt_ob2 = findBLhgt(BL_logical_ob2,gate_min)

BLhgt_2_sm, BLhgt_2_sm_range = BLhgtFiltSmooth(BLhgt_2, window=7)
BLhgt_2_sm = np.array(BLhgt_2_sm, copy=True)
BLhgt_2_sm_range = np.array(BLhgt_2_sm_range, copy=True)
BLhgt_om2_sm, BLhgt_om2_sm_range = BLhgtFiltSmooth(BLhgt_om2, window=7)
BLhgt_om2_sm = np.array(BLhgt_om2_sm, copy=True)
BLhgt_om2_sm_range = np.array(BLhgt_om2_sm_range, copy=True)
BLhgt_ob2_sm, BLhgt_ob2_sm_range = BLhgtFiltSmooth(BLhgt_ob2, window=7)
BLhgt_ob2_sm = np.array(BLhgt_ob2_sm, copy=True)
BLhgt_ob2_sm_range = np.array(BLhgt_ob2_sm_range, copy=True)

sunup_min = (sunup - base_time)/60.
sundown_min = (sundown - base_time)/60.
#%%
# Deal with files that may be less than 24 hours long
if x[-1] > sunup_min: # if there are enough data to care about cutting the overnight terms off
    cut_start = np.where(x > sunup_min)[0][0] 
    if sundown_min < 1410.: # 23:30 Z
        search_term = np.where(x > sundown_min)
        if len(search_term[0])<1: #the file ends before sunset and before 2359
            cut_end = len(x)
        else:
            cut_end = np.where(x > sundown_min)[0][0]+1
    else: #if sundown is inbetween 23:30 and 00Z
        cut_end = len(x)-1
    if cut_end < cut_start: #sunset is after 0
        BLhgt_om2_sm[cut_start:]=np.nan 
        BLhgt_om2_sm_range[cut_start:]=np.nan
        BLhgt_ob2_sm[cut_start:]=np.nan
        BLhgt_ob2_sm_range[cut_start:]=np.nan
        BLhgt_om2_sm[:cut_end]=np.nan 
        BLhgt_om2_sm_range[:cut_end]=np.nan
        BLhgt_ob2_sm[:cut_end]=np.nan
        BLhgt_ob2_sm_range[:cut_end]=np.nan
    else:
        BLhgt_om2_sm[cut_start:cut_end]=np.nan 
        BLhgt_om2_sm_range[cut_start:cut_end]=np.nan
        BLhgt_ob2_sm[cut_start:cut_end]=np.nan
        BLhgt_ob2_sm_range[cut_start:cut_end]=np.nan

# Output BL_hgt time in epoch seconds (base_time from runner = period start if multi-day).
if not isinstance(base_time, (int, float)):
    base_time = datetime(int(str(Case)[0:4]), 
                         int(str(Case)[4:6]), 
                         int(str(Case)[6:8])).replace(tzinfo=timezone.utc).timestamp()
base_time_vec = base_time + (x * 60.0)


  

 #%%   
if plot_me == True:
    #########################################################
    # Plot second generation aggregrate
    #########################################################
    plt.figure(figsize=(18,6))
    plt.pcolormesh(x,y,sum_fuzz_2.transpose(),vmin=0,vmax=1,cmap='inferno')
    plt.plot(x,BLhgt_2,marker='o',ls='none',color='skyblue',markeredgecolor='navy',zorder=1000,alpha=.5)
    plt.plot(x,BLhgt_2_sm,color='navy',lw=5)
    plt.plot(x,BLhgt_2_sm,color='skyblue',lw=3,label='2nd gen')
    plt.plot(x,BLhgt,marker='o',ls='none', color='lightpink',markeredgecolor='purple',zorder=1000,alpha=.5)
    plt.plot(x,BLhgt_sm,color='purple',lw=5)
    plt.plot(x,BLhgt_sm,color='lightpink',lw=3,label='1st gen')
    plt.colorbar(label='Aggregrate 2nd Gen')
    plt.ylim(0.06,2.75)
    plt.xticks(np.arange(0,1440.1,180),x_tick_labels)
    plt.xlim(0.0,1440.1)
    plt.xlabel('Hour [UTC]')
    plt.ylabel(' Height AGL [km]')
    plt.title(str(platform)+' '+str(date_label))
    plt.legend()
    if show_me == True:
        plt.show()
    else:
        plt.savefig(path_to_plots+date_label+'_SecondGenAg_'+platform+'.png')
        plt.close()

print('Second Gen. Fuzzy Complete')    
if write_me==True:  
    hourly_t = x[np.where(x%60==0)]*60. #units of seconds, hourly on the hour
    hourly_t = np.insert(hourly_t, 0, 0., axis=0) #0 dosent work because we started at 10 so... 
    hourly_epoch = base_time_vec[np.where(x%60==0)]
    hourly_epoch = np.insert(hourly_epoch,0,base_time_vec[0])
    hourly_pblh = BLhgt_2_sm[np.where(x%60==0)]
    hourly_pblh = np.insert(hourly_pblh, 0, BLhgt_2_sm[0], axis=0)
    hourly_pblh_std = BLhgt_2_sm_range[np.where(x%60==0)]
    hourly_pblh_std = np.insert(hourly_pblh_std, 0, BLhgt_2_sm_range[0], axis=0)
    hourly_pblh_om = BLhgt_om2_sm[np.where(x%60==0)]
    hourly_pblh_om = np.insert(hourly_pblh_om, 0, BLhgt_om2_sm[0], axis=0)
    hourly_pblh_ob = BLhgt_ob2_sm[np.where(x%60==0)]
    hourly_pblh_ob = np.insert(hourly_pblh_ob, 0, BLhgt_ob2_sm[0], axis=0)
    
    ten_t = x*60. #units of seconds, 10 min data
    ten_epoch = base_time_vec
    ten_pblh = BLhgt_2_sm
    ten_pblh_std = BLhgt_2_sm_range
    ten_pblh_om = BLhgt_om2_sm
    ten_pblh_ob = BLhgt_ob2_sm
    
    # create output file nc4.Dataset(name, write mode, clear if it exists, file format)
    output_file = nc.Dataset(path_to_write+date_label+'_'+platform+'fuzzyPBLh.nc', 'w', clobber=True, format='NETCDF3_64BIT')
    
    
    # global attributes
    output_file.title = 'CLAMPS Multi-Instrument Fuzzy Logic Estimated PBL Heights'
    output_file.author = author_list
    output_file.contact = contact_list
    output_file.reference = 'coming soon... contact for more info'
    output_file.campaign = campaign
    output_file.basetime = str(base_time)
    output_file.platform = platform
    output_file.latitude = sun_lat
    output_file.longitude = sun_lon
    
    
    
    # define dimensions       (name,value)
    output_file.createDimension('t', len(x)) #time dimension, 10min
    output_file.createDimension('t_1hr', len(hourly_t)) #time dimension, 10min
    
    #ten min output
    # create a variable file.createVariable(name, precision, dimensions) = values (usually some array)    
    output_file.createVariable('t','f8',('t'))[:] = ten_t
    # set attributes of variable file.variables[name], name, value)
    setattr(output_file.variables['t'],'units','seconds since 00Z UTC/basetime')
    setattr(output_file.variables['t'],'description','time axis for 10-minute data')
    
    output_file.createVariable('t_epoch','f8',('t'))[:] = ten_epoch
    setattr(output_file.variables['t_epoch'],'units','second epoch time (since 00UTC on 1/1/1970)')
    setattr(output_file.variables['t_epoch'],'description','time axis for 10-minute data in epoch seconds')
            
    output_file.createVariable('pblh','f4',('t'))[:] = ten_pblh
    setattr(output_file.variables['pblh'],'units','km a.g.l.')
    setattr(output_file.variables['pblh'],'description','PBL height as estimated every 10min by fuzzy logic from CLAMPS')
    
    output_file.createVariable('stdev','f4',('t'))[:] = ten_pblh_std
    setattr(output_file.variables['stdev'],'units','km')
    setattr(output_file.variables['stdev'],'description','standard deviation of all PBL estimates in hour-wide triangle rolling window')
    
    output_file.createVariable('pblh_mech','f4',('t'))[:] = ten_pblh_om
    setattr(output_file.variables['pblh_mech'],'units','km a.g.l.')
    setattr(output_file.variables['pblh_mech'],'description','PBL height including only "mechanical" terms" from lidar')
    
    output_file.createVariable('pblh_therm','f4',('t'))[:] = ten_pblh_ob
    setattr(output_file.variables['pblh_therm'],'units','km a.g.l.')
    setattr(output_file.variables['pblh_therm'],'description','PBL height including only "thermal" terms" from thermo retrievals')
    
    
    
    # hourly output
    output_file.createVariable('t_1hr','f8',('t_1hr'))[:] = hourly_t
    setattr(output_file.variables['t_1hr'],'units','seconds since 00Z UTC/basetime')
    setattr(output_file.variables['t_1hr'],'description','time axis for 1-hour data')
    
    output_file.createVariable('t_1hr_epoch','f8',('t_1hr'))[:] = hourly_epoch
    setattr(output_file.variables['t_1hr_epoch'],'units','second epoch time (since 00UTC on 1/1/1970)')
    setattr(output_file.variables['t_1hr_epoch'],'description','time axis for 1-hour data in epoch seconds')
    
    output_file.createVariable('pblh_1hr','f4',('t_1hr'))[:] = hourly_pblh
    setattr(output_file.variables['pblh_1hr'],'units','km a.g.l.')
    setattr(output_file.variables['pblh_1hr'],'description','PBL height as estimated hourly by fuzzy logic from CLAMPS')
    
    output_file.createVariable('stdev_1hr','f4',('t_1hr'))[:] = hourly_pblh_std
    setattr(output_file.variables['stdev_1hr'],'units','km')
    setattr(output_file.variables['stdev_1hr'],'description','standard deviation of all PBL estimates in hourly averaging window')
    
    output_file.createVariable('pblh_1hr_mech','f4',('t_1hr'))[:] = hourly_pblh_om
    setattr(output_file.variables['pblh_1hr_mech'],'units','km a.g.l.')
    setattr(output_file.variables['pblh_1hr_mech'],'description','PBL height including only "mechanical" terms" from lidar')
    
    output_file.createVariable('pblh_1hr_therm','f4',('t_1hr'))[:] = hourly_pblh_ob
    setattr(output_file.variables['pblh_1hr_therm'],'units','km a.g.l.')
    setattr(output_file.variables['pblh_1hr_therm'],'description','PBL height including only "thermal" terms" from thermo retrievals')
    
    # close it up
    output_file.close()
    print("File written: "+str(path_to_write+date_label+'_'+campaign+'_'+platform+'_fuzzyPBLh.nc'))
