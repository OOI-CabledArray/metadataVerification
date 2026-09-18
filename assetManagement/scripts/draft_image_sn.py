#!/usr/bin/env python3
"""Start the imageSN draft: this year's deployments that no raw file could verify.

Emits one blank row per deployment still needing an image check. Filling in imageFile,
imageSerialNumber and imageAssetID from the cruise photos is manual -- save the result
as params/imageSN_<year>.csv, which is the input to fuzzyMatchSNandAssetID.ipynb.

\b
  ./draft_image_sn.py
  ./draft_image_sn.py --year 2025 --output /tmp/check.csv

Run this after extract_raw_sn.py, so the raw-file serial numbers are current.
"""

import glob
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
import pandas as pd
from loguru import logger

from deployments import ROOT, isRawCheckSensor, refDesDict

COLUMNS = ["referenceDesignator", "deployYear", "imageFile", "imageSerialNumber",
           "imageAssetID", "notes"]


def setupLogging(logFile):
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")
    logger.add(logFile, level="DEBUG", mode="w",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}")
    return logFile


def newestRawFile():
    dated = sorted(f for f in glob.glob(os.path.join(ROOT, "params", "rawFileSN_2*.csv"))
                   if len(pd.read_csv(f)))
    if not dated:
        raise click.ClickException("no params/rawFileSN_*.csv found, pass --raw-input")
    return dated[-1]


def reportNeeded(needed):
    """List what needs an image check, split by why it needs one.

    An instrument that was mined and came back empty is worth a closer look -- the raw
    file may just be late to the archive. One that is not raw-verifiable at all is the
    routine case and always needs a photo.

    Split on the sensor type rather than on a '-99999' row, so a miss still lands in the
    right group whether it was recorded as the sentinel or left out of the file entirely.
    """
    searched = [key for key in needed if isRawCheckSensor(key)]
    neverMined = [key for key in needed if not isRawCheckSensor(key)]

    if searched:
        logger.warning("\n  mined but no serial number in the archive (%d)" % len(searched))
        logger.warning("  these were searched and came up empty, worth a second look:")
        for key in searched:
            logger.warning("      " + key)

    logger.info("\n  not verifiable from raw files (%d), always need a photo:" % len(neverMined))
    for instrument in sorted({key[18:23] for key in neverMined}):
        for key in [k for k in neverMined if k[18:23] == instrument]:
            logger.info("      %-6s %s" % (instrument, key))


@click.command(help=__doc__)
@click.option("--year", type=int, default=date.today().year, show_default=True,
              help="Deployment year to draft.")
@click.option("--am-repo", type=click.Path(), default="~/repos/asset-management",
              show_default=True, help="Local asset-management clone.")
@click.option("--raw-input", "rawInput", type=click.Path(), default=None,
              help="rawFileSN csv holding this year's results. Default is the newest in params/.")
@click.option("--output", "outputFile", type=click.Path(), default=None,
              help="Default is inputs/imageSN_<year>_draft.csv.")
def main(year, am_repo, rawInput, outputFile):
    amRepo = os.path.expanduser(am_repo)
    rawInput = rawInput or newestRawFile()
    outputFile = outputFile or os.path.join(ROOT, "inputs", "imageSN_%d_draft.csv" % year)
    logFile = setupLogging(os.path.splitext(outputFile)[0] + ".log")

    refDes = refDesDict(amRepo)
    deployed = sorted({key for key, deployments in refDes.items()
                       for d in deployments if d["deployDate"].year == year})

    raw = pd.read_csv(rawInput)
    thisYear = raw[raw.deployYear == year]
    ### -99999 is the 'no serial number found' sentinel written by extract_raw_sn.py.
    ### A reference designator counts as verified only if every one of its deployments
    ### that year resolved -- a pod redeployed mid-cruise has two, and one can miss.
    missed = set(thisYear[thisYear.rawSerialNumber.astype(str).str.contains("-99999")]
                 .referenceDesignator)
    verified = set(thisYear.referenceDesignator) - missed
    needed = [key for key in deployed if key not in verified]

    logger.info("asset-management:   " + amRepo)
    logger.info("raw serial numbers: %s (%d rows for %d)" % (rawInput, len(thisYear), year))
    logger.info("writing:            " + outputFile)
    logger.info("run log:            " + logFile + "\n")

    if not deployed:
        raise click.ClickException(
            "no %d deployments in the sheets -- is the asset-management clone synced?" % year)
    if thisYear.empty:
        logger.warning("%s holds no %d rows. Run extract_raw_sn.py first, or every "
                       "instrument below will look unverifiable." % (rawInput, year))

    logger.info("%d deployments in %d" % (len(deployed), year))
    logger.info("%d verified from raw files" % len(verified))
    logger.info("%d need an image check" % len(needed))
    reportNeeded(needed)

    ### rows carry only the identity columns; the serial number and assetID come off the
    ### photos by hand, which is the point of this file
    draft = pd.DataFrame({"referenceDesignator": needed, "deployYear": year,
                          "imageFile": "", "imageSerialNumber": "",
                          "imageAssetID": "", "notes": ""})
    draft.to_csv(outputFile, index=False, columns=COLUMNS)
    logger.debug("draft rows written: " + ", ".join(needed))

    logger.info("\nwrote %s (%d rows)" % (outputFile, len(draft)))
    logger.info("\nnext: fill in imageFile, imageSerialNumber and imageAssetID from the cruise\n"
                "photos, drop any instrument you do not image-verify, and save the result as\n"
                "params/imageSN_%d.csv" % year)


if __name__ == "__main__":
    main()
