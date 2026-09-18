#!/usr/bin/env python3
"""Verify RCA deployment metadata against raw files, cruise photos and vendor calibrations.

Runs two passes. The calibration pass compares every asset-management calibration file
against the original vendor file. The deployment pass checks each deployment's serial
number against the raw archive, the cruise photos and the deployment sheet, then assigns
a verification status. --skip-cal runs only the deployment pass, which is what you want
when re-running after editing HITL files.

\b
  ./verify_metadata.py --dry-run     # show which inputs resolved, then stop
  ./verify_metadata.py
  ./verify_metadata.py --skip-cal    # deployment pass only, no vendor cal fetching
  ./verify_metadata.py --local --am-repo ~/repos/asset-management

Remote mode verifies what CI has ingested; --local verifies a clone with changes not yet
pushed, for a pre-cruise check.
"""

import csv
import datetime
import glob
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
import numpy as np
import pandas as pd
import requests
from loguru import logger

import metadataFunctions as mf
from deployments import CABLED_ARRAY, ROOT, loadDeploymentSheets, refDesDict

AM_RAW = "https://raw.githubusercontent.com/oceanobservatories/asset-management/master"
AM_HEAD = "https://github.com/oceanobservatories/asset-management/tree/master"
CAL_RAW = "https://raw.githubusercontent.com/OOI-CabledArray/calibrationFiles/master"
CAL_HEAD = "https://github.com/OOI-CabledArray/calibrationFiles/tree/master"

### instrument types whose serial number can be read out of a raw archive file
VERIFIABLE_BY_SN = ["CTD", "SPK", "NUT", "PAR", "FLOR", "PREST", "TMPSFA", "OPTAA", "ADCP"]
RAW_CHECK_DP = ["ENG000000", "VEL3DA105", "FLCDRA103", "FLNTUA103", "DOSTAD105",
                "VEL3DA103", "FLCDRA102", "FLNTUA102", "DOSTAD104",
                "VEL3DA303", "FLCDRA302", "FLNTUA302", "DOSTAD304"]
EXCLUDE_SENSORS = ["CTDPFA110"]   ### MARUM PI sensor, no raw data in the archive
EXCLUDE_NODES = []


def setupLogging(logFile=None):
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")
    if logFile:
        logger.add(logFile, level="DEBUG", mode="w",
                   format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}")
    return logFile


def newest(pattern, description):
    """Most recent file matching a params/reportOuts glob."""
    found = sorted(glob.glob(pattern))
    if not found:
        raise click.ClickException("no %s found matching %s" % (description, pattern))
    return found[-1]


class Repos:
    """Asset-management and calibration repos, read either locally or from github.

    The two repos do not always name a sensor directory the same way -- PHSEN-H
    calibrations live in asset-management 'PHSENH0' but in calibrationFiles 'PHSENH' --
    so directory names are read from each repo rather than assumed.
    """

    def __init__(self, useLocal, amRepo, calRepo, cacheDir):
        self.useLocal = useLocal
        self.am = amRepo if useLocal else AM_RAW
        self.cal = calRepo if useLocal else CAL_RAW
        self.cacheDir = cacheDir
        self.vendorFiles = {}
        os.makedirs(cacheDir, exist_ok=True)

    def githubFileList(self, url, extension):
        extension = "[A-Za-z.]+" if "*" in extension else extension
        pattern = re.compile('"name":"(AT[^"]*__[0-9]{8}[^"]*\\.' + extension + ')"', re.I)
        return sorted(set(re.findall(pattern, requests.get(url).text)))

    def sensorFiles(self, localDir, url, extension):
        if self.useLocal:
            if not os.path.isdir(localDir):
                logger.debug("directory does not exist: " + localDir)
                return []
            return sorted(f for f in os.listdir(localDir) if f.startswith("AT"))
        return self.githubFileList(url, extension)

    def sensorDirs(self, localDir, url, repoPath):
        if self.useLocal:
            return sorted(d for d in os.listdir(localDir) if os.path.isdir(localDir + "/" + d))
        pattern = re.compile('"name":"([^"]+)","path":"' + repoPath
                             + '[^"]*","contentType":"directory"')
        return sorted(set(re.findall(pattern, requests.get(url).text)))

    def vendorFilePath(self, fileStem):
        """Local path to a vendor cal file stem, for mf.compareCalCoefficients.

        In remote mode the sibling files for that stem are cached to disk first. PDFs are
        only probed with os.path.isfile and never read, so a placeholder is written
        instead of downloading them.
        """
        entries = self.vendorFiles.get(fileStem)
        if not entries:
            return None
        if self.useLocal:
            return self.cal + "/" + entries[0][0] + "/" + fileStem

        cacheDir = self.cacheDir + "/" + entries[0][0]
        os.makedirs(cacheDir, exist_ok=True)
        for sensor, fileName in entries:
            target = cacheDir + "/" + fileStem + fileName[len(fileStem):].lower()
            if os.path.isfile(target):
                continue
            if target.endswith(".pdf"):
                open(target, "wb").close()
            else:
                open(target, "wb").write(
                    requests.get(CAL_RAW + "/" + sensor + "/" + fileName).content)
        return cacheDir + "/" + fileStem


