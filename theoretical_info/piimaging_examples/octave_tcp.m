% load the instrument control package
pkg load instrument-control

% open the device on the localhost, port 9998
t = tcpclient('localhost',9999);
fopen(t)

% read the server response
bytesav   = get(t, 'bytesavailable');
msg       = fread(t, bytesav);
msgstr    = native2unicode(msg)

%% set the fans to full speed
fwrite(t, ['S,2\n' ]);
pause(0.1)

% read if successful
bytesav = 0;
while bytesav == 0
  pause(0.1)
  bytesav   = get(t, 'bytesavailable');
end
msg       = fread(t, bytesav);
msgstr    = native2unicode(msg) % print the paths to the files for further processing

%% create 8-bit intensity images of 15 ms and for 20 frames without overlap and saving the data to disk, no external frame triggering, no sparse mode in non 1-bit imaging
fwrite(t, ['I,8,15,20,0,0,0,0\n' ]);
pause(0.1)

% read if successful
bytesav = 0;
while bytesav == 0
  pause(0.1)
  bytesav   = get(t, 'bytesavailable');
end
msg       = fread(t, bytesav);
msgstr    = native2unicode(msg) % print the paths to the files for further processing

% load the data from the path and process the images
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% do an 8-bit gated measurement and wait for it to finish, there are 60 gate steps, each gate step is exposed for 2ms, shifted by 360ps, with a width of 6 = 6ns, the initial offset is 180ps, the gate direction is 1 (incrementing), we are not using the external frame or gate trigger, overlapping is enabled, saving data to disk
fwrite(t, ['G,8,2,1,60,360,0,6,180,1,0,1,0\n' ]);
pause(0.1)

% read if successful
bytesav   = get(t, 'bytesavailable');
while bytesav == 0
  pause(0.1)
  bytesav   = get(t, 'bytesavailable');
end
msg       = fread(t, bytesav);
msgstr    = native2unicode(msg) % print the paths to the files for further processing

% load the data from the path and process the images
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% calibrate the system for mono-exponential FLIM measurements, the exposure time is 6.2 ms, the expected lifetime is 1.8 ns and the gate width is set to short
fwrite(t, ['F,c,0,6.2,1.8,0\n' ]);
pause(0.1)

% read if successful
bytesav   = get(t, 'bytesavailable');
while bytesav == 0
  pause(0.1)
  bytesav   = get(t, 'bytesavailable');
end
msg       = fread(t, bytesav);
msgstr    = native2unicode(msg) % print that the calibration is completed

%% do a standard FLIM measurement and wait for the graphs to be displayed, the integration time is changed to 12 ms and the optimal gate steps are divided by 10 to reduce the acquisition and processing time, we are saving the images by setting the 0 flag
fwrite(t, ['F,i,12,10,0\n' ]);
pause(0.1)

% read if successful
bytesav   = get(t, 'bytesavailable');
while bytesav == 0
  pause(0.1)
  bytesav   = get(t, 'bytesavailable');
end
msg       = fread(t, bytesav);
msgstr    = native2unicode(msg) % print the paths to the files for further processing

% load the data from the path and process the images
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

fclose(t)