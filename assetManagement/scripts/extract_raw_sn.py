#!/usr/bin/env python3
"""Mine instrument serial numbers out of the OOI raw data archive.

Each year's output is the next year's input, so only deployments that have not
already been resolved get crawled.  Run --dry-run first to see the work list.

\b
  ./extract_raw_sn.py --dry-run
  ./extract_raw_sn.py --am-repo ~/repos/asset-management
  ./extract_raw_sn.py --refdes RS01SLBS-LJ01A-12-CTDPFB101

Runs in the python3 env from verification.yml.  Binary sensors (ADCP/VADCP/OPTAA)
shell out to the python2 'mi-racle' env for the mi-instrument playback drivers, so
conda must be on PATH for those.
"""

import glob
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
import pandas as pd
from loguru import logger

import metadataFunctions as mf
from deployments import ROOT, isBinarySensor, isRawCheckSensor, refDesDict

HEADER = "referenceDesignator,deployYear,rawFile,rawSerialNumber\n"


def setupLogging(logFile=None):
    """Readable console, full detail on disk.

    The console carries progress only. The log file also captures every archive folder
    searched and every playback invocation, which is what you want months later when
    asking where a given serial number came from. A dry run passes no logFile, so it
    leaves nothing behind in params/.
    """
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<level>{message}</level>")
    if logFile:
        logger.add(logFile, level="DEBUG", mode="w",
                   format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}")
    return logFile


def newestInputFile(exclude=None):
    """Most recent params/rawFileSN_<date>.csv, which is last year's output.

    Skips this run's own output file, and any file holding nothing but a header. Either
    would otherwise be picked as the newest, carry nothing forward, and silently re-mine
    the whole archive instead of just this year's deployments.
    """
    dated = sorted(glob.glob(os.path.join(ROOT, "params", "rawFileSN_2*.csv")))
    if exclude:
        dated = [f for f in dated if os.path.abspath(f) != os.path.abspath(exclude)]
    dated = [f for f in dated if len(pd.read_csv(f))]
    if not dated:
        raise click.ClickException("no usable params/rawFileSN_*.csv found, pass --input explicitly")
    return dated[-1]


def buildWorkList(refDes, previous, refDesFilter=None, yearFilter=None):
    """Deployments with no serial number yet, as (refDes, year, deployment) rows."""
    resolved = set(zip(previous.referenceDesignator, previous.deployYear))
    work = []
    for key, deployments in refDes.items():
        for deployment in deployments:
            year = deployment["deployDate"].year
            if (key, year) in resolved or not isRawCheckSensor(key):
                continue
            if refDesFilter and refDesFilter not in key:
                continue
            if yearFilter and year != yearFilter:
                continue
            ### seed the miss sentinel, as the notebook did: an instrument that is mined
            ### and yields nothing is recorded as 'none,-99999' rather than dropped, so a
            ### searched-and-empty deployment stays distinguishable from one never tried
            deployment["rawSN"] = "-99999"
            deployment["firstRawFile"] = "none"
            work.append((key, year, deployment))
    return sorted(work, key=lambda row: (row[0], row[1]))


def printWorkList(work):
    logger.info("%d refdes-deployments to mine, %d unique reference designators\n"
                % (len(work), len({key for key, _, _ in work})))
    for key, year, _ in work:
        logger.info("  %s  %s%s" % (year, key, "  [mi-racle]" if isBinarySensor(key) else ""))


def writeRows(handle, key, deployments):
    """Append every resolved deployment of one reference designator."""
    for deployment in deployments:
        if "undef" not in deployment["firstRawFile"]:
            handle.write("%s,%s,%s,%s\n" % (key, deployment["deployDate"].strftime("%Y"),
                                            deployment["firstRawFile"], deployment["rawSN"]))
        handle.flush()


def elapsedSince(started):
    return "%dm%02ds" % divmod(int(time.time() - started), 60)


def reportResults(deployments, wantedYears):
    """Say what this reference designator resolved to. Returns (found, missed)."""
    found = missed = 0
    for deployment in sorted(deployments, key=lambda d: d["deployDate"]):
        year = deployment["deployDate"].year
        if year not in wantedYears:
            continue
        serialNumber = str(deployment["rawSN"])
        if "-99999" in serialNumber or "undef" in serialNumber:
            logger.warning("    %s  no serial number found in the archive" % year)
            missed += 1
        else:
            logger.success("    %s  SN %s" % (year, serialNumber))
            logger.info("          %s" % os.path.basename(deployment["firstRawFile"]))
            found += 1
    return found, missed