def calFileBits(fileName):
    """assetID and calibration date parsed out of a cal file name."""
    bits = re.match(r"(.*)__([0-9]{8})", fileName)
    if not bits:
        return None, None
    return bits.group(1), datetime.datetime.strptime(bits.group(2), "%Y%m%d")


def loadCalFileLists(repos):
    """Cal file paths in asset-management, and the vendor originals in calibrationFiles."""
    amHead = AM_HEAD if not repos.useLocal else repos.am
    githubFiles = []
    for sensor in repos.sensorDirs(repos.am + "/calibration", AM_HEAD + "/calibration",
                                   "calibration/"):
        sensorDir = repos.am + "/calibration/" + sensor
        for calFile in repos.sensorFiles(sensorDir, AM_HEAD + "/calibration/" + sensor, "csv"):
            githubFiles.append(sensorDir + "/" + calFile)

    vendorStems = []
    for sensor in repos.sensorDirs(repos.cal, CAL_HEAD, ""):
        sensorDir = repos.cal + "/" + sensor
        for calFile in repos.sensorFiles(sensorDir, CAL_HEAD + "/" + sensor, "*"):
            stem = calFile.split(".")[0]
            vendorStems.append(stem)
            repos.vendorFiles.setdefault(stem, []).append([sensor, calFile])
    return githubFiles, vendorStems


def verifySensorBulk(assetIDs, assetList, outputFile):
    """Compare serial numbers between the OOI sensor bulk record and the RCA master list."""
    byAsset = assetList.set_index("assetID").T.to_dict("series")
    match, matchFormat, mismatch, missingFromBulk, missingFromRCA = [], [], [], [], []

    for key in assetIDs:
        if ("ATAPL" in key or "ATOSU" in key) and key not in byAsset:
            missingFromRCA.append(key)

    for key, values in byAsset.items():
        if key not in assetIDs:
            missingFromBulk.append(key)
            continue
        bulkSN = str(assetIDs[key]).strip()
        categories = []
        if "nan" in bulkSN:
            categories.append("0")
        else:
            for serial in values["mfgSN"]:
                serial = serial.strip()
                if serial == bulkSN:
                    categories.append("2")
                elif mf.partialMatch(serial, bulkSN, 3):
                    categories.append("1")
                else:
                    categories.append("0")
        row = [key, values["mfgSN"], bulkSN]
        if "2" in categories:
            match.append(row)
        elif "1" in categories:
            matchFormat.append(row)
        else:
            mismatch.append(row)

    with open(outputFile, "w") as handle:
        for label, rows in [("match", match), ("matchFormat", matchFormat),
                            ("mismatch", mismatch)]:
            handle.write(label + "\n")
            for row in rows:
                handle.write("%s, %s, %s\n" % (row[0], row[1], row[2]))
        for label, rows in [("missingFromSensorBulk", missingFromBulk),
                            ("missingFromRCAlist", missingFromRCA)]:
            handle.write(label + "\n")
            for entry in rows:
                handle.write("%s\n" % entry)

    logger.info("  %d match, %d match on format only, %d mismatch"
                % (len(match), len(matchFormat), len(mismatch)))
    if mismatch:
        logger.warning("  serial numbers disagreeing with sensorBulk:")
        for key, rcaSN, bulkSN in mismatch:
            logger.warning("      %-22s RCA %s / bulk %s" % (key, rcaSN, bulkSN))
    logger.info("  %d in the RCA list but not sensorBulk, %d in sensorBulk but not the RCA list"
                % (len(missingFromBulk), len(missingFromRCA)))


