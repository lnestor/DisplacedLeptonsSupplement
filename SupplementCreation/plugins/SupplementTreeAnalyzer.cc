#include "FWCore/Framework/interface/one/EDAnalyzer.h"
#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/EventSetup.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/Framework/interface/Run.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/ServiceRegistry/interface/Service.h"
#include "CommonTools/UtilAlgos/interface/TFileService.h"

#include "DataFormats/PatCandidates/interface/Muon.h"
#include "DataFormats/PatCandidates/interface/Electron.h"
#include "DataFormats/HepMCCandidate/interface/GenParticle.h"
#include "DataFormats/BeamSpot/interface/BeamSpot.h"
#include "DataFormats/Common/interface/RefVector.h"
#include "DataFormats/VertexReco/interface/Vertex.h"
#include "DataFormats/Math/interface/deltaR.h"
#include "TrackingTools/TransientTrack/interface/TransientTrackBuilder.h"
#include "TrackingTools/TransientTrack/interface/TransientTrack.h"
#include "TrackingTools/Records/interface/TransientTrackRecord.h"
#include "RecoVertex/KalmanVertexFit/interface/KalmanVertexFitter.h"
#include "RecoVertex/VertexPrimitives/interface/TransientVertex.h"

#include "TTree.h"

#include <cstdint>
#include <limits>

