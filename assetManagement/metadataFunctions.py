#!/usr/local/bin/python3

# -*- coding: utf-8 -*-



# import packages

import ast
from bs4 import BeautifulSoup
import csv
import datetime
import glob
import numpy as np
import os
import pandas as pd
import re
import requests
import subprocess
import xml.etree.ElementTree as ET






def compareCalCoefficients(githubCal, googleDriveFile, CalCoeff_dict, CalConstants_dict):

    calCompare = ['NAN']

    CTDid = ['66662','69828','69827','67627']
    DOFSTAid = ['58694']
    FLNTUid = ['70110']
    FLCDRid = ['70111']
    FLORDid = ['58322']
    NUTNRid = ['68020']
    OPTAAid = ['69943','58332']
    PARAid = ['66645','78452']
    SPKIRid = ['58341']
    
    if any(assetID in googleDriveFile for assetID in CTDid):
        calCompare = ['COMPARED']
        sensor = 'CTD'
        # read in google drive xmlcon
        if os.path.isfile(googleDriveFile + '.xmlcon'):
            googleDriveCal = ET.parse(googleDriveFile + '.xmlcon')
            root = googleDriveCal.getroot()
            for calCoeff, row in githubCal.iterrows():
                github_coeff = row['value']
                if row['name'] in CalConstants_dict[sensor]:
                    xmlcon_coeff = float(CalConstants_dict[sensor][row['name']])
                else:
                    #print(fileName)
                    xmlcon_coeffName = CalCoeff_dict[row['name']][1]
                    elemTag = "Instrument/SensorArray/Sensor/" + CalCoeff_dict[row['name']][0] + "Sensor/"
                    for elem in root.findall(elemTag):
                        for subElem in elem.iter():
                            if subElem.tag == xmlcon_coeffName:
                                xmlcon_coeff = float(subElem.text)
                coeffDiff = (github_coeff - xmlcon_coeff)

                if coeffDiff != 0:
                    calCompare[0] = 'MISMATCH'
                    calCompare.append([googleDriveFile, row['name'], github_coeff, xmlcon_coeff, coeffDiff])

        elif os.path.isfile(googleDriveFile + '.cal'):
            vendorCals = parseVendorCal(googleDriveFile + '.cal',sensor)
            for calCoeff, row in githubCal.iterrows():
                github_coeff = row['value']
                if row['name'] in CalConstants_dict[sensor]:
                    vendor_coeff = CalConstants_dict[sensor][row['name']]
                else:
                    #vendor_coeffName = CalCoeff_dict[row['name']][1]
                    vendor_coeff = float(vendorCals[row['name']])

            coeffDiff = (github_coeff - vendor_coeff)
            if coeffDiff != 0:
                calCompare[0] = 'MISMATCH'
                calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])

        elif os.path.isfile(googleDriveFile + '.pdf'):
            calCompare[0] = 'PDF_NOTCOMPARED' 
        
    elif any(assetID in googleDriveFile for assetID in DOFSTAid):
        calCompare = ['COMPARED']
        sensor = 'DOFSTA'
        if os.path.isfile(googleDriveFile + '.cal'):
            vendorCals = parseVendorCal(googleDriveFile + '.cal',sensor)
            for calCoeff, row in githubCal.iterrows():
                github_coeff = row['value']
                if row['name'] in CalConstants_dict[sensor]:
                    vendor_coeff = CalConstants_dict[sensor][row['name']]
                else:
                    vendor_coeffName = CalCoeff_dict[row['name']][1]
                    vendor_coeff = float(vendorCals[vendor_coeffName])

            coeffDiff = (github_coeff - vendor_coeff)
            if coeffDiff != 0:
                calCompare[0] = 'MISMATCH'
                calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])

        elif os.path.isfile(googleDriveFile + '.xml'):
            calCompare = ['COMPARED_XML']
            googleDriveCal = ET.parse(googleDriveFile + '.xml')
            root = googleDriveCal.getroot()
            for calCoeff, row in githubCal.iterrows():
                github_coeff = row['value']
                if row['name'] in CalConstants_dict[sensor]:
                    xml_coeff = float(CalConstants_dict[sensor][row['name']])
                else:
                    #print(fileName)
                    xml_coeffName = CalCoeff_dict[row['name']][1]
                    elemTag = 'CalibrationCoefficients'
                    for elem in root.findall(elemTag):
                        if float(elem.get('equation')) == 1:
                            for subElem in elem.iter():
                                if subElem.tag == xml_coeffName:
                                    xml_coeff = float(subElem.text)

                coeffDiff = (github_coeff - xml_coeff)

                if coeffDiff != 0:
                    calCompare[0] = 'MISMATCH'
                    calCompare.append([googleDriveFile, row['name'], github_coeff, xml_coeff, coeffDiff])
        elif os.path.isfile(googleDriveFile + '.pdf'):
            calCompare[0] = 'PDF_NOTCOMPARED'
        
    elif any(assetID in googleDriveFile for assetID in FLNTUid):
        calCompare = ['COMPARED']
        sensor = 'FLNTU'
        if os.path.isfile(googleDriveFile + '.dev') or os.path.isfile(googleDriveFile + '.dev.lambda'):
            if os.path.isfile(googleDriveFile + '.dev.lambda'):
                fileSuffix = '.dev.lambda'
            else:
                fileSuffix = '.dev'
            vendorCals = parseVendorCal(googleDriveFile + fileSuffix, sensor)
            for calCoeff, row in githubCal.iterrows():
                github_coeff = float(row['value'])
                if row['name'] in CalConstants_dict[sensor]:
                    vendor_coeff = float(CalConstants_dict[sensor][row['name']])
                else:
                    vendor_coeff = float(vendorCals[row['name']])
                coeffDiff = (github_coeff - vendor_coeff)
                if coeffDiff != 0:
                    calCompare[0] = 'MISMATCH'
                    calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])
        elif os.path.isfile(googleDriveFile + '.pdf'):
            calCompare[0] = 'PDF_NOTCOMPARED'
        
    elif any(assetID in googleDriveFile for assetID in FLCDRid):
        calCompare = ['COMPARED']
        sensor = 'FLCDR'
        if os.path.isfile(googleDriveFile + '.dev'):
            vendorCals = parseVendorCal(googleDriveFile + '.dev', sensor)
            for calCoeff, row in githubCal.iterrows():
                github_coeff = float(row['value'])
                vendor_coeff = float(vendorCals[row['name']])
                coeffDiff = (github_coeff - vendor_coeff)
                if coeffDiff !=0:
                    calCompare[0] = 'MISMATCH'
                    calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])
        elif os.path.isfile(googleDriveFile + '.pdf'):
            calCompare[0] = 'PDF_NOTCOMPARED'

    elif any(assetID in googleDriveFile for assetID in FLORDid):
        calCompare = ['COMPARED']
        sensor = 'FLORD'
        if os.path.isfile(googleDriveFile + '.dev') or os.path.isfile(googleDriveFile + '.dev.lambda'):        
            if os.path.isfile(googleDriveFile + '.dev.lambda'):
                fileSuffix = '.dev.lambda'
            else:
                fileSuffix = '.dev'
            vendorCals = parseVendorCal(googleDriveFile + fileSuffix, sensor)
            for calCoeff, row in githubCal.iterrows():
                github_coeff = float(row['value'])
                if row['name'] in CalConstants_dict[sensor]:
                    vendor_coeff = float(CalConstants_dict[sensor][row['name']])
                else:
                    vendor_coeff = float(vendorCals[row['name']])
                coeffDiff = (github_coeff - vendor_coeff)
                if coeffDiff != 0:
                    calCompare[0] = 'MISMATCH'
                    calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])
        elif os.path.isfile(googleDriveFile + '.pdf'):
            calCompare[0] = 'PDF_NOTCOMPARED'
 
    elif any(assetID in googleDriveFile for assetID in NUTNRid):
        calCompare = ['COMPARED']
        sensor = 'NUTNR'
        if os.path.isfile(googleDriveFile + '.cal'):
            vendorCals = parseVendorCal(googleDriveFile + '.cal', sensor)
            for calCoeff, row in githubCal.iterrows():
                if '[' in row['value']:
                    github_coeff = ast.literal_eval(row['value'])
                else:
                    github_coeff = float(row['value'])
                if row['name'] in CalConstants_dict[sensor]:
                    vendor_coeff = float(CalConstants_dict[sensor][row['name']])
                else:
                    vendor_coeff = vendorCals[row['name']]
                if isinstance(github_coeff,list):
                    coeffDiff = set(github_coeff).symmetric_difference(vendor_coeff)
                else:
                    coeffDiff = github_coeff - vendor_coeff
                if coeffDiff:
                    if coeffDiff != 0:
                        calCompare[0] = 'MISMATCH'
                        calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])

    elif any(assetID in googleDriveFile for assetID in OPTAAid):
        pass
    elif any(assetID in googleDriveFile for assetID in PARAid):
        calCompare = ['COMPARED']
        sensor = 'PARA'
        if os.path.isfile(googleDriveFile + '.tdf'):
            vendorCals = parseVendorCal(googleDriveFile + '.tdf', sensor)
            #print(vendorCals)
            if 'CC_a0' in vendorCals:
                for calCoeff, row in githubCal.iterrows():
                    github_coeff = row['value']
                    vendor_coeff = float(vendorCals[row['name']])
                    coeffDiff = (github_coeff - vendor_coeff)
                    if coeffDiff != 0:
                        calCompare[0] = 'MISMATCH'
                        calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])
        elif os.path.isfile(googleDriveFile + '.pdf'):
            calCompare[0] = 'PDF_NOTCOMPARED'

    elif any(assetID in googleDriveFile for assetID in SPKIRid):
        calCompare = ['COMPARED']
        sensor = 'SPKIR'
        if os.path.isfile(googleDriveFile + '.cal'):
            vendorCals = parseVendorCal(googleDriveFile + '.cal', sensor)
            #print(vendorCals)
            if 'CC_scale' in vendorCals:
                if vendorCals['CC_scale']:
                    for calCoeff, row in githubCal.iterrows():
                        github_coeff = ast.literal_eval(row['value'])
                        vendor_coeff = vendorCals[row['name']]
                        coeffDiff = set(github_coeff).symmetric_difference(vendor_coeff)
                        if coeffDiff:
                            calCompare[0] = 'MISMATCH'
                            calCompare.append([googleDriveFile, row['name'], github_coeff, vendor_coeff, coeffDiff])
    
    return calCompare