def verifyCalibrations(repos, githubFiles, vendorStems, assetIDs, HITLcal,
                       coeffMap, constants, calVerifyFile, missingCalFile):
    """Compare each asset-management calibration file against its vendor original."""
    calVerify = {}
    parsedNames = []

    for number, githubFile in enumerate(githubFiles, start=1):
        instrument = os.path.basename(os.path.dirname(githubFile))
        fileName = os.path.basename(githubFile)
        stem = os.path.splitext(fileName)[0]
        if "__" not in stem:
            logger.warning("  invalid cal file name: " + fileName)
            continue
        if number % 100 == 0:
            logger.info("  %d/%d cal files" % (number, len(githubFiles)))

        parsedNames.append(stem)
        entry = {"instrument": instrument}
        if fileName in HITLcal["githubFile"].tolist():
            entry["HITLstatus"] = HITLcal[HITLcal.githubFile == fileName].Status.item()
            entry["HITLnotes"] = HITLcal[HITLcal.githubFile == fileName].HITLnotes.item()
        else:
            entry["HITLstatus"] = "NA"
            entry["HITLnotes"] = " "
        entry["calRepo_check"] = "MATCH" if stem in vendorStems else "NOMATCH"

        githubCal = None
        try:
            githubCal = pd.read_csv(githubFile, sep=",", converters={"value": np.float64},
                                    float_precision="round_trip")
            entry["fileParse"] = "SUCCESS_TYPE1"
        except ValueError:
            try:
                githubCal = pd.read_csv(githubFile, sep=",", float_precision="round_trip")
                entry["fileParse"] = "SUCCESS_TYPE2"
            except ValueError:
                entry["fileParse"] = "FAIL"
                logger.warning("  could not parse " + fileName)

        if githubCal is not None:
            entry["serialNumber"] = checkCalSerial(githubCal, stem, assetIDs)
            if ".ext" not in githubFile:
                entry["duplicateCoeff"] = checkDuplicateCoefficients(githubCal)
            if entry["calRepo_check"] == "NOMATCH":
                entry["vendorMatch"] = "NAN"
            else:
                compared = mf.compareCalCoefficients(githubCal, repos.vendorFilePath(stem),
                                                     coeffMap, constants)
                entry["vendorMatch"] = "NOTCOMPARED" if compared[0] == "NAN" else compared
                if compared[0] == "MISMATCH":
                    logger.warning("  coefficient mismatch in " + fileName)
        calVerify[fileName] = entry

    ### vendor files with no counterpart in asset-management
    missing = sorted(set(stem for stem in vendorStems if stem not in parsedNames))
    with open(missingCalFile, "w") as handle:
        handle.write("calRepo_gitHub_missing\n")
        for stem in missing:
            handle.write("%s\n" % stem)

    with open(calVerifyFile, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["githubFile", "instrument", "calRepo_check", "HITLstatus",
                         "HITLnotes", "fileParse", "serialNumber", "duplicateCoeff",
                         "vendorMatch"])
        for fileName, entry in calVerify.items():
            if "ext" in fileName:
                continue
            writer.writerow([fileName, entry["instrument"], entry["calRepo_check"],
                             entry["HITLstatus"], entry["HITLnotes"], entry.get("fileParse"),
                             entry.get("serialNumber"), entry.get("duplicateCoeff"),
                             entry.get("vendorMatch")])

    mismatched = sum(1 for e in calVerify.values()
                     if isinstance(e.get("vendorMatch"), list) and e["vendorMatch"][0] == "MISMATCH")
    noVendor = sum(1 for e in calVerify.values() if e["calRepo_check"] == "NOMATCH")
    logger.info("\n  %d cal files checked, %d coefficient mismatches, %d with no vendor file"
                % (len(calVerify), mismatched, noVendor))
    logger.info("  %d vendor files missing from asset-management" % len(missing))


