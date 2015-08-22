#  Copyright CERFACS (http://cerfacs.fr/)
#  Apache License, Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0)
#
#  Author: Natalia Tatarinova


import numpy
numpy.set_printoptions(threshold=numpy.nan)
from datetime import datetime
from collections import OrderedDict, defaultdict
from time import time
import calendar
from netcdftime import utime

#import util.callback as callback

import ctypes
from numpy.ctypeslib import ndpointer
import os
my_rep = os.path.dirname(os.path.abspath(__file__)) + os.sep
libraryC = ctypes.cdll.LoadLibrary(my_rep+'libC.so')

## BUG: Segmentation fault (core dumped)
## https://bugzilla.redhat.com/show_bug.cgi?id=674206#c5 ----> comment 4
#libraryC.malloc.restype = ctypes.c_void_p
#libraryC.malloc.argtypes = [ctypes.c_size_t]
#memarr = libraryC.malloc(1024)
#libraryC.free(memarr)

############### utility functions: begin ################## 



def get_dict_caldays(dt_arr):
    '''
    Create a dictionary of calendar days, where keys=months, values=days.
    
    :param dt_arr: time steps vector
    :type dt_arr: numpy.ndarray (1D) of datetime objects
    
    :rtype: dict
    
    '''

    dic = defaultdict(list)

    for dt in dt_arr:
        dic[dt.month].append(dt.day)

    for key in dic.keys():
        dic[key] = list(set(dic[key])) 
    
    return dic



    
def get_masked(current_date, month, day, hour, window_width, only_leap_years, ignore_Feb29th=False): 

    '''
    Returns "True" if "current_date" is not in the window centered on the given calendar day (month-day).
    Returns "False", if it enters in the window.
    
    :param current_date: current date
    :type current_date: datetime object 
    :param month: month of the corresponding calendar day
    :type month: int
    :param day: day of the corresponding calendar day
    :type day: int
    :param hour: hour of the current day
    :type hour int
    :param window_width: window width, must be odd
    :type window_width: int
    :param only_leap_years: option for February 29th 
    :type only_leap_years: bool

    :rtype: bool (if True, the date will be masked)
    
    '''
    
    yyyy = current_date.year
    

    if (day==29 and month==02):
        if calendar.isleap(yyyy):
            dt1 = datetime(yyyy,month,day,hour)
            diff = abs(current_date-dt1).days
            toReturn = diff > window_width/2
        else:
            if only_leap_years:
                toReturn=True
            else:                
                dt1 = datetime(yyyy,02,28,hour)
                diff = (current_date-dt1).days
                toReturn = (diff < (-(window_width/2) + 1)) or (diff > window_width/2)
    else:
        
        
        
        d1 = datetime(yyyy,month,day, hour)
        
        # In the case the current date is in December and calendar day (day-month) is at the beginning of year.
        # For example we are looking for dates around January 2nd, and the current date is 31 Dec 1999,
        # we will compare it with 02 Jan 2000 (1999 + 1)
        d2 = datetime(yyyy+1,month,day, hour)
        
        # In the case the current date is in January and calendar day (day-month) is at the end of year.
        # For example we are looking for dates around December 31st, and the current date is 02 Jan 2003,
        # we will compare it with 01 Jan 2002 (2003 - 1) 
        d3 = datetime(yyyy-1,month,day, hour)
        
        
        
        diff=min(abs(current_date-d1).days,abs(current_date-d2).days,abs(current_date-d3).days)    

        if ignore_Feb29th==True and calendar.isleap(yyyy) and (   abs((current_date-datetime(yyyy,02,29,hour)).days) < window_width/2 ):

            diff =  diff -1
            
            
            
        toReturn = diff > window_width/2
        
    return toReturn


def get_mask_dt_arr(dt_arr, month, day, dt_hour, window_width, only_leap_years, ignore_Feb29th=False):
    '''
    Creates a binary mask for a datetime vector for a given calendar day (month-day).
    
    :param dt_arr: time steps vector
    :type dt_arr: numpy.ndarray (1D) of datetime objects
    :param month: month of a calendar day
    :type month: int
    :param day: day of a calendar day
    :type day: int
    :param window_width: window width, must be odd
    :type window_width: int
    :param only_leap_years: option for February 29th 
    :type only_leap_years: bool
    
    :param window_width: window width, must be odd
    :type window_width: int
    
    rtype: numpy.ndarray (1D)   
    ''' 
    mask = numpy.array([get_masked(dt, month, day, dt_hour, window_width, only_leap_years, ignore_Feb29th) for dt in dt_arr])
    return mask