// Phase 1 pixel detector material geometry (all dimensions in cm), ported
// from OSUNano's InMaterialVertexTableProducer. Each volume is expanded by
// 10 um in each direction to account for vertex position resolution,
// following the Run 2 DisplacedSUSY analysis convention. Beam center offsets
// are from 2018 (CMSSW_10_2_x alignment).
// TODO: update beam center values for Run 3 alignment per year.
namespace {

// beam pipe
constexpr double kBeamPipeXCenter  =  0.171;
constexpr double kBeamPipeYCenter  = -0.176;
constexpr double kBeamPipeInnerR   =  2.170;
constexpr double kBeamPipeOuterR   =  2.251;

// BPIX inner shield (two offset half-cylinders)
constexpr double kNearShieldXCenter = -0.093;
constexpr double kNearShieldYCenter = -0.091;
constexpr double kFarShieldXCenter  =  0.044;
constexpr double kFarShieldYCenter  = -0.098;
constexpr double kInnerShieldInnerR =  2.360;
constexpr double kInnerShieldOuterR =  2.441;

// BPIX barrel layers (L1-L4)
constexpr double kBpixXCenter   =  0.0856367;
constexpr double kBpixYCenter   = -0.101882;
constexpr double kBpixZCenter   = -0.326049;
constexpr double kBpixZHalfLen  = 27.4505;
constexpr double kBpixL1InnerR  =  2.725;
constexpr double kBpixL1OuterR  =  3.176;
constexpr double kBpixL2InnerR  =  6.525;
constexpr double kBpixL2OuterR  =  7.076;
constexpr double kBpixL3InnerR  = 10.825;
constexpr double kBpixL3OuterR  = 10.976;
constexpr double kBpixL4InnerR  = 15.925;
constexpr double kBpixL4OuterR  = 16.076;

// FPIX forward disks (D1-D3, both +/-z sides)
constexpr double kFpixXCenter    =  0.0311191;
constexpr double kFpixYCenter    = -0.106233;
constexpr double kFpixZCenter    = -0.338382;
constexpr double kFpixInnerR     =  4.500;
constexpr double kFpixOuterR     = 16.101;
constexpr double kFpixZHalfThick =  0.0755;
constexpr double kFpixD1ZCenter  = 29.1;
constexpr double kFpixD2ZCenter  = 39.6;
constexpr double kFpixD3ZCenter  = 51.6;

// pixel support tube
constexpr double kTubeXCenter  = -0.080;
constexpr double kTubeYCenter  = -0.320;
constexpr double kTubeInnerRX  = 21.625;
constexpr double kTubeInnerRY  = 21.725;
constexpr double kTubeOuterRX  = 21.776;
constexpr double kTubeOuterRY  = 21.876;

bool inCircle(double cx, double cy, double r, double x, double y) {
    double dx = x - cx, dy = y - cy;
    return dx*dx + dy*dy < r*r;
}

bool inEllipse(double cx, double cy, double rx, double ry, double x, double y) {
    double dx = x - cx, dy = y - cy;
    return dx*dx/(rx*rx) + dy*dy/(ry*ry) < 1.0;
}

bool inMaterial(double vx, double vy, double vz) {
    if (inCircle(kBeamPipeXCenter, kBeamPipeYCenter, kBeamPipeOuterR, vx, vy) &&
        !inCircle(kBeamPipeXCenter, kBeamPipeYCenter, kBeamPipeInnerR, vx, vy))
        return true;

    bool inBpixZ = vz > kBpixZCenter - kBpixZHalfLen &&
                   vz < kBpixZCenter + kBpixZHalfLen;

    if (inBpixZ) {
        bool nearSide = vx > 0.0 &&
            inCircle(kNearShieldXCenter, kNearShieldYCenter, kInnerShieldOuterR, vx, vy) &&
            !inCircle(kNearShieldXCenter, kNearShieldYCenter, kInnerShieldInnerR, vx, vy);
        bool farSide = vx <= 0.0 &&
            inCircle(kFarShieldXCenter, kFarShieldYCenter, kInnerShieldOuterR, vx, vy) &&
            !inCircle(kFarShieldXCenter, kFarShieldYCenter, kInnerShieldInnerR, vx, vy);
        if (nearSide || farSide) return true;
    }

    if (inBpixZ) {
        bool inL1 = inCircle(kBpixXCenter, kBpixYCenter, kBpixL1OuterR, vx, vy) &&
                    !inCircle(kBpixXCenter, kBpixYCenter, kBpixL1InnerR, vx, vy);
        bool inL2 = inCircle(kBpixXCenter, kBpixYCenter, kBpixL2OuterR, vx, vy) &&
                    !inCircle(kBpixXCenter, kBpixYCenter, kBpixL2InnerR, vx, vy);
        bool inL3 = inCircle(kBpixXCenter, kBpixYCenter, kBpixL3OuterR, vx, vy) &&
                    !inCircle(kBpixXCenter, kBpixYCenter, kBpixL3InnerR, vx, vy);
        bool inL4 = inCircle(kBpixXCenter, kBpixYCenter, kBpixL4OuterR, vx, vy) &&
                    !inCircle(kBpixXCenter, kBpixYCenter, kBpixL4InnerR, vx, vy);
        if (inL1 || inL2 || inL3 || inL4) return true;
    }

    bool inFpixR = inCircle(kFpixXCenter, kFpixYCenter, kFpixOuterR, vx, vy) &&
                   !inCircle(kFpixXCenter, kFpixYCenter, kFpixInnerR, vx, vy);
    if (inFpixR) {
        auto inDisk = [&](double dz) {
            return (vz > kFpixZCenter + dz - kFpixZHalfThick &&
                    vz < kFpixZCenter + dz + kFpixZHalfThick) ||
                   (vz > kFpixZCenter - dz - kFpixZHalfThick &&
                    vz < kFpixZCenter - dz + kFpixZHalfThick);
        };
        if (inDisk(kFpixD1ZCenter) || inDisk(kFpixD2ZCenter) || inDisk(kFpixD3ZCenter))
            return true;
    }

    if (inEllipse(kTubeXCenter, kTubeYCenter, kTubeOuterRX, kTubeOuterRY, vx, vy) &&
        !inEllipse(kTubeXCenter, kTubeYCenter, kTubeInnerRX, kTubeInnerRY, vx, vy))
        return true;

    return false;
}

// Gen-matching for Muon_genVtx_*/Electron_genVtx_*: nearest deltaR among
// finalGenParticles with matching abs(pdgId), within kSimpleMatchMaxDeltaR.
// An earlier version replicated central NanoAOD's full MCMatcher/
// CandMCMatchTableProducer chain (ambiguity resolution, pt-consistency cut,
// dressed-lepton/photon-conversion fallback for electrons) via
// muonMCTable/electronMCTable FlatTables. A/B tested against that chain on
// both a clean DY->ee sample and a busy TTbar dileptonic sample (jets, taus,
// converted photons): this simple deltaR+pdgId match reproduced the exact
// same matched-lepton set with bit-identical vx/vy/vz in both cases, while
// running 1.3-3x faster and dropping the Rivet/HepMC dependency chain
// (particleLevel/tautaggerForMatching/matchingElecPhoton/etc).
constexpr float kSimpleMatchMaxDeltaR = 0.3;

template <typename LeptonRefVector>
void matchGenVtxByDeltaR(const LeptonRefVector& leptons,
                          const reco::GenParticleCollection& genParts,
                          int pdgId,
                          std::vector<float>& vx,
                          std::vector<float>& vy) {
    for (const auto& lepRef : leptons) {
        const auto& lep = *lepRef;
        const reco::GenParticle* best = nullptr;
        float bestDR = kSimpleMatchMaxDeltaR;

        for (const auto& gp : genParts) {
            if (std::abs(gp.pdgId()) != pdgId)
                continue;
            float dr = reco::deltaR(lep, gp);
            if (dr < bestDR) {
                bestDR = dr;
                best = &gp;
            }
        }

        if (best) {
            vx.push_back(best->vx());
            vy.push_back(best->vy());
        } else {
            vx.push_back(std::numeric_limits<float>::quiet_NaN());
            vy.push_back(std::numeric_limits<float>::quiet_NaN());
        }
    }
}

}  // namespace