def checkCalSerial(githubCal, stem, assetIDs):
    """Is the serial number consistent within the file and against sensorBulk?"""
    if "serial" not in githubCal.columns:
        return "NOTFOUND_FILE"
    if len(np.unique(githubCal["serial"])) > 1:
        return "MULTIPLE"
    assetID = stem.split("__")[0]
    if assetID not in assetIDs:
        return "PARSING_ERROR"
    bulkSN = str(assetIDs[assetID]).strip()
    if "nan" in bulkSN:
        return "NOTFOUND_SENSORBULK"
    return ("MATCH_SENSORBULK" if str(np.unique(githubCal["serial"])[0]) in str(bulkSN)
            else "MISMATCH_SENSORBULK")


def checkDuplicateCoefficients(githubCal):
    """Repeated coefficient names are fine only when their values agree."""
    duplicates = githubCal[githubCal.duplicated("name")]
    if duplicates.empty:
        return "NONE"
    for name in duplicates["name"]:
        if not githubCal[githubCal["name"] == name].drop_duplicates(keep=False).empty:
            return "DUPLICATES_NOTIDENTICAL"
    return "DUPLICATES_IDENTICAL"


def checkDeploymentSheets(deployments, sensorList, platformList, cruiseList):
    """Sanity checks on the deployment sheets themselves, reported as warnings."""
    for column, reference, label in [("sensor.uid", sensorList.ASSET_UID, "sensorBulk"),
                                     ("mooring.uid", platformList.ASSET_UID, "platformBulk"),
                                     ("CUID_Deploy", cruiseList.CUID, "cruiseList")]:
        missing = deployments[~deployments[column].isin(reference)]
        if len(missing):
            logger.warning("  %d %s values absent from %s:" % (len(missing), column, label))
            for _, row in missing.iterrows():
                logger.warning("      %s  %s" % (row[column], row["Reference Designator"]))

    ### the same instrument cannot be in two places in one deployment
    dates = pd.to_datetime(deployments["startDateTime"])
    for year in sorted(dates.dt.year.unique()):
        subset = deployments[dates.dt.year == year]
        for number in subset["deploymentNumber"].unique():
            group = subset[subset["deploymentNumber"] == number]
            duplicated = group[group["sensor.uid"].duplicated(keep=False)]
            for _, row in duplicated.iterrows():
                logger.warning("  duplicate assetID %s in %d deployment %s: %s"
                               % (row["sensor.uid"], year, number, row["Reference Designator"]))


def isRawCheckable(key, includeDeepProfiler=True):
    """Should this instrument have a serial number in the raw archive?

    includeDeepProfiler mirrors the notebook, which counts the deep-profiler codes when
    deciding what to look up but not when deciding whether a missing file is NO_FILE.
    """
    instrument = key[18:27]
    families = any(s in instrument for s in VERIFIABLE_BY_SN)
    if includeDeepProfiler:
        families = families or any(s in instrument for s in RAW_CHECK_DP)
    return (families
            and all(s not in instrument for s in EXCLUDE_SENSORS)
            and all(n not in key[9:14] for n in EXCLUDE_NODES))