def createFileList(refDesg):
    ## This subroutine returns a list of filenames and associated filedates for all directories 
    ## on the OOI online raw repository for a given Reference Designator
    fileList = []
    ## Define url base for the OOI online raw repository
    rawURLbase = 'https://rawdata.oceanobservatories.org/files/'
    ## Extract Site, Node, and Instrument information from Reference Designator
    rf_site = refDesg[0:8]
    rf_node = refDesg[9:14]
    rf_instrument = refDesg[18:27]
    rf_instrument_partial = refDesg[18:23]
    print(rf_site + ' ' + rf_node + ' ' + rf_instrument)
    ## Build top level directory URL
    nodeURL = rawURLbase + rf_site + '/' + rf_node
    ## Create file list for top directory and 2 subsequent sub-directories,
    ## following the directory structure of year and month subdirectoreis,
    ## with some older files (2014-2017) collected in the top level'
    ## TODO: refine code to allow for a variable number of sub-directories,
    ## as some files are sorted into day folders as well.  (This code does not include
    ## those sensors, so it has not been an issue thus far...)
    ###print('time before listFD: ', datetime.datetime.now())
    nodeFileList, nodeFolderList = listFD(nodeURL)
    ###print('time after listFD: ', datetime.datetime.now())
    if nodeFileList:
        for dataFile in nodeFileList:
            if rf_instrument_partial in dataFile:
                fileList.append(dataFile)
    if nodeFolderList:
        for instFolder in nodeFolderList:
            if rf_instrument in instFolder:
                ###print('time before listFD: ', datetime.datetime.now())
                instFileList, instFolderList = listFD(instFolder)
                ###print('time after listFD: ', datetime.datetime.now())
                if instFileList:
                    fileList = fileList + instFileList
                if instFolderList:
                    for subFolder in instFolderList:
                        if not re.search(r".*\/\/files.*",subFolder):
                            print("searching subfolder: " + subFolder)
                            ###print('time before listFD: ', datetime.datetime.now())
                            instFileList_sub1, instFolderList_sub1 = listFD(subFolder)
                            ###print('time after listFD: ', datetime.datetime.now())
                            if instFileList_sub1:
                                fileList = fileList + instFileList_sub1
                            if instFolderList_sub1:
                                for sub_subFolder in instFolderList_sub1:
                                    if re.search(r".*\/\/files.*",sub_subFolder):
                                        print("invalid folder: " + sub_subFolder)
                                    else:
                                        print("searching: " + sub_subFolder)
                                        ###print('time before listFD: ', datetime.datetime.now())
                                        instFileList_sub2, instFolderList_sub2 = listFD(sub_subFolder)
                                        ###print('time after listFD: ', datetime.datetime.now())
                                        if instFileList_sub2:
                                            fileList = fileList + instFileList_sub2   
    fileDates = []
    ## Extract filedate from filename and convert to datetime format
    for entry in fileList:
        fileDateStringLine1 = re.search(r".*_(\d{8}T\d{4})_UTC.*",entry)
        fileDateStringLine2 = re.search(r".*_(\d{8})_UTC.*",entry)
        if fileDateStringLine1:
            rawFileDate =  datetime.datetime.strptime(fileDateStringLine1.group(1), '%Y%m%dT%H%M')
        elif fileDateStringLine2:
            rawFileDate =  datetime.datetime.strptime(fileDateStringLine2.group(1), '%Y%m%d') 
        fileDates.append(rawFileDate)
        
    ## Zip filedates and filenames into single list
    combinedFileList = zip(fileDates,fileList)
    
    return combinedFileList




            

