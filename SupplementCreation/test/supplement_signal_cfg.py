import FWCore.ParameterSet.Config as cms
import FWCore.ParameterSet.VarParsing as VarParsing

import HLTrigger.HLTfilters.hltHighLevel_cfi as hlt

# This pset is shared by every MC sample/year (see SAMPLE_PSETS in
# create_crab_configs.py) -- the GlobalTag varies by campaign, so it is
# passed in via pyCfgParams rather than hardcoded, to avoid silently reusing
# the wrong year's conditions (as happened before this was parameterized).
options = VarParsing.VarParsing("analysis")
options.register(
    "globalTag", "150X_mcRun3_2024_realistic_v2",
    VarParsing.VarParsing.multiplicity.singleton,
    VarParsing.VarParsing.varType.string,
    "GlobalTag matching the input MiniAOD's conditions",
)
options.register(
    "recomputeMuonIds", False,
    VarParsing.VarParsing.multiplicity.singleton,
    VarParsing.VarParsing.varType.bool,
    "Recompute muon cut-based ID selector bits from the MiniAOD",
)
options.parseArguments()

process = cms.Process("SUPPLEMENT")

process.load("FWCore.MessageService.MessageLogger_cfi")
process.MessageLogger.cerr.FwkReport.reportEvery = 1000

process.load("Configuration.StandardSequences.GeometryRecoDB_cff")
process.load("Configuration.StandardSequences.MagneticField_cff")
process.load("Configuration.StandardSequences.FrontierConditions_GlobalTag_cff")
process.load("TrackingTools.TransientTrack.TransientTrackBuilder_cfi")
process.load("SimGeneral.HepPDTESSource.pythiapdt_cfi")
process.load("PhysicsTools.NanoAOD.genparticles_cff")

from Configuration.AlCa.GlobalTag import GlobalTag
process.GlobalTag = GlobalTag(process.GlobalTag, options.globalTag, "")

process.maxEvents = cms.untracked.PSet(input = cms.untracked.int32(-1))

process.source = cms.Source("PoolSource",
    fileNames = cms.untracked.vstring(
        options.inputFiles if options.inputFiles else
        ["root://cmseos.fnal.gov//store/user/lnestor/signal_mc/StopToLB_M-1000_CTau-100mm_TuneCP5_13p6TeV_madgraphMLM-pythia8/2024_v1/261019_013122/0000/miniaod_1.root"]
    ),
)

process.supplementTriggerFilter = hlt.hltHighLevel.clone(
    TriggerResultsTag = cms.InputTag("TriggerResults", "", "HLT"),
    HLTPaths = cms.vstring(
        "HLT_DoublePhoton70_v*",
        "HLT_Diphoton30_22_R9Id_OR_IsoCaloId_AND_HE_R9Id_Mass90_v*",
        "HLT_Mu48NoFiltersNoVtx_Photon48_CaloIdL_v*",
        "HLT_DoubleMu43NoFiltersNoVtx_v*",
        "HLT_PFMET120_PFMHT120_IDTight_v*",
        "HLT_PFMET250_NotCleaned_v*",
        "HLT_PFMETNoMu120_PFMHTNoMu120_IDTight_v*",
        "HLT_CaloMET350_NotCleaned_v*",
    ),
    andOr = cms.bool(True),
    throw = cms.bool(False),
)

process.slimmedMuonsUpdated = cms.EDProducer("PATMuonUpdater",
    src = cms.InputTag("slimmedMuons"),
    vertices = cms.InputTag("offlineSlimmedPrimaryVertices"),
    fixDxySign = cms.bool(True),
    recomputeMuonBasicSelectors = cms.bool(options.recomputeMuonIds),
    recomputeSoftMuonMvaRun3 = cms.bool(False),
)

process.finalMuons = cms.EDFilter("PATMuonRefSelector",
    src = cms.InputTag("slimmedMuonsUpdated"),
    cut = cms.string("pt > 15 || (pt > 3 && (passed('CutBasedIdLoose') || passed('SoftCutBasedId') || passed('SoftMvaId') || passed('CutBasedIdGlobalHighPt') || passed('CutBasedIdTrkHighPt')))"),
)

process.finalElectrons = cms.EDFilter("PATElectronRefSelector",
    src = cms.InputTag("slimmedElectrons"),
    cut = cms.string("pt > 5"),
)

process.prunedSignalGen = cms.EDProducer("GenParticlePruner",
    src = cms.InputTag("genParticlePlusGeant", "", "SIM"),
    select = cms.vstring(
        "drop *",
        "keep+ abs(pdgId) == 1000612 || abs(pdgId) == 1000622 || abs(pdgId) == 1000632 || abs(pdgId) == 1000642 || abs(pdgId) == 1000652 || abs(pdgId) == 1006113 || abs(pdgId) == 1006211 || abs(pdgId) == 1006213 || abs(pdgId) == 1006223 || abs(pdgId) == 1006311 || abs(pdgId) == 1006313 || abs(pdgId) == 1006321 || abs(pdgId) == 1006323 || abs(pdgId) == 1006333",
        "drop abs(pdgId) != 11 && abs(pdgId) != 13",
    ),
)

process.supplementTree = cms.EDAnalyzer("SupplementTreeAnalyzer",
    version = cms.int32(2),
    doMuMu = cms.bool(True),
    doEE = cms.bool(True),
    doEMu = cms.bool(True),
    muons = cms.InputTag("finalMuons"),
    electrons = cms.InputTag("finalElectrons"),
    beamSpot = cms.InputTag("offlineBeamSpot"),
    genParts = cms.untracked.InputTag("prunedSignalGen"),
)

process.TFileService = cms.Service("TFileService",
    fileName = cms.string("supplement.root"),
)

process.p = cms.Path(process.supplementTriggerFilter + process.slimmedMuonsUpdated + process.finalMuons + process.finalElectrons +
                      process.prunedSignalGen + process.supplementTree)
