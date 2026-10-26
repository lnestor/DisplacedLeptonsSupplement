import argparse
import math

import ROOT
from DataFormats.FWLite import Events, Handle

ROOT.gErrorIgnoreLevel = ROOT.kError

RHADRON_IDS = {1000612, 1000622, 1000632, 1000642, 1000652, 1006113, 1006211, 1006213,
               1006223, 1006311, 1006313, 1006321, 1006323, 1006333}
LCUT_MM = 1000.


def is_rhadron(pdg):
    return abs(pdg) in RHADRON_IDS


def gen_ancestor(p):
    while p.status() == 8 and p.numberOfMothers() > 0:
        p = p.mother(0)
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--ctau", type=float, required=True, help="Nominal ctau in mm")
    parser.add_argument("--dump", action="store_true")
    args = parser.parse_args()

    gen = Handle("vector<reco::GenParticle>")
    gpg = Handle("vector<reco::GenParticle>")
    n_events = 0
    n_gen_rh = 0
    n_gen_stop_decays = 0
    n_decays = 0
    ctau_obs = []
    expected_inside = 0.
    observed_inside = 0
    leptons = {11: 0, 13: 0, 15: 0, 16: 0}
    n_charged_daughters = []

    for event in Events(args.files):
        n_events += 1
        event.getByLabel("genParticles", gen)
        event.getByLabel("genParticlePlusGeant", gpg)

        for p in gen.product():
            if abs(p.pdgId()) == 1000006 and p.numberOfDaughters() > 0:
                if any(abs(p.daughter(i).pdgId()) in (11, 13, 15) for i in range(p.numberOfDaughters())):
                    n_gen_stop_decays += 1
            if is_rhadron(p.pdgId()) and p.status() == 1:
                n_gen_rh += 1
                bg = p.p() / p.mass()
                expected_inside += 1. - math.exp(-LCUT_MM / (bg * args.ctau))

        for p in gpg.product():
            if not is_rhadron(p.pdgId()):
                continue
            products = [p.daughter(i) for i in range(p.numberOfDaughters()) if not is_rhadron(p.daughter(i).pdgId())]
            if not products:
                continue
            n_decays += 1
            origin = gen_ancestor(p)
            # Products of B, K0S, Lambda decays done inside the decayer start displaced; the closest
            # product (e.g. the lepton from the stop decay) marks the R-hadron decay point
            length_mm = 10. * min(
                math.sqrt((q.vx() - origin.vx())**2 + (q.vy() - origin.vy())**2 + (q.vz() - origin.vz())**2)
                for q in products)
            ctau_obs.append(length_mm * origin.mass() / origin.p())
            if length_mm < LCUT_MM:
                observed_inside += 1
            n_charged_daughters.append(sum(1 for q in products if q.charge() != 0))
            for q in products:
                if abs(q.pdgId()) in leptons:
                    leptons[abs(q.pdgId())] += 1
            if args.dump and n_decays <= 3:
                print("decay of %d (status %d) at L=%.2f mm from gen origin %d: %s" % (
                    p.pdgId(), p.status(), length_mm, origin.pdgId(),
                    sorted((q.pdgId(), q.status()) for q in products)))

    print("events: %d" % n_events)
    print("gen-level stop decays to leptons (expect 0): %d" % n_gen_stop_decays)
    print("gen-level undecayed R-hadrons: %d (%.2f per event, expect 2)" % (n_gen_rh, n_gen_rh / max(n_events, 1)))
    print("R-hadron decays found in genParticlePlusGeant: %d" % n_decays)
    if ctau_obs:
        ctau_obs.sort()
        mean = sum(ctau_obs) / len(ctau_obs)
        print("observed ctau: mean %.4g mm, median %.4g mm (nominal %.4g, median expect %.4g)" % (
            mean, ctau_obs[len(ctau_obs) // 2], args.ctau, args.ctau * math.log(2)))
    print("decays within %.0f mm: observed %d, expected %.1f +- %.1f" % (
        LCUT_MM, observed_inside, expected_inside, math.sqrt(max(expected_inside, 1.))))
    print("leptons among decay products (e, mu, tau, nu_tau): %s" % leptons)
    if n_charged_daughters:
        print("mean charged decay products per decay: %.1f" % (sum(n_charged_daughters) / len(n_charged_daughters)))


if __name__ == "__main__":
    main()
