
from CRABClient.UserUtilities import config

config = config()

config.General.requestName = 'JetMET0_Run2025F_v1_supplement_v1'
config.General.workArea = 'crab_projects'
config.General.transferOutputs = True
config.General.transferLogs = True

config.JobType.pluginName = 'Analysis'
config.JobType.psetName = 'supplement_met_cfg.py'
config.JobType.outputFiles = ['supplement.root']
config.JobType.maxMemoryMB = 3000
config.JobType.numCores = 1

config.Data.inputDataset = '/JetMET0/Run2025F-PromptReco-v1/MINIAOD'
config.Data.inputDBS = 'global'
config.Data.splitting = 'LumiBased'
config.Data.unitsPerJob = 400
config.Data.publication = False
config.Data.lumiMask = 'https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions25/Cert_Collisions2025_391658_398903_Golden.json'
config.Data.outLFNDirBase = '/store/user/lnestor/'
config.Data.outputDatasetTag = 'JetMET0_Run2025F_v1_supplement_v1'

config.Site.storageSite = 'T3_US_FNALLPC'
