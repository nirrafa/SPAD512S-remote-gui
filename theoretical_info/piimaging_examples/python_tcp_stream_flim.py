#!/usr/bin/env python

import sys
import socket
import time
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt

# open the device on the localhost, port XXXX
t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
t.connect(('127.0.0.1', 9998))

# read the server response
data = t.recv(8192)
print(data.decode('utf8'))

# Settings calibration
expected_lifetime = 5 # in ns
gate_width = 15 # in ns

# Settings measurement
nr_images = 1
measurement_time = 12 # time in ms
gate_subsampling = 10

# Calibration 
command = bytes("F,c," + str(0) + "," + str(1) + ",5,1" + '\n', "utf8")
t.send(command)
msg = t.recv(8192)
print(msg)


if msg != b"Cannot find the IRF for the FLIM calibration. ERROR":
    
    start = time.time()
    # make a FLIM image and retrieve the raw data
    command = bytes("F,i," + str(measurement_time) + "," + str(gate_subsampling) + "," + str(5) +",1" + '\n', "utf8")
    t.send(command)
    
    datastr = ""
    # look for the response
    while 1:
        data = t.recv(32768) # try different buffer sizes
        datastr += data.decode('utf8')
        
        if data[-4:] == bytearray("DONE", 'utf8'):
            
            print("Process complete")
            break
            
        elif data[-5:] == bytearray("ERROR", 'utf8'):
            
            print(data[-160:])
            print("Completed the run with errors")
            quit()
    
    # close communication channel, get read time
    t.close()
    read = time.time()
    print("Read time: ", "{:.2f}".format(read - start), " s")
    
    # Découper la chaîne en lignes et retirer la ligne "DONE"
    lines = datastr.strip().split("\n")
    if lines[-1] == "DONE":
        lines = lines[:-1]

    # Extraire les premières valeurs de chaque ligne
    first_values = [int(line.split(",")[0]) for line in lines]

    # Calculer le nombre d'images (n)
    num_frames = len(first_values) // (512 * 512)

    # Générer et afficher chaque image
    for i in range(num_frames):
        start_idx = i * 512 * 512
        end_idx = start_idx + 512 * 512
        frame_values = first_values[start_idx:end_idx]

        # Convertir les valeurs en une matrice 512x512
        image_array = np.array(frame_values).reshape(512, 512)

        # Afficher l'image
        plt.figure()
        plt.imshow(image_array, cmap="gray")
        plt.title(f"Frame {i + 1}")
        plt.axis("off")  # Désactiver les axes pour une meilleure visibilité
        plt.show()
