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
options.register(
    "lowerMuonPtThreshold", False,
    VarParsing.VarParsing.multiplicity.singleton,
    VarParsing.VarParsing.varType.bool,
    "Lower the loose-muon pt threshold to 2 GeV, matching central NanoAOD's "
    "run3_nanoAOD_2025 era modifier (2025+ data-taking)",
)
options.register(
    "egamma2025PtBoundaryFix", False,
    VarParsing.VarParsing.multiplicity.singleton,
    VarParsing.VarParsing.varType.bool,
    "EGamma 2025 central NanoAOD keeps electrons/muons with pt exactly equal "
    "to a selector pt boundary, which a strict '>' cut here drops, breaking "
    "the supplement join. Widen all pt boundary cuts to '>=' to match.",
)
options.register(
    "lumisToProcess", [],
    VarParsing.VarParsing.multiplicity.list,
    VarParsing.VarParsing.varType.string,
    "Restrict processing to these luminosity blocks (CMSSW run:lumi-run:lumi format), "
    "for manual recovery runs outside of CRAB",
)
options.parseArguments()

_muon_pt_threshold = 2 if options.lowerMuonPtThreshold else 3
_pt_boundary_op = ">=" if options.egamma2025PtBoundaryFix else ">"

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
        options.inputFiles if options.inputFiles else [
            "/store/data/Run2024C/EGamma0/MINIAOD/MINIv6NANOv15-v1/2540000/006e191e-5aa1-472c-94c4-e0f0563c4072.root"
        ]
    ),
)
if options.lumisToProcess:
    process.source.lumisToProcess = cms.untracked.VLuminosityBlockRange(options.lumisToProcess)

process.supplementTriggerFilter = hlt.hltHighLevel.clone(
    TriggerResultsTag = cms.InputTag("TriggerResults", "", "HLT"),
    HLTPaths = cms.vstring(
        "HLT_DoublePhoton70_v*",
        "HLT_Diphoton30_22_R9Id_OR_IsoCaloId_AND_HE_R9Id_Mass90_v*",
    ),
    andOr = cms.bool(True),
    throw = cms.bool(False),
)

process.finalMuons = cms.EDFilter("PATMuonRefSelector",
    src = cms.InputTag("slimmedMuons"),
    cut = cms.string("pt {op} 15 || (pt {op} {threshold} && (passed('CutBasedIdLoose') || passed('SoftCutBasedId') || passed('SoftMvaId') || passed('CutBasedIdGlobalHighPt') || passed('CutBasedIdTrkHighPt')))".format(op=_pt_boundary_op, threshold=_muon_pt_threshold)),
)

process.finalElectrons = cms.EDFilter("PATElectronRefSelector",
    src = cms.InputTag("slimmedElectrons"),
    cut = cms.string("pt {op} 5".format(op=_pt_boundary_op)),
)

process.supplementTree = cms.EDAnalyzer("SupplementTreeAnalyzer",
    version = cms.int32(2),
    doMuMu = cms.bool(False),
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