def createFileList_DP(refDesg):
    ## This subroutine returns a list of filenames and associated filedates for all serial number 
    ## files on the OOI online raw repository for a given Deep Profiler Reference Designator
    fileList = []
    fileString = 'sernums_hi-res_'
    ## Define url base for the OOI online raw repository
    rawURLbase = 'https://rawdata.oceanobservatories.org/files/'
    ## Extract Site, Node information from Reference Designator
    rf_site = refDesg[0:8]
    rf_node = refDesg[9:14].replace('DP','PD')
    
    ## Build top level directory URL
    nodeURL = rawURLbase + rf_site + '/' + rf_node + '/' + 'eng_data' + '/'
    #####print('nodeURL: ' + nodeURL)
    ## Create file list for top directory and 2 subsequent sub-directories,
    ## following the directory structure of year and month subdirectoreis,
    ###print('time before listFD: ', datetime.datetime.now())
    nodeFileList, nodeFolderList = listFD(nodeURL)
    #####print(nodeFolderList)
    ###print('time after listFD: ', datetime.datetime.now())
    if nodeFolderList:
        for yearFolder in nodeFolderList:
            if not re.search(r".*\/\/files.*",yearFolder) and re.search(r".*202.*",yearFolder):
                #####print('yearFolder:')
                #####print(yearFolder)
                monthFileList, monthFolderList = listFD(yearFolder)
                for monthFolder in monthFolderList:
                    if not re.search(r".*\/\/files.*",monthFolder):
                        #####print('monthFolder:')
                        #####print(monthFolder)
                        dayFileList, dayFolderList = listFD(monthFolder)
                        for dayFolder in dayFolderList:
                            if not re.search(r".*\/\/files.*",dayFolder):
                                #####print('dayFolder:')
                                #####print(dayFolder)
                                dayFileList, dayFolderList = listFD(dayFolder)
                                if dayFileList:
                                    for dayFile in dayFileList:
                                        if fileString in dayFile:
                                            fileList.append(dayFile)

    
    fileDates = []
    ## Extract filedate from filename and convert to datetime format
    #####print(fileList)
    for entry in fileList:
        fileDateStringLine = re.search(r".*_(\d{8}T\d{6})_UTC.*",entry)
        if fileDateStringLine:
            rawFileDate =  datetime.datetime.strptime(fileDateStringLine.group(1), '%Y%m%dT%H%M%S')
            fileDates.append(rawFileDate)
        else:
            rawFileDate = '-99999'
        
    ## Zip filedates and filenames into single list
    combinedFileList = zip(fileDates,fileList)
    
    return combinedFileList