def assignCalFiles(refDes, sensorCals):
    """Attach the calibration file in force at each deployment."""
    for key, deployments in refDes.items():
        for deployment in deployments:
            if deployment["AssetID"] not in sensorCals:
                continue
            history = sensorCals[deployment["AssetID"]]["calFile"]
            before = [c for c in history if c[0] < deployment["deployDate"]]
            if not before:
                deployment["calFile"] = "noValidCalFile"
                deployment["calFile_verify"] = "NO_VALID_FILE"
                continue
            closest = min(before, key=lambda c: abs(c[0] - deployment["deployDate"]))
            deployment["calFile"] = closest[1]
            ### a calibration much older than the deployment is still a valid file,
            ### but worth surfacing separately
            stale = deployment["deployDate"] - closest[0] > datetime.timedelta(days=450)
            deployment["calFile_verify"] = ("VALID_FILE_CAL_OLDER_THAN_15MONTHS" if stale
                                            else "VALID_FILE")


def applyRawSerials(refDes, rawFileSN):
    """Attach raw-archive serial numbers, and verify them against sensorBulk."""
    for key, deployments in refDes.items():
        for deployment in deployments:
            year = int(deployment["deployDate"].strftime("%Y"))
            hit = rawFileSN[(rawFileSN.referenceDesignator == key)
                            & (rawFileSN.deployYear == year)]
            if len(hit):
                deployment["rawSN"] = hit.rawSerialNumber.iloc[0]
                deployment["firstRawFile"] = hit.rawFile.iloc[0]
            elif isRawCheckable(key):
                logger.debug("no raw file listed for %s %d" % (key, year))
                deployment["rawSN"] = "-99999"
                deployment["firstRawFile"] = "none"


def verifyRawSerials(refDes, assetIDs):
    for key, deployments in refDes.items():
        for deployment in deployments:
            rawFile = str(deployment["firstRawFile"])
            if "none" in rawFile:
                if isRawCheckable(key, includeDeepProfiler=False):
                    deployment["rawFile_verify"] = "NO_FILE"
            elif "undef" in rawFile:
                deployment["rawFile_verify"] = "NAN"
            elif "-99999" in str(deployment["rawSN"]):
                deployment["rawFile_verify"] = "NO_SN"
            elif str(deployment["rawSN"]) in str(assetIDs.get(deployment["AssetID"])):
                deployment["rawFile_verify"] = "MATCH"
            else:
                ### name the asset the raw serial number actually belongs to, if any
                owner = "unknown"
                for assetID, serial in assetIDs.items():
                    if deployment["AssetID"][0:11] in assetID and str(deployment["rawSN"]) in str(serial):
                        owner = assetID
                deployment["rawFile_verify"] = ("MISMATCH: raw: %s:%s"
                                                % (deployment["rawSN"], owner))


def applyImageAssets(refDes, fuzzy):
    """Attach the assetID read off the cruise photos, curated in the HITL pass."""
    for key, deployments in refDes.items():
        for deployment in deployments:
            year = int(deployment["deployDate"].strftime("%Y"))
            hit = fuzzy[(fuzzy.referenceDesignator == key) & (fuzzy.deployYear == year)]
            if not len(hit):
                deployment["image_verify"] = "NAN"
                continue
            deployment["imageAssetID"] = hit.imageAssetID.iloc[0]
            if str(deployment["imageAssetID"]) in deployment["AssetID"]:
                deployment["image_verify"] = "MATCH"
            else:
                deployment["image_verify"] = ("MISMATCH: image: %s deployment:%s"
                                              % (deployment["imageAssetID"], deployment["AssetID"]))


def assignStatus(refDes, requiringCalibration):
    for key, deployments in refDes.items():
        for deployment in deployments:
            deployment["calibrationRequired"] = (
                True if any(s in key for s in requiringCalibration) else "NAN")
            if (deployment["rawFile_verify"] == "MATCH"
                    or deployment["HITLstatus"] == "Clear"
                    or deployment["image_verify"] == "MATCH"):
                deployment["verificationStatus"] = "VERIFIED"
            elif any(s in key for s in VERIFIABLE_BY_SN):
                deployment["verificationStatus"] = "RAW_SN_POSSIBLE"
            else:
                deployment["verificationStatus"] = "NOT_VERIFIED"


