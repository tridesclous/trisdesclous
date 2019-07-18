from tridesclous import get_dataset
from tridesclous.peakdetector import peakdetector_engines

import time
import itertools

import scipy.signal
import numpy as np
import sklearn.metrics.pairwise

from matplotlib import pyplot

from tridesclous.tests.test_signalpreprocessor import offline_signal_preprocessor

from tridesclous.peakdetector import make_sum_rectified, detect_peaks_in_rectified
from tridesclous.peakdetector import HAVE_PYOPENCL

def offline_peak_detect(normed_sigs, sample_rate, geometry, 
                peak_sign='-',relative_threshold = 5,  peak_span_ms=0.5, adjacency_radius_um=None):
    
    
    n_span = int(sample_rate * peak_span_ms / 1000.)//2
    
    if adjacency_radius_um is None:
        spatial_matrix = None
    else:
        d = sklearn.metrics.pairwise.euclidean_distances(geometry)
        spatial_matrix = np.exp(-d/adjacency_radius_um)
        spatial_matrix[spatial_matrix<0.01] = 0.
    
    sum_rectified = make_sum_rectified(normed_sigs, relative_threshold, peak_sign, spatial_matrix)
    mask_peaks = detect_peaks_in_rectified(sum_rectified, n_span, relative_threshold, peak_sign)
    ind_peaks,  = np.nonzero(mask_peaks)
    ind_peaks += n_span
    
    return ind_peaks, sum_rectified


    

def test_compare_offline_online_engines():
    #~ HAVE_PYOPENCL = True
    #~ if HAVE_PYOPENCL:
        #~ engines = ['numpy', 'opencl']
        #~ engines = [ 'opencl']
        #~ engines = ['numpy']
    #~ else:
        #~ engines = ['numpy']
        
    engines = ['numpy']

    # get sigs
    sigs, sample_rate = get_dataset(name='olfactory_bulb')
    #~ sigs = np.tile(sigs, (1, 20)) #for testing large channels num
    
    nb_channel = sigs.shape[1]
    print('nb_channel', nb_channel)
    
    geometry = np.zeros((nb_channel, 2))
    geometry[:, 0] = np.arange(nb_channel) * 50 # um spacing

    
    
    #params
    chunksize = 1024
    peak_sign = '-'
    relative_threshold = 8
    peak_span_ms = 0.9
    adjacency_radius_um = None
    
    #~ print('n_span', n_span)
    nloop = sigs.shape[0]//chunksize
    sigs = sigs[:chunksize*nloop]
    
    print('sig duration', sigs.shape[0]/sample_rate)
    
    # normalize sigs
    highpass_freq = 300.
    preprocess_params = dict(
                highpass_freq=highpass_freq,
                common_ref_removal=True,
                backward_chunksize=chunksize+chunksize//4,
                output_dtype='float32')
    normed_sigs = offline_signal_preprocessor(sigs, sample_rate, **preprocess_params)
    
    
    
    #~ for peak_sign in ['-', '+', ]:
    for peak_sign, adjacency_radius_um in itertools.product(['-', '+'], [None, 100]):
    #~ for peak_sign in ['+', ]:
    #~ for peak_sign in ['-', ]:
        print()
        print('peak_sign', peak_sign, 'adjacency_radius_um', adjacency_radius_um)
        if peak_sign=='-':
            sigs = normed_sigs
        elif peak_sign=='+':
            sigs = -normed_sigs
        
        #~ print(sigs.shape)
        #~ print('nloop', nloop)
        
        
        t1 = time.perf_counter()
        offline_peaks, rectified_sum = offline_peak_detect(sigs, sample_rate, geometry, 
                                        peak_sign=peak_sign, relative_threshold=relative_threshold, peak_span_ms=peak_span_ms, 
                                        adjacency_radius_um=adjacency_radius_um)
        t2 = time.perf_counter()
        print('offline', 'process time', t2-t1)
        #~ print(offline_peaks)
        
        online_peaks = {}
        for engine in engines:
            print(engine)
            EngineClass = peakdetector_engines[engine]
            #~ buffer_size = chunksize*4
            peakdetector_engine = EngineClass(sample_rate, nb_channel, chunksize, 'float32', geometry)
            
            peakdetector_engine.change_params(peak_sign=peak_sign, relative_threshold=relative_threshold,
                            peak_span_ms=peak_span_ms, adjacency_radius_um=adjacency_radius_um)
            
            all_online_peaks = []
            t1 = time.perf_counter()
            for i in range(nloop):
                #~ print(i)
                pos = (i+1)*chunksize
                chunk = sigs[pos-chunksize:pos,:]
                n_peaks, chunk_peaks = peakdetector_engine.process_data(pos, chunk)
                #~ print(n_peaks)
                if chunk_peaks is not None:
                    #~ all_online_peaks.append(chunk_peaks['index'])
                    all_online_peaks.append(chunk_peaks)
            online_peaks[engine] = np.concatenate(all_online_peaks)
            t2 = time.perf_counter()
            print(engine, 'process time', t2-t1)
        
        # remove peaks on border for comparison
        offline_peaks = offline_peaks[(offline_peaks>chunksize) & (offline_peaks<sigs.shape[0]-chunksize)]
        for engine in engines:
            onlinepeaks = online_peaks[engine]
            onlinepeaks = onlinepeaks[(onlinepeaks>chunksize) & (onlinepeaks<sigs.shape[0]-chunksize)]
            online_peaks[engine] = onlinepeaks

        # compare
        for engine in engines:
            onlinepeaks = online_peaks[engine]
            assert offline_peaks.size==onlinepeaks.size, '{} nb_peak{} instead {}'.format(engine,  offline_peaks.size, onlinepeaks.size)
            assert np.array_equal(offline_peaks, onlinepeaks)
    
        # plot
        #~ fig, axs = pyplot.subplots(nrows=nb_channel, sharex=True)
        #~ for i in range(nb_channel):
            #~ axs[i].plot(sigs[:, i])
            #~ axs[i].plot(offline_peaks, sigs[offline_peaks, i], ls = 'None', marker = 'o', color='g', markersize=12)
            #~ for engine in engines:
                #~ onlinepeaks = online_peaks[engine]
                #~ axs[i].plot(onlinepeaks, sigs[onlinepeaks, i], ls = 'None', marker = 'o', color='r', markersize=6)
        
        #~ fig, ax = pyplot.subplots()
        #~ ax.plot(rectified_sum)
        #~ ax.plot(offline_peaks, rectified_sum[offline_peaks], ls = 'None', marker = 'o', color='g', markersize=12)
        #~ for engine in engines:
            #~ onlinepeaks = online_peaks[engine]
            #~ ax.plot(onlinepeaks, rectified_sum[onlinepeaks], ls = 'None', marker = 'o', color='r', markersize=6)
        
        #~ for i in range(nloop):
            #~ ax.axvline(i*chunksize, color='k', alpha=0.4)
        
        #~ pyplot.show()
    
    

    
if __name__ == '__main__':
    test_compare_offline_online_engines()