def listFD(url):
    ## This subroutine returns a directory listing of filenames and folders parsed
    ## for a given URL 
    page = requests.get(url).text
    soup = BeautifulSoup(page, 'html.parser')
    
    if url.endswith('/'):
        fileList = [url + node.get('href') for node in soup.find_all('a') if node.get('href').endswith('t')]
        folderList = [url + node.get('href') for node in soup.find_all('a') if node.get('href').endswith('/')]
    else:
        fileList = [url + '/' + node.get('href') for node in soup.find_all('a') if node.get('href').endswith('t')]
        folderList = [url + '/' + node.get('href') for node in soup.find_all('a') if node.get('href').endswith('/')]

    #print('fileList length: ', len(fileList))
    #print('folderList length: ', len(folderList))

    return fileList, folderList


def parseVendorCal(fileName,sensor):
    # TODO: test to make sure variables are not empty
    vendorCals = {}
    vendorCals['fileName']=fileName
    if "xml" in fileName:
        if "CTD" in sensor:
            print("parse CTD values")
            ##tree = ET.parse(fileName)
            ##root = tree.getroot()
    elif "cal" in fileName or "dev" in fileName or "tdf" in fileName:
        with open(fileName, errors = 'ignore') as fp:
            for line in fp:
                if "CTD" in sensor:
                    mat = re.match(r"(\S+)=\s*(\S+).*",line)
                    if mat is not None:
                        excludeList = ['C1','C2','C3','D1','D2','T1','T2','T3','T4','T5']
                        calName = mat.group(1)
                        if calName not in excludeList:
                            calName = mat.group(1).lower()
                            tempList = ['ta0','ta1','ta2','ta3']
                            if calName in tempList:
                                calName = calName.replace('t','')
                            condList = ['cg','ch','ci','cj']
                            if calName in condList:
                                calName = calName.replace('c','')
                        vendorCals['CC_' + calName] = mat.group(2)

                if "DOFSTA" in sensor:
                    if "SOC=" in line:
                        mat = re.match(r"^SOC=\s*(\S+)",line)
                        if mat is None:
                            print('no match for Soc!')
                        else:
                            vendorCals['Soc'] = mat.group(1)
                    elif "VOFFSET=" in line:
                        mat = re.match(r"^VOFFSET=\s*(\S+)",line)
                        if mat is None:
                            print('no match for voffset!')
                        else:
                            vendorCals['offset'] = mat.group(1)
                    elif "A=" in line:
                        mat = re.match(r"^A=\s*(\S+)",line)
                        if mat is None:
                            print('no match for A!')
                        else:
                            vendorCals['A'] = mat.group(1)
                    elif "B=" in line:
                        mat = re.match(r"^B=\s*(\S+)",line)
                        if mat is None:
                            print('no match for B!')
                        else:
                            vendorCals['B'] = mat.group(1)
                    elif "C=" in line: 
                        mat = re.match(r"^C=\s*(\S+)",line)
                        if mat is None:
                            print('no match for C!')
                        else:
                            vendorCals['C'] = mat.group(1)
                    elif "E=" in line:
                        if re.search(r"^E=.*",line):
                            mat = re.match(r"^E=\s*(\S+)",line)
                            if mat is None:
                                print('no match for E!')
                            else:
                                vendorCals['E'] = mat.group(1)
                    elif "Tau20=" in line:
                        mat = re.match(r"^Tau20=\s*(\S+)",line)
                        if mat is None:
                            print('no match for Tau20!')
                        else:
                            vendorCals['Tau20'] = mat.group(1)

                if "FLCDR" in sensor:
                    if "CDOM" in line:
                        mat = re.match(r"^CDOM=\d\s*(\S+)\s*(\S+)",line)
                        if mat is not None:
                            vendorCals['CC_scale_factor_cdom'] = mat.group(1)
                            vendorCals['CC_dark_counts_cdom'] = mat.group(2)

                if "FLNTU" in sensor:
                    if ".lambda" not in fileName:
                        vendorCals['CC_scale_factor_volume_scatter'] = "NAN"
                        vendorCals['CC_dark_counts_volume_scatter'] = "NAN"
                        vendorCals['CC_measurement_wavelength'] = "NAN"
                    if "Chl=" in line:
                        mat = re.match(r"^Chl=4\s*(\S+)\s*(\S+)",line)
                        if mat is not None:
                            if 'CC_scale_factor_chlorophyll_a' in vendorCals:
                                if vendorCals['CC_scale_factor_chlorophyll_a'] == mat.group(1):
                                    print('duplicate values...ignoring second set')
                                else:
                                    print('not duplicate values!!!')
                            else:
                                vendorCals['CC_scale_factor_chlorophyll_a'] = mat.group(1)
                                vendorCals['CC_dark_counts_chlorophyll_a'] = mat.group(2)
                    if "lambda=" in line or "Lambda" in line:
                        mat = re.match(r"^lambda=6\s*(\S+)\s*(\S+)\s*(\S+)\s*.*",line,re.I)
                        if mat is not None:
                            vendorCals['CC_scale_factor_volume_scatter'] = mat.group(1)
                            vendorCals['CC_dark_counts_volume_scatter'] = mat.group(2)
                            vendorCals['CC_measurement_wavelength'] = mat.group(3)

                if "FLORD" in sensor:
                    if "LAMBDA" in line or "lambda" in line or "Lambda" in line:
                        mat = re.match(r"^lambda=4\s*(\S+)\s*(\S+)\s*(\S+)\s*.*",line,re.I)
                        if mat is not None:
                            vendorCals['CC_scale_factor_volume_scatter'] = mat.group(1)
                            vendorCals['CC_dark_counts_volume_scatter'] = mat.group(2)
                            vendorCals['CC_measurement_wavelength'] = mat.group(3)
                    if "CHL" in line or "chl" in line or "Chl" in line:
                        mat = re.match(r"^Chl=6\s*(\S+)\s*(\S+)",line, re.I)
                        if mat is not None:
                            vendorCals['CC_scale_factor_chlorophyll_a'] = mat.group(1)
                            vendorCals['CC_dark_counts_chlorophyll_a'] = mat.group(2)
                    if "CDOM" in line or "cdom" in line or "Cdom" in line:
                        mat = re.match(r"^CDOM=8\s*(\S+)\s*(\S+)",line, re.I)
                        if mat is not None:
                            vendorCals['CC_scale_factor_cdom'] = mat.group(1)
                            vendorCals['CC_dark_counts_cdom'] = mat.group(2)
                if "NUTNR" in sensor:
                    if 'CC_di' not in vendorCals:
                        vendorCals['CC_wl'] = []
                        vendorCals['CC_eno3'] = []
                        vendorCals['CC_eswa'] = []
                        vendorCals['CC_di'] = []
                    matTemp1 = re.match(r"H,T_CAL\s+([-+]?\d*\.\d+|\d+).*",line)
                    matTemp2 = re.match(r"H,T_CAL_SWA\s+([-+]?\d*\.\d+|\d+).*",line)
                    if matTemp1 is not None:
                        vendorCals['CC_cal_temp'] = float(matTemp1.group(1))
                    if matTemp2 is not None:
                        vendorCals['CC_cal_temp'] = float(matTemp2.group(1))
                    mat = re.match(r"^E,([-+]?\d*\.\d+|\d+),([-+]?\d*\.\d+|\d+),([-+]?\d*\.\d+|\d+),([-+]?\d*\.\d+|\d+),([-+]?\d*\.\d+|\d+).*",line)
                    if mat is not None:
                        vendorCals['CC_wl'].append(float(mat.group(1)))
                        vendorCals['CC_eno3'].append(float(mat.group(2)))
                        vendorCals['CC_eswa'].append(float(mat.group(3)))
                        vendorCals['CC_di'].append(float(mat.group(5)))

                if "PARA" in sensor:
                    mat = re.match(r"^(\d+\.\d+)\s+(\d+\.\d+e-\d+)\s+(\d+\.\d+)\s*",line)                            
                    if mat is not None:
                        vendorCals['CC_a0'] = mat.group(1)
                        vendorCals['CC_a1'] = mat.group(2)
                        vendorCals['CC_Im'] = mat.group(3)
                
                if "SPKIR" in sensor:
                    if 'CC_scale' not in vendorCals:
                        vendorCals['CC_immersion_factor'] = []
                        vendorCals['CC_offset'] = []
                        vendorCals['CC_scale'] = []
                    mat = re.match(r"^(\d+\.\d+)\s+(\d+\.\d+e-\d+)\s+(\d+\.\d+)\s*",line)
                    if mat is not None:
                        vendorCals['CC_offset'].append(float(mat.group(1)))
                        vendorCals['CC_scale'].append(float(mat.group(2)))
                        vendorCals['CC_immersion_factor'].append(float(mat.group(3)))
                  

                                    
    return vendorCals                          

                             