def applyHITL(refDes, HITLdeploy):
    for key, deployments in refDes.items():
        for deployment in deployments:
            stamp = "%s.%s.%s" % (key, deployment["deployDate"].strftime("%Y"),
                                  deployment["deployNum"])
            hit = HITLdeploy[HITLdeploy.referenceDesignatorYearDeployNum == stamp]
            deployment["HITLstatus"] = hit.Status.item() if len(hit) else "NA"
            deployment["HITLnotes"] = hit.HITLnotes.item() if len(hit) else ""


def writeDeploymentVerification(refDes, outputFile, year):
    with open(outputFile, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["verificationStatus", "referenceDesignator", "deployYear",
                         "deploymentSheetAssetID", "rawFileVerification", "imageVerification",
                         "calFileVerification", "calibrationRequired", "HITLstatus",
                         "HITLnotes"])
        for key, deployments in refDes.items():
            for deployment in deployments:
                writer.writerow([deployment["verificationStatus"], key,
                                 deployment["deployDate"].strftime("%Y"), deployment["AssetID"],
                                 deployment["rawFile_verify"], deployment["image_verify"],
                                 deployment["calFile_verify"], deployment["calibrationRequired"],
                                 deployment["HITLstatus"], deployment["HITLnotes"]])

    ### this year's deployments are what the HITL pass acts on, so report them separately
    current = [(key, d) for key, ds in refDes.items() for d in ds
               if d["deployDate"].year == year]
    mismatchRaw = [(k, d) for k, d in current if "MISMATCH" in str(d["rawFile_verify"])]
    mismatchImage = [(k, d) for k, d in current if "MISMATCH" in str(d["image_verify"])]
    unverified = [(k, d) for k, d in current if d["verificationStatus"] == "NOT_VERIFIED"]

    logger.info("\n  %d deployments in %d: %d verified, %d raw-SN possible, %d not verified"
                % (len(current), year,
                   sum(1 for _, d in current if d["verificationStatus"] == "VERIFIED"),
                   sum(1 for _, d in current if d["verificationStatus"] == "RAW_SN_POSSIBLE"),
                   len(unverified)))
    if mismatchRaw:
        logger.error("\n  %d deployment/raw-file mismatches -- highest priority:" % len(mismatchRaw))
        for key, deployment in mismatchRaw:
            logger.error("      %-30s %s" % (key, deployment["rawFile_verify"]))
    if mismatchImage:
        logger.error("\n  %d deployment/image mismatches -- high priority:" % len(mismatchImage))
        for key, deployment in mismatchImage:
            logger.error("      %-30s %s" % (key, deployment["image_verify"]))
    if unverified:
        logger.warning("\n  %d not verified by any route:" % len(unverified))
        for key, _ in unverified:
            logger.warning("      " + key)


@click.command(help=__doc__)
@click.option("--year", type=int, default=date.today().year, show_default=True,
              help="Deployment year being verified, for the summary.")
@click.option("--am-repo", type=click.Path(), default="~/repos/asset-management",
              show_default=True, help="Local asset-management clone.")
@click.option("--cal-repo", type=click.Path(), default="~/repos/calibrationFiles",
              show_default=True, help="Local calibrationFiles clone, used with --local.")
@click.option("--local/--remote", "useLocal", default=False, show_default=True,
              help="--local verifies your clone, for a pre-cruise check. --remote verifies "
                   "what CI has ingested.")
@click.option("--raw-input", "rawInput", type=click.Path(), default=None,
              help="rawFileSN csv. Default is the newest in params/.")
@click.option("--image-sn", "imageSN", type=click.Path(), default=None,
              help="imageSN csv. Default is params/imageSN_<year>.csv.")
@click.option("--fuzzy-hitl", "fuzzyHITL", type=click.Path(), default=None,
              help="Curated fuzzyMatches_HITL csv. Default is the newest in reportOuts/.")
@click.option("--out-dir", "outDir", type=click.Path(), default=None,
              help="Where report outs land. Default reportOuts/.")
@click.option("--skip-cal", is_flag=True,
              help="Skip the calibration pass, which fetches every vendor cal file.")
@click.option("--dry-run", is_flag=True,
              help="Report the inputs that resolved, then stop.")
