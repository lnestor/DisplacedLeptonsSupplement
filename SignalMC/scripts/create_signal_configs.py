import argparse
import math
import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor

MASSES = list(range(400, 2201, 100)) + [2400]
CTAUS = ["0p1", "1", "10", "100", "1000"]

ERAS = {
    "2024": {
        "conditions": "140X_mcRun3_2024_realistic_v26",
        "era": "Run3_2024",
        "beamspot": "DBrealistic",
        "hlt": "HLT:2024v14",
        "premix": "/Neutrino_E-10_gun/RunIIISummer24PrePremix-Premixlib2024_140X_mcRun3_2024_realistic_v26-v1/PREMIX",
        "mini_conditions": "150X_mcRun3_2024_realistic_v2",
        "mini_era": "Run3_2024",
    },
}

HBARC_GEV_MM = 1.973269804e-13
GRIDPACK_BASE = "/cvmfs/cms-griddata.cern.ch/phys_generator/gridpacks_tarball/pp/13p6TeV/madgraph/Stop_SMS-T2bW"
DECAYS = [(5, -11), (5, -13), (5, -15)]
N_PREMIX_FILES = 10000
THREADS = 2
KEEP_GEN_PLUS_GEANT = "keep *_genParticlePlusGeant_*_*"

# Same table as the official RunIII2024Summer24 SMS-2Stop-T2bW fragments, which use these gridpacks
MATCH_PARAMS = [
    (649, 62., 0.274), (699, 64., 0.269), (749, 64., 0.269), (799, 66., 0.259), (849, 66., 0.261),
    (899, 68., 0.257), (949, 68., 0.252), (999, 70., 0.250), (1049, 70., 0.248), (1099, 70., 0.248),
    (1149, 70., 0.249), (1199, 70., 0.242), (1249, 70., 0.239), (1299, 70., 0.242), (1349, 70., 0.241),
    (1399, 70., 0.237), (1449, 70., 0.239), (1499, 70., 0.241), (1549, 70., 0.235), (1599, 70., 0.239),
    (1649, 70., 0.239), (1699, 70., 0.237), (1749, 70., 0.241), (1799, 70., 0.237), (1849, 70., 0.237),
    (1899, 70., 0.240), (1949, 70., 0.241), (1999, 70., 0.244), (2049, 70., 0.246), (2099, 70., 0.249),
    (2149, 70., 0.246), (2199, 70., 0.246), (2249, 70., 0.251), (2299, 70., 0.249), (2349, 70., 0.257),
    (2399, 70., 0.257), (2449, 70., 0.261), (2499, 70., 0.264), (2549, 70., 0.266),
]

FRAGMENT_TEMPLATE = """import FWCore.ParameterSet.Config as cms

externalLHEProducer = cms.EDProducer("ExternalLHEProducer",
    args = cms.vstring('{gridpack}'),
    nEvents = cms.untracked.uint32(5000),
    numberOfParameters = cms.uint32(1),
    outputFile = cms.string('cmsgrid_final.lhe'),
    generateConcurrently = cms.untracked.bool(True),
    scriptName = cms.FileInPath('GeneratorInterface/LHEInterface/data/run_generic_tarball_cvmfs.sh')
)

from Configuration.Generator.Pythia8CommonSettings_cfi import *
from Configuration.Generator.MCTunesRun3ECM13p6TeV.PythiaCP5Settings_cfi import *
from Configuration.Generator.PSweightsPythia.PythiaPSweightsSettings_cfi import *

generator = cms.EDFilter("Pythia8ConcurrentHadronizerFilter",
    maxEventsToPrint = cms.untracked.int32(1),
    pythiaPylistVerbosity = cms.untracked.int32(1),
    pythiaHepMCVerbosity = cms.untracked.bool(False),
    filterEfficiency = cms.untracked.double(1.0),
    crossSection = cms.untracked.double(-1),
    comEnergy = cms.double(13600.),
    SLHAFileForPythia8 = cms.string('{slha}'),
    PythiaParameters = cms.PSet(
        pythia8CommonSettingsBlock,
        pythia8CP5SettingsBlock,
        pythia8PSweightsSettingsBlock,
        processParameters = cms.vstring(
            'JetMatching:setMad = off',
            'JetMatching:scheme = 1',
            'JetMatching:merge = on',
            'JetMatching:jetAlgorithm = 2',
            'JetMatching:etaJetMax = 5.',
            'JetMatching:coneRadius = 1.',
            'JetMatching:slowJetPower = 1',
            'JetMatching:qCut = {qcut:.0f}',
            'JetMatching:nQmatch = 5',
            'JetMatching:nJetMax = 2',
            'JetMatching:doShowerKt = off',
            '6:m0 = 172.5',
            '24:mMin = 0.1',
            'Check:abortIfVeto = on',
            '1000006:mayDecay = off',
            'RHadrons:allow = on',
            'RHadrons:allowDecay = off',
            'RHadrons:setMasses = on',
        ),
        parameterSets = cms.vstring(
            'pythia8CommonSettings',
            'pythia8CP5Settings',
            'pythia8PSweightsSettings',
            'processParameters',
        )
    )
)

generator.hscpFlavor = cms.untracked.string('stop')
generator.massPoint = cms.untracked.int32({mass})
generator.particleFile = cms.untracked.string('Configuration/Generator/data/particles_stop_{mass}_GeV.txt')
generator.slhaFile = cms.untracked.string('{slha}')
generator.processFile = cms.untracked.string('SimG4Core/CustomPhysics/data/stophadronProcessList.txt')
generator.pdtFile = cms.FileInPath('Configuration/Generator/data/hscppythiapdtstop{mass}.tbl')
generator.useregge = cms.bool(False)

ProductionFilterSequence = cms.Sequence(generator)
"""