def partialMatch(str1,str2,minCharacters):
    if len(str1) >= minCharacters and len(str2) > minCharacters:
        if str1 in str2 or str2 in str1:
            return True
        else:
            str1_partial = str1[len(str1)-minCharacters:len(str1)]
            if str1_partial in str2:
                return True
    else:
        return False


def rawFileMatchExtract(RefDes_dict):
    ## List sensors that produce binary data files
    binaryRaw = ['ADCP','OPTAA']
    ## Main loop start to iterate over each Reference Designator listed in the deployment sheets:
    for key,values in RefDes_dict.items():
        ## Filter to include all sensors listed in "rawCheckSensors",
        ## and exclude sensors in exclude lists (sensors and nodes)
        print ("creating file list for: " + key)
        ## Create list of filenames paired with filedates of all files on the raw archive for a
        ## given sensor in the main and sub-directories, then sort by date
        ###print('time before createFileList: ', datetime.datetime.now())
        if 'PD' in key and 'DP' in key:
            fileList = createFileList_DP(key)
        else:
            fileList = createFileList(key)
        ###print('time after createFileList: ', datetime.datetime.now())
        sortedFileList = sorted(fileList,key=lambda x: (x[0]))
        if sortedFileList:
            for deployment in RefDes_dict[key]:
                print(deployment['firstRawFile'])
                if 'nan' not in str(deployment['deployEnd']):
                    endDate = datetime.datetime.strptime(deployment['deployEnd'], '%Y-%m-%dT%H:%M:%S')
                else:
                    endDate = datetime.datetime.now()
                ### TODO: should this be x instead of x[0]?  am I getting the closest date???
                closestMatch = min(sortedFileList, key = lambda x:abs(x[0]-deployment['deployDate']))
                ###print('time before SNraw, first file: ', datetime.datetime.now())
                SNraw = SNfromFirstRaw(closestMatch[1])
                ###print('time after SNraw, first file: ', datetime.datetime.now())
                fileDate = closestMatch[0]
                if '-99999' not in SNraw and fileDate < endDate:
                    deployment['firstRawFile'] = closestMatch[1]
                    deployment['rawSN'] = SNraw
                else:
                    closestMatchIndex = sortedFileList.index(closestMatch)
                    if len(sortedFileList) > 1:
                        ###print('time before SNraw, first file: ', datetime.datetime.now())
                        SNraw = SNfromFirstRaw(sortedFileList[closestMatchIndex-1][1])
                        ###print('time after SNraw, first file: ', datetime.datetime.now())
                        fileDate = sortedFileList[closestMatchIndex-1][0]
                        if '-99999' not in SNraw and fileDate < endDate:
                            deployment['firstRawFile'] = sortedFileList[closestMatchIndex-1][1]
                            deployment['rawSN'] = SNraw
                        else:
                            if len(sortedFileList) > (closestMatchIndex+1):
                                ###print('time before SNraw, first file: ', datetime.datetime.now())
                                SNraw = SNfromFirstRaw(sortedFileList[closestMatchIndex+1][1])
                                ###print('time after SNraw, first file: ', datetime.datetime.now())
                                fileDate = sortedFileList[closestMatchIndex+1][0]
                                if '-99999' not in SNraw and fileDate < endDate:
                                    deployment['firstRawFile'] = sortedFileList[closestMatchIndex+1][1]
                                    deployment['rawSN'] = SNraw
                                else:
                                    #print sortedFileList[closestMatchIndex+3][1]
                                    #print "cannot find match in first raw...trying to extract sn from raw data line"
                                    if len(sortedFileList) > (closestMatchIndex+3):
                                        if sortedFileList[closestMatchIndex+3][0] > deployment['deployDate']:
                                            if any(sensor in key[18:27] for sensor in binaryRaw):
                                                ###print('time before SNraw, binary: ', datetime.datetime.now())
                                                SNraw = SNfromRawBinary(sortedFileList[closestMatchIndex+3][1])
                                                ###print('time after SNraw, binary: ', datetime.datetime.now())
                                                fileDate = sortedFileList[closestMatchIndex+3][0]
                                                if '-99999' not in SNraw and fileDate < endDate:
                                                    deployment['firstRawFile'] = sortedFileList[closestMatchIndex+3][1]
                                                    deployment['rawSN'] = SNraw
                                                else:
                                                    #print "no serial number in binary file...trying one more file..."
                                                    if len(sortedFileList) > (closestMatchIndex+5):
                                                        ###print('time before SNraw, binary: ', datetime.datetime.now())
                                                        SNraw = SNfromRawBinary(sortedFileList[closestMatchIndex+5][1])
                                                        ###print('time after SNraw, binary: ', datetime.datetime.now())
                                                        fileDate = sortedFileList[closestMatchIndex+5][0]
                                                        if '-99999' not in SNraw and fileDate < endDate:
                                                            deployment['firstRawFile'] = sortedFileList[closestMatchIndex+5][1]
                                                            deployment['rawSN'] = SNraw
                                            elif 'PD' in key and 'DP' in key:
                                                SNraw = SNfromDP(sortedFileList[closestMatchIndex+3][1],key)
                                                fileDate = sortedFileList[closestMatchIndex+3][0]
                                                if '-99999' not in SNraw and fileDate < endDate:
                                                    deployment['firstRawFile'] = sortedFileList[closestMatchIndex+3][1]
                                                    deployment['rawSN'] = SNraw
                                            else:
                                                #print(sortedFileList[closestMatchIndex+3][1])
                                                ###print('time before SNraw, raw file: ', datetime.datetime.now())
                                                SNraw = SNfromRaw(sortedFileList[closestMatchIndex+3][1])
                                                ###print('time after SNraw, raw file: ', datetime.datetime.now())
                                                fileDate = sortedFileList[closestMatchIndex+3][0]
                                                if '-99999' not in SNraw and fileDate < endDate:
                                                    deployment['firstRawFile'] = sortedFileList[closestMatchIndex+3][1]
                                                    deployment['rawSN'] = SNraw

    return (RefDes_dict)





