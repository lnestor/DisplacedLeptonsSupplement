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
        "/store/mc/RunIII2024Summer24MiniAODv6/DYto2E-4Jets_Bin-MLL-50_TuneCP5_13p6TeV_madgraphMLM-pythia8/MINIAODSIM/150X_mcRun3_2024_realistic_v2-v3/2530000/ae7e01ea-f7a0-470f-90c6-4fa1c2ea6904.root"
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

process.finalMuons = cms.EDFilter("PATMuonRefSelector",
    src = cms.InputTag("slimmedMuons"),
    cut = cms.string("pt > 15 || (pt > 3 && (passed('CutBasedIdLoose') || passed('SoftCutBasedId') || passed('SoftMvaId') || passed('CutBasedIdGlobalHighPt') || passed('CutBasedIdTrkHighPt')))"),
)

process.finalElectrons = cms.EDFilter("PATElectronRefSelector",
    src = cms.InputTag("slimmedElectrons"),
    cut = cms.string("pt > 5"),
)

process.supplementTree = cms.EDAnalyzer("SupplementTreeAnalyzer",
    version = cms.int32(2),
    doMuMu = cms.bool(True),
    doEE = cms.bool(True),
    doEMu = cms.bool(True),
    muons = cms.InputTag("finalMuons"),
    electrons = cms.InputTag("finalElectrons"),
    beamSpot = cms.InputTag("offlineBeamSpot"),
    genParts = cms.untracked.InputTag("finalGenParticles"),
)

process.TFileService = cms.Service("TFileService",
    fileName = cms.string("supplement.root"),
)

process.p = cms.Path(process.supplementTriggerFilter + process.finalMuons + process.finalElectrons +
                      process.finalGenParticles + process.supplementTree)
