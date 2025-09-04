# metadataVerification
Metadata verification scripts for OOI RCA. 

---------------
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
First you run ExtractRawArchiveSerialNumber.ipynb. Make sure your local asset management repo is synced with the OOI remote.

Update the `param/RCA-InstrumentList.csv` in your local assetManagement repo with any new deployments for the current year. 
These can be found in `ooi/asset-management/bulk/sensor_bulk_load-AssetRecord.csv`

-----------
### matching manufacturer serial numbers to image serial numbers
After serial numbers are extracted from the raw files we also need to match manufacturer serial numbers to image serial numbers 
from the cruise. And image assetID to master list assetID. To do this, filter `rawFileSN_YYYYMMDD` by current year, and remove
all rows where a serial number was succesfully extracted from a RAW file. The csv structure will be: 
`referenceDesignator,deployYear,imageFile,imageSerialNumber,imageAssetID` Save this csv as `imageSN_YYYY_draft.csv` and fill it out 
using images from the most recent cruise. Remember to save your final version as in the `params` directory as `imageSN_YYYY.csv`
It will be the input to `fuzzyMatchSNandAssetID.ipynb`.


`fuzzyMatchSNandAssetID.ipynb` contains a script to match these serial numbers - 
including partial matches. If no matching serial number is found the script will attempt to match asset ids from the 
master list/manufacturer serial number csv to image asset ids. This outputs a CSV that sometimes contains multiple assetID
matches. We go through this output csv `fuzzyMatches_HITL_date.csv` by hand to create a HITL curated column of assetID 
matches. 

----------
### final verification
`fuzzyMatches_HITL_data.csv` can now serve as input to the final part of `criticalMetaDataVerification.ipynb` which loops through
each deployment for each instrument, checking raw files verification and image verification status. In 2023 we also added logic to check
if instruments require calibration and if instruments can be verified via raw file. This should help prioritize in the final HITL step.

**NOTE** If running `criticalMetaDataVerification.ipynb` locally make sure that all your local asset management repos: `deployments`,
`asset-management` and `deployments` are up to date with the remotes.

In the final step we manually go through `deploymentVerification_YYYYMMDD.csv` and investigate instances where there is a deployment-raw file 
mismatch (highest priority) and where there is a deployment-image mismatch (high priority). 
