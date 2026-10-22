import argparse
import os
import re
import subprocess

import yaml

DATA_CRAB_TEMPLATE = """
from CRABClient.UserUtilities import config

config = config()

config.General.requestName = '{{ request_name }}'
config.General.workArea = 'crab_projects'
config.General.transferOutputs = True
config.General.transferLogs = True

config.JobType.pluginName = 'Analysis'
config.JobType.psetName = '{{ pset }}'
config.JobType.pyCfgParams = {{ py_cfg_params }}
config.JobType.outputFiles = ['supplement.root']
config.JobType.maxMemoryMB = 3000
config.JobType.numCores = 1
config.JobType.priority = {{ priority }}

config.Data.inputDataset = '{{ dataset }}'
config.Data.inputDBS = 'global'
config.Data.splitting = 'LumiBased'
config.Data.unitsPerJob = 400
config.Data.publication = False
config.Data.lumiMask = '{{ golden }}'
config.Data.outLFNDirBase = '/store/user/lnestor/'
config.Data.outputDatasetTag = '{{ request_name }}'

config.Site.storageSite = 'T3_US_FNALLPC'
"""

MC_CRAB_TEMPLATE = """
from CRABClient.UserUtilities import config

config = config()

config.General.requestName = '{{ request_name }}'
config.General.workArea = 'crab_projects'
config.General.transferOutputs = True
config.General.transferLogs = True

config.JobType.pluginName = 'Analysis'
config.JobType.psetName = '{{ pset }}'
config.JobType.pyCfgParams = {{ py_cfg_params }}
config.JobType.outputFiles = ['supplement.root']
config.JobType.maxMemoryMB = 3000
config.JobType.maxJobRuntimeMin = 200
config.JobType.numCores = 1
config.JobType.priority = {{ priority }}

config.Data.inputDataset = '{{ dataset }}'
config.Data.inputDBS = 'global'
config.Data.splitting = 'FileBased'
config.Data.unitsPerJob = 35
config.Data.publication = False
config.Data.outLFNDirBase = '/store/user/lnestor/'
config.Data.outputDatasetTag = '{{ request_name }}'

config.Site.storageSite = 'T3_US_FNALLPC'
"""

EOS_CRAB_TEMPLATE = """
from CRABClient.UserUtilities import config

config = config()

config.General.requestName = '{{ request_name }}'
config.General.workArea = 'crab_projects'
config.General.transferOutputs = True
config.General.transferLogs = True

config.JobType.pluginName = 'Analysis'
config.JobType.psetName = '{{ pset }}'
config.JobType.pyCfgParams = {{ py_cfg_params }}
config.JobType.outputFiles = ['supplement.root']
config.JobType.maxMemoryMB = 2500
config.JobType.maxJobRuntimeMin = 200
config.JobType.numCores = 1
config.JobType.priority = {{ priority }}

config.Data.userInputFiles = {{ input_files }}
config.Data.outputPrimaryDataset = '{{ primary_dataset }}'
config.Data.splitting = 'FileBased'
config.Data.unitsPerJob = 35
config.Data.publication = False
config.Data.outLFNDirBase = '/store/user/lnestor/'
config.Data.outputDatasetTag = '{{ request_name }}'

config.Site.storageSite = 'T3_US_FNALLPC'
config.Site.whitelist = {{ whitelist }}
"""

EOS_REDIRECTOR = "root://cmseos.fnal.gov"

# CRAB needs an explicit whitelist when running over userInputFiles (see the lpc-crab skill)
EOS_SITE_WHITELIST = [
    "T1_US_FNAL", "T1_FR_CCIN2P3", "T1_DE_KIT",
    "T2_IT_Rome", "T2_FI_HIP", "T2_IT_Bari", "T2_FR_IPHC", "T2_IT_Legnaro", "T2_DE_RWTH",
    "T2_UK_London_IC", "T2_CH_CSCS", "T2_DE_DESY", "T2_UK_SGrid_RALPP", "T2_US_Caltech",
    "T2_US_Wisconsin", "T2_US_Purdue",
    "T3_UK_London_QMUL", "T3_UK_London_RHUL", "T3_UK_SGrid_Oxford",
]

DATA_SAMPLES = ["EGamma", "MET", "MuonEG", "Muon"]

SAMPLE_PSETS = {
    "EGamma": "supplement_ee_cfg.py",
    "MuonEG": "supplement_emu_cfg.py",
    "Muon": "supplement_mumu_cfg.py",
    "MET": "supplement_met_cfg.py",
    "TTbar": "supplement_mc_cfg.py",
    "SingleTop": "supplement_mc_cfg.py",
    "DY": "supplement_mc_cfg.py",
    "Diboson": "supplement_mc_cfg.py",
    "QCDEle": "supplement_mc_cfg.py",
    "QCDMu": "supplement_mc_cfg.py",
    "Signal": "supplement_signal_cfg.py",
}

