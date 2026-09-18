# metadataVerification
Metadata verification scripts for OOI RCA. 

---------------
### environments
Two, because the OOI raw-file parsers are still python 2.

Everything in this repo runs in `verification`:

```
conda env create -f verification.yml
conda activate verification
```

`mi-racle` reads serial numbers out of binary raw files (ADCP/VADCP/OPTAA). You never
activate it -- the scripts call into it on their own -- but it has to exist, and conda
has to be on your PATH. Build it once:

```
CONDA_SUBDIR=osx-64 conda env create -f mi.yml
conda activate mi-racle
pip install -r ~/repos/mi-instrument/requirements.txt
pip install -e ~/repos/mi-instrument
pip install -e ~/repos/ooi_port_agent
```

`CONDA_SUBDIR=osx-64` is required -- python 2.7 is only available for that platform now.
A few things to fix as you install mi-instrument:

* unpin twisted in the mi-instrument repo
* requirements.txt has a single `=` in the ion-functions repo
* use `pygsw==0.0.10`, not `pygsw==0.0.11`
* make sure only one numpy ends up installed

If an old environment throws a numpy import error, rebuild it from the yml rather than
trying to repair it.

-----------
### create rawfileSN_YYYYMMDD and enter new instruments
Make sure your local asset management repo is synced with the OOI remote, then run
`assetManagement/scripts/extract_raw_sn.py` (this replaces ExtractRawArchiveSerialNumbers.ipynb,
which is kept for reference and does the same thing).

```
cd assetManagement/scripts
./extract_raw_sn.py --dry-run     # work list only, no archive crawl
./extract_raw_sn.py
```

Each year's output is the next year's input: `--input` defaults to the newest
`params/rawFileSN_*.csv`, so only deployments that have not already been resolved get crawled.
Useful flags: `--refdes` and `--year` to re-run a single instrument that failed, `--am-repo` to
point at a clone other than `~/repos/asset-management`. Results are written as each reference
designator finishes, so a run that dies partway through keeps what it did resolve.

The console shows progress only. A `rawFileSN_YYYYMMDD.log` is written next to the output csv
with the full detail -- every archive folder searched and every serial number extraction --
which is what you want when a HITL question comes up months later.

Update the `param/RCA-InstrumentList.csv` in your local assetManagement repo with any new deployments for the current year. 
These can be found in `ooi/asset-management/bulk/sensor_bulk_load-AssetRecord.csv`

Note that an `assetID` there is a *slot*, not one physical instrument: a single assetID accumulates
comma-separated `mfgSN` values as instruments are swapped into it over the years. So a year's update
can mean adding a new assetID *or* appending a serial number to an existing one. The
`missingFromRCAlist` and `mismatch` sections of `reportOuts/sensorBulkVerification_*.txt` are what
flag each case.

-----------
### matching manufacturer serial numbers to image serial numbers
After serial numbers are extracted from the raw files we also need to match manufacturer serial numbers to image serial numbers
from the cruise. And image assetID to master list assetID.

`scripts/draft_image_sn.py` writes `inputs/imageSN_YYYY_draft.csv`, one blank row per deployment
no raw file could verify. `scripts/find_deployment_photos.py` then writes
`inputs/deploymentPhotos_YYYY.yaml`, listing the candidate cruise photos for each of those
instruments on the Data0 share, along with the assetID and serial number the deployment sheet
says to expect. Nothing is copied off the share -- open the paths directly.

```
./draft_image_sn.py
./find_deployment_photos.py
```

Fill in `imageFile`, `imageSerialNumber` and `imageAssetID` from the photos, and delete rows for
instruments you do not image-verify. Leave a row blank if the label is not legible; blanks are
carried through and resolved at final review.

The filled-in draft is the input to `fuzzyMatchSNandAssetID.ipynb`, which reads it from `inputs/`
in place -- set `current_year` in that notebook to the year you are working on. Also copy it to
`params/imageSN_YYYY.csv`, which is what `criticalMetaDataVerification.ipynb` reads in the final
step.


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


## REPORT OUT: calibration verification 
This compares what is in OOI asset management github and what is in the originl vender file. For example, 
for a CTD it will go to OOI assett management and the CTD vendor file located on the RCA github and compare
row for row each coefficient and the serial number. These report outs are cumulative 2014-present.

# Adding HITL notes
To add HITL notes, go to 2i_HITL and select either calibrationVerification or deploymentVerification