def main(year, am_repo, cal_repo, useLocal, rawInput, imageSN, fuzzyHITL, outDir,
         skip_cal, dry_run):
    amRepo = os.path.expanduser(am_repo)
    calRepo = os.path.expanduser(cal_repo)
    outDir = outDir or os.path.join(ROOT, "reportOuts")
    runDate = date.today().strftime("%Y%m%d")

    ### resolve the three inputs that used to be hand-edited constants
    rawInput = rawInput or newest(os.path.join(ROOT, "params", "rawFileSN_2*.csv"),
                                  "rawFileSN csv")
    imageSN = imageSN or os.path.join(ROOT, "params", "imageSN_%d.csv" % year)
    fuzzyHITL = fuzzyHITL or newest(os.path.join(outDir, "fuzzyMatches_HITL_*.csv"),
                                    "curated fuzzyMatches_HITL csv")

    calVerifyFile = os.path.join(outDir, "calibrationVerification_%s.csv" % runDate)
    deployVerifyFile = os.path.join(outDir, "deploymentVerification_%s.csv" % runDate)
    sensorBulkFile = os.path.join(outDir, "sensorBulkVerification_%s.txt" % runDate)
    missingCalFile = os.path.join(outDir, "missingCalFiles_%s.txt" % runDate)
    logFile = setupLogging(None if dry_run
                           else os.path.join(outDir, "verifyMetadata_%s.log" % runDate))

    logger.info("mode:                 %s" % ("local clone" if useLocal
                                              else "remote, as ingested by CI"))
    logger.info("asset-management:     %s" % (amRepo if useLocal else AM_RAW))
    logger.info("calibration files:    %s" % (calRepo if useLocal else CAL_RAW))
    logger.info("raw serial numbers:   %s" % rawInput)
    logger.info("image serial numbers: %s" % imageSN)
    logger.info("curated image matches: %s" % fuzzyHITL)
    logger.info("writing:              %s" % deployVerifyFile)
    logger.info("                      %s" % sensorBulkFile)
    if not skip_cal:
        logger.info("                      %s" % calVerifyFile)
        logger.info("                      %s" % missingCalFile)
    logger.info("run log:              %s" % (logFile or "none, dry run"))
    for path, label in [(rawInput, "raw serial numbers"), (imageSN, "image serial numbers"),
                        (fuzzyHITL, "curated image matches")]:
        if not os.path.isfile(path):
            raise click.ClickException("%s not found: %s" % (label, path))
    if dry_run:
        return

    repos = Repos(useLocal, amRepo, calRepo, os.path.join(ROOT, "tmp", "calCache"))

    logger.info("\nloading asset-management records...")
    sensorList = pd.read_csv(repos.am + "/bulk/sensor_bulk_load-AssetRecord.csv")
    platformList = pd.read_csv(repos.am + "/bulk/platform_bulk_load-AssetRecord.csv")
    cruiseList = pd.read_csv(repos.am + "/cruise/CruiseInformation.csv")
    deployments = loadDeploymentSheets(repos.am)
    refDes = refDesDict(repos.am)
    assetIDs = pd.Series(sensorList["Manufacturer's Serial No./Other Identifier"].values,
                         index=sensorList["ASSET_UID"]).to_dict()
    logger.info("  %d reference designators, %d deployments, %d sensor bulk records"
                % (len(refDes), len(deployments), len(sensorList)))

    assetList = pd.read_csv(os.path.join(ROOT, "params", "RCA-InstrumentList.csv"))
    assetList["mfgSN"] = assetList["mfgSN"].str.split(", ")
    assetList["instrumentType"] = assetList["instrumentType"].str.split(",")
    coeffMap = pd.read_csv(os.path.join(ROOT, "params", "coefficientMap.csv"))
    coeffMap = coeffMap.set_index("github").transpose().to_dict("list")
    constantsFrame = pd.read_csv(os.path.join(ROOT, "params", "coefficientConstants.csv"),
                                 sep=",", converters={"value": np.float64},
                                 float_precision="round_trip")
    constants = {}
    for _, row in constantsFrame.iterrows():
        constants.setdefault(row.sensor, {})[row.coeff] = row.constant
    HITLcal = pd.read_csv(os.path.join(ROOT, "2i_HITL", "2i_HITL_calibrationVerification.csv"))
    HITLdeploy = pd.read_csv(os.path.join(ROOT, "2i_HITL", "2i_HITL_deploymentVerification.csv"))

    logger.info("\nreading calibration file listings...")
    githubFiles, vendorStems = loadCalFileLists(repos)
    logger.info("  %d asset-management cal files, %d vendor files"
                % (len(githubFiles), len(vendorStems)))

    sensorCals = {}
    for githubFile in githubFiles:
        assetID, calDate = calFileBits(os.path.basename(githubFile))
        if assetID:
            sensorCals.setdefault(assetID, {"calFile": []})["calFile"].append(
                [calDate, os.path.basename(githubFile)])

    logger.info("\n=== sensor bulk verification ===")
    verifySensorBulk(assetIDs, assetList, sensorBulkFile)

    if skip_cal:
        logger.info("\n=== calibration verification skipped ===")
    else:
        logger.info("\n=== calibration verification ===")
        verifyCalibrations(repos, githubFiles, vendorStems, assetIDs, HITLcal,
                           coeffMap, constants, calVerifyFile, missingCalFile)

    logger.info("\n=== deployment sheet checks ===")
    checkDeploymentSheets(deployments, sensorList, platformList, cruiseList)

    logger.info("\n=== deployment verification ===")
    applyHITL(refDes, HITLdeploy)
    assignCalFiles(refDes, sensorCals)
    applyRawSerials(refDes, pd.read_csv(rawInput))
    verifyRawSerials(refDes, assetIDs)
    checkImageSerials(pd.read_csv(imageSN), assetIDs)

    fuzzy = pd.read_csv(fuzzyHITL)
    fuzzy["matching_asset_ids"] = fuzzy["matching_asset_ids"].str.strip("[]'")
    fuzzy["matching_mfg_sn"] = fuzzy["matching_mfg_sn"].str.strip("[]'")
    fuzzy = fuzzy[["referenceDesignator", "imageFile", "deployYear",
                   "matching_mfg_sn", "matching_asset_ids"]].rename(
        columns={"matching_mfg_sn": "imageSerialNumber",
                 "matching_asset_ids": "imageAssetID"})
    applyImageAssets(refDes, fuzzy)

    requiringCalibration = repos.sensorDirs(repos.am + "/calibration",
                                            AM_HEAD + "/calibration", "calibration/")
    assignStatus(refDes, requiringCalibration)
    writeDeploymentVerification(refDes, deployVerifyFile, year)

    logger.info("\nwrote " + deployVerifyFile)
    logger.info("\nnext: work through %s by hand, starting with the mismatches above.\n"
                "Record decisions in 2i_HITL/2i_HITL_deploymentVerification.csv"
                % os.path.basename(deployVerifyFile))


def checkImageSerials(imageList, assetIDs):
    """Sanity-check the imageSN csv before its curated form is used."""
    for _, image in imageList.iterrows():
        hasSN = not pd.isnull(image["imageSerialNumber"])
        hasAsset = not pd.isnull(image["imageAssetID"])
        if hasAsset and not hasSN:
            logger.warning("  %s: assetID but no serial number" % image["referenceDesignator"])
        elif hasSN and not hasAsset:
            logger.warning("  %s: serial number but no assetID" % image["referenceDesignator"])
        elif hasSN and hasAsset:
            if image["imageAssetID"] not in assetIDs:
                logger.warning("  %s: assetID %s is not in sensorBulk"
                               % (image["referenceDesignator"], image["imageAssetID"]))
            elif not any(part in str(assetIDs[image["imageAssetID"]])
                         for part in str(image["imageSerialNumber"]).split(",")):
                logger.warning("  %s: serial %s does not belong to %s"
                               % (image["referenceDesignator"], image["imageSerialNumber"],
                                  image["imageAssetID"]))


if __name__ == "__main__":
    main()