// Writes a simplified NanoAOD-like file: an "Events" tree with hand picked
// branches booked directly here, plus a "Runs" tree carrying one entry per
// run with the package version number. Only variables that are NOT already
// present in central NanoAOD/MiniAOD go here -- this file is meant to be
// joined to the central files by run/luminosityBlock/event.
//
// Muon_genVtx_{x,y}/Electron_genVtx_{x,y} (MC only, gated by the optional
// "genParts" input tag) are one exception: they are the production vertex
// (x,y only -- z is unused downstream) of whichever finalGenParticles entry
// each muon/electron matches to via deltaR+pdgId (see matchGenVtxByDeltaR
// above), sized to the Muon/Electron collections rather than duplicating the
// full GenPart collection.
//
// BeamSpot_x/BeamSpot_y are the other exception: central NanoAOD's BeamSpot
// table only carries z, but gen_absd0_um (computed downstream from
// Muon_genVtx_x/y) needs to be measured relative to the beamspot -- the same
// reference point reco d0 (dxybs) uses -- not the detector origin, so the
// transverse beamspot position has to come from here.
class SupplementTreeAnalyzer : public edm::one::EDAnalyzer<edm::one::WatchRuns, edm::one::SharedResources> {
public:
  explicit SupplementTreeAnalyzer(const edm::ParameterSet&);

private:
  void beginJob() override;
  void analyze(const edm::Event&, const edm::EventSetup&) override;
  void beginRun(const edm::Run&, const edm::EventSetup&) override;
  void endRun(const edm::Run&, const edm::EventSetup&) override {}

  void fillMuons(const edm::Event&);
  void fillElectrons(const edm::Event&);
  void fillInMaterialVertices(const edm::Event&, const edm::EventSetup&);
  void fillGenVtx(const edm::Event&);
  void fillBeamSpot(const edm::Event&);

  const int version_;
  const bool doMuMu_;
  const bool doEE_;
  const bool doEMu_;
  const bool doGenPart_;