def get_year_list(dt_arr):
    '''
    Just to get a list of all years conteining in time steps vector (dt_arr).
    '''

    year_list = []
    for dt in dt_arr:
        year_list.append(dt.year)
        
    year_list = list(set(year_list))
    
    return year_list

def get_masked_arr(arr, fill_val):
    '''
    If a masked array is passed, this function does nothing.
    If a filled array is passed (fill_value must be passed also), it will be transformed into a masked array.
    
    '''
    if isinstance(arr, numpy.ma.MaskedArray):               # numpy.ma.MaskedArray
        masked_arr = arr
    else:                                                   # numpy.ndarray
        if (fill_val==None):
            raise(ValueError('If input array is not a masked array, a "fill_value" must be provided.'))
        mask_arr = (arr==fill_val)
        masked_arr = numpy.ma.masked_array(arr, mask=mask_arr, fill_value=fill_val)
    
    return masked_arr

############### utility functions: end ##################

def get_percentile_dict(arr, dt_arr, percentile, window_width, only_leap_years=False, callback=None, callback_percentage_start_value=0, 
                        callback_percentage_total=100, chunk_counter=1, precipitation=False, fill_val=None,
                        ignore_Feb29th=False, interpolation="hyndman_fan"):
    '''
    Creates a dictionary with keys=calendar day (month,day) and values=numpy.ndarray (2D)
    Example - to get the 2D percentile array corresponding to the 15th Mai: percentile_dict[5,15]
    
    :param arr: array of values (in case of precipitation, units must be `mm/s`)
    :type arr: numpy.ndarray (3D) or numpy.ma.MaskedArray (3D) of float
    
    :param dt_arr: corresponding time steps vector (base period: usually 1961-1990)
    :type dt_arr: numpy.ndarray (1D) of datetime objects
    
    :param percentile: percentile to compute which must be between 0 and 100 inclusive
    :type percentile: int
    
    :param window_width: window width, must be odd
    :type window_width: int
    
    :param only_leap_years: option for February 29th (default: False)
    :type only_leap_years: bool
    
    :param callback: progress bar, if ``None`` progress bar will not be printed
    :type callback: :func:`callback.defaultCallback2`
    
    :param callback_percentage_start_value: init value for percentage of progress bar (default: 0)
    :type callback_percentage_start_value: int
    
    :param callback_percentage_total: final value for percentage of progress bar (default: 100)   
    :type callback_percentage_total: int
        
    :param chunk_counter: chunk counter in case of chunking 
    :type chunk_counter: int
    
    :param precipitation: just to inticate if ``arr`` is precipitation (`True`) or other variable (`False`) to process data differently (default: False) 
    :type precipitation: bool
    
    :param fill_val: fill value of ``arr``
    :type fill_val: float
    
    :rtype: dict

    .. warning:: If "arr" is a masked array, the parameter "fill_val" is ignored, because it has no sense in this case.
    
    '''
    
    assert(arr.ndim == 3)
    assert(arr.shape[0]==dt_arr.shape[0])
    
    # for callback print
    nb_months = 12*1.0
    percent_one_month = ((callback_percentage_total)/nb_months) ######## callback_percentage_total default value = 100 %; set callback_percentage_total=50% for WPS: computing percentiles will be 50%  (other 50% for computing indice)
    
    percent_current_month = callback_percentage_start_value + (chunk_counter-1)*callback_percentage_total

    
#     # February 29th
#     if ignore_Feb29th == True:
#         mask_Feb29th = numpy.array([ (dt.month==2 and dt.day==29) for dt in dt_arr])
#         indices_masked_Feb29th = numpy.where(mask_Feb29th==False)
#         dt_arr = dt_arr[indices_masked_Feb29th]
#         arr = arr[indices_masked_Feb29th,:,:].squeeze()
 
        
        
    # step1: creation of the dictionary with all calendar days:
    dic_caldays = get_dict_caldays(dt_arr)
    
    percentile_dict = OrderedDict()
    
    dt_hour = dt_arr[0].hour # (we get hour of a date only one time, because usually the hour is the same for all dates in input dt_arr)
    
    # we mask our array in case it has fill_values
    arr_masked = get_masked_arr(arr, fill_val)
    
    fill_val = arr_masked.fill_value
    
            
    if precipitation == True:

        arr_masked = arr_masked*60*60*24 # mm/s --> mm/day

