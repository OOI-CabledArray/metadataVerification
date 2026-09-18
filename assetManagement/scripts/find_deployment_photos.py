#!/usr/bin/env python3
"""Find candidate cruise photos for each instrument still needing an image check.

Writes a yaml manifest keyed by reference designator, listing every photo on the
Data0 share that could show that instrument's label, newest first. Nothing is
copied -- the paths point at the mounted share, so open them directly.

\b
  ./find_deployment_photos.py
  ./find_deployment_photos.py --year 2025 --photo-root /Volumes/Data0/.../VISIONS25

Matching is on the instrument code in the filename rather than on directory layout,
which varies year to year and between operators.
"""

import glob
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
import pandas as pd
from loguru import logger

from deployments import ROOT, refDesDict

PHOTO_ROOT = "/Volumes/Data0/Archive/Images/Equipment_Photos/VISIONS26"
### the share path as recorded in imageSN csvs, which drop the /Volumes prefix
SHARE_PREFIX = "/Volumes/"
EXTENSIONS = (".jpg", ".jpeg", ".png")


def photoIndex(photoRoot):
    """Every image under the cruise photo root."""
    return [p for p in glob.glob(os.path.join(photoRoot, "**", "*"), recursive=True)
            if p.lower().endswith(EXTENSIONS)]


def describe(path):
    """(date, kind) parsed out of a photo filename, e.g. X_20260808_204040_predeploy.JPG."""
    name = os.path.basename(path)
    stamp = re.search(r"_(\d{8})_", name)
    kind = "predeploy" if "predeploy" in name.lower() else (
        "recovered" if "recovered" in name.lower() else "other")
    return (stamp.group(1) if stamp else ""), kind


def candidatesFor(instrument, index, year):
    """Photos whose filename carries this instrument code, this year's first."""
    hits = [p for p in index if instrument in os.path.basename(p)]
    thisYear = [p for p in hits if describe(p)[0].startswith(str(year))]
    ### predeploy first, then by filename, whose trailing HHMMSS orders the shots
    ### within a session -- the date alone does not, they are all the same day
    return sorted(thisYear or hits,
                  key=lambda p: (describe(p)[1] != "predeploy", os.path.basename(p)))


def yamlBlock(key, expectedAssetID, expectedSN, photos, sharedWith=None):
    lines = ["%s:" % key,
             "  expectedAssetID: %s" % (expectedAssetID or "unknown"),
             "  expectedSerialNumber: %s" % (expectedSN or "unknown")]
    if sharedWith:
        lines.append("  note: no photos under this instrument code; shares assetID with %s"
                     % sharedWith)
    if not photos:
        lines.append("  photos: []   # none found -- check the share by hand")
        return "\n".join(lines)

    kinds = sorted({describe(p)[1] for p in photos})
    lines.append("  photoCount: %d   # %s" % (len(photos), ", ".join(kinds)))
    lines.append("  photos:")
    for path in photos:
        stamp, kind = describe(path)
        lines.append("    - %s   # %s %s" % (path, stamp, kind))
    return "\n".join(lines)


@click.command(help=__doc__)
@click.option("--year", type=int, default=date.today().year, show_default=True,
              help="Deployment year being verified.")
@click.option("--draft", "draftFile", type=click.Path(), default=None,
              help="imageSN draft listing what needs checking. Default inputs/imageSN_<year>_draft.csv.")
@click.option("--am-repo", type=click.Path(), default="~/repos/asset-management",
              show_default=True, help="Local asset-management clone.")
@click.option("--photo-root", "photoRoot", type=click.Path(), default=PHOTO_ROOT,
              show_default=True, help="Cruise equipment photo directory on the share.")
@click.option("--output", "outputFile", type=click.Path(), default=None,
              help="Default is inputs/deploymentPhotos_<year>.yaml.")
def main(year, draftFile, am_repo, photoRoot, outputFile):
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")

    amRepo = os.path.expanduser(am_repo)
    draftFile = draftFile or os.path.join(ROOT, "inputs", "imageSN_%d_draft.csv" % year)
    outputFile = outputFile or os.path.join(ROOT, "inputs", "deploymentPhotos_%d.yaml" % year)

    if not os.path.isdir(photoRoot):
        raise click.ClickException(
            "%s is not reachable -- is the Data0 share mounted?" % photoRoot)

    draft = pd.read_csv(draftFile)
    refDes = refDesDict(amRepo)
    instruments = pd.read_csv(os.path.join(ROOT, "params", "RCA-InstrumentList.csv"))
    serialFor = dict(zip(instruments.assetID, instruments.mfgSN))

    ### assetID deployed at each reference designator this year, so a reference designator
    ### with no photos of its own can borrow those of a co-located instrument on the same
    ### physical assembly -- D1000 and RASFL share one sampler, and one set of photos
    assetFor = {key: d["AssetID"] for key, deployments in refDes.items()
                for d in deployments if d["deployDate"].year == year}
    byAsset = {}
    for key, assetID in assetFor.items():
        byAsset.setdefault(assetID, []).append(key)

    index = photoIndex(photoRoot)
    logger.info("photo root:  %s (%d images indexed)" % (photoRoot, len(index)))
    logger.info("draft:       %s (%d instruments)" % (draftFile, len(draft)))
    logger.info("writing:     %s\n" % outputFile)

    blocks, missing, borrowed = [], [], []
    for key in draft.referenceDesignator:
        assetID = assetFor.get(key)
        photos = candidatesFor(key[18:27], index, year)
        sharedWith = None
        if not photos and assetID:
            ### try the other reference designators on the same physical instrument
            for sibling in [s for s in byAsset.get(assetID, []) if s != key]:
                photos = candidatesFor(sibling[18:27], index, year)
                if photos:
                    sharedWith = sibling
                    borrowed.append((key, sibling))
                    break
        if not photos:
            missing.append(key)
        blocks.append(yamlBlock(key, assetID, serialFor.get(assetID), photos, sharedWith))
        logger.info("  %-30s %3d photos%s"
                    % (key, len(photos), "  (via %s)" % sharedWith if sharedWith else ""))

    header = ("### Candidate cruise photos for %d image verification.\n"
              "### Generated by scripts/find_deployment_photos.py -- paths point at the\n"
              "### mounted Data0 share, nothing is copied locally.\n"
              "### expectedAssetID/expectedSerialNumber come from the deployment sheet and\n"
              "### RCA-InstrumentList; confirm them against the label in the photo.\n\n" % year)
    with open(outputFile, "w") as handle:
        handle.write(header + "\n\n".join(blocks) + "\n")

    if borrowed:
        logger.warning("\n%d borrowed photos from a co-located instrument:" % len(borrowed))
        for key, sibling in borrowed:
            logger.warning("    %s -> %s" % (key, sibling))
    if missing:
        logger.warning("\n%d with no candidate photos at all:" % len(missing))
        for key in missing:
            logger.warning("    " + key)

    logger.info("\nwrote " + outputFile)


if __name__ == "__main__":
    main()