  // finalMuons/finalElectrons (as selected by PATMuonRefSelector /
  // PATElectronRefSelector using the same cuts as central NanoAOD) are
  // edm::RefVectors into slimmedMuons/slimmedElectrons, not plain
  // std::vectors -- consumed as such so the array order and length here
  // match central NanoAOD's Muon_*/Electron_* arrays index-for-index.
  edm::EDGetTokenT<edm::RefVector<std::vector<pat::Muon>>> muonToken_;
  edm::EDGetTokenT<edm::RefVector<std::vector<pat::Electron>>> electronToken_;
  edm::EDGetTokenT<reco::BeamSpot> beamSpotToken_;
  edm::EDGetTokenT<reco::GenParticleCollection> genPartToken_;
  edm::ESGetToken<TransientTrackBuilder, TransientTrackRecord> ttbToken_;

  TTree* eventsTree_ = nullptr;
  TTree* runsTree_ = nullptr;

  // Events branches
  unsigned int run_ = 0;
  unsigned int lumi_ = 0;
  unsigned long long event_ = 0;

  // BeamSpot -- transverse position [cm], not present in central NanoAOD's
  // BeamSpot table (z only). Always filled (data and MC), unlike genVtx.
  float BeamSpot_x_ = 0.f;
  float BeamSpot_y_ = 0.f;

  // Muon -- OSUNano custom_osu_cff.py add_muon_vars() additions, not present
  // in central NanoAOD's muonTable
  std::vector<float> Muon_pfIso04_sumChargedHadronPt_, Muon_pfIso04_sumPUPt_, Muon_pfIso04_sumNeutralEt_;
  std::vector<int> Muon_timeNdof_;
  std::vector<float> Muon_timeAtIpInOut_;

  // Electron -- OSUNano custom_osu_cff.py add_electron_vars() additions, not
  // present in central NanoAOD's electronTable
  std::vector<float> Electron_pfIso03_sumChargedHadronPt_, Electron_pfIso03_sumPUPt_, Electron_pfIso03_sumNeutralEt_;
  std::vector<bool> Electron_isEBEEGap_;
  std::vector<float> Electron_dxybs_, Electron_dxybsErr_;

  // InMaterialVtx -- OSUNano custom_osu_cff.py add_material_vertices()
  // addition, not present in central NanoAOD. Lepton pairs (mu-mu, e-e,
  // e-mu, gated by doMuMu_/doEE_/doEMu_) whose Kalman-fitted two-track
  // vertex falls within tracker material.
  std::vector<int16_t> InMaterialVtx_lep1Idx_, InMaterialVtx_lep2Idx_;
  std::vector<uint8_t> InMaterialVtx_lep1Flavor_, InMaterialVtx_lep2Flavor_;

  // genVtx -- production vertex (x,y) [cm] of the finalGenParticles entry
  // each muon/electron matches to via deltaR+pdgId (matchGenVtxByDeltaR).
  // z is not stored -- unused downstream (gen_absd0_um only needs x,y
  // relative to BeamSpot_x/BeamSpot_y). NaN where there is no gen match.
  // Sized and ordered to match Muon_*/Electron_* index-for-index.
  std::vector<float> Muon_genVtx_x_, Muon_genVtx_y_;
  std::vector<float> Electron_genVtx_x_, Electron_genVtx_y_;

  // Runs branches, one entry filled per run in beginRun()
  unsigned int runsRun_ = 0;
  int runsVersion_ = 0;
};

SupplementTreeAnalyzer::SupplementTreeAnalyzer(const edm::ParameterSet& iConfig)
    : version_(iConfig.getParameter<int>("version")),
      doMuMu_(iConfig.getParameter<bool>("doMuMu")),
      doEE_(iConfig.getParameter<bool>("doEE")),
      doEMu_(iConfig.getParameter<bool>("doEMu")),
      doGenPart_(!iConfig.getUntrackedParameter<edm::InputTag>("genParts", edm::InputTag()).label().empty()),
      muonToken_(consumes<edm::RefVector<std::vector<pat::Muon>>>(iConfig.getParameter<edm::InputTag>("muons"))),
      electronToken_(
          consumes<edm::RefVector<std::vector<pat::Electron>>>(iConfig.getParameter<edm::InputTag>("electrons"))),
      beamSpotToken_(consumes<reco::BeamSpot>(iConfig.getParameter<edm::InputTag>("beamSpot"))),
      ttbToken_(esConsumes<TransientTrackBuilder, TransientTrackRecord>(edm::ESInputTag("", "TransientTrackBuilder"))) {
  this->usesResource("TFileService");
  if (doGenPart_) {
    genPartToken_ = consumes<reco::GenParticleCollection>(iConfig.getUntrackedParameter<edm::InputTag>("genParts"));
  }
}

