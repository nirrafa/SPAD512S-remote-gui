#!/usr/bin/env python

import sys
import socket
import time
import numpy as np
import matplotlib.pyplot as plt

# open the device on the localhost, port 9999
t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
t.connect(('127.0.0.1', 9998))
intBitDepths = np.array([1,4,6,7,8,9,10,11,12])
col = np.array([4,8,16,32,64,128,256,512])

# read the server response
data = t.recv(8192)
print(data.decode('utf8'))

'''


Choose your parameters :
----------
iterations : int
    Defines the number of measurements to repeat and average.
intTime : float
    Defines the integration time for the measurement
    (in ms for 6, 7, 8, 9, 10, 11, 12bits and in us for 1, 4bits).
bitDepth : int
    Defines the bit depth of the generated images.
    Valid values are 1,4,6,7,8,9,10,11,12.
overlap : int
    1 for enabling read/exposure overlap, 0 otherwise
timeout : int
    1 for enabling timeout in the function to redo measurement after measurement failed, 0 otherwise
pileup : int
    1 for pileup corrected values, 0 otherwise
im_width : int
    Valid values are 4, 8, 16, 32, 64 , 128, 256, 512
    

Returns
-------
img : float array
    Arrays (size 512x512xiterations) of  photon counts in each 
    individual SPAD pixel.

'''
iterations = 255
intTime = 10
bitDepth = 8
overlap = 1
timeout = 0
pileup = 0
im_width = 512







command = bytes("PU," + str(pileup), "utf8")
t.send(command)
msg = t.recv(32768)

if not (bitDepth in intBitDepths): 
    print("Chosen bit depth is invalid. Please use one of the following"
          " values: %s.\nDefault value of 8bit is used instead!"
          % intBitDepths)
    bitDepth = 8
if not (im_width in col): 
    print("Chosen image width is invalid. Please use one of the following"
          " values: %s.\nDefault width of 512 is used instead!"
          % col)
    im_width = 512
command = bytes("I," + str(bitDepth) + ","+ str(intTime) + ","  +
                str(iterations) + "," + "0," + str(overlap) + ",0" + ",1", "utf8")
t.send(command)
if timeout:
    t.settimeout(25.0)  # Set a timeout of 5 seconds
else:
    t.settimeout(None)  # Remove the timeout

time.sleep(1)
data = bytearray()
img = np.empty([512,im_width,iterations])
if bitDepth == 1:
    while 1:
        datablock = t.recv(32768) # try different buffer sizes
        data.extend(datablock)

        # we stream binary pixel values, either 0 for no data, or 255 for a 1 (each byte represents one pixel)

        if datablock[-4:] == bytearray("DONE", 'utf8'):

            print("Process complete")
            break

        elif datablock[-5:] == bytearray("ERROR", 'utf8'):

            print(datablock[-160:])
            print("Completed the run with errors")


    # remove DONE from the end of the data
    data = data[:-4]
    for i in range(iterations): 
        img_index_old = i*512*64
        img_index = (i+1)*512*64

        dataint = np.array(data[img_index_old:img_index], dtype = "uint8")
        databit = np.unpackbits(dataint)
        databit = np.rot90(databit.reshape((512, 512)))
        img[:,:,i] = databit
else:
    if pileup:
        while 1:
            datablock = t.recv(32768) 
            data.extend(datablock)
            if data[-4:] == bytearray("DONE", 'utf8'):
                break
        data = data[:-4]
        img_index = 0
        for i in range(iterations):
            img_index_old = img_index
            img_index = (i+1)*512*im_width*2
            if img_index - img_index_old > 10:
                np_data = np.asarray(data[img_index_old:img_index])
                array_262144_even = np_data[::2].astype(np.uint32)
                array_262144_odd = np_data[1::2].astype(np.uint32)
                new_array = (array_262144_odd.astype(np.uint32) * (2**8)) + (array_262144_even.astype(np.uint32))
                img[:,:,i] = new_array.reshape((512, im_width))                    
            
    else :
        while 1:
            datablock = t.recv(32768)
            data.extend(datablock)
            if data[-4:] == bytearray("DONE", 'utf8'):
                break
        data = data[:-4]
        img_index = 0
        if bitDepth < 9:
            for i in range(iterations):
                img_index_old = img_index
                img_index = (i+1)*512*im_width
                if img_index - img_index_old > 10:
                    np_data = np.asarray(data[img_index_old:img_index])
                    img[:,:,i] = np.reshape(np_data,[512,im_width])
        else:
            for i in range(iterations):
                img_index_old = img_index
                img_index = (i+1)*512*im_width*2
                if img_index - img_index_old > 10:
                    np_data = np.asarray(data[img_index_old:img_index])
                    array_262144_even = np_data[::2].astype(np.uint32)
                    array_262144_odd = np_data[1::2].astype(np.uint32)
                    new_array = (array_262144_odd.astype(np.uint32) * (2**8)) + (array_262144_even.astype(np.uint32))
                    img[:,:,i] = new_array.reshape((512, im_width))
                    


mean_img = np.mean(img, axis=2)

# Plot the mean image
plt.imshow(mean_img, cmap='gray')  
plt.colorbar()  
plt.title("Mean Image")
plt.show()