#         print "arr: "
#          
#         print arr_masked[0:10, :, :]
 
         
        # 2) we need to process only wet days (i.e. days with RR >= 1 mm)
        # so, we mask values < 1 mm 
        mask_arr_masked = arr_masked < 1.0 # new mask of already masked array 
        arr_masked_masked = numpy.ma.array(arr_masked, mask=mask_arr_masked)
         
#         print "arr masked thresh=1mm:"
#         print arr_masked_masked[0:10, :, :]
#         print arr_masked_masked.fill_value
       
 
         
        # 3) we fill all masked values with fill_val to pass the filled array to the C function
        arr_filled = arr_masked_masked.filled(fill_val)
#         print "arr filled with fill_value:"
#         print arr_filled[0:10, :, :]
         
 
         
        del arr_masked, mask_arr_masked, arr_masked_masked
        
    else:
        arr_filled = arr_masked.filled(fill_val)
        del arr_masked
          

    ############################## prepare calling C function   
    # data type should be 'float32' to pass it to C function
    if arr_filled.dtype != 'float32':
        arr_filled = numpy.array(arr_filled, dtype='float32')
        
        
    C_percentile = libraryC.percentile_3d
    C_percentile.restype = None    
    
    C_percentile.argtypes = [ndpointer(ctypes.c_float),
                                        ctypes.c_int,
                                        ctypes.c_int,
                                        ctypes.c_int,
                                        ndpointer(ctypes.c_double),
                                        ctypes.c_int,
                                        ctypes.c_float,
                                        ctypes.c_char_p]
                                                
    
    
    ## we check the fill_value (we need it to be the maximum value in the array)
        
    if fill_val == arr_filled.max():
        pass
    else:
        fill_val_new = 1e+20 
        arr_filled[arr_filled==fill_val] = fill_val_new 
        fill_val = fill_val_new
        
    #############################

    for month in dic_caldays.keys():
        for day in dic_caldays[month]:

            arr_percentille_current_calday = numpy.zeros([arr.shape[1], arr.shape[2]]) # we reserve memory
            
            #print arr_percentille_current_calday.dtype #float64, i.e. double ----> OK
            
            # step2: we do a mask for the datetime vector for current calendar day (day/month)
            dt_arr_mask = get_mask_dt_arr(dt_arr, month, day, dt_hour, window_width, only_leap_years, ignore_Feb29th)
            
#             if month==2 and day==27:
#                 
#                 print dt_arr[dt_arr_mask]
            
            # step3: we are looking for the indices of non-masked dates (i.e. where dt_arr_mask==False) 
            indices_non_masked = numpy.where(dt_arr_mask==False)[0]
             
            # step4: we subset our arr
            #arr_subset = arr_filled[indices_non_masked, :, :].squeeze()
            arr_subset = arr_filled[indices_non_masked, :, :]
            
            
#             arr_subset = numpy.random.randint(1,10, (50,2,2))
#             arr_subset[arr_subset>6]=fill_val
# #             print arr_subset
# #             fill_val=999999
#             if arr_subset.dtype != 'float32':
#                     arr_subset = numpy.array(arr_subset, dtype='float32')
            
#             print fill_val.dtype
            
            # step5: we compute the percentile for current arr_subset           
            C_percentile(arr_subset, arr_subset.shape[0], arr_subset.shape[1], arr_subset.shape[2], arr_percentille_current_calday, percentile, fill_val, interpolation)
            arr_percentille_current_calday = arr_percentille_current_calday.reshape(arr.shape[1], arr.shape[2])
#             print month, day, arr_percentille_current_calday[0:5, 0:5]
            
            
#             import sys
#             sys.exit()

            # step6: we add to the dictionnary...
            percentile_dict[month,day] = arr_percentille_current_calday

        
        if callback != None:
            percent_current_month =  percent_current_month + percent_one_month
            callback(percent_current_month)
        
#     import sys
#     sys.exit()
        
    return percentile_dict