void SupplementTreeAnalyzer::beginJob() {
  edm::Service<TFileService> fs;

  eventsTree_ = fs->make<TTree>("Events", "Selected events");
  eventsTree_->Branch("run", &run_, "run/i");
  eventsTree_->Branch("luminosityBlock", &lumi_, "luminosityBlock/i");
  eventsTree_->Branch("event", &event_, "event/l");
  eventsTree_->Branch("BeamSpot_x", &BeamSpot_x_, "BeamSpot_x/F");
  eventsTree_->Branch("BeamSpot_y", &BeamSpot_y_, "BeamSpot_y/F");

  eventsTree_->Branch("Muon_pfIso04_sumChargedHadronPt", &Muon_pfIso04_sumChargedHadronPt_);
  eventsTree_->Branch("Muon_pfIso04_sumPUPt", &Muon_pfIso04_sumPUPt_);
  eventsTree_->Branch("Muon_pfIso04_sumNeutralEt", &Muon_pfIso04_sumNeutralEt_);
  eventsTree_->Branch("Muon_timeNdof", &Muon_timeNdof_);
  eventsTree_->Branch("Muon_timeAtIpInOut", &Muon_timeAtIpInOut_);

  eventsTree_->Branch("Electron_pfIso03_sumChargedHadronPt", &Electron_pfIso03_sumChargedHadronPt_);
  eventsTree_->Branch("Electron_pfIso03_sumPUPt", &Electron_pfIso03_sumPUPt_);
  eventsTree_->Branch("Electron_pfIso03_sumNeutralEt", &Electron_pfIso03_sumNeutralEt_);
  eventsTree_->Branch("Electron_isEBEEGap", &Electron_isEBEEGap_);
  eventsTree_->Branch("Electron_dxybs", &Electron_dxybs_);
  eventsTree_->Branch("Electron_dxybsErr", &Electron_dxybsErr_);

  eventsTree_->Branch("InMaterialVtx_lep1Idx", &InMaterialVtx_lep1Idx_);
  eventsTree_->Branch("InMaterialVtx_lep2Idx", &InMaterialVtx_lep2Idx_);
  eventsTree_->Branch("InMaterialVtx_lep1Flavor", &InMaterialVtx_lep1Flavor_);
  eventsTree_->Branch("InMaterialVtx_lep2Flavor", &InMaterialVtx_lep2Flavor_);

  if (doGenPart_) {
    eventsTree_->Branch("Muon_genVtx_x", &Muon_genVtx_x_);
    eventsTree_->Branch("Muon_genVtx_y", &Muon_genVtx_y_);
    eventsTree_->Branch("Electron_genVtx_x", &Electron_genVtx_x_);
    eventsTree_->Branch("Electron_genVtx_y", &Electron_genVtx_y_);
  }

  runsTree_ = fs->make<TTree>("Runs", "Run-level metadata");
  runsTree_->Branch("run", &runsRun_, "run/i");
  runsTree_->Branch("version", &runsVersion_, "version/I");
}

void SupplementTreeAnalyzer::beginRun(const edm::Run& iRun, const edm::EventSetup&) {
  runsRun_ = iRun.run();
  runsVersion_ = version_;
  runsTree_->Fill();
}