ALL_SAMPLES = ["EGamma", "MET", "Muon", "MuonEG", "TTbar", "SingleTop", "DY", "Diboson", "QCDEle", "QCDMu", "Signal"]
ALL_YEARS = ["2022preEE", "2022postEE", "2023preBPix", "2023postBPix", "2024", "2025", "2026"]
GOLDEN_JSONS = {
    "2022preEE": "https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions22/Cert_Collisions2022_355100_362760_Golden.json",
    "2022postEE": "https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions22/Cert_Collisions2022_355100_362760_Golden.json",
    "2023preBPix": "https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions23/Cert_Collisions2023_366442_370790_Golden.json",
    "2023postBPix": "https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions23/Cert_Collisions2023_366442_370790_Golden.json",
    "2024": "https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions24/Cert_Collisions2024_378981_386951_Golden.json",
    # Double check 2025 here, they have several to choose from. I chose the one with the most runs
    "2025": "https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions25/Cert_Collisions2025_391658_398903_Golden.json"
}

# Taken from summary slides on https://twiki.cern.ch/twiki/bin/viewauth/CMS/PdmVRun3Analysis
# (same map used in OSUNano/CustomNanoAOD/scripts/make_configs.py)
DATA_GLOBAL_TAGS = {
    "2022preEE": "130X_dataRun3_v2",
    "2022postEE": "130X_dataRun3_PromptAnalysis_v1",
    "2023preBPix": "130X_dataRun3_PromptAnalysis_v1",
    "2023postBPix": "130X_dataRun3_PromptAnalysis_v1",
    "2024": "150X_dataRun3_v2",
    "2025": "150X_dataRun3_Prompt_v1",
}

PRE_142X_MINIAOD_YEARS = {"2022preEE", "2022postEE", "2023preBPix", "2023postBPix"}

LOWERED_MUON_PT_YEARS = {"2025", "2026"}

# EGamma 2025 central NanoAOD keeps electrons/muons with pt exactly equal to
# a selector pt boundary, breaking the supplement join (a strict '>' cut here
# drops what central keeps). Only EGamma is affected, and only 2025 has been
# confirmed to need it.
EGAMMA_PT_BOUNDARY_FIX_YEARS = {"2025"}


def _yaml_year(year):
    for prefix in ("2022", "2023"):
        if year.startswith(prefix):
            return prefix + "_" + year[len(prefix):]
    return year


