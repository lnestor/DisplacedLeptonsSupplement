import FWCore.ParameterSet.Config as cms

externalLHEProducer = cms.EDProducer("ExternalLHEProducer",
    args = cms.vstring('/cvmfs/cms-griddata.cern.ch/phys_generator/gridpacks_tarball/pp/13p6TeV/madgraph/Stop_SMS-T2bW/SMS-StopStop_mStop-1000_slc7_amd64_gcc10_CMSSW_12_4_8_tarball.tar.xz'),
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
    SLHAFileForPythia8 = cms.string('DisplacedLeptonsSupplement/SignalMC/data/slha/stop_to_lb_M_1000_ctau_0p1mm.slha'),
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
            'JetMatching:qCut = 70',
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
generator.massPoint = cms.untracked.int32(1000)
generator.particleFile = cms.untracked.string('Configuration/Generator/data/particles_stop_1000_GeV.txt')
generator.slhaFile = cms.untracked.string('DisplacedLeptonsSupplement/SignalMC/data/slha/stop_to_lb_M_1000_ctau_0p1mm.slha')
generator.processFile = cms.untracked.string('SimG4Core/CustomPhysics/data/stophadronProcessList.txt')
generator.pdtFile = cms.FileInPath('Configuration/Generator/data/hscppythiapdtstop1000.tbl')
generator.useregge = cms.bool(False)

ProductionFilterSequence = cms.Sequence(generator)