CRAB_TEMPLATE = """from CRABClient.UserUtilities import config

config = config()

config.General.requestName = '{request_name}'
config.General.workArea = 'crab_projects'
config.General.transferOutputs = True
config.General.transferLogs = True

config.JobType.pluginName = 'PrivateMC'
config.JobType.generator = 'pythia'
config.JobType.psetName = 'step1_{name}_cfg.py'
config.JobType.scriptExe = '../run_gen_to_nano.sh'
config.JobType.inputFiles = ['step2_cfg.py', 'step3_cfg.py', 'step4_cfg.py']
config.JobType.outputFiles = ['miniaod.root', 'nanoaod.root']
config.JobType.disableAutomaticOutputCollection = True
config.JobType.maxMemoryMB = {memory}
config.JobType.numCores = {threads}
config.JobType.maxJobRuntimeMin = {runtime}

config.Data.outputPrimaryDataset = '{primary_dataset}'
config.Data.splitting = 'EventBased'
config.Data.unitsPerJob = {events_per_job}
config.Data.totalUnits = {total_events}
config.Data.publication = False
config.Data.outputDatasetTag = '{dataset_tag}'
config.Data.outLFNDirBase = '{lfn_base}'

config.Site.storageSite = 'T3_US_FNALLPC'
"""


def ctau_mm(ctau):
    return float(ctau.replace("p", "."))


def match_params(mass):
    for upper, qcut, eff in MATCH_PARAMS:
        if mass < upper:
            return qcut, eff
    return 70., 0.243


def gridpack(mass):
    if mass < 600:
        return "%s/SMS-StopStop_mStop-%i_el8_amd64_gcc10_CMSSW_12_4_8_tarball.tar.xz" % (GRIDPACK_BASE, mass)
    return "%s/SMS-StopStop_mStop-%i_slc7_amd64_gcc10_CMSSW_12_4_8_tarball.tar.xz" % (GRIDPACK_BASE, mass)


def point_name(mass, ctau):
    return "stop_to_lb_M_%i_ctau_%smm" % (mass, ctau)


def primary_dataset(mass, ctau):
    return "StopToLB_M-%i_CTau-%smm_TuneCP5_13p6TeV_madgraphMLM-pythia8" % (mass, ctau)


def find_in_search_path(relpath):
    for base in os.environ["CMSSW_SEARCH_PATH"].split(":"):
        path = os.path.join(base, relpath)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(relpath)


def rhadron_mass_lines(mass):
    stop_ids = {1000006, 1000612, 1000622, 1000632, 1000642, 1000652, 1006113, 1006211,
                1006213, 1006223, 1006311, 1006313, 1006321, 1006323, 1006333}
    path = find_in_search_path("Configuration/Generator/data/hscppythiapdtstop%i.tbl" % mass)
    lines = []
    with open(path) as f:
        for line in f:
            fields = line.split()
            if len(fields) < 4 or not fields[0].lstrip("-").isdigit():
                continue
            if abs(int(fields[0])) in stop_ids:
                lines.append("   %9s   %s   # %s" % (fields[0], fields[3], fields[1]))
    return lines