def list_eos_root_files(eos_dir):
    result = subprocess.run(["xrdfs", EOS_REDIRECTOR, "ls", "-R", eos_dir], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit("xrdfs ls -R {} failed:\n{}".format(eos_dir, result.stderr.strip()))
    paths = sorted(line.strip() for line in result.stdout.splitlines() if line.strip().endswith(".root"))
    if not paths:
        raise SystemExit("No .root files found under {}".format(eos_dir))
    names = [os.path.basename(p) for p in paths]
    if len(set(names)) != len(names):
        raise SystemExit("Duplicate file names under {}".format(eos_dir))
    return ["{}/{}".format(EOS_REDIRECTOR, p) for p in paths]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--samples",
        nargs="+",
        default=["all"],
        choices=ALL_SAMPLES + ["all"]
    )
    parser.add_argument(
        "--years",
        nargs="+",
        default=["all"],
        choices=ALL_YEARS + ["all"]
    )
    parser.add_argument("--dataset-definitions", default="../data/datasets_full.yaml")
    parser.add_argument("--output-dir", default="../test/")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument(
        "--priority", type=int, default=10,
        help="CRAB task priority (config.JobType.priority) for all configs generated in this "
             "invocation -- higher runs first among your own tasks. CRAB defaults to 10; run this "
             "script multiple times with different --samples/--years and --priority to stagger "
             "less-important resubmissions behind more important ones."
    )
    args = parser.parse_args()

    with open(args.dataset_definitions) as f:
        dataset_defs = yaml.safe_load(f)

    samples = ALL_SAMPLES if "all" in args.samples else args.samples
    years = ALL_YEARS if "all" in args.years else args.years
    yaml_years = {_yaml_year(y) for y in years}

    by_group = {}
    eos_entries = []
    for e in dataset_defs:
        if e["sample"] not in samples or e["year"] not in yaml_years:
            continue
        if e.get("type") == "eos":
            eos_entries.append(e)
        elif e.get("type") == "dataset":
            by_group.setdefault((e["sample"], e["year"], e.get("era")), []).append(e)
        else:
            raise SystemExit("Entry for {} has type {!r}, expected 'dataset' or 'eos': {}".format(
                e["sample"], e.get("type"), e["miniaod"]))

    entries = []
    for (sample, yaml_year, _era), group in by_group.items():
        year = yaml_year.replace("_", "")
        is_data = sample in DATA_SAMPLES
        if is_data:
            prim_counts = {}
            for e in group:
                prim = e["miniaod"].strip("/").split("/")[0]
                prim_counts[prim] = prim_counts.get(prim, 0) + 1
            for e in group:
                prim = e["miniaod"].strip("/").split("/")[0]
                entries.append((sample, year, e["miniaod"], prim_counts[prim] > 1, None))
        else:
            for e in group:
                entries.append((sample, year, e["miniaod"], False, e["global_tag"]))

    configs = []
    os.makedirs(args.output_dir, exist_ok=True)
    for sample, year, dataset, multi_version, mc_global_tag in entries:
        is_data = sample in DATA_SAMPLES
        prim_dataset, acq_block, _tier = dataset.strip("/").split("/")

        if is_data:
            # acq_block looks like 'Run2024I-MINIv6NANOv15_v2-v1' or
            # 'Run2023C-22Sep2023_v3-v1'. The run/era token alone collides
            # across reprocessing variants within the same era (e.g. 2023C
            # has _v1..._v4, 2024I has a plain and a _v2 variant), so pull
            # any trailing _vN off the processing tag and fold it in.
            acq_parts = acq_block.split("-")
            era = acq_parts[0]
            if year == "2025":
                # 2025 datasets use 'PromptReco' as the processing tag with
                # no embedded version, unlike 2023/2024I. The only
                # differentiator is the trailing DBS version (e.g. 'v1'),
                # which is present on every dataset regardless of whether
                # a reprocessing actually happened, so only fold it in when
                # this era genuinely has more than one dataset version.
                if multi_version:
                    era += "_" + acq_parts[-1]
            else:
                proc_tag = acq_parts[1] if len(acq_parts) > 1 else ""
                suffix_match = re.search(r"(_v\d+)$", proc_tag)
                if suffix_match:
                    era += suffix_match.group(1)
            request_name = "{}_{}_supplement_v{}".format(prim_dataset, era, args.version)
        else:
            short_name = prim_dataset.split("_TuneCP5")[0]
            request_name = "{}_{}_supplement_v{}".format(short_name, year, args.version)

        global_tag = DATA_GLOBAL_TAGS[year] if is_data else mc_global_tag

        if is_data:
            py_cfg_params = [
                "globalTag={}".format(global_tag),
                "lowerMuonPtThreshold={}".format(year in LOWERED_MUON_PT_YEARS),
            ]
            if sample == "EGamma" and year in EGAMMA_PT_BOUNDARY_FIX_YEARS:
                py_cfg_params.append("egamma2025PtBoundaryFix=True")
        else:
            py_cfg_params = [
                "globalTag={}".format(global_tag),
                "recomputeMuonIds={}".format(year in PRE_142X_MINIAOD_YEARS),
            ]

        config_text = (DATA_CRAB_TEMPLATE if is_data else MC_CRAB_TEMPLATE) \
            .replace("{{ request_name }}", request_name) \
            .replace("{{ pset }}", SAMPLE_PSETS[sample]) \
            .replace("{{ dataset }}", dataset) \
            .replace("{{ py_cfg_params }}", repr(py_cfg_params)) \
            .replace("{{ priority }}", str(args.priority))
        if is_data:
            config_text = config_text.replace("{{ golden }}", GOLDEN_JSONS[year])

        out_path = os.path.join(args.output_dir, "{}_cfg.py".format(request_name))
        configs.append(os.path.basename(out_path))
        with open(out_path, "w") as f:
            f.write(config_text)
        print("Wrote {}".format(out_path))

    for e in eos_entries:
        year = e["year"].replace("_", "")
        name = os.path.basename(e["supplements_path"].rstrip("/"))
        request_name = "{}_supplement_v{}".format(name, args.version)
        input_files = list_eos_root_files(e["miniaod"])
        py_cfg_params = [
            "globalTag={}".format(e["global_tag"]),
            "recomputeMuonIds={}".format(year in PRE_142X_MINIAOD_YEARS),
        ]

        config_text = EOS_CRAB_TEMPLATE \
            .replace("{{ request_name }}", request_name) \
            .replace("{{ pset }}", SAMPLE_PSETS[e["sample"]]) \
            .replace("{{ py_cfg_params }}", repr(py_cfg_params)) \
            .replace("{{ priority }}", str(args.priority)) \
            .replace("{{ input_files }}", "[\n" + "".join("    '{}',\n".format(f) for f in input_files) + "]") \
            .replace("{{ primary_dataset }}", name) \
            .replace("{{ whitelist }}", repr(EOS_SITE_WHITELIST))

        out_path = os.path.join(args.output_dir, "{}_cfg.py".format(request_name))
        configs.append(os.path.basename(out_path))
        with open(out_path, "w") as f:
            f.write(config_text)
        print("Wrote {} ({} files)".format(out_path, len(input_files)))

    bulk_submit_path = os.path.join(args.output_dir, "submit.sh")
    with open(bulk_submit_path, "w") as f:
        for c in configs:
            f.write(f"crab submit -c {c}\n")
    subprocess.run(["chmod", "+x", bulk_submit_path])


if __name__ == "__main__":
    main()