void SupplementTreeAnalyzer::fillMuons(const edm::Event& iEvent) {
  Muon_pfIso04_sumChargedHadronPt_.clear();
  Muon_pfIso04_sumPUPt_.clear();
  Muon_pfIso04_sumNeutralEt_.clear();
  Muon_timeNdof_.clear();
  Muon_timeAtIpInOut_.clear();

  edm::Handle<edm::RefVector<std::vector<pat::Muon>>> muons;
  iEvent.getByToken(muonToken_, muons);

  for (const auto& muRef : *muons) {
    const pat::Muon& mu = *muRef;
    Muon_pfIso04_sumChargedHadronPt_.push_back(mu.pfIsolationR04().sumChargedHadronPt);
    Muon_pfIso04_sumPUPt_.push_back(mu.pfIsolationR04().sumPUPt);
    Muon_pfIso04_sumNeutralEt_.push_back(mu.pfIsolationR04().sumNeutralHadronEt + mu.pfIsolationR04().sumPhotonEt);
    Muon_timeNdof_.push_back(mu.time().nDof);
    Muon_timeAtIpInOut_.push_back(mu.time().timeAtIpInOut);
  }
}

void SupplementTreeAnalyzer::fillElectrons(const edm::Event& iEvent) {
  Electron_pfIso03_sumChargedHadronPt_.clear();
  Electron_pfIso03_sumPUPt_.clear();
  Electron_pfIso03_sumNeutralEt_.clear();
  Electron_isEBEEGap_.clear();
  Electron_dxybs_.clear();
  Electron_dxybsErr_.clear();

  edm::Handle<edm::RefVector<std::vector<pat::Electron>>> electrons;
  iEvent.getByToken(electronToken_, electrons);

  edm::Handle<reco::BeamSpot> beamSpot;
  iEvent.getByToken(beamSpotToken_, beamSpot);

  for (const auto& eleRef : *electrons) {
    const pat::Electron& ele = *eleRef;
    Electron_pfIso03_sumChargedHadronPt_.push_back(ele.pfIsolationVariables().sumChargedHadronPt);
    Electron_pfIso03_sumPUPt_.push_back(ele.pfIsolationVariables().sumPUPt);
    Electron_pfIso03_sumNeutralEt_.push_back(ele.pfIsolationVariables().sumNeutralHadronEt +
                                              ele.pfIsolationVariables().sumPhotonEt);
    Electron_isEBEEGap_.push_back(ele.isEBEEGap());

    // pat::Electron doesn't get an embedded dB('BS2D') from standard MiniAOD
    // production (only muons do), so compute it directly from the gsfTrack,
    // matching OSUNano's ElectronDxyBSProducer.
    auto trk = ele.gsfTrack();
    if (trk.isNonnull()) {
      Electron_dxybs_.push_back(trk->dxy(*beamSpot));
      Electron_dxybsErr_.push_back(trk->dxyError());
    } else {
      Electron_dxybs_.push_back(-999.f);
      Electron_dxybsErr_.push_back(-999.f);
    }
  }
}