@click.command(help=__doc__)
@click.option(
    "--am-repo",
    type=click.Path(),
    default="~/repos/asset-management",
    show_default=True,
    help="Local asset-management clone, synced with the OOI remote.",
)
@click.option(
    "--input",
    "inputFile",
    type=click.Path(),
    default=None,
    help="Previous year's rawFileSN csv to carry forward. Default is the newest in params/.",
)
@click.option(
    "--output",
    "outputFile",
    type=click.Path(),
    default=None,
    help="Where to write results. Default is params/rawFileSN_<today>.csv.",
)
@click.option(
    "--refdes",
    type=str,
    default=None,
    help="Mine only reference designators containing this string.",
)
@click.option(
    "--year",
    type=int,
    default=None,
    help="Mine only deployments starting in this year.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the work list and exit, without crawling the raw archive.",
)
def main(am_repo, inputFile, outputFile, refdes, year, dry_run):
    amRepo = os.path.expanduser(am_repo)
    if not os.path.isdir(os.path.join(amRepo, "deployment")):
        raise click.ClickException("no deployment/ directory under " + amRepo)

    outputFile = outputFile or os.path.join(
        ROOT, "params", "rawFileSN_" + date.today().strftime("%Y%m%d") + ".csv")
    inputFile = inputFile or newestInputFile(exclude=outputFile)
    logFile = setupLogging(None if dry_run else os.path.splitext(outputFile)[0] + ".log")

    previous = pd.read_csv(inputFile)
    refDes = refDesDict(amRepo)
    work = buildWorkList(refDes, previous, refdes, year)

    logger.info("asset-management: " + amRepo)
    logger.info("deployment sheets: %d reference designators, %d deployments"
                % (len(refDes), sum(len(d) for d in refDes.values())))
    logger.info("carried forward:  %s (%d rows)" % (inputFile, len(previous)))
    logger.info("writing:          " + (outputFile if not dry_run else "nothing, dry run"))
    logger.info("full run log:     " + (logFile or "none, dry run") + "\n")
    printWorkList(work)

    if dry_run:
        return
    if not work:
        logger.info("\nnothing to mine")
        return

    ### carry last year's resolved serial numbers onto this year's deployment dict, so the
    ### output file stays cumulative rather than holding only what was mined today
    for key, deployments in refDes.items():
        for deployment in deployments:
            hit = previous[(previous.referenceDesignator == key)
                           & (previous.deployYear == deployment["deployDate"].year)]
            if len(hit):
                deployment["rawSN"] = hit.rawSerialNumber.iloc[0]
                deployment["firstRawFile"] = hit.rawFile.iloc[0]

    ### years wanted per reference designator, so the per-instrument report covers only
    ### what was actually asked for rather than every year that came back
    wanted = {}
    for key, workYear, _ in work:
        wanted.setdefault(key, set()).add(workYear)

    logger.info("\ncrawling rawdata.oceanobservatories.org, this takes a while.")

    started = time.time()
    totalFound = totalMissed = 0
    keys = sorted(wanted)
    with open(outputFile, "w") as handle:
        handle.write(HEADER)
        ### written as each reference designator finishes, so a run that dies partway
        ### through still leaves the instruments it did finish on disk
        for number, key in enumerate(keys, start=1):
            logger.info("\n=== [%d/%d] %s%s" % (number, len(keys), key,
                                        "  (needs mi-racle)" if isBinarySensor(key) else ""))
            instrumentStarted = time.time()
            deployments = mf.rawFileMatchExtract({key: refDes[key]})[key]
            found, missed = reportResults(deployments, wanted[key])
            totalFound += found
            totalMissed += missed
            logger.info("    done in %s, %s elapsed overall"
                        % (elapsedSince(instrumentStarted), elapsedSince(started)))
            writeRows(handle, key, deployments)

        ### everything carried over from previous years, appended after the new results
        for key, deployments in refDes.items():
            if key not in wanted:
                writeRows(handle, key, deployments)

    logger.info("\n%d serial numbers found, %d not in the archive, %s elapsed"
                % (totalFound, totalMissed, elapsedSince(started)))
    logger.info("wrote " + outputFile)
    logger.info("\nnext: point criticalMetaDataVerification.ipynb at this file, and add any new\n"
                "instruments to params/RCA-InstrumentList.csv")


if __name__ == "__main__":
    main()
