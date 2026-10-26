source /cvmfs/cms.cern.ch/cmsset_default.sh
cmsenv
source /cvmfs/cms.cern.ch/common/crab-setup.sh
for m in 400 800 1200 2400; do for c in 0p1 1 10 100 1000; do
  f=crab_stop_to_lb_M_${m}_ctau_${c}mm_cfg.py
  echo "=== $f"
  crab submit -c $f 2>&1 | grep -E "Success|Error|error|Task name"
done; done
echo ALLDONE
