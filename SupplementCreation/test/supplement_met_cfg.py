import FWCore.ParameterSet.Config as cms
import FWCore.ParameterSet.VarParsing as VarParsing

import HLTrigger.HLTfilters.hltHighLevel_cfi as hlt

# This pset is shared across all eras/years for this channel -- the
# GlobalTag varies by era, so it is passed in via pyCfgParams rather than
# hardcoded, to avoid silently reusing the wrong era's conditions.
options = VarParsing.VarParsing("analysis")
options.register(
    "globalTag", "150X_dataRun3_v2",
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

from Configuration.AlCa.GlobalTag import GlobalTag
process.GlobalTag = GlobalTag(process.GlobalTag, options.globalTag, "")

process.maxEvents = cms.untracked.PSet(input = cms.untracked.int32(-1))

process.source = cms.Source("PoolSource",
    fileNames = cms.untracked.vstring(
        "/store/data/Run2024C/EGamma0/MINIAOD/MINIv6NANOv15-v1/2540000/006e191e-5aa1-472c-94c4-e0f0563c4072.root"
    ),
)

process.supplementTriggerFilter = hlt.hltHighLevel.clone(
    TriggerResultsTag = cms.InputTag("TriggerResults", "", "HLT"),
    HLTPaths = cms.vstring(
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
)

process.TFileService = cms.Service("TFileService",
    fileName = cms.string("supplement.root"),
)

process.p = cms.Path(process.supplementTriggerFilter + process.finalMuons + process.finalElectrons + process.supplementTree)
