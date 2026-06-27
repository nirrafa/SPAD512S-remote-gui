#!/usr/bin/env python

import sys
import socket
import time
import numpy as np
import matplotlib.pyplot as plt

# open the device on the localhost, port 9999
t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
t.connect(('127.0.0.1', 9998))
intBitDepths = np.array([6,7,8,9,10,11,12])
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
    (in ms)
bitDepth : int
    Defines the bit depth of the generated images.
    Valid values are 6,7,8,9,10,11,12.
im_width : int
    Valid values are 4, 8, 16, 32, 64 , 128, 256, 512

Returns
-------
img : float array
    Arrays (size 512x512xiterations) of  photon counts in each 
    individual SPAD pixel.

'''

iterations = 5
intTime = 10
bitDepth = 8
overlap = 1
timeout = 0
pileup = 0
gate_steps = 10
gate_step_size = 10
gate_step_arbitrary = 0
gate_width = 25
gate_offset = 15
gate_direction = 1
gate_trig = 0
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
command = bytes("G," + str(bitDepth) + "," + str(intTime) + "," + 
                str(iterations) + ","+ str(gate_steps) + ","  + 
                str(gate_step_size)+ "," + str(gate_step_arbitrary) +
                ',' + str(gate_width) + "," + str(gate_offset) + ","+
                str(gate_direction) + ","  + str(gate_trig)+ "," +
                str(overlap) + ","+ str(1),  " utf8 ")
t.send(command)
data = bytearray()
img = np.empty([512,im_width,iterations*gate_steps])

if pileup:
    while 1:
        datablock = t.recv(32768) # error
        data.extend(datablock)
        if data[-4:] == bytearray("DONE", 'utf8'):
            break
    data = data[:-4]
    img_index = 0
    for i in range(iterations*gate_steps):
        img_index_old = img_index
        img_index = (i+1)*512*im_width*2
        if img_index - img_index_old > 10:
            np_data = np.asarray(data[img_index_old:img_index])
            array_262144_even = np_data[::2].astype(np.uint32)
            array_262144_odd = np_data[1::2].astype(np.uint32)
            # new_array = (array_262144_odd.astype(np.uint32) * (2 ** (bitDepth - 8))) + (array_262144_even.astype(np.uint32) >> (16 - bitDepth))
            new_array = (array_262144_odd.astype(np.uint32) * (2**8)) + (array_262144_even.astype(np.uint32))
            img[:,:,i] = new_array.reshape((512, 512))                    
        
else :
    while 1:
        datablock = t.recv(32768)
        data.extend(datablock)
        if data[-4:] == bytearray("DONE", 'utf8'):
            break
    data = data[:-4]
    img_index = 0
    if bitDepth < 9:
        for i in range(iterations*gate_steps):
            img_index_old = img_index
            img_index = (i+1)*512*im_width
            if img_index - img_index_old > 10:
                np_data = np.asarray(data[img_index_old:img_index])
                img[:,:,i] = np.reshape(np_data,[512,im_width])
                # img[:,:,i] = img[:,:,i].astype(int) >> (8-bitDepth)
    else:
        for i in range(iterations*gate_steps):
            img_index_old = img_index
            img_index = (i+1)*512*im_width*2
            if img_index - img_index_old > 10:
                np_data = np.asarray(data[img_index_old:img_index])
                array_262144_even = np_data[::2].astype(np.uint32)
                array_262144_odd = np_data[1::2].astype(np.uint32)
                # new_array = (array_262144_odd.astype(np.uint32) * (2 ** (bitDepth - 8))) + (array_262144_even.astype(np.uint32) >> (16 - bitDepth))
                new_array = (array_262144_odd.astype(np.uint32) * (2**8)) + (array_262144_even.astype(np.uint32))
                img[:,:,i] = new_array.reshape((512, 512))





# Plot one of the image
plt.imshow(img[:,:,0], cmap='gray')  
plt.colorbar()  
plt.title("One gated image")
plt.show()









