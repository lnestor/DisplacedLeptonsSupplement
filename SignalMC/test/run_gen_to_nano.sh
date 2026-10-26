#!/bin/bash
set -e

MINI_RELEASE=CMSSW_15_0_10

echo "==== step1 (LHE,GEN,SIM) $(date)"
cmsRun -e -j FrameworkJobReport.xml PSet.py

echo "==== step2 (DIGI,DATAMIX,L1,DIGI2RAW,HLT) $(date)"
cmsRun -e -j FrameworkJobReport.xml step2_cfg.py
rm -f step1.root

echo "==== step3 (RECO) $(date)"
cmsRun -e -j FrameworkJobReport.xml step3_cfg.py
rm -f step2.root

echo "==== step4 (PAT,NANO) in ${MINI_RELEASE} $(date)"
(
    source /cvmfs/cms.cern.ch/cmsset_default.sh
    scram project -n mini_release CMSSW ${MINI_RELEASE}
    cd mini_release/src
    eval $(scram runtime -sh)
    cd ../..
    cmsRun -e -j FrameworkJobReport.xml step4_cfg.py
)
rm -f step3.root

echo "==== done $(date)"
ls -la
