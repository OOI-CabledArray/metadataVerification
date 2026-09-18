#!/usr/bin/env python3
"""Match image serial numbers against the RCA master instrument list.

Reads the filled-in imageSN draft, resolves each photographed serial number to an
assetID, and writes the two reportOuts csvs. Exact matches are reported as such;
anything else is a partial match or an assetID-only match and needs the HITL pass.

\b
  ./fuzzy_match_sn.py
  ./fuzzy_match_sn.py --year 2025 --no-strip     # reproduce the notebook exactly

An assetID in the master list is a slot, not one instrument: it carries a comma
separated list of every serial number that has occupied it, so one assetID can be
reached by several serial numbers.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
import numpy as np
import pandas as pd
from loguru import logger

from deployments import ROOT, refDesDict


def setupLogging(logFile=None):
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")
    if logFile:
        logger.add(logFile, level="DEBUG", mode="w",
                   format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}")
    return logFile


def serialToAsset(master, strip=True):
    """{serial number: assetID}, one entry per serial number an assetID has held."""
    lookup = {}
    for _, row in master.iterrows():
        for serial in str(row["mfgSN"]).split(","):
            lookup[serial.strip() if strip else serial] = row["assetID"]
    return lookup


def splitSerials(value):
    """A cell may hold several serial numbers, separated by / or ,"""
    if not isinstance(value, str):
        return [value]
    for separator in ("/", ","):
        if separator in value:
            return value.split(separator)
    return [value]


def matchRow(row, lookup, strip=True):
    """Resolve one draft row to candidate assetIDs. Mirrors the notebook's columns."""
    key = row["referenceDesignator"]
    imageAssetID = row["imageAssetID"]
    serials = splitSerials(row["imageSerialNumber"])

    matches, proportions, matchedSerials = [], [], []
    exactSN = exactAsset = anyMatch = False

    for serial in serials:
        if strip and isinstance(serial, str):
            serial = serial.strip()
        if not isinstance(serial, str):
            logger.debug("%s: no serial number entered" % key)

        for candidate, assetID in lookup.items():
            if isinstance(serial, str) and serial == candidate:
                logger.debug("%s: exact match %s -> %s" % (key, serial, assetID))
                matches = sorted(set(matches + [assetID]))
                matchedSerials.append(candidate)
                exactSN = anyMatch = True

        if not exactSN:
            for candidate, assetID in lookup.items():
                if isinstance(serial, str) and serial in candidate and serial != candidate:
                    logger.debug("%s: partial match %s inside %s -> %s" % (key, serial, candidate, assetID))
                    matches = sorted(set(matches + [assetID]))
                    proportions.append(round(len(serial) / len(candidate), 2))
                    matchedSerials.append(candidate)
                    anyMatch = True

        if not anyMatch:
            ### nothing matched on serial number, so fall back to the assetID read
            ### off the photo and check it is one the master list knows about
            for assetID in lookup.values():
                if isinstance(imageAssetID, str) and imageAssetID == assetID:
                    logger.debug("%s: matched on assetID %s" % (key, assetID))
                    matches = sorted(set(matches + [assetID]))
                    anyMatch = exactAsset = True

    row["matching_asset_ids"] = matches or np.nan
    row["proportion_match"] = proportions or np.nan
    row["matching_mfg_sn"] = matchedSerials or np.nan
    row["exact_SN_match"] = True if exactSN else np.nan
    row["exact_assetID_match"] = True if exactAsset else np.nan
    row["any_match"] = True if anyMatch else np.nan
    return row


@click.command(help=__doc__)
@click.option("--year", type=int, default=date.today().year, show_default=True,
              help="Deployment year being verified.")
@click.option("--draft", "draftFile", type=click.Path(), default=None,
              help="Filled-in imageSN draft. Default inputs/imageSN_<year>_draft.csv.")
@click.option("--out-dir", "outDir", type=click.Path(), default=None,
              help="Where the two csvs land. Default reportOuts/.")
@click.option("--am-repo", "amRepo", type=click.Path(), default="~/repos/asset-management",
              show_default=True, help="Local asset-management clone, for the deployment sheets.")
@click.option("--strip/--no-strip", default=True, show_default=True,
              help="Trim whitespace around serial numbers. --no-strip reproduces the notebook, "
                   "which misses exact matches on the 116 master-list serials that carry a "
                   "leading space.")