def write_slha(path, mass, ctau):
    width = HBARC_GEV_MM / ctau_mm(ctau)
    out = ["BLOCK MASS", "# PDG code   mass   particle"]
    out += rhadron_mass_lines(mass)
    out.append("#")
    out.append("DECAY   1000006   %.8E   # ~t_1 decays, ctau = %s mm" % (width, ctau))
    out.append("#   BR   NDA   ID1   ID2")
    for d1, d2 in DECAYS:
        out.append("   %.8E   2   %i   %i" % (1.0 / len(DECAYS), d1, d2))
    out.append("#")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def write_fragment(path, mass, slha_rel):
    qcut, _ = match_params(mass)
    with open(path, "w") as f:
        f.write(FRAGMENT_TEMPLATE.format(gridpack=gridpack(mass), slha=slha_rel, qcut=qcut, mass=mass))


def run_cmsdriver(args, cwd):
    result = subprocess.run(["cmsDriver.py"] + args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("cmsDriver failed:\n%s\n%s" % (" ".join(args), result.stdout + result.stderr))


def step1_args(name, cfg):
    return [
        "DisplacedLeptonsSupplement/SignalMC/python/%s_cff.py" % name,
        "--python_filename", "step1_%s_cfg.py" % name,
        "--fileout", "file:step1.root",
        "--mc", "--eventcontent", "RAWSIM", "--datatier", "GEN-SIM",
        "--conditions", cfg["conditions"], "--beamspot", cfg["beamspot"],
        "--geometry", "DB:Extended", "--era", cfg["era"],
        "--step", "LHE,GEN,SIM",
        "--customise", "SimG4Core/CustomPhysics/Exotica_HSCP_SIM_cfi.customise,"
                       "Configuration/DataProcessing/Utils.addMonitoring",
        "--nThreads", str(THREADS), "--no_exec", "-n", "10",
    ]


def step2_args(cfg, premix_list):
    return [
        "step2", "--python_filename", "step2_cfg.py",
        "--filein", "file:step1.root", "--fileout", "file:step2.root",
        "--pileup_input", "filelist:%s" % premix_list,
        "--mc", "--eventcontent", "PREMIXRAW", "--datatier", "GEN-SIM-RAW",
        "--conditions", cfg["conditions"], "--geometry", "DB:Extended", "--era", cfg["era"],
        "--step", "DIGI,DATAMIX,L1,DIGI2RAW,%s" % cfg["hlt"],
        "--procModifiers", "premix_stage2", "--datamix", "PreMix",
        "--outputCommand", KEEP_GEN_PLUS_GEANT,
        "--customise", "DisplacedLeptonsSupplement/SignalMC/randomize_seeds.customise,"
                       "Configuration/DataProcessing/Utils.addMonitoring",
        "--nThreads", str(THREADS), "--no_exec", "-n", "-1",
    ]


def step3_args(cfg):
    return [
        "step3", "--python_filename", "step3_cfg.py",
        "--filein", "file:step2.root", "--fileout", "file:step3.root",
        "--mc", "--eventcontent", "AODSIM", "--datatier", "AODSIM",
        "--conditions", cfg["conditions"], "--geometry", "DB:Extended", "--era", cfg["era"],
        "--step", "RAW2DIGI,L1Reco,RECO,RECOSIM",
        "--customise", "SimG4Core/CustomPhysics/GenPlusSimParticles_cfi.customizeKeep,"
                       "DisplacedLeptonsSupplement/SignalMC/randomize_seeds.customise,"
                       "Configuration/DataProcessing/Utils.addMonitoring",
        "--nThreads", str(THREADS), "--no_exec", "-n", "-1",
    ]


def step4_args(cfg):
    return [
        "step4", "--python_filename", "step4_cfg.py",
        "--filein", "file:step3.root", "--fileout", "file:miniaod.root",
        "--mc", "--eventcontent", "MINIAODSIM,NANOAODSIM", "--datatier", "MINIAODSIM,NANOAODSIM",
        "--conditions", cfg["mini_conditions"], "--geometry", "DB:Extended", "--era", cfg["mini_era"],
        "--step", "PAT,NANO",
        "--customise", "SimG4Core/CustomPhysics/GenPlusSimParticles_cfi.customizeKeep,"
                       "Configuration/DataProcessing/Utils.addMonitoring",
        "--customise_commands", "process.NANOAODSIMoutput.fileName = 'file:nanoaod.root'",
        "--nThreads", str(THREADS), "--no_exec", "-n", "-1",
    ]


def write_premix_list(path, dataset, seed):
    result = subprocess.run(["dasgoclient", "-query", "file dataset=%s" % dataset],
                            capture_output=True, text=True, check=True)
    files = sorted(result.stdout.split())
    chosen = sorted(random.Random(seed).sample(files, N_PREMIX_FILES))
    with open(path, "w") as f:
        f.write("\n".join(chosen) + "\n")


def total_events(mass, events, events_per_job):
    _, eff = match_params(mass)
    n_jobs = math.ceil(events / eff / events_per_job)
    return n_jobs * events_per_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--masses", nargs="+", type=int, default=MASSES)
    parser.add_argument("--ctaus", nargs="+", default=CTAUS)
    parser.add_argument("--years", nargs="+", default=list(ERAS), choices=list(ERAS))
    parser.add_argument("--package-dir", default="..")
    parser.add_argument(
        "--fragments", action="store_true",
        help="Write generator fragments and SLHA files (run in the GEN-to-RECO release)")
    parser.add_argument(
        "--step-configs", action="store_true",
        help="Write premix file lists and step1/2/3 configs (run in the GEN-to-RECO release)")
    parser.add_argument(
        "--step4-config", action="store_true",
        help="Write the PAT+NANO config (run in the MiniAOD release, e.g. CMSSW_15_0_10)")
    parser.add_argument("--crab", action="store_true", help="Write CRAB configs")
    parser.add_argument("--events", type=int, default=50000, help="Target events per point after matching")
    parser.add_argument("--events-per-job", type=int, default=1000, help="LHE events per job, before matching")
    parser.add_argument("--memory", type=int, default=5000, help="step2 peaks at ~4.5 GB RSS with 2 threads")
    parser.add_argument("--runtime", type=int, default=360)
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--lfn-base", default="/store/user/lnestor/signal_mc")
    parser.add_argument("--premix-seed", type=int, default=12345)
    parser.add_argument("--jobs", type=int, default=8, help="Parallel cmsDriver calls")
    args = parser.parse_args()

    points = [(m, c) for m in args.masses for c in args.ctaus]
    python_dir = os.path.join(args.package_dir, "python")
    slha_dir = os.path.join(args.package_dir, "data", "slha")

    if args.fragments:
        os.makedirs(slha_dir, exist_ok=True)
        for mass, ctau in points:
            name = point_name(mass, ctau)
            slha_rel = "DisplacedLeptonsSupplement/SignalMC/data/slha/%s.slha" % name
            write_slha(os.path.join(slha_dir, name + ".slha"), mass, ctau)
            write_fragment(os.path.join(python_dir, name + "_cff.py"), mass, slha_rel)
        print("wrote %i fragments and SLHA files" % len(points))

    for year in args.years:
        cfg = ERAS[year]
        year_dir = os.path.join(args.package_dir, "test", year)
        os.makedirs(year_dir, exist_ok=True)

        if args.step_configs:
            premix_list = os.path.join(year_dir, "premix_files.txt")
            if not os.path.exists(premix_list):
                write_premix_list(premix_list, cfg["premix"], args.premix_seed)
            run_cmsdriver(step2_args(cfg, "premix_files.txt"), year_dir)
            run_cmsdriver(step3_args(cfg), year_dir)
            with ThreadPoolExecutor(args.jobs) as pool:
                list(pool.map(lambda p: run_cmsdriver(step1_args(point_name(*p), cfg), year_dir), points))
            print("%s: wrote step2, step3 and %i step1 configs" % (year, len(points)))

        if args.step4_config:
            run_cmsdriver(step4_args(cfg), year_dir)
            print("%s: wrote step4 config" % year)

        if args.crab:
            for mass, ctau in points:
                name = point_name(mass, ctau)
                text = CRAB_TEMPLATE.format(
                    request_name="StopToLB_M-%i_CTau-%smm_%s_v%i" % (mass, ctau, year, args.version),
                    name=name,
                    memory=args.memory,
                    threads=THREADS,
                    runtime=args.runtime,
                    primary_dataset=primary_dataset(mass, ctau),
                    events_per_job=args.events_per_job,
                    total_events=total_events(mass, args.events, args.events_per_job),
                    dataset_tag="%s_v%i" % (year, args.version),
                    lfn_base=args.lfn_base,
                )
                with open(os.path.join(year_dir, "crab_%s_cfg.py" % name), "w") as f:
                    f.write(text)
            print("%s: wrote %i CRAB configs" % (year, len(points)))


if __name__ == "__main__":
    main()