void SupplementTreeAnalyzer::fillInMaterialVertices(const edm::Event& iEvent, const edm::EventSetup& iSetup) {
  InMaterialVtx_lep1Idx_.clear();
  InMaterialVtx_lep2Idx_.clear();
  InMaterialVtx_lep1Flavor_.clear();
  InMaterialVtx_lep2Flavor_.clear();

  edm::Handle<edm::RefVector<std::vector<pat::Muon>>> muons;
  iEvent.getByToken(muonToken_, muons);

  edm::Handle<edm::RefVector<std::vector<pat::Electron>>> electrons;
  iEvent.getByToken(electronToken_, electrons);

  const auto& ttBuilder = iSetup.getData(ttbToken_);
  KalmanVertexFitter kvf;

  auto tryFit = [&](const reco::TransientTrack& tt1, const reco::TransientTrack& tt2, int16_t i1, uint8_t f1,
                     int16_t i2, uint8_t f2) {
    std::vector<reco::TransientTrack> tts = {tt1, tt2};
    TransientVertex tv = kvf.vertex(tts);
    if (!tv.isValid()) return;
    reco::Vertex vtx(tv);
    if (vtx.normalizedChi2() >= 20.0) return;
    if (!inMaterial(vtx.x(), vtx.y(), vtx.z())) return;
    InMaterialVtx_lep1Idx_.push_back(i1);
    InMaterialVtx_lep2Idx_.push_back(i2);
    InMaterialVtx_lep1Flavor_.push_back(f1);
    InMaterialVtx_lep2Flavor_.push_back(f2);
  };

  const bool needMuons = doMuMu_ || doEMu_;
  const bool needElectrons = doEE_ || doEMu_;

  std::vector<std::pair<reco::TransientTrack, int16_t>> muTTs, elTTs;
  if (needMuons) {
    for (int16_t i = 0; i < static_cast<int16_t>(muons->size()); ++i) {
      const pat::Muon& mu = *(*muons)[i];
      if (mu.innerTrack().isNonnull()) muTTs.emplace_back(ttBuilder.build(mu.innerTrack()), i);
    }
  }
  if (needElectrons) {
    for (int16_t i = 0; i < static_cast<int16_t>(electrons->size()); ++i) {
      const pat::Electron& ele = *(*electrons)[i];
      if (ele.gsfTrack().isNonnull()) elTTs.emplace_back(ttBuilder.build(ele.gsfTrack()), i);
    }
  }

  if (doMuMu_) {
    for (size_t i = 0; i < muTTs.size(); ++i)
      for (size_t j = i + 1; j < muTTs.size(); ++j)
        tryFit(muTTs[i].first, muTTs[j].first, muTTs[i].second, 0, muTTs[j].second, 0);
  }

  if (doEE_) {
    for (size_t i = 0; i < elTTs.size(); ++i)
      for (size_t j = i + 1; j < elTTs.size(); ++j)
        tryFit(elTTs[i].first, elTTs[j].first, elTTs[i].second, 1, elTTs[j].second, 1);
  }

  if (doEMu_) {
    for (auto& [muTT, muIdx] : muTTs)
      for (auto& [elTT, elIdx] : elTTs)
        tryFit(muTT, elTT, muIdx, 0, elIdx, 1);
  }
}

void SupplementTreeAnalyzer::fillGenVtx(const edm::Event& iEvent) {
  Muon_genVtx_x_.clear();
  Muon_genVtx_y_.clear();
  Electron_genVtx_x_.clear();
  Electron_genVtx_y_.clear();

  if (!doGenPart_) return;

  edm::Handle<reco::GenParticleCollection> genParts;
  iEvent.getByToken(genPartToken_, genParts);

  edm::Handle<edm::RefVector<std::vector<pat::Muon>>> muons;
  iEvent.getByToken(muonToken_, muons);
  matchGenVtxByDeltaR(*muons, *genParts, 13, Muon_genVtx_x_, Muon_genVtx_y_);

  edm::Handle<edm::RefVector<std::vector<pat::Electron>>> electrons;
  iEvent.getByToken(electronToken_, electrons);
  matchGenVtxByDeltaR(*electrons, *genParts, 11, Electron_genVtx_x_, Electron_genVtx_y_);
}

void SupplementTreeAnalyzer::fillBeamSpot(const edm::Event& iEvent) {
  edm::Handle<reco::BeamSpot> beamSpot;
  iEvent.getByToken(beamSpotToken_, beamSpot);
  BeamSpot_x_ = beamSpot->x0();
  BeamSpot_y_ = beamSpot->y0();
}

void SupplementTreeAnalyzer::analyze(const edm::Event& iEvent, const edm::EventSetup& iSetup) {
  run_ = iEvent.id().run();
  lumi_ = iEvent.id().luminosityBlock();
  event_ = iEvent.id().event();

  fillMuons(iEvent);
  fillElectrons(iEvent);
  fillInMaterialVertices(iEvent, iSetup);
  fillGenVtx(iEvent);
  fillBeamSpot(iEvent);

  eventsTree_->Fill();
}

DEFINE_FWK_MODULE(SupplementTreeAnalyzer);