def main(year, draftFile, outDir, amRepo, strip):
    draftFile = draftFile or os.path.join(ROOT, "inputs", "imageSN_%d_draft.csv" % year)
    outDir = outDir or os.path.join(ROOT, "reportOuts")
    runDate = date.today().strftime("%Y%m%d")
    matchFile = os.path.join(outDir, "fuzzyMatches_%s.csv" % runDate)
    hitlFile = os.path.join(outDir, "fuzzyMatches_HITL_%s.csv" % runDate)
    logFile = setupLogging(os.path.join(outDir, "fuzzyMatches_%s.log" % runDate))

    master = pd.read_csv(os.path.join(ROOT, "params", "RCA-InstrumentList.csv"))
    draft = pd.read_csv(draftFile)
    lookup = serialToAsset(master, strip)

    ### what the deployment sheet claims went in at each reference designator this year
    refDes = refDesDict(os.path.expanduser(amRepo))
    expectedAsset = {key: d["AssetID"] for key, deployments in refDes.items()
                     for d in deployments if d["deployDate"].year == year}

    logger.info("master list: %d assetIDs, %d serial numbers" % (len(master), len(lookup)))
    logger.info("draft:       %s (%d rows)" % (draftFile, len(draft)))
    logger.info("whitespace trimming: %s" % ("on" if strip else "off, notebook behaviour"))
    logger.info("writing:     %s" % matchFile)
    logger.info("             %s" % hitlFile)
    logger.info("run log:     %s\n" % logFile)

    matched = draft.apply(matchRow, axis=1, args=(lookup, strip))

    blank, failed, ambiguous, conflicts = [], [], [], []
    for _, row in matched.iterrows():
        key = row["referenceDesignator"]
        assetIDs = row["matching_asset_ids"]
        expected = expectedAsset.get(key)

        if not isinstance(assetIDs, list):
            ### an empty row is expected -- the label was unreadable and is left for final
            ### review. A filled row that matched nothing is a different problem entirely.
            if pd.isna(row["imageSerialNumber"]) and pd.isna(row["imageAssetID"]):
                blank.append(key)
                logger.info("  %-30s blank, left for final review" % key)
            else:
                failed.append(key)
                logger.error("  %-30s NO MATCH for %r -- not in the master list"
                             % (key, row["imageSerialNumber"]))
            continue

        if len(assetIDs) > 1:
            ambiguous.append(key)
            logger.warning("  %-30s %d candidates, needs HITL: %s"
                           % (key, len(assetIDs), ", ".join(assetIDs)))
            continue

        found = assetIDs[0]
        how = ("exact serial" if row["exact_SN_match"] is True
               else "assetID only" if row["exact_assetID_match"] is True else "partial serial")
        ### the point of the exercise: does the instrument in the photo agree with the
        ### one the deployment sheet says went in the water?
        if expected and found != expected:
            conflicts.append((key, found, expected))
            logger.error("  %-30s %s (%s) but deployment sheet says %s"
                         % (key, found, how, expected))
        else:
            logger.success("  %-30s %s (%s)" % (key, found, how))

    logger.info("\n%d matched, %d ambiguous, %d blank, %d unmatched"
                % (len(matched) - len(ambiguous) - len(blank) - len(failed),
                   len(ambiguous), len(blank), len(failed)))
    if conflicts:
        logger.error("\n%d disagree with the deployment sheet -- highest priority:" % len(conflicts))
        for key, found, expected in conflicts:
            logger.error("    %-30s photo %s / sheet %s" % (key, found, expected))
    if failed:
        logger.error("\n%d filled in but matched nothing:" % len(failed))
        for key in failed:
            logger.error("    " + key)

    matched.to_csv(matchFile)
    hitl = matched.copy()
    hitl["HITL_match_notes"] = pd.Series(dtype="object")
    hitl.to_csv(hitlFile)
    logger.info("wrote %s" % matchFile)
    logger.info("wrote %s" % hitlFile)
    logger.info("\nnext: work through the HITL csv by hand, resolving rows with more than one\n"
                "candidate assetID and filling HITL_match_notes")


if __name__ == "__main__":
    main()