def searchITM(RF_assignment, RF_key, ITM_dict):
    for key, values in ITM_dict.items():
        if any(RF_key[18:24] in instType.replace('-','') for instType in ITM_dict[key]['instrumentType']):
            if any(RF_assignment in assign for assign in ITM_dict[key]['assignments']):
                return key

   




def SNfromDP(rawFileName,sensor):
    ## This subroutine returns a serial number extracted from a deep profiler raw data file
    response = requests.get(rawFileName, stream=True)
    text = [ByteLine.decode('utf-8',errors='ignore') for ByteLine in response.iter_lines()]
    if 'ENG' in sensor:
        SNregex = re.compile(r".*DPC\s*(\d+).*$")
    if 'CTDPFL' in sensor:
        SNregex = re.compile(r".*ctd_1\s*(\d+).*$")
    if 'VEL3DA' in sensor:
        SNregex = re.compile(r".*acm_1\s*(\d+).*$")
    if 'FLCDRA' in sensor:
        SNregex = re.compile(r".*flcd_1\s*(\d+).*$")
    if 'FLNTUA' in sensor:
        SNregex = re.compile(r".*flntu_1\s*(\d+).*$")
    if 'DOSTAD' in sensor:
        SNregex = re.compile(r".*optode_1\s*(\d+).*$")

    for line in text:
        serialNumberLine = SNregex.search(line)
        if serialNumberLine:
            break
    
    if serialNumberLine:
        #####print(serialNumberLine)
        #####print(serialNumberLine.group(1))
        SN = serialNumberLine.group(1)                                                                 
    else:
        SN = '-99999'

    return SN






