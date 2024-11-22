# metadataVerification
Metadata verification scripts for OOI RCA. 

---------------
### creating a python 2 environment on m2 mac 
https://stackoverflow.com/questions/67380286/anaconda-channel-for-installing-python-2-7

uninstall pip

curl https://bootstrap.pypa.io/pip/2.7/get-pip.py -o get-pip.py

python get-pip.py

### extracting serial numbers from raw data files
In order to verify instrument serial numbers the mi-instrument 
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

-----------
### create rawfileSN_YYYYMMDD and enter new instruments
First you run ExtractRawArchiveSerialNumber.ipynb. Make sure your local asset management repo is synced with the **OOI remote** (not just your personal remote). 

Update the `param/RCA-InstrumentList.csv` in your local assetManagement repo with any new deployments for the current year. 
These can be found in `ooi/asset-management/bulk/sensor_bulk_load-AssetRecord.csv`

-----------
### matching manufacturer serial numbers to image serial numbers
After serial numbers are extracted from the raw files we also need to match manufacturer serial numbers to image serial numbers 
taken on the cruise, and/or image assetIDs to master list assetIDs. To do this, filter `rawFileSN_YYYYMMDD` by current year, and remove
all rows where a serial number was succesfully extracted from a RAW file. The csv structure will be: 
`referenceDesignator,deployYear,imageFile,imageSerialNumber,imageAssetID`

### NOTE 
This is just the initial insturments that were expected to have a raw SN to follow up on for the current, year. You will need to either get 
the final deploymentVerification.csv output to see what other current year instruments need to be verified OR we need to automate this step to produce a list of instruments that
do not output SN in raw data. #TODO. A script that outputs all deployments for the current year that include instruments that do not broadcast their SN.

`fuzzyMatchSNandAssetID.ipynb` contains a script to match these serial numbers - 
including partial matches. If no matching serial number is found the script will attempt to match asset ids from the 
master list/manufacturer serial number csv to image asset ids. This outputs a CSV that sometimes contains multiple assetID
matches. We go through this output csv `fuzzyMatches_HITL_date.csv` by hand to create a HITL curated column of assetID 
matches. NOTE **MAKE SURE TO FILL IN HITL MATCHES in the `matching_asset_ids` column!** 

----------
### final verification
`fuzzyMatches_HITL_data.csv` can now serve as input to the final part of `criticalMetaDataVerification.ipynb` which loops through
each deployment for each instrument, checking raw files verification and image verification status. In 2023 we also added logic to check
if instruments require calibration and if instruments can be verified via raw file. This should help prioritize in the final HITL step.

In the final step we manually go through `deploymentVerification_date.csv` and investigate instances where there is a deployment-raw file 
mismatch (highest priority) and where there is a deployment-image mismatch (high priority). 

----------
### Yearly take-aways
2024 
* repeated errors and typos in physcial PCO2 serial numbers
* DOSTA photos often missing, but these instruments do require cals


