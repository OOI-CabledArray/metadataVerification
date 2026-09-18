"""Cabled Array deployment sheets, loaded from a local asset-management clone.

Shared by the extract and verification steps so the reference designator ->
deployment mapping is defined in exactly one place.
"""

import datetime
import os

import pandas as pd

### assetManagement/, so params/ and reportOuts/ resolve no matter the cwd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CABLED_ARRAY = ['CE02SHBP', 'CE04OSBP', 'CE04OSPD', 'CE04OSPS', 'RS01SBPD', 'RS01SBPS',
                'RS01SLBS', 'RS01SUM1', 'RS03AXBS', 'RS03AXPD', 'RS03AXPS', 'RS03INT2',
                'RS03INT1', 'RS01SUM2', 'RS03CCAL', 'RS03ECAL', 'RS03ASHS']

### instruments whose serial number can be read out of a raw archive file
RAW_CHECK_SENSORS = ['CTD', 'SPK', 'NUT', 'PAR', 'FLOR', 'PREST', 'TMPSFA', 'OPTAA', 'ADCP']
RAW_CHECK_SENSORS_DP = ['ENG000000', 'VEL3DA105', 'FLCDRA103', 'FLNTUA103', 'DOSTAD105',
                        'VEL3DA103', 'FLCDRA102', 'FLNTUA102', 'DOSTAD104',
                        'VEL3DA303', 'FLCDRA302', 'FLNTUA302', 'DOSTAD304']

### binary raw files, parsed by the python2 mi-instrument playback drivers
BINARY_SENSORS = ['ADCP', 'OPTAA']

### MARUM PI sensor, no raw data in the archive
EXCLUDE_SENSORS = ['CTDPFA110']


def loadDeploymentSheets(amRepo):
    """Every Cabled Array deployment row as one dataframe."""
    sheets = [os.path.join(amRepo, 'deployment', array + '_Deploy.csv') for array in CABLED_ARRAY]
    return pd.concat([pd.read_csv(f, skip_blank_lines=True, comment='#') for f in sheets],
                     ignore_index=True)


def refDesDict(amRepo):
    """Reference designator -> list of its deployments, newest first."""
    df = loadDeploymentSheets(amRepo).sort_values(
        by=['Reference Designator', 'startDateTime'], ascending=False)

    refDes = {}
    for key in df['Reference Designator'].unique():
        refDes[key] = [{'deployDate': datetime.datetime.strptime(df['startDateTime'][j],
                                                                 '%Y-%m-%dT%H:%M:%S'),
                        'deployEnd': df['stopDateTime'][j],
                        'AssetID': df['sensor.uid'][j],
                        'deployNum': df['deploymentNumber'][j],
                        'calFile': 'none', 'calFile_verify': 'none', 'ITM_verify': 'none',
                        'firstRawFile': 'undef', 'rawSN': 'undef', 'rawFile_verify': 'none',
                        'imageAssetID': 'undef', 'image_verify': 'none'}
                       for j in df[df['Reference Designator'] == key].index]
    return refDes


def isRawCheckSensor(refDes):
    """Can this instrument's serial number be mined from the raw archive?"""
    instrument = refDes[18:27]
    if any(s in instrument for s in EXCLUDE_SENSORS):
        return False
    return (any(s in instrument for s in RAW_CHECK_SENSORS)
            or any(s in instrument for s in RAW_CHECK_SENSORS_DP))


def isBinarySensor(refDes):
    """Does this instrument need the python2 mi playback drivers?"""
    return any(s in refDes[18:27] for s in BINARY_SENSORS)
