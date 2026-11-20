#!/bin/bash
set -e

NANO_RELEASE=CMSSW_15_0_10
# Used when mini_cfg.py is shipped (2022): PAT in SPLIT_MINI_RELEASE, NANO in NANO_RELEASE
SPLIT_MINI_RELEASE=CMSSW_13_0_13
SPLIT_MINI_COMPILER=gcc11

echo "==== step1 (LHE,GEN,SIM) $(date)"
cmsRun -e -j FrameworkJobReport.xml PSet.py

echo "==== step2 (DIGI,DATAMIX,L1,DIGI2RAW,HLT) $(date)"
cmsRun -e -j FrameworkJobReport.xml step2_cfg.py
rm -f step1.root

echo "==== step3 (RECO) $(date)"
cmsRun -e -j FrameworkJobReport.xml step3_cfg.py
rm -f step2.root

OS=${SCRAM_ARCH%%_*}
if [ -f mini_cfg.py ]; then
    echo "==== step4 (PAT) in ${SPLIT_MINI_RELEASE} $(date)"
    (
        source /cvmfs/cms.cern.ch/cmsset_default.sh
        export SCRAM_ARCH=${OS}_amd64_${SPLIT_MINI_COMPILER}
        scram project -n split_mini_release CMSSW ${SPLIT_MINI_RELEASE}
        cd split_mini_release/src
        eval $(scram runtime -sh)
        cd ../..
        cmsRun -e -j FrameworkJobReport.xml mini_cfg.py
    )
    rm -f step3.root
    LAST_CFG=nano_cfg.py
    echo "==== step5 (NANO) in ${NANO_RELEASE} $(date)"
else
    LAST_CFG=step4_cfg.py
    echo "==== step4 (PAT,NANO) in ${NANO_RELEASE} $(date)"
fi
(
    source /cvmfs/cms.cern.ch/cmsset_default.sh
    export SCRAM_ARCH=${OS}_amd64_gcc12
    scram project -n mini_release CMSSW ${NANO_RELEASE}
    cd mini_release/src
    eval $(scram runtime -sh)
    cd ../..
    cmsRun -e -j FrameworkJobReport.xml ${LAST_CFG}
    # CRAB reads the output PSet hash from the FJR, else runs edmProvDump in the submit release,
    # which cannot read files written by ${NANO_RELEASE}
    psethash=$(edmProvDump miniaod.root | python3 -c "
import re, sys
found, depth, best = False, -1, ''
for line in sys.stdin:
    line = line.rstrip()
    if not found:
        found = line == 'Processing History:'
        continue
    m = re.match(r'(\s+).*\(([a-f0-9]{32})\)$', line)
    if not m:
        break
    if len(m.group(1)) >= depth:
        depth, best = len(m.group(1)), m.group(2)
print(best)
")
    [ -n "${psethash}" ] || { echo "no PSet hash found in miniaod.root"; exit 1; }
    sed -i "0,/<FrameworkJobReport>/s//<FrameworkJobReport>\n<Process><ParameterSetID>${psethash}<\/ParameterSetID><\/Process>/" FrameworkJobReport.xml
)
rm -f step3.root

echo "==== done $(date)"
ls -la
