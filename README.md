# metadataVerification

TODO: create docker image to run `ExtractRawArchiveSerialNumbers.ipynb`

Metadata verification scripts for OOI RCA. In order to verify instrument serial numbers the mi-instrument 
playback function must have a correctly configured python 2.7 env available. This is defined in the mi.yml
file in this repo and was configured in part using these instructions: 

https://github.com/friedrichknuth/ooi_local_processing

Some caveats: 

* unpinned twisted package in mi-instrument repo
* requirements.txt has single = in ion-functions repo
* used pygsw==0.0.10 instead of pygsw==0.0.11
* had to install ooi_port_agent into mi environment 
* has to ensure two version of numpy were not installed and ensure that in the mi env
  * xarray==0.11.3
  * pandas==0.24.2
  * numpy==1.16.5