def SNfromFirstRaw(rawFileName):
    ## This subroutine returns a serial number extracted from a raw data file,
    ## specifically searching for the serial number reported by the sensor 
    ## during power-on.
    ## rawFileName is given as the URL to the file, which is downloaded in 
    ## chunks until a value is returned (or end of file is reached).
    ## A value of -99999 is returned if no valid serial number is found.
    SN = '-99999'
    ## stream file until valid regex matches a serial number, or EOF
    response = requests.get(rawFileName, stream=True)
    text = [ByteLine.decode('utf-8',errors='ignore') for ByteLine in response.iter_lines()]
    for line in text:
        if 'CTD' in rawFileName:
            serialNumberLine1 = re.search(r"<HardwareData.*SerialNumber\s=\s\'(\d{1,10})\'>",line)
            serialNumberLine2 = re.search(r"SerialNumber\s=\s'(\d{1,10})'>",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-4:len(serialNumberLine1.group(1))]
                break
            elif serialNumberLine2:
                SN = serialNumberLine2.group(1)[len(serialNumberLine2.group(1))-4:len(serialNumberLine2.group(1))]
                break
        elif 'SPKIR' in rawFileName:
            serialNumberLine1 = re.search(r"S\/N:\s+(\d{2,4})",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-3:len(serialNumberLine1.group(1))]
                break
        elif 'NUTNR' in rawFileName:
            serialNumberLine1 = re.search(r"SUNA\sSN:(\d{1,4}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-3:len(serialNumberLine1.group(1))]
                break
        elif 'FLOR' in rawFileName:
            serialNumberLine1 = re.search(r"Ser\s.*-(\d{1,4}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)
                break
        elif 'PREST' in rawFileName:
            serialNumberLine1 = re.search(r"SerialNumber=.*(\d{1,9}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-2:len(serialNumberLine1.group(1))]
                break   
        elif 'TMPSFA' in rawFileName:
            serialNumberLine1 = re.search(r"RBR\s+XR-420\s+\d.\d{2,4}\s+(\d{1,9}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-5:len(serialNumberLine1.group(1))]
                break      
        
    return SN



def SNfromRaw(rawFileName):
    ## This subroutine returns a serial number extracted from a raw data file,
    ## specifically searching for the serial number included in data lines.
    ## rawFileName is given as the URL to the file, which is downloaded in 
    ## chunks until a value is returned (or end of file is reached).
    ## A value of -99999 is returned if no valid serial number is found.
    SN = '-99999'
    ## stream file until valid regex matches a serial number, or EOF
    response = requests.get(rawFileName, stream=True)
    text = [ByteLine.decode('utf-8',errors='ignore') for ByteLine in response.iter_lines()]
    for line in text:
        if 'SPKIR' in rawFileName:
            serialNumberLine1 = re.search(r".*SATDI70(\d{3}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-3:len(serialNumberLine1.group(1))]
                break
        if 'NUTNR' in rawFileName:
            serialNumberLine1 = re.search(r"SATSDF(\d{1,4}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-3:len(serialNumberLine1.group(1))]
                break
        if 'PARAD' in rawFileName:
            ## TODO: this regex needs refining after the sensor bulk records are cleaned up...
            ### SerialNumber='05400030', !!! Serial number in bulk is 5471540-0030 !!!
            serialNumberLine1 = re.search(r"SATPAR(\d{1,4}).*",line)
            serialNumberLine2 = re.search(r"SATPRS(\d{1,4}).*",line)
            if serialNumberLine1:
                SN = serialNumberLine1.group(1)[len(serialNumberLine1.group(1))-3:len(serialNumberLine1.group(1))]
                break
            if serialNumberLine2:
                SN = serialNumberLine2.group(1)[len(serialNumberLine2.group(1))-3:len(serialNumberLine2.group(1))]
                break
    return SN



def SNfromRawBinary(rawFileName):
    ## This subroutine returns a serial number extracted from a binary raw data file,
    ## specifically searching for the serial number included in data lines.
    ## rawFileName is given as the URL to the file, of which a small chunk is downloaded.
    ## A value of -99999 is returned if no valid serial number is found.
    
    def parse(driver):
        ## This subroutine calls the mi.instrument playback with the sensor-appropriate driver.
        ## mi.instrument drivers are developed and maintained by CI on gitHub:
        ## https://github.com/oceanobservatories/mi-instrument
        response = requests.get(rawFileName, stream=True)
        downloadFile = re.search(r"https://\S+/\S+/\S+/\S+/(.*)",rawFileName).group(1)
        handle = open(downloadFile,'wb')
        ## Download first small section of file
        for chunk in response.iter_content(chunk_size=512*6):
            if chunk:
                handle.write(chunk)
                break
        handle.close()
        # calls mi playback function and params in the python2 mi environment
        # for this to work there must be a correctly configured mi env available
        # see README for step to build mi environment and mi.yml in this repo
        playback = 'python2 -m mi.core.instrument.playback datalog ' + driver + ' ' + refDes + ' log:// csv:// ' + downloadFile  
        playback_cmd = 'conda run -n mi ' + playback
        print(playback_cmd)
        processResults = subprocess.call(playback_cmd, shell=True)
        os.remove(downloadFile)
        return processResults
    
    SN = '-99999'
    refDes = 'emptyField'
    if 'ADCP' in rawFileName and 'VADCP' not in rawFileName:
        driver = 'mi.instrument.teledyne.workhorse.adcp.driver'   
        if parse(driver) == 0:
            if os.path.isfile('adcp_config.csv'):
                df = pd.read_csv('adcp_config.csv')
                SN = str(int(df.serial_number))  
                os.remove('adcp_config.csv')
            else:
                print('no file created')
                SN = '-99999'
    ## TODO: this driver returns without error, but does not produce files...
    if 'VADCP' in rawFileName:
        driver = 'mi.instrument.teledyne.workhorse.vadcp.driver'
        if parse(driver) == 0:
            if os.path.isfile('adcp_config.csv'):
                df = pd.read_csv('adcp_config.csv')
                SN = str(int(df.serial_number))  
                os.remove('adcp_config.csv')
            else:
                print('no file created')
                SN = '-99999'
    if 'OPTAA' in rawFileName:
        driver = 'mi.instrument.wetlabs.ac_s.ooicore.driver'
        if parse(driver) == 0:
            if os.path.isfile('optaa_sample.csv'):
                df = pd.read_csv('optaa_sample.csv',nrows=1)
                SN = str(int(df.serial_number))
                os.remove('optaa_sample.csv')
            else:
                print('no file created')
                SN = '-99999'
                
    ##### TODO: how do I get a string out of a dataframe without first going to an int?!?!?
    return SN




