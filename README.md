# metadataVerification
Metadata verification scripts for OOI RCA.

Run once a year after the summer cruise, in order, from `assetManagement/scripts`:

| | |
|---|---|
| `extract_raw_sn.py` | mine serial numbers from the raw data archive (~1 hr) |
| `draft_image_sn.py` | list the deployments no raw file could verify |
| `find_deployment_photos.py` | find candidate cruise photos for those instruments |
| `fuzzy_match_sn.py` | match photographed serial numbers to assetIDs |
| `verify_metadata.py` | final verification and report outs |

Each takes `--help`, logs the inputs it resolved before doing any work, and writes a run
log next to its output. The notebooks they replaced are kept for reference.

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

`fuzzy_match_sn.py` reads the filled-in draft from `inputs/` in place. Also copy it to
`params/imageSN_YYYY.csv`, which `verify_metadata.py` reads in the final step.


`fuzzy_match_sn.py` matches these serial numbers, including partial matches. If no matching
serial number is found it attempts to match asset ids from the master list to image asset ids.
Every single-candidate match is also checked against the deployment sheet, and disagreements
are called out as the highest priority finding.

The output `fuzzyMatches_HITL_YYYYMMDD.csv` sometimes contains multiple candidate assetIDs, so
we go through it by hand. Pare **both** `matching_asset_ids` and `matching_mfg_sn` down to a
single value each, keeping the `['...']` bracket form -- the next step strips the brackets and
a multi-value cell strips to garbage.

----------
### final verification
The curated `fuzzyMatches_HITL_YYYYMMDD.csv` is the input to `verify_metadata.py`, which loops
through each deployment for each instrument, checking raw file and image verification status. It
also checks whether instruments require calibration and whether they can be verified via raw
file, which helps prioritise the final HITL step.

```
./verify_metadata.py --dry-run     # confirm which inputs resolved
./verify_metadata.py
./verify_metadata.py --skip-cal    # deployment pass only, skips fetching vendor cal files
```

It picks the newest `rawFileSN_*.csv`, `imageSN_<year>.csv` and `fuzzyMatches_HITL_*.csv` and
prints all three before starting; `--raw-input`, `--image-sn` and `--fuzzy-hitl` override.

**NOTE** By default it reads the github repos, verifying what CI has ingested. Use `--local` for
a pre-cruise check against changes not yet pushed, and make sure your `asset-management` and
`calibrationFiles` clones are up to date with the remotes.

In the final step we manually go through `deploymentVerification_YYYYMMDD.csv` and investigate instances where there is a deployment-raw file 
mismatch (highest priority) and where there is a deployment-image mismatch (high priority). 


## REPORT OUT: calibration verification 
This compares what is in OOI asset management github and what is in the originl vender file. For example, 
for a CTD it will go to OOI assett management and the CTD vendor file located on the RCA github and compare
row for row each coefficient and the serial number. These report outs are cumulative 2014-present.

# Adding HITL notes
To add HITL notes, go to 2i_HITL and select either calibrationVerification or deploymentVerification